"""Turn raw source JSON into table rows. Pure functions, no I/O."""
import re
import unicodedata
from datetime import datetime

LIVE_STATUS_SHORT = {"1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE"}
FINAL_STATUS_SHORT = {"FT", "AET", "PEN", "AWD", "WO", "CANC", "ABD", "PST"}
FD_NOT_PLAYING = {"FINISHED", "POSTPONED", "CANCELLED", "SUSPENDED", "AWARDED"}


def season_year(season: dict | None) -> int | None:
    start = (season or {}).get("startDate")
    return int(start[:4]) if start else None


def competition_row(comp: dict, af_league_id: int | None, season: dict | None) -> dict:
    return {
        "id": comp["id"], "code": comp["code"], "name": comp["name"],
        "area": (comp.get("area") or {}).get("name"), "emblem": comp.get("emblem"),
        "af_league_id": af_league_id, "season": season_year(season),
        "current_matchday": (season or {}).get("currentMatchday"),
    }


def team_row(team: dict) -> dict:
    return {"id": team["id"], "name": team.get("name") or "", "short_name": team.get("shortName"),
            "tla": team.get("tla"), "crest": team.get("crest")}


def fixture_row(match: dict, competition_id: int) -> dict:
    score = match.get("score") or {}
    full, half = score.get("fullTime") or {}, score.get("halfTime") or {}
    return {
        "id": match["id"], "competition_id": competition_id, "season": season_year(match.get("season")),
        "matchday": match.get("matchday"), "stage": match.get("stage"), "utc_date": match["utcDate"],
        "status": match["status"],
        "home_team_id": (match.get("homeTeam") or {}).get("id"), "away_team_id": (match.get("awayTeam") or {}).get("id"),
        "home_score": full.get("home"), "away_score": full.get("away"),
        "ht_home_score": half.get("home"), "ht_away_score": half.get("away"),
        "winner": score.get("winner"),
    }


def standing_rows(payload: dict, competition_id: int) -> list[dict]:
    season = season_year(payload.get("season"))
    rows = []
    for block in payload.get("standings", []):
        for r in block.get("table", []):
            rows.append({
                "competition_id": competition_id, "season": season, "type": block.get("type", "TOTAL"),
                "grp": block.get("group") or "", "position": r["position"], "team_id": r["team"]["id"],
                "played": r.get("playedGames", 0), "won": r.get("won", 0), "draw": r.get("draw", 0), "lost": r.get("lost", 0),
                "points": r.get("points", 0), "goals_for": r.get("goalsFor", 0), "goals_against": r.get("goalsAgainst", 0),
                "goal_difference": r.get("goalDifference", 0), "form": r.get("form"),
            })
    return rows


def live_state_row(item: dict, fixture_id: int) -> dict:
    status = item["fixture"]["status"]
    goals = item.get("goals") or {}
    return {
        "fixture_id": fixture_id, "af_fixture_id": item["fixture"]["id"], "status_short": status.get("short") or "NS",
        "elapsed": status.get("elapsed"), "extra": status.get("extra"),
        "home_goals": goals.get("home"), "away_goals": goals.get("away"),
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }


def event_rows(item: dict, fixture_id: int, af_team_to_team: dict[int, int]) -> list[dict]:
    rows, seen = [], set()
    for e in item.get("events") or []:
        time = e.get("time") or {}
        player, assist, team = e.get("player") or {}, e.get("assist") or {}, e.get("team") or {}
        key = "|".join(str(x) for x in (time.get("elapsed"), time.get("extra"), e.get("type"), e.get("detail"),
                                         player.get("id") or player.get("name"), team.get("id")))
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "fixture_id": fixture_id, "dedupe_key": key, "minute": time.get("elapsed") or 0, "extra_minute": time.get("extra"),
            "type": e.get("type") or "", "detail": e.get("detail"), "team_id": af_team_to_team.get(team.get("id")),
            "player_name": player.get("name"), "assist_name": assist.get("name"), "comments": e.get("comments"),
        })
    return rows


def lineup_rows(item: dict, fixture_id: int, af_team_to_team: dict[int, int]) -> list[dict]:
    def players(entries):
        return [{"name": p["player"].get("name"), "number": p["player"].get("number"),
                 "pos": p["player"].get("pos"), "grid": p["player"].get("grid")} for p in entries or []]

    rows = []
    for lu in item.get("lineups") or []:
        team_id = af_team_to_team.get((lu.get("team") or {}).get("id"))
        if team_id is None:
            continue
        rows.append({"fixture_id": fixture_id, "team_id": team_id, "formation": lu.get("formation"),
                     "coach": (lu.get("coach") or {}).get("name"),
                     "starters": players(lu.get("startXI")), "substitutes": players(lu.get("substitutes"))})
    return rows


# --- team name matching between the two sources ------------------------------------------------
_NOISE = {"fc", "afc", "cf", "sc", "ac", "as", "ssc", "us", "rc", "rcd", "cd", "ud", "fk", "sv", "vfb", "vfl", "tsg", "1", "de", "the"}


def norm_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    tokens = [t for t in re.split(r"[^a-z0-9]+", text) if t and t not in _NOISE]
    return " ".join(tokens)


def names_match(a: str, b: str) -> bool:
    na, nb = norm_name(a), norm_name(b)
    if not na or not nb:
        return False
    return na == nb or na in nb or nb in na


def team_matches(our_team: dict, af_name: str) -> bool:
    candidates = [our_team.get("name"), our_team.get("short_name")]
    return any(c and names_match(c, af_name) for c in candidates)
