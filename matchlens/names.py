"""Player display names: override, then lineup nickname, then full name."""
from collections.abc import Mapping

from . import config


def resolve_display_name(player_id: int | None, full_name: str, nickname: str | None = None) -> str:
    overrides = config.DISPLAY_NAME_OVERRIDES
    if player_id in overrides:
        return overrides[player_id]
    if full_name in overrides:
        return overrides[full_name]
    return nickname or full_name


def build_display_names(lineups: list[dict]) -> dict[int, str]:
    """Map StatsBomb player id to display name for everyone in a match's lineups."""
    return {
        p["player_id"]: resolve_display_name(p["player_id"], p["player_name"], p.get("player_nickname"))
        for team in lineups
        for p in team["lineup"]
    }


def display_name(names: Mapping[int, str] | None, player_id: int | None, full_name: str | None) -> str | None:
    """Display name for a player, falling back to overrides and then the full name when not in the lineups."""
    if full_name is None:
        return None
    if names and player_id in names:
        return names[player_id]
    return resolve_display_name(player_id, full_name)
