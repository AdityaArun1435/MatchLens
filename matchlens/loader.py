"""Fetch StatsBomb open-data JSON and cache it verbatim under data/raw/."""
import json
from pathlib import Path
from typing import Any

import httpx

from . import config


def _cache_path(rel: str) -> Path:
    return config.RAW_DIR / rel


def get_json(rel: str, *, offline_only: bool = False) -> Any:
    """Return parsed JSON for a path under open-data/data, using the local cache first."""
    path = _cache_path(rel)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if offline_only:
        raise FileNotFoundError(f"{path} is not cached; run scripts/fetch_data.py")
    resp = httpx.get(f"{config.OPEN_DATA_BASE}/{rel}", timeout=60, follow_redirects=True)
    resp.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(resp.content)
    return resp.json()


def load_competitions(**kw: Any) -> list[dict]:
    return get_json("competitions.json", **kw)


def load_season_matches(competition_id: int, season_id: int, **kw: Any) -> list[dict]:
    return get_json(f"matches/{competition_id}/{season_id}.json", **kw)


def load_events(match_id: int, **kw: Any) -> list[dict]:
    return get_json(f"events/{match_id}.json", **kw)


def load_lineups(match_id: int, **kw: Any) -> list[dict]:
    return get_json(f"lineups/{match_id}.json", **kw)


def find_match(query: dict) -> dict:
    """Resolve a match from a {competition_id, season_id, home, away, stage} query."""
    matches = load_season_matches(query["competition_id"], query["season_id"])
    hits = [
        m
        for m in matches
        if query["home"] in (m["home_team"]["home_team_name"], m["away_team"]["away_team_name"])
        and query["away"] in (m["home_team"]["home_team_name"], m["away_team"]["away_team_name"])
        and query["stage"].lower() in m["competition_stage"]["name"].lower()
    ]
    if len(hits) != 1:
        raise LookupError(f"query {query} matched {len(hits)} matches")
    return hits[0]


# --- preloaded match registry -------------------------------------------------

INDEX_FILE = "index.json"


def _index_entry(match: dict) -> dict:
    return {
        "match_id": match["match_id"],
        "competition_id": match["competition"]["competition_id"],
        "season_id": match["season"]["season_id"],
    }


def preload(extra: list[dict] | None = None) -> list[dict]:
    """Download and cache the default plus extra matches, and write data/raw/index.json.

    `extra` entries are {match_id, competition_id, season_id} for user-chosen matches.
    """
    entries = [
        _index_entry(find_match(q)) for q in [config.DEFAULT_MATCH_QUERY, *config.EXTRA_MATCH_QUERIES]
    ]
    entries += extra or []
    load_competitions()
    for e in entries:
        load_season_matches(e["competition_id"], e["season_id"])
        load_events(e["match_id"])
        load_lineups(e["match_id"])
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    (config.RAW_DIR / INDEX_FILE).write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return entries


def load_index() -> list[dict]:
    """Return the cached registry of preloaded matches (offline)."""
    path = config.RAW_DIR / INDEX_FILE
    if not path.exists():
        raise FileNotFoundError(f"{path} missing; run `python scripts/fetch_data.py`")
    return json.loads(path.read_text(encoding="utf-8"))


def load_match_meta(match_id: int, competition_id: int, season_id: int) -> dict:
    for m in load_season_matches(competition_id, season_id):
        if m["match_id"] == match_id:
            return m
    raise LookupError(f"match {match_id} not in competition {competition_id} season {season_id}")
