"""Moment detection: pure Python over normalised events."""
from ..models import Event, MatchMeta, Moment
from .cards import detect_cards
from .chances import detect_big_chances
from .common import MatchContext
from .goals import detect_goals
from .momentum import detect_momentum
from .quick_response import detect_quick_responses
from .shootout import detect_shootout
from .substitutions import detect_substitutions

_TYPE_ORDER = {
    "goal": 0,
    "quick_response": 1,
    "red_card": 2,
    "second_yellow": 2,
    "big_chance_missed": 3,
    "substitution_impact": 4,
    "momentum_swing": 5,
    "penalty_shootout": 6,
}


def detect_moments(events: list[Event], meta: MatchMeta) -> list[Moment]:
    """Run every detector, sort by match order and assign stable ids m_001, m_002, ..."""
    ctx = MatchContext(events, meta)
    found = [
        *detect_goals(ctx),
        *detect_quick_responses(ctx),
        *detect_big_chances(ctx),
        *detect_cards(ctx),
        *detect_momentum(ctx),
        *detect_substitutions(ctx),
        *detect_shootout(ctx),
    ]
    found.sort(key=lambda m: (m.first_index, _TYPE_ORDER[m.type]))
    return [m.model_copy(update={"id": f"m_{i:03d}"}) for i, m in enumerate(found, start=1)]
