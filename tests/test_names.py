from matchlens import config
from matchlens.detect import detect_moments
from matchlens.names import build_display_names, display_name, resolve_display_name
from matchlens.normalise import normalise_event

from .helpers import AWAY, HOME, META, ev, shot

LINEUPS = [
    {"team_name": "X", "lineup": [
        {"player_id": 1, "player_name": "Lionel Andrés Messi Cuccittini", "player_nickname": "Lionel Messi"},
        {"player_id": 2, "player_name": "Plain Name", "player_nickname": None},
        {"player_id": 22097, "player_name": "Randal Kolo Muani", "player_nickname": "Randal Kolo"},
    ]},
]


def test_nickname_then_full_name_then_override():
    names = build_display_names(LINEUPS)
    assert names[1] == "Lionel Messi"
    assert names[2] == "Plain Name"
    assert names[22097] == "Randal Kolo Muani"  # shipped override beats the nickname


def test_override_by_name_and_by_id(monkeypatch):
    monkeypatch.setitem(config.DISPLAY_NAME_OVERRIDES, "Plain Name", "Plain")
    monkeypatch.setitem(config.DISPLAY_NAME_OVERRIDES, 1, "Leo")
    assert resolve_display_name(2, "Plain Name", None) == "Plain"
    assert resolve_display_name(1, "Lionel Andrés Messi Cuccittini", "Lionel Messi") == "Leo"


def test_player_missing_from_lineups_falls_back_to_full_name():
    assert display_name({1: "A"}, 99, "Someone Else") == "Someone Else"
    assert display_name(None, 22097, "Randal Kolo Muani") == "Randal Kolo Muani"
    assert display_name({}, 5, None) is None


def _raw_pass() -> dict:
    return {
        "id": "x", "index": 1, "period": 1, "timestamp": "00:01:00.000", "minute": 1, "second": 0,
        "type": {"name": "Pass"}, "team": {"id": 9, "name": "A"}, "player": {"id": 1, "name": "Lionel Andrés Messi Cuccittini"},
        "pass": {"recipient": {"id": 2, "name": "Plain Name"}},
    }


def test_event_keeps_full_name_and_id_and_adds_display_name():
    e = normalise_event(_raw_pass(), build_display_names(LINEUPS))
    assert (e.player, e.player_id, e.player_display_name) == ("Lionel Andrés Messi Cuccittini", 1, "Lionel Messi")
    assert e.detail["recipient"] == "Plain Name" and e.detail["recipient_display_name"] == "Plain Name"


def test_headlines_and_stats_use_display_name_but_moment_keeps_full_name_and_id():
    s = shot(1, 1, 100, HOME, 0.3, outcome="Goal", player="Lionel Andrés Messi Cuccittini")
    s = s.model_copy(update={"player_id": 1, "player_display_name": "Lionel Messi"})
    (m,) = detect_moments([s], META)
    assert "Lionel Messi" in m.headline and "Cuccittini" not in m.headline
    assert m.stats["scorer"] == "Lionel Messi"
    assert m.players == ["Lionel Andrés Messi Cuccittini"] and m.player_ids == [1]
    assert m.player_display_names == ["Lionel Messi"]


def test_shipped_overrides_fix_known_nickname_problems():
    assert resolve_display_name(27886, "Alexis Mac Allister", "Alexis MacAllister") == "Alexis Mac Allister"
    assert resolve_display_name(22097, "Randal Kolo Muani", "Randal Kolo") == "Randal Kolo Muani"
