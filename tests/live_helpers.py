"""In-memory stand-in for matchlens.live.store.Store plus sample payloads for the live ingestion tests."""
from datetime import datetime, timedelta, timezone

import httpx

from matchlens.live.apifootball import ApiFootball
from matchlens.live.config import Settings
from matchlens.live.footballdata import FootballData
from matchlens.live.refresh import Refresher

KEYS = {"competitions": ("id",), "teams": ("id",), "fixtures": ("id",), "live_state": ("fixture_id",),
        "lineups": ("fixture_id", "team_id"), "standings": ("competition_id", "season", "type", "grp", "position"),
        "events": ("fixture_id", "dedupe_key")}


class FakeStore:
    def __init__(self):
        self.tables: dict[str, dict] = {t: {} for t in KEYS}
        self.cache: dict[str, tuple[datetime, object]] = {}
        self.usage: dict[tuple[str, str], int] = {}
        self.now = datetime.now(timezone.utc)

    def get_cache(self, key, allow_stale=False):
        hit = self.cache.get(key)
        if hit is None or (not allow_stale and hit[0] <= datetime.now(timezone.utc)):
            return None
        return hit[1]

    def put_cache(self, key, source, payload, ttl_s):
        self.cache[key] = (datetime.now(timezone.utc) + timedelta(seconds=ttl_s), payload)

    def bump_usage(self, source, bucket, limit):
        n = self.usage.get((source, bucket), 0)
        if n >= limit:
            return False
        self.usage[(source, bucket)] = n + 1
        return True

    def get_usage(self, source, bucket):
        return self.usage.get((source, bucket), 0)

    def upsert(self, table, rows, on_conflict, ignore_duplicates=False):
        for row in rows:
            key = tuple(row[c] for c in KEYS[table])
            self.tables[table].setdefault(key, {}).update(row)

    def update(self, table, match, values):
        for row in self.tables[table].values():
            if all(row.get(k) == v for k, v in match.items()):
                row.update(values)

    def _team(self, team_id):
        return self.tables["teams"].get((team_id,))

    def fixtures_between(self, start, end):
        out = []
        for row in self.tables["fixtures"].values():
            when = datetime.fromisoformat(row["utc_date"].replace("Z", "+00:00"))
            if start <= when < end:
                out.append({"af_fixture_id": None, **row, "home": self._team(row["home_team_id"]), "away": self._team(row["away_team_id"])})
        return sorted(out, key=lambda r: r["utc_date"])

    def backfill_candidates(self, limit):
        rows = [{"af_fixture_id": None, "map_attempts": 0, "detail_status": None, **r, "home": self._team(r["home_team_id"]), "away": self._team(r["away_team_id"])}
                for r in self.tables["fixtures"].values()]
        rows = [r for r in rows if r["status"] == "FINISHED" and r["detail_status"] is None]
        return sorted(rows, key=lambda r: r["utc_date"])[:limit]

    def live_states(self, ids):
        return {k[0]: v for k, v in self.tables["live_state"].items() if k[0] in ids}

    def fixtures_with_lineups(self, ids):
        return {k[0] for k in self.tables["lineups"] if k[0] in ids}

    def sync_events(self, fixture_id, rows):
        keep = {r["dedupe_key"] for r in rows}
        for key in [k for k in self.tables["events"] if k[0] == fixture_id and k[1] not in keep]:
            del self.tables["events"][key]
        self.upsert("events", rows, "fixture_id,dedupe_key")


def fd_match(match_id=100, kickoff="2026-10-20T19:00:00Z", status="TIMED", home=(57, "Arsenal FC", "Arsenal", "ARS"),
             away=(61, "Chelsea FC", "Chelsea", "CHE"), score=(None, None)):
    def team(t):
        return {"id": t[0], "name": t[1], "shortName": t[2], "tla": t[3], "crest": f"https://c/{t[0]}.png"}
    return {"id": match_id, "utcDate": kickoff, "status": status, "matchday": 9, "stage": "REGULAR_SEASON",
            "season": {"startDate": "2026-08-15", "currentMatchday": 9}, "homeTeam": team(home), "awayTeam": team(away),
            "score": {"winner": None, "fullTime": {"home": score[0], "away": score[1]}, "halfTime": {"home": None, "away": None}}}


def fd_body(matches):
    return {"competition": {"id": 2021, "name": "Premier League", "code": "PL", "emblem": "https://e/pl.png"}, "matches": matches}


def af_item(af_id=9001, kickoff=datetime(2026, 10, 20, 19, 0, tzinfo=timezone.utc), short="1H", elapsed=23, goals=(1, 0),
            events=None, lineups=None, home=(42, "Arsenal"), away=(49, "Chelsea")):
    return {"fixture": {"id": af_id, "timestamp": int(kickoff.timestamp()), "status": {"short": short, "elapsed": elapsed, "extra": None}},
            "league": {"id": 39, "season": 2026}, "teams": {"home": {"id": home[0], "name": home[1]}, "away": {"id": away[0], "name": away[1]}},
            "goals": {"home": goals[0], "away": goals[1]}, "events": events, "lineups": lineups}


def goal_event(minute=12, player="Saka", team=(42, "Arsenal"), detail="Normal Goal"):
    return {"time": {"elapsed": minute, "extra": None}, "team": {"id": team[0], "name": team[1]},
            "player": {"id": 7, "name": player}, "assist": {"id": None, "name": None}, "type": "Goal", "detail": detail, "comments": None}


class Router:
    """httpx mock transport: routes by host and path, records every request."""

    def __init__(self):
        self.routes: dict[tuple[str, str], list] = {}
        self.calls: list[httpx.Request] = []

    def add(self, host_part: str, path: str, *responses):
        self.routes[(host_part, path)] = list(responses)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        for (host_part, path), queue in self.routes.items():
            if host_part in request.url.host and request.url.path.endswith(path):
                item = queue[0] if len(queue) == 1 else queue.pop(0)
                if isinstance(item, httpx.Response):
                    return item
                return httpx.Response(200, json=item)
        return httpx.Response(404, json={"message": f"no route for {request.url}"})

    def count(self, host_part: str) -> int:
        return sum(1 for r in self.calls if host_part in r.url.host)


def build(router: Router, **overrides):
    settings = Settings(supabase_url="http://x", supabase_service_key="k", football_data_token="t", api_football_key="k",
                        tracked=["PL"], **overrides)
    store = FakeStore()
    client = httpx.Client(transport=httpx.MockTransport(router))
    sleeps: list[float] = []
    fd = FootballData(store, settings, client=client, sleep=sleeps.append)
    af = ApiFootball(store, settings, client=client, sleep=sleeps.append)
    return store, fd, af, Refresher(store, fd, af, settings), settings, sleeps
