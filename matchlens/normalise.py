"""Turn raw StatsBomb event dicts into the internal Event model."""
from typing import Any

from . import config
from .models import Event

_TYPE_KEYS = {"Goal Keeper": "goalkeeper", "Ball Receipt*": "ball_receipt"}


def _type_key(name: str) -> str:
    return _TYPE_KEYS.get(name) or name.lower().replace(" ", "_").replace("/", "_")


def parse_timestamp(ts: str) -> float:
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def clock_label(period: int, minute: int) -> tuple[str, int]:
    """Return the display label and stoppage minutes for an elapsed whole minute.

    StatsBomb minute 22 means 22:xx elapsed, which football reports as 23'.
    """
    if period == config.SHOOTOUT_PERIOD:
        return "Pens", 0
    shown = minute + 1
    end = config.PERIOD_END_MINUTE[period]
    if shown > end:
        return f"{end}+{shown - end}'", shown - end
    return f"{shown}'", 0


def _outcome(raw: dict, key: str) -> str | None:
    block = raw.get(key)
    if block is None:
        return None
    if "outcome" in block:
        return block["outcome"]["name"]
    return "Complete" if raw["type"]["name"] == "Pass" else None


def _detail(raw: dict) -> dict[str, Any]:
    t = raw["type"]["name"]
    out: dict[str, Any] = {}
    if t == "Shot":
        shot = raw["shot"]
        out["shot_type"] = shot["type"]["name"]
        out["body_part"] = shot.get("body_part", {}).get("name")
        out["key_pass_id"] = shot.get("key_pass_id")
    elif t == "Pass":
        p = raw["pass"]
        out["recipient"] = p.get("recipient", {}).get("name")
        out["goal_assist"] = bool(p.get("goal_assist"))
        out["shot_assist"] = bool(p.get("shot_assist"))
    elif t == "Substitution":
        out["replacement"] = raw["substitution"]["replacement"]["name"]
        out["replacement_id"] = raw["substitution"]["replacement"]["id"]
    for block in ("foul_committed", "bad_behaviour"):
        if "card" in raw.get(block, {}):
            out["card"] = raw[block]["card"]["name"]
    return out


def normalise_event(raw: dict) -> Event:
    period = raw["period"]
    t = raw["type"]["name"]
    is_shootout = period == config.SHOOTOUT_PERIOD
    label, stoppage = clock_label(period, raw["minute"])
    team = raw.get("team") or {}
    player = raw.get("player") or {}
    loc = raw.get("location")
    xg = None
    if t == "Shot" and not is_shootout:
        xg = raw["shot"].get("statsbomb_xg")
    return Event(
        id=raw["id"],
        index=raw["index"],
        period=period,
        minute=raw["minute"],
        second=raw["second"],
        match_clock_seconds=config.PERIOD_OFFSET_SECONDS[period] + parse_timestamp(raw["timestamp"]),
        clock_label=label,
        stoppage_minutes=stoppage,
        in_play=not is_shootout,
        type=t,
        team=team.get("name"),
        team_id=team.get("id"),
        player=player.get("name"),
        player_id=player.get("id"),
        location=(loc[0], loc[1]) if loc else None,
        outcome=_outcome(raw, _type_key(t)),
        xg=xg,
        possession=raw.get("possession"),
        possession_team=(raw.get("possession_team") or {}).get("name"),
        related_ids=raw.get("related_events", []),
        detail=_detail(raw),
    )


def normalise_events(raw_events: list[dict]) -> list[Event]:
    return sorted((normalise_event(r) for r in raw_events), key=lambda e: e.index)
