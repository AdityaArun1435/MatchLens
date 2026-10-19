from matchlens import config
from matchlens.detect import detect_moments
from matchlens.detect.quick_response import detect_quick_responses

from .helpers import AWAY, HOME, META, ctx, period_end, shot


def goal(index, period, secs, team, player="Scorer"):
    return shot(index, period, secs, team, 0.3, outcome="Goal", player=player)


def test_brace_within_five_minutes():
    c = ctx([goal(1, 1, 600, HOME), goal(2, 1, 850, HOME), period_end(9, 1, 2700)])
    (m,) = detect_quick_responses(c)
    assert m.type == "quick_response" and m.team == HOME
    assert m.stats["reasons"] == ["brace"] and m.evidence == ["e1", "e2"]
    assert m.score_before == (0, 0) and m.score_after == (2, 0)
    assert m.importance >= 0.8


def test_goals_further_apart_than_five_minutes_are_not_a_brace():
    c = ctx([goal(1, 1, 600, HOME), goal(2, 1, 1000, HOME), period_end(9, 1, 2700)])
    assert detect_quick_responses(c) == []


def test_equaliser_within_three_minutes_of_conceding():
    c = ctx([goal(1, 1, 600, HOME), goal(2, 1, 700, AWAY), period_end(9, 1, 2700)])
    (m,) = detect_quick_responses(c)
    assert m.team == AWAY and m.stats["reasons"] == ["equaliser_after_conceding"]
    assert m.evidence == ["e1", "e2"] and m.score_before == (0, 0) and m.score_after == (1, 1)
    assert m.importance >= 0.9  # result changed


def test_reply_after_three_minutes_does_not_count():
    c = ctx([goal(1, 1, 600, HOME), goal(2, 1, 800, AWAY), period_end(9, 1, 2700)])  # 200 s
    assert detect_quick_responses(c) == []


def test_lead_change_within_three_minutes():
    c = ctx([goal(1, 1, 600, HOME), goal(2, 1, 650, AWAY), goal(3, 1, 3000 - 2400, HOME)])  # 1-0, 1-1, 2-1 at 600 s
    moments = detect_quick_responses(c)
    assert any("lead_change_after_conceding" in m.stats["reasons"] for m in moments)


def test_reply_that_only_reduces_the_deficit_is_not_flagged():
    c = ctx([goal(1, 1, 100, HOME), goal(2, 1, 150, HOME), goal(3, 1, 200, AWAY), period_end(9, 1, 2700)])
    reasons = [r for m in detect_quick_responses(c) for r in m.stats["reasons"]]
    assert "equaliser_after_conceding" not in reasons and "lead_change_after_conceding" not in reasons


def test_overlapping_triggers_merge_into_one_moment():
    # B concedes, equalises 100 s later and takes the lead 60 s after that: brace + equaliser + lead change
    c = ctx([goal(1, 1, 600, HOME), goal(2, 1, 700, AWAY), goal(3, 1, 760, AWAY), period_end(9, 1, 2700)])
    (m,) = detect_quick_responses(c)
    assert set(m.stats["reasons"]) == {"brace", "equaliser_after_conceding", "lead_change_after_conceding"}
    assert m.evidence == ["e1", "e2", "e3"] and m.score_before == (0, 0) and m.score_after == (1, 2)


def test_play_time_not_broadcast_clock_across_half_time():
    # 45+2' then 46': 100 s of stoppage left in period 1 plus 60 s of period 2 = 160 s of play
    close = ctx([goal(1, 1, 2800, HOME), period_end(2, 1, 2900), goal(3, 2, 60, HOME), period_end(4, 2, 2700)])
    assert len(detect_quick_responses(close)) == 1
    far = ctx([goal(1, 1, 1000, HOME), period_end(2, 1, 2900), goal(3, 2, 10, HOME), period_end(4, 2, 2700)])
    assert detect_quick_responses(far) == []


def test_thresholds_are_configurable(monkeypatch):
    c = ctx([goal(1, 1, 600, HOME), goal(2, 1, 1000, HOME), period_end(9, 1, 2700)])
    assert detect_quick_responses(c) == []
    monkeypatch.setattr(config, "QUICK_RESPONSE_BRACE_MIN", 8)
    assert len(detect_quick_responses(c)) == 1


def test_included_in_detect_moments_and_sorted_after_its_last_goal():
    moments = detect_moments([goal(1, 1, 600, HOME), goal(2, 1, 700, AWAY), period_end(9, 1, 2700)], META)
    assert [m.type for m in moments] == ["goal", "goal", "quick_response"]
