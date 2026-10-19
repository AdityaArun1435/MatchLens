from matchlens import config
from matchlens.detect.momentum import detect_momentum, window_leader, window_stats

from .helpers import AWAY, HOME, META, ctx, period_end, shot


def _swing_events():
    # A leads the 10-minute window from minute 2 to 13; B from minute 15 to 26.
    return [
        shot(1, 1, 120, HOME, 0.3), shot(2, 1, 240, HOME, 0.3),
        shot(3, 1, 900, AWAY, 0.3), shot(4, 1, 960, AWAY, 0.3), shot(5, 1, 1020, AWAY, 0.3),
        period_end(6, 1, 1800),
    ]


def test_swing_detected_with_both_teams_numbers():
    moments = detect_momentum(ctx(_swing_events()))
    assert len(moments) == 1
    m = moments[0]
    assert m.type == "momentum_swing" and m.team == AWAY
    assert m.stats["previous_leader"] == HOME and m.stats["new_leader"] == AWAY
    assert m.stats["window"][AWAY] == {"xg": 0.3, "shots": 1}
    assert m.stats["window"][HOME] == {"xg": 0.0, "shots": 0}
    assert m.clock_label == "15'" and m.stats["held_minutes"] >= config.MOMENTUM_HOLD_MIN
    assert m.evidence == ["e3"]


def test_short_flicker_is_not_a_swing():
    events = [
        shot(1, 1, 120, HOME, 0.3), shot(2, 1, 240, HOME, 0.3),
        shot(3, 1, 900, AWAY, 0.2),  # B leads one minute only
        shot(4, 1, 960, HOME, 0.4),
        period_end(5, 1, 1800),
    ]
    assert detect_momentum(ctx(events)) == []


def test_small_gap_is_not_a_leader():
    a, b = window_stats([shot(1, 1, 60, HOME, 0.10), shot(2, 1, 90, AWAY, 0.05)], (HOME, AWAY), 0, 600), None
    assert window_leader(a, (HOME, AWAY), 0.15) is None


def test_no_swing_across_half_time():
    events = [
        shot(1, 1, 1500, HOME, 0.5),  # A leads the last five minutes of period 1
        period_end(2, 1, 1800),
        shot(3, 2, 60, AWAY, 0.5),  # B leads the start of period 2
        period_end(4, 2, 1800),
    ]
    assert detect_momentum(ctx(events)) == []


def test_window_never_includes_other_period():
    events = [shot(1, 1, 2700, HOME, 0.9), shot(2, 2, 30, AWAY, 0.1)]
    w = window_stats([e for e in events if e.period == 2], (HOME, AWAY), 0, 600)
    assert w.xg == {HOME: 0.0, AWAY: 0.1}


def test_penalty_excluded_by_default_and_included_on_request(monkeypatch):
    events = [shot(1, 1, 120, HOME, 0.3), shot(2, 1, 240, HOME, 0.3),
              shot(3, 1, 900, AWAY, 0.78, outcome="Goal", shot_type="Penalty"), period_end(4, 1, 1800)]
    assert detect_momentum(ctx(events)) == []
    monkeypatch.setattr(config, "EXCLUDE_PENALTIES_FROM_WINDOWS", False)
    assert len(detect_momentum(ctx(events))) == 1
