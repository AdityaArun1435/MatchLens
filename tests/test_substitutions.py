from matchlens.detect.substitutions import detect_substitutions, group_substitutions

from .helpers import AWAY, HOME, ctx, ev, period_end, shot


def _sub(index, secs, team=HOME, off="Off", on="On", period=1):
    return ev(index, period, secs, "Substitution", team, player=off, detail={"replacement": on})


def _base(extra):
    return [*extra, period_end(99, 1, 2700)]


def test_impactful_sub_reports_numbers_only():
    events = _base([
        shot(1, 1, 700, HOME, 0.1),
        _sub(2, 1200),
        *[shot(3 + i, 1, 1300 + 100 * i, HOME, 0.2) for i in range(4)],
        shot(20, 1, 1250, AWAY, 0.05),
    ])
    (m,) = detect_substitutions(ctx(events))
    assert m.type == "substitution_impact" and m.team == HOME
    assert m.stats["before"] == {"xg": 0.1, "shots": 1}
    assert m.stats["after"] == {"xg": 0.8, "shots": 4}
    assert m.stats["xg_change"] == 0.7 and m.stats["shots_change"] == 3
    assert m.stats["opponent_after"] == {"xg": 0.05, "shots": 1}
    assert m.stats["off"] == ["Off"] and m.stats["on"] == ["On"]
    for word in ("because", "caused", "due to", "thanks to", "impact"):
        assert word not in m.headline.lower()


def test_small_change_is_not_flagged():
    events = _base([shot(1, 1, 700, HOME, 0.1), _sub(2, 1200), shot(3, 1, 1300, HOME, 0.15)])
    assert detect_substitutions(ctx(events)) == []


def test_decline_is_flagged_too():
    events = _base([*[shot(i, 1, 650 + 80 * i, HOME, 0.2) for i in range(1, 6)], _sub(10, 1200)])
    (m,) = detect_substitutions(ctx(events))
    assert m.stats["xg_change"] < 0


def test_sub_without_room_inside_period_is_skipped():
    events = [_sub(1, 120), *[shot(2 + i, 1, 150 + 20 * i, HOME, 0.3) for i in range(5)], period_end(99, 1, 2700)]
    assert detect_substitutions(ctx(events)) == []


def test_windows_do_not_cross_into_other_period():
    # sub at the start of period 2; heavy period-1 xG must not count as "before"
    events = [*[shot(i, 1, 2000 + 60 * i, HOME, 0.4) for i in range(1, 6)], _sub(10, 0, period=2),
              period_end(98, 1, 2700), period_end(99, 2, 2700)]
    assert detect_substitutions(ctx(events)) == []


def test_double_substitution_is_one_moment():
    events = _base([_sub(1, 1200, off="O1", on="N1"), _sub(2, 1230, off="O2", on="N2"),
                    *[shot(3 + i, 1, 1300 + 100 * i, HOME, 0.2) for i in range(4)]])
    assert len(group_substitutions([e for e in events if e.type == "Substitution"])) == 1
    (m,) = detect_substitutions(ctx(events))
    assert m.stats["off"] == ["O1", "O2"] and m.stats["on"] == ["N1", "N2"] and len(m.evidence) == 2


def test_other_team_subs_not_grouped():
    subs = [_sub(1, 1200, HOME), _sub(2, 1210, AWAY)]
    assert len(group_substitutions(subs)) == 2
