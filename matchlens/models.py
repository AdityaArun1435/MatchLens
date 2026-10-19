"""Pydantic models shared by the detectors, summary and API."""
from typing import Any, Literal

from pydantic import BaseModel, Field


class Event(BaseModel):
    id: str
    index: int
    period: int
    minute: int  # StatsBomb elapsed whole minute (continuous across periods, not unique)
    second: int
    match_clock_seconds: float  # period offset + in-period timestamp; resets overlap at period starts
    clock_label: str  # football display, e.g. "23'", "45+2'", "90+3'", "Pens"
    stoppage_minutes: int  # minutes past the period's nominal end, else 0
    in_play: bool  # False for the penalty shootout (period 5)
    type: str
    team: str | None = None
    team_id: int | None = None
    player: str | None = None
    player_id: int | None = None
    location: tuple[float, float] | None = None
    outcome: str | None = None
    xg: float | None = None  # shots only; always None for shootout kicks
    possession: int | None = None
    possession_team: str | None = None
    related_ids: list[str] = Field(default_factory=list)
    detail: dict[str, Any] = Field(default_factory=dict)  # type-specific normalised fields


class MatchMeta(BaseModel):
    match_id: int
    competition: str
    season: str
    stage: str
    date: str
    home_team: str
    away_team: str
    home_score: int  # official score after extra time, shootout excluded
    away_score: int
    stadium: str | None = None
    referee: str | None = None


MomentType = Literal[
    "goal",
    "big_chance_missed",
    "red_card",
    "second_yellow",
    "momentum_swing",
    "substitution_impact",
    "penalty_shootout",
]


class Moment(BaseModel):
    id: str
    minute: int  # elapsed whole minute, as in Event.minute
    clock_label: str
    period: int
    type: MomentType
    team: str | None
    players: list[str]
    score_before: tuple[int, int]  # (home, away), in-play goals only
    score_after: tuple[int, int]
    importance: float = Field(ge=0, le=1)
    headline: str
    stats: dict[str, Any]
    evidence: list[str]  # Event.id values that back the moment
    first_index: int  # Event.index of the anchoring event, used for ordering


class TimelinePoint(BaseModel):
    period: int
    minute: int
    label: str
    xg: dict[str, float]  # team -> xG created in this minute bucket
    cumulative_xg: dict[str, float]


class ShootoutKick(BaseModel):
    order: int
    team: str
    player: str
    outcome: str
    scored: bool


class MatchSummary(BaseModel):
    meta: MatchMeta
    final_score: tuple[int, int]  # after extra time, shootout excluded
    score_after_90: tuple[int, int]
    score_after_extra_time: tuple[int, int] | None  # None when no extra time was played
    went_to_extra_time: bool
    shootout: dict[str, Any] | None  # {kicks, score, winner}
    total_xg: dict[str, float]
    shots: dict[str, int]
    shots_on_target: dict[str, int]
    possession_share: dict[str, float]
    xg_timeline: list[TimelinePoint]
