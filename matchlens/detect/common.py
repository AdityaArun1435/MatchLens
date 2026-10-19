"""Shared context for the detectors: score log, lookups and time helpers."""
from bisect import bisect_left
from dataclasses import dataclass, field

from .. import config
from ..models import Event, MatchMeta


@dataclass(frozen=True)
class Goal:
    event: Event  # the shot, or the "Own Goal For" event
    team: str  # team credited with the goal
    scorer: str | None
    kind: str  # open_play | penalty | free_kick | own_goal | other_set_piece
    score_before: tuple[int, int]
    score_after: tuple[int, int]
    evidence: tuple[str, ...]  # event ids: the shot or both own-goal events


@dataclass
class MatchContext:
    events: list[Event]
    meta: MatchMeta
    by_id: dict[str, Event] = field(init=False)
    goals: list[Goal] = field(init=False)
    _goal_indexes: list[int] = field(init=False)

    def __post_init__(self) -> None:
        self.by_id = {e.id: e for e in self.events}
        self.goals = build_goal_log(self.events, self.meta.home_team, self.meta.away_team, self.by_id)
        self._goal_indexes = [g.event.index for g in self.goals]

    def score_before(self, index: int) -> tuple[int, int]:
        """In-play score before the event with this index."""
        n = bisect_left(self._goal_indexes, index)
        return self.goals[n - 1].score_after if n else (0, 0)

    def home_away(self, team: str) -> int:
        """0 if team is home, 1 if away."""
        return 0 if team == self.meta.home_team else 1


def in_period_seconds(e: Event) -> float:
    return e.match_clock_seconds - config.PERIOD_OFFSET_SECONDS[e.period]


def period_length_seconds(events: list[Event], period: int) -> float:
    return max((in_period_seconds(e) for e in events if e.period == period), default=0.0)


def window_shots(events: list[Event], period: int) -> list[Event]:
    """In-play shots of one period used for rolling-window comparisons (penalties optionally excluded)."""
    return [
        e
        for e in events
        if e.period == period
        and e.type == "Shot"
        and e.in_play
        and not (config.EXCLUDE_PENALTIES_FROM_WINDOWS and e.detail.get("shot_type") == "Penalty")
    ]


def plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _goal_kind(shot: Event) -> str:
    return {
        "Open Play": "open_play",
        "Penalty": "penalty",
        "Free Kick": "free_kick",
    }.get(shot.detail.get("shot_type", ""), "other_set_piece")


def build_goal_log(events: list[Event], home: str, away: str, by_id: dict[str, Event]) -> list[Goal]:
    """Walk events in order and record each in-play goal with the running score.

    Goals are shots with outcome Goal, plus own goals (credited via "Own Goal For").
    Shootout kicks (in_play False) are never goals.
    """
    score = [0, 0]
    goals: list[Goal] = []
    for e in events:
        if not e.in_play:
            continue
        if e.type == "Shot" and e.outcome == "Goal":
            team, scorer, kind, evidence = e.team, e.player, _goal_kind(e), (e.id,)
        elif e.type == "Own Goal For":
            against = next((by_id[r] for r in e.related_ids if r in by_id and by_id[r].type == "Own Goal Against"), None)
            team, scorer, kind = e.team, against.player if against else None, "own_goal"
            evidence = (e.id, against.id) if against else (e.id,)
        else:
            continue
        before = (score[0], score[1])
        score[0 if team == home else 1] += 1
        goals.append(Goal(e, team, scorer, kind, before, (score[0], score[1]), evidence))
    return goals
