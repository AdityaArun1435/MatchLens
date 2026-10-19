import pytest

from matchlens.normalise import clock_label, normalise_event


@pytest.mark.parametrize(
    "period,minute,expected",
    [(1, 0, "1'"), (1, 22, "23'"), (1, 44, "45'"), (1, 45, "45+1'"), (1, 52, "45+8'"),
     (2, 45, "46'"), (2, 92, "90+3'"), (2, 100, "90+11'"), (3, 100, "101'"), (3, 105, "105+1'"),
     (4, 117, "118'"), (4, 120, "120+1'"), (5, 120, "Pens")],
)
def test_clock_label(period, minute, expected):
    assert clock_label(period, minute)[0] == expected


def test_stoppage_minutes():
    assert clock_label(2, 92)[1] == 3
    assert clock_label(2, 80)[1] == 0


def _raw_shot(period: int) -> dict:
    return {
        "id": "x", "index": 1, "period": period, "timestamp": "00:01:00.000", "minute": 120 if period == 5 else 1,
        "second": 0, "type": {"name": "Shot"}, "team": {"id": 1, "name": "A"}, "player": {"id": 2, "name": "P"},
        "possession": 3, "possession_team": {"id": 1, "name": "A"},
        "shot": {"statsbomb_xg": 0.7835, "outcome": {"name": "Goal"}, "type": {"name": "Penalty"}},
    }


def test_shootout_shot_has_no_xg_and_is_not_in_play():
    e = normalise_event(_raw_shot(5))
    assert e.xg is None and not e.in_play and e.outcome == "Goal" and e.clock_label == "Pens"


def test_in_play_penalty_keeps_xg():
    e = normalise_event(_raw_shot(1))
    assert e.xg == 0.7835 and e.in_play


def test_period_clock_offsets():
    raw = _raw_shot(3)
    raw["minute"] = 91
    assert normalise_event(raw).match_clock_seconds == 90 * 60 + 60
