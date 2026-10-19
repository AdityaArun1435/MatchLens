"""A small invented match with known moments, used by the Phase 2 tests (no StatsBomb data needed)."""
from matchlens.detect import detect_moments
from matchlens.detect.common import MatchContext
from matchlens.service import ProcessedMatch
from matchlens.summary import build_summary

from .helpers import AWAY, HOME, META, ev, period_end, shot


def named(e, display: str, pid: int):
    return e.model_copy(update={"player_display_name": display, "player_id": pid})


def small_match() -> ProcessedMatch:
    """A trails 0-1, levels, then wins 2-1 in normal time; B then win a shootout 1-0.

    m_001 goal B 11' | m_002 goal A 26' | m_003 momentum swing 25' | m_004 big chance A 61' (xG 0.40)
    m_005 goal A 86' | m_006 shootout won by B. The tests assert these ids, so keep the events stable.
    """
    events = [
        named(shot(1, 1, 600, AWAY, 0.31, "Goal", player="Ben Brook"), "Ben Brook", 20),
        named(shot(2, 1, 1500, HOME, 0.20, "Goal", player="Alan Archer"), "Alan Archer", 10),
        named(shot(3, 2, 900, HOME, 0.40, "Saved", player="Dan Dale"), "Dan Dale", 11),
        named(shot(4, 2, 2400, HOME, 0.55, "Goal", player="Alan Archer"), "Alan Archer", 10),
        period_end(5, 1, 2700),
        period_end(6, 2, 2700),
        named(ev(7, 5, 10, "Shot", AWAY, player="Cal Cross", outcome="Goal", detail={"shot_type": "Penalty"}), "Cal Cross", 21),
        named(ev(8, 5, 60, "Shot", HOME, player="Dan Dale", outcome="Saved", detail={"shot_type": "Penalty"}), "Dan Dale", 11),
    ]
    events.sort(key=lambda e: e.index)
    moments = detect_moments(events, META)
    return ProcessedMatch(META, events, moments, build_summary(MatchContext(events, META)))
