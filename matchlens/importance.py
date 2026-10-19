"""Importance scoring (0 to 1) for every moment type. Tune the numbers here.

Goals
    base 0.60. +0.30 if the goal changes who is winning (takes the lead or equalises).
    +0.10 if scored from the 75th minute of normal time onward (period 2 minute >= 74 elapsed) or in extra time.
Big chance missed
    0.25 + 0.5 * xG, +0.10 if the score is within one goal at that moment.
Red card 0.70, second yellow 0.65; either is 0.20 when shown after the shootout started.
Momentum swing
    0.25 + 0.30 * min(xG lead of the new leader / 0.5, 1).
Substitution impact
    0.15 + 0.25 * min(|xG change per 10 min| / 1.0, 1).
Penalty shootout 0.95 (it decides the match).
All results are clamped to [0, 1] and rounded to 2 decimals.
"""

GOAL_BASE = 0.60
GOAL_RESULT_CHANGE = 0.30
GOAL_LATE = 0.10
LATE_GOAL_CLOCK_SECONDS = 74 * 60  # elapsed seconds on the period-2 clock; anything in periods 3+ is late too

CHANCE_BASE = 0.25
CHANCE_XG_WEIGHT = 0.50
CHANCE_CLOSE_GAME = 0.10

RED_CARD = 0.70
SECOND_YELLOW = 0.65
CARD_AFTER_SHOOTOUT = 0.20

MOMENTUM_BASE = 0.25
MOMENTUM_SPAN = 0.30
MOMENTUM_LEAD_FULL = 0.5

SUB_BASE = 0.15
SUB_SPAN = 0.25
SUB_XG_FULL = 1.0

SHOOTOUT = 0.95


def _clamp(x: float) -> float:
    return round(max(0.0, min(1.0, x)), 2)


def goal(*, changes_result: bool, period: int, clock_seconds: float) -> float:
    late = period >= 3 or (period == 2 and clock_seconds >= LATE_GOAL_CLOCK_SECONDS)
    return _clamp(
        GOAL_BASE + (GOAL_RESULT_CHANGE if changes_result else 0) + (GOAL_LATE if late else 0)
    )


def big_chance(*, xg: float, score_diff_abs: int) -> float:
    return _clamp(CHANCE_BASE + CHANCE_XG_WEIGHT * xg + (CHANCE_CLOSE_GAME if score_diff_abs <= 1 else 0))


def card(*, second_yellow: bool, after_shootout: bool) -> float:
    if after_shootout:
        return _clamp(CARD_AFTER_SHOOTOUT)
    return _clamp(SECOND_YELLOW if second_yellow else RED_CARD)


def momentum(*, lead_xg: float) -> float:
    return _clamp(MOMENTUM_BASE + MOMENTUM_SPAN * min(lead_xg / MOMENTUM_LEAD_FULL, 1))


def substitution(*, xg_change_per_10: float) -> float:
    return _clamp(SUB_BASE + SUB_SPAN * min(abs(xg_change_per_10) / SUB_XG_FULL, 1))


def shootout() -> float:
    return _clamp(SHOOTOUT)
