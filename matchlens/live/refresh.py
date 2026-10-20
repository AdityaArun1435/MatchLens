"""One scheduled tick of the refresh job. Called every minute by Supabase pg_cron through api/refresh.py.

Every source call goes through the cached clients, so how often a source is hit depends on the clock and the
TTLs below, never on how many people look at the site.
"""
from datetime import date, datetime, timedelta, timezone

from . import normalise as nm
from .apifootball import ApiFootball
from .base import BudgetExceeded, SourceError, day_bucket
from .config import COMPETITIONS, Settings
from .footballdata import FootballData

FD_WINDOW_BACK_DAYS = 2
FD_WINDOW_FORWARD_DAYS = 7
DETAIL_MAX_PER_TICK = 2
SETTLE_MAX_PER_TICK = 3
KICKOFF_LEAD = timedelta(minutes=10)
LIVE_WINDOW = timedelta(hours=3)
SETTLE_AFTER = timedelta(minutes=100)

AF_LEAGUE_BY_FD_ID = {fd: af for fd, af in COMPETITIONS.values()}


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def live_interval_s(settings: Settings, used_today: int) -> int:
    """Stretch the live polling interval as the daily API-Football budget gets used up."""
    if used_today < 70:
        return settings.live_min_interval_s
    if used_today < 85:
        return settings.live_min_interval_s * 2
    return settings.live_min_interval_s * 4


def needs_live(fix: dict, live: dict | None, now: datetime) -> bool:
    status_short = (live or {}).get("status_short")
    if status_short in nm.FINAL_STATUS_SHORT:
        return False
    if fix["status"] in nm.FD_NOT_PLAYING and status_short not in nm.LIVE_STATUS_SHORT:
        return False
    kickoff = parse_ts(fix["utc_date"])
    return kickoff - KICKOFF_LEAD <= now <= kickoff + LIVE_WINDOW


def find_fixture(item: dict, candidates: list[dict]) -> dict | None:
    """Match an API-Football fixture to one of our fixtures by league, kickoff time and team names."""
    teams, league = item["teams"], item["league"]["id"]
    kickoff = datetime.fromtimestamp(item["fixture"]["timestamp"], tz=timezone.utc)
    for fix in candidates:
        if AF_LEAGUE_BY_FD_ID.get(fix["competition_id"]) != league:
            continue
        if abs(parse_ts(fix["utc_date"]) - kickoff) > timedelta(hours=6):
            continue
        if nm.team_matches(fix["home"] or {}, teams["home"]["name"]) and nm.team_matches(fix["away"] or {}, teams["away"]["name"]):
            return fix
    return None


class Refresher:
    def __init__(self, store, fd: FootballData, af: ApiFootball, settings: Settings):
        self.store, self.fd, self.af, self.settings = store, fd, af, settings
        self.report: dict = {"did": [], "skipped": [], "errors": []}

    # --- helpers -------------------------------------------------------------------------------
    def _step(self, label: str, fn, *args):
        try:
            result = fn(*args)
            self.report["did"].append(label)
            return result
        except BudgetExceeded as exc:
            self.report["skipped"].append(f"{label}: {exc}")
        except (SourceError, RuntimeError) as exc:
            self.report["errors"].append(f"{label}: {exc}")
        return None

    # --- football-data.org ---------------------------------------------------------------------
    def refresh_fixtures(self, code: str, today: date) -> int:
        body = self.fd.matches(code, today - timedelta(days=FD_WINDOW_BACK_DAYS), today + timedelta(days=FD_WINDOW_FORWARD_DAYS))
        matches = body.get("matches", [])
        comp = {**body["competition"], "code": code}
        season = matches[0].get("season") if matches else None
        self.store.upsert("competitions", [nm.competition_row(comp, COMPETITIONS[code][1], season)], "id")
        teams = {}
        for m in matches:
            for side in ("homeTeam", "awayTeam"):
                t = m.get(side) or {}
                if t.get("id"):
                    teams[t["id"]] = nm.team_row(t)
        self.store.upsert("teams", list(teams.values()), "id")
        self.store.upsert("fixtures", [nm.fixture_row(m, comp["id"]) for m in matches], "id")
        return len(matches)

    def refresh_standings(self, code: str) -> int:
        payload = self.fd.standings(code)
        comp_id = COMPETITIONS[code][0]
        comp = {**payload.get("competition", {}), "id": comp_id, "code": code, "name": payload.get("competition", {}).get("name", code)}
        self.store.upsert("competitions", [nm.competition_row(comp, COMPETITIONS[code][1], payload.get("season"))], "id")
        rows = nm.standing_rows(payload, comp_id)
        teams = {}
        for block in payload.get("standings", []):
            for r in block.get("table", []):
                teams[r["team"]["id"]] = nm.team_row(r["team"])
        self.store.upsert("teams", list(teams.values()), "id")
        self.store.upsert("standings", rows, "competition_id,season,type,grp,position")
        return len(rows)

    # --- API-Football --------------------------------------------------------------------------
    def map_day(self, day: date, window: list[dict]) -> int:
        unmapped = [f for f in window if f["af_fixture_id"] is None and parse_ts(f["utc_date"]).date() == day]
        if not unmapped:
            return 0
        mapped = 0
        for item in self.af.fixtures_on(day.isoformat()):
            fix = find_fixture(item, unmapped)
            if fix is None:
                continue
            self._link(fix, item)
            if item["fixture"]["status"].get("short") not in ("NS", "TBD", "PST"):
                self.store.upsert("live_state", [nm.live_state_row(item, fix["id"])], "fixture_id")
            mapped += 1
        return mapped

    def _link(self, fix: dict, item: dict) -> None:
        self.store.update("fixtures", {"id": fix["id"]}, {"af_fixture_id": item["fixture"]["id"]})
        fix["af_fixture_id"] = item["fixture"]["id"]
        for side in ("home", "away"):
            team = fix.get(side) or {}
            if team.get("id") and team.get("af_team_id") != item["teams"][side]["id"]:
                self.store.update("teams", {"id": team["id"]}, {"af_team_id": item["teams"][side]["id"]})
                team["af_team_id"] = item["teams"][side]["id"]

    def _team_map(self, fix: dict, item: dict) -> dict[int, int]:
        return {item["teams"]["home"]["id"]: fix["home_team_id"], item["teams"]["away"]["id"]: fix["away_team_id"]}

    def apply_item(self, fix: dict, item: dict, with_lineups: bool = False) -> None:
        self.store.upsert("live_state", [nm.live_state_row(item, fix["id"])], "fixture_id")
        team_map = self._team_map(fix, item)
        if item.get("events") is not None:
            self.store.sync_events(fix["id"], nm.event_rows(item, fix["id"], team_map))
        if with_lineups:
            self.store.upsert("lineups", nm.lineup_rows(item, fix["id"], team_map), "fixture_id,team_id")

    def poll_live(self, window: list[dict], lives: dict[int, dict], now: datetime) -> int:
        candidates = [f for f in window if needs_live(f, lives.get(f["id"]), now)]
        if not candidates:
            return 0
        used = self.store.get_usage("af", day_bucket(now))
        last = self.store.get_cache("state:last_live_poll")
        if last and (now - parse_ts(last["at"])).total_seconds() < live_interval_s(self.settings, used):
            self.report["skipped"].append("live poll: interval not reached")
            return 0
        items = self.af.live_all()
        self.store.put_cache("state:last_live_poll", "state", {"at": now.isoformat()}, 3600)
        by_af = {f["af_fixture_id"]: f for f in window if f["af_fixture_id"]}
        seen = set()
        for item in items:
            fix = by_af.get(item["fixture"]["id"]) or find_fixture(item, window)
            if fix is None:
                continue
            if fix["af_fixture_id"] is None:
                self._link(fix, item)
            self.apply_item(fix, item)
            seen.add(fix["id"])
        self._settle([f for f in candidates if f["id"] not in seen and lives.get(f["id"]) and
                      lives[f["id"]]["status_short"] in nm.LIVE_STATUS_SHORT and now - parse_ts(f["utc_date"]) > SETTLE_AFTER])
        return len(seen)

    def _settle(self, fixtures: list[dict]) -> None:
        """A match that left the live feed has probably finished: fetch it once to record the final state."""
        for fix in fixtures[:SETTLE_MAX_PER_TICK]:
            if fix["af_fixture_id"]:
                self._step(f"settle {fix['id']}", self._fetch_detail, fix, 60)

    def _fetch_detail(self, fix: dict, ttl_s: int) -> bool:
        items = self.af.fixture_detail(fix["af_fixture_id"], ttl_s=ttl_s)
        if not items:
            return False
        self.apply_item(fix, items[0], with_lineups=True)
        return bool(items[0].get("lineups"))

    def fetch_details(self, window: list[dict], now: datetime) -> int:
        """Lineups for matches about to start, running or just finished. One call per match, retried at most every 10 minutes."""
        eligible = [f for f in window if f["af_fixture_id"] and
                    now - timedelta(hours=6) <= parse_ts(f["utc_date"]) <= now + timedelta(minutes=75)]
        have = self.store.fixtures_with_lineups([f["id"] for f in eligible])
        todo = [f for f in eligible if f["id"] not in have][:DETAIL_MAX_PER_TICK]
        for fix in todo:
            marker = f"state:no_lineups:{fix['id']}"
            if self.store.get_cache(marker):
                continue
            got = self._step(f"detail {fix['id']}", self._fetch_detail, fix, 600)
            if got is False:
                self.store.put_cache(marker, "state", {"empty": True}, 1800)
        return len(todo)

    # --- one tick ------------------------------------------------------------------------------
    def tick(self, now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        today = now.date()
        codes = self.settings.tracked
        if self.settings.football_data_token and codes:
            minute_of_day = now.hour * 60 + now.minute
            self._step("fd fixtures", self.refresh_fixtures, codes[minute_of_day % len(codes)], today)
            if now.minute % 3 == 0:
                self._step("fd standings", self.refresh_standings, codes[(minute_of_day // 3) % len(codes)])
        if self.settings.api_football_key:
            window = self.store.fixtures_between(now - timedelta(days=1, hours=6), now + timedelta(days=1))
            lives = self.store.live_states([f["id"] for f in window])
            days = [today] + ([today - timedelta(days=1)] if now.hour < 3 else [])
            for day in days:
                self._step(f"af map {day}", self.map_day, day, window)
            self._step("af live", self.poll_live, window, lives, now)
            self._step("af details", self.fetch_details, window, now)
        self.report["requests"] = {"fd": self.fd.requests_made, "af": self.af.requests_made}
        self.report["af_remaining_quota"] = self.af.remaining_quota
        return self.report
