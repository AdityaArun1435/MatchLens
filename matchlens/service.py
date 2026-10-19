"""Load, normalise and analyse a match once; keep the result in memory."""
from dataclasses import dataclass
from functools import lru_cache

from . import loader
from .detect import detect_moments
from .detect.common import MatchContext
from .models import Event, MatchMeta, MatchSummary, Moment
from .names import build_display_names
from .normalise import normalise_events
from .summary import build_summary


@dataclass(frozen=True)
class ProcessedMatch:
    meta: MatchMeta
    events: list[Event]
    moments: list[Moment]
    summary: MatchSummary


def build_meta(m: dict) -> MatchMeta:
    return MatchMeta(
        match_id=m["match_id"],
        competition=m["competition"]["competition_name"],
        season=m["season"]["season_name"],
        stage=m["competition_stage"]["name"],
        date=m["match_date"],
        home_team=m["home_team"]["home_team_name"],
        away_team=m["away_team"]["away_team_name"],
        home_score=m["home_score"],
        away_score=m["away_score"],
        stadium=(m.get("stadium") or {}).get("name"),
        referee=(m.get("referee") or {}).get("name"),
    )


def process(meta: MatchMeta, raw_events: list[dict], lineups: list[dict] | None = None) -> ProcessedMatch:
    events = normalise_events(raw_events, build_display_names(lineups) if lineups else None)
    return ProcessedMatch(meta, events, detect_moments(events, meta), build_summary(MatchContext(events, meta)))


def resolve_ids(match_id: int, *, allow_network: bool = False) -> tuple[int, int]:
    """Find (competition_id, season_id) for a match id: registry, then cached season files, then the network."""
    try:
        for e in loader.load_index():
            if e["match_id"] == match_id:
                return e["competition_id"], e["season_id"]
    except FileNotFoundError:
        pass
    for path in sorted((loader.config.RAW_DIR / "matches").glob("*/*.json")):
        if any(m["match_id"] == match_id for m in loader.get_json(f"matches/{path.parent.name}/{path.name}", offline_only=True)):
            return int(path.parent.name), int(path.stem)
    if allow_network:
        for c in loader.load_competitions():
            comp, season = c["competition_id"], c["season_id"]
            if any(m["match_id"] == match_id for m in loader.load_season_matches(comp, season)):
                return comp, season
    raise LookupError(f"match {match_id} not found; run scripts/fetch_data.py --add {match_id}:<competition_id>:<season_id>")


@lru_cache(maxsize=32)
def get_match(match_id: int, allow_network: bool = False) -> ProcessedMatch:
    comp, season = resolve_ids(match_id, allow_network=allow_network)
    meta = build_meta(loader.load_match_meta(match_id, comp, season, offline_only=not allow_network))
    return process(
        meta,
        loader.load_events(match_id, offline_only=not allow_network),
        loader.load_lineups(match_id, offline_only=not allow_network),
    )


def default_match_id() -> int:
    return loader.load_index()[0]["match_id"]


def list_matches() -> list[MatchMeta]:
    return [get_match(e["match_id"]).meta for e in loader.load_index()]
