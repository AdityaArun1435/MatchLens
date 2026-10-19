"""Builders for small hand-made event lists."""
from matchlens import config
from matchlens.detect.common import MatchContext
from matchlens.models import Event, MatchMeta
from matchlens.normalise import clock_label

HOME, AWAY = "A", "B"
META = MatchMeta(
    match_id=1, competition="Test", season="1", stage="Test", date="2000-01-01",
    home_team=HOME, away_team=AWAY, home_score=0, away_score=0,
)


def ev(index: int, period: int, secs: float, type_: str, team: str | None = None, *, player: str | None = None,
       xg: float | None = None, outcome: str | None = None, possession: int | None = None,
       detail: dict | None = None, related: list[str] | None = None) -> Event:
    """Event at `secs` into the period."""
    minute = int((config.PERIOD_OFFSET_SECONDS[period] + secs) // 60)
    label, stop = clock_label(period, minute)
    return Event(
        id=f"e{index}", index=index, period=period, minute=minute, second=int(secs % 60),
        match_clock_seconds=config.PERIOD_OFFSET_SECONDS[period] + secs, clock_label=label,
        stoppage_minutes=stop, in_play=period != 5, type=type_, team=team, player=player,
        outcome=outcome, xg=xg if period != 5 else None, possession=possession,
        possession_team=team, related_ids=related or [], detail=detail or {},
    )


def shot(index: int, period: int, secs: float, team: str, xg: float, outcome: str = "Saved",
         shot_type: str = "Open Play", player: str = "P") -> Event:
    return ev(index, period, secs, "Shot", team, player=player, xg=xg, outcome=outcome, detail={"shot_type": shot_type})


def period_end(index: int, period: int, secs: float) -> Event:
    """Marks how long a period lasted."""
    return ev(index, period, secs, "Half End", HOME)


def ctx(events: list[Event]) -> MatchContext:
    return MatchContext(sorted(events, key=lambda e: e.index), META)
