"""Shared context for the detectors: score log, lookups and time helpers."""
from bisect import bisect_left
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import NamedTuple

from .. import config
from ..models import Event, MatchMeta


class Person(NamedTuple):
    name: str  # full StatsBomb name
    id: int | None
    display: str


def person_of(e: Event) -> Person | None:
    """The player on an event, if any."""
    return Person(e.player, e.player_id, e.player_display_name or e.player) if e.player else None


def people_fields(people: Iterable[Person | None]) -> dict[str, list]:
    """players / player_ids / player_display_names for a Moment, de-duplicated in order."""
    seen: list[Person] = []
    for p in people:
        if p and p not in seen:
            seen.append(p)
    return {
        "players": [p.name for p in seen],
        "player_ids": [p.id for p in seen],
        "player_display_names": [p.display for p in seen],
    }


@dataclass(frozen=True)
class Goal:
    event: Event  # the shot, or the "Own Goal For" event
    team: str  # team credited with the goal
    scorer: Person | None  # for an own goal, the player who put it in
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
    _play_offsets: dict[int, float] = field(init=False)

    def __post_init__(self) -> None:
        self.by_id = {e.id: e for e in self.events}
        self.goals = build_goal_log(self.events, self.meta.home_team, self.meta.away_team, self.by_id)
        self._goal_indexes = [g.event.index for g in self.goals]
        self._play_offsets, total = {}, 0.0
        for period in config.IN_PLAY_PERIODS:
            self._play_offsets[period] = total
            total += period_length_seconds(self.events, period)

    def play_seconds(self, e: Event) -> float:
        """Seconds of play since kick-off: unlike the broadcast clock it never repeats across a period boundary."""
        return self._play_offsets[e.period] + in_period_seconds(e)

    def result_change(self, goal: "Goal") -> str:
        """How a goal changed the score from its own team's point of view."""
        i = self.home_away(goal.team)
        before = goal.score_before[i] - goal.score_before[1 - i]
        if before < 0:
            return "equalised" if before == -1 else "reduced_deficit"
        return "took_lead" if before == 0 else "extended_lead"

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


_OUTCOME_TEXT = {"Off T": "off target", "Saved to Post": "saved onto the post", "Saved Off Target": "saved, off target"}


def outcome_text(raw: str) -> str:
    """StatsBomb shot outcome as plain lower-case words ("Off T" -> "off target")."""
    return _OUTCOME_TEXT.get(raw, raw.lower())


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
            team, scorer, kind, evidence = e.team, person_of(e), _goal_kind(e), (e.id,)
        elif e.type == "Own Goal For":
            against = next((by_id[r] for r in e.related_ids if r in by_id and by_id[r].type == "Own Goal Against"), None)
            team, scorer, kind = e.team, person_of(against) if against else None, "own_goal"
            evidence = (e.id, against.id) if against else (e.id,)
        else:
            continue
        before = (score[0], score[1])
        score[0 if team == home else 1] += 1
        goals.append(Goal(e, team, scorer, kind, before, (score[0], score[1]), evidence))
    return goals
