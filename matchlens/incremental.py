"""Moment detection that only sees events up to the clock, for the live replay.

Every time something could have changed, the batch detectors are run on the events streamed so far and a moment is released
only when it is *complete*, meaning no later event could still change it:

* goals, big chances, cards: complete when their event arrives;
* quick responses: when the longest window in which another goal could join them has passed;
* substitutions: when the window after the change has fully been played (or the period has ended) and no further
  substitution can join the group;
* momentum swings: when the leading run has ended (a later minute has a different leader) or the period has ended,
  because the moment records how long the lead was held;
* the shootout: when it has ended.

Content comes from the batch detectors on that prefix, so a released moment is identical to the one the batch run finds on
the whole match. Moment ids are only labels: they are copied from the batch run (`canonical_ids`), they are not used to decide
anything. The test suite proves both properties on the real matches.
"""
from . import config
from .detect import detect_moments
from .detect.common import MatchContext, in_period_seconds
from .detect.substitutions import GROUP_GAP_SECONDS
from .models import Event, MatchMeta, Moment

_TRIGGER_TYPES = {"Shot", "Own Goal For", "Substitution", "Half Start", "Half End"}


def canonical_ids(moments: list[Moment]) -> dict[tuple[str, int], str]:
    """(type, first_index) -> the id the batch run gave the moment."""
    return {(m.type, m.first_index): m.id for m in moments}


class IncrementalDetector:
    def __init__(self, meta: MatchMeta, ids: dict[tuple[str, int], str] | None = None) -> None:
        self.meta = meta
        self.events: list[Event] = []
        self.score = [0, 0]
        self.finished = False
        self._ids = ids or {}
        self._emitted: set[tuple[str, int]] = set()
        self._ended: set[int] = set()
        self._last_minute: tuple[int, int] | None = None

    # ---- feeding ---------------------------------------------------------------------------------
    def feed(self, e: Event) -> list[Moment]:
        """Take the next event in match order; return the moments that are complete now."""
        self.events.append(e)
        if e.type == "Half End":
            self._ended.add(e.period)
        if e.in_play and ((e.type == "Shot" and e.outcome == "Goal") or e.type == "Own Goal For"):
            self.score[0 if e.team == self.meta.home_team else 1] += 1
        minute = (e.period, int(in_period_seconds(e) // 60))
        trigger = e.type in _TRIGGER_TYPES or bool(e.detail.get("card")) or minute != self._last_minute
        self._last_minute = minute
        return self._release() if trigger else []

    def finish(self) -> list[Moment]:
        """No more events: everything still waiting is complete."""
        self.finished = True
        return self._release()

    # ---- releasing -------------------------------------------------------------------------------
    def _release(self) -> list[Moment]:
        if not self.events:
            return []
        now = self.events[-1]
        out: list[Moment] = []
        state = _Now(self, now)
        for c in detect_moments(self.events, self.meta):  # sorted by match order
            key = (c.type, c.first_index)
            if key in self._emitted or not state.ready(c):
                continue
            self._emitted.add(key)
            out.append(c.model_copy(update={"id": self._ids[key]}) if key in self._ids else c)
        return out


class _Now:
    """The clock position at one release check, and the completeness rule for each moment type."""

    def __init__(self, det: IncrementalDetector, now: Event) -> None:
        self.det, self.now = det, now
        self.s_now = in_period_seconds(now)
        self._ctx: MatchContext | None = None

    def period_done(self, period: int) -> bool:
        return self.det.finished or period < self.now.period or period in self.det._ended

    def ready(self, c: Moment) -> bool:
        if self.det.finished or c.type in ("goal", "big_chance_missed", "red_card", "second_yellow"):
            return True
        return {
            "quick_response": self._quick_response,
            "substitution_impact": self._substitution,
            "momentum_swing": self._momentum,
            "penalty_shootout": lambda m: self.period_done(m.period),
        }[c.type](c)

    def _quick_response(self, c: Moment) -> bool:
        if self.now.period not in config.IN_PLAY_PERIODS:
            return True
        self._ctx = self._ctx or MatchContext(self.det.events, self.det.meta)
        last_goal = c.stats["goals"][-1]["play_seconds"]
        horizon = 60 * max(config.QUICK_RESPONSE_BRACE_MIN, config.QUICK_RESPONSE_REPLY_MIN)  # a later goal could still join
        return self._ctx.play_seconds(self.now) >= last_goal + horizon

    def _substitution(self, c: Moment) -> bool:
        if self.period_done(c.period):
            return True
        evidence = set(c.evidence)
        subs = [e for e in self.det.events if e.id in evidence]
        first, last = min(in_period_seconds(e) for e in subs), max(in_period_seconds(e) for e in subs)
        window = 60 * config.SUB_WINDOW_MIN
        return self.s_now >= first + window and self.s_now >= last + GROUP_GAP_SECONDS

    def _momentum(self, c: Moment) -> bool:
        if self.period_done(c.period):
            return True
        start_step = c.minute - config.PERIOD_OFFSET_SECONDS[c.period] // 60 + 1
        end_step = start_step + c.stats["held_minutes"] - 1
        return int(self.s_now // 60) > end_step  # a later minute exists, and its leader differs, so the run has ended
