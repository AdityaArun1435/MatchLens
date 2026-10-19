from matchlens.detect import detect_moments
from matchlens.detect.goals import detect_goals
from matchlens.detect.shootout import detect_shootout
from matchlens.summary import build_summary

from .helpers import AWAY, HOME, META, ctx, ev, period_end, shot


def test_own_goal_credits_other_team_and_updates_score():
    events = [
        ev(1, 1, 600, "Own Goal For", AWAY, possession=7, related=["e2"]),
        ev(2, 1, 600, "Own Goal Against", HOME, player="Defender", related=["e1"]),
    ]
    (m,) = detect_goals(ctx(events))
    assert m.team == AWAY and m.score_after == (0, 1) and m.stats["goal_kind"] == "own_goal"
    assert m.players == ["Defender"] and m.evidence == ["e1", "e2"]


def test_goal_buildup_uses_completed_passes_of_scoring_team_in_possession():
    def pas(i, team, outcome):
        return ev(i, 1, 100 + i, "Pass", team, player=f"p{i}", outcome=outcome, possession=5, detail={"recipient": "r"})
    events = [pas(1, HOME, "Complete"), pas(2, HOME, "Incomplete"), pas(3, AWAY, "Complete"), pas(4, HOME, "Complete"),
              shot(5, 1, 110, HOME, 0.3, outcome="Goal")]
    events[-1] = events[-1].model_copy(update={"possession": 5})
    (m,) = detect_goals(ctx(events))
    assert m.evidence == ["e1", "e4", "e5"] and m.stats["buildup_passes"] == 2


def test_red_card_and_second_yellow_become_moments_yellow_does_not():
    events = [
        ev(1, 2, 100, "Foul Committed", HOME, player="X", detail={"card": "Red Card"}),
        ev(2, 2, 200, "Bad Behaviour", AWAY, player="Y", detail={"card": "Second Yellow"}),
        ev(3, 2, 300, "Foul Committed", AWAY, player="Z", detail={"card": "Yellow Card"}),
    ]
    moments = detect_moments(events, META)
    assert [m.type for m in moments] == ["red_card", "second_yellow"]
    assert moments[0].players == ["X"] and moments[0].importance > moments[1].importance


def test_shootout_kicks_do_not_score_or_count_xg():
    events = [
        shot(1, 1, 100, HOME, 0.3, outcome="Goal"),
        shot(2, 5, 10, HOME, 0.78, outcome="Goal", shot_type="Penalty"),
        shot(3, 5, 60, AWAY, 0.78, outcome="Saved", shot_type="Penalty"),
        period_end(4, 1, 2700),
    ]
    c = ctx(events)
    assert c.goals[-1].score_after == (1, 0) and len(c.goals) == 1
    s = build_summary(c)
    assert s.total_xg[HOME] == 0.3 and s.shots[HOME] == 1
    assert s.shootout["score"] == {HOME: 1, AWAY: 0} and s.shootout["winner"] == HOME
    (m,) = detect_shootout(c)
    assert m.stats["kick_count"] == 2 and m.evidence == ["e2", "e3"]


def test_moment_ids_sequential_and_importance_in_range():
    events = [shot(1, 1, 100, HOME, 0.3, outcome="Goal"), shot(2, 2, 100, AWAY, 0.4, outcome="Saved"),
              shot(3, 2, 900, AWAY, 0.3, outcome="Goal")]
    moments = detect_moments(events, META)
    assert [m.id for m in moments] == ["m_001", "m_002", "m_003"]
    assert all(0 <= m.importance <= 1 for m in moments)
    assert moments[0].type == "goal" and moments[1].type == "big_chance_missed"


def test_big_chance_threshold_configurable():
    from matchlens.detect.chances import detect_big_chances
    c = ctx([shot(1, 1, 100, HOME, 0.2), shot(2, 1, 200, HOME, 0.35)])
    assert len(detect_big_chances(c)) == 1
    assert len(detect_big_chances(c, threshold=0.1)) == 2


def test_rebound_goal_lists_preceding_shot():
    first = shot(1, 1, 100, HOME, 0.2, outcome="Saved").model_copy(update={"possession": 4})
    goal = shot(2, 1, 101, HOME, 0.4, outcome="Goal", player="Scorer").model_copy(update={"possession": 4})
    (m,) = detect_goals(ctx([first, goal]))
    assert m.stats["preceding_shots"] == [{"player": "P", "outcome": "Saved", "xg": 0.2, "clock": "2'"}]
    assert m.evidence == ["e1", "e2"]
