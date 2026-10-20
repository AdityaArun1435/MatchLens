"""Live replay of a match: events streamed in match order on a compressed clock, with incrementally detected moments.

`ReplayEngine` is pure (no sleeping, no sockets): give it a replay time and it returns the messages that became due. The
WebSocket in api.py only paces it. Replay time is "match time with the breaks cut out": half-time and the break before extra
time are skipped, and the stoppage time of a period is not overlapped by the next one.
"""
import asyncio
import time
from dataclasses import dataclass

from . import config
from .detect.common import in_period_seconds
from .incremental import IncrementalDetector, canonical_ids
from .models import Event
from .normalise import clock_label
from .service import ProcessedMatch

SPEEDS = (1, 10, 30, 60)
TICK_SECONDS = 0.1  # wall-clock interval between clock ticks
_NOTABLE = {"Shot", "Own Goal For", "Substitution", "Half Start", "Half End", "Bad Behaviour"}


@dataclass(frozen=True)
class Timeline:
    """Replay seconds for every event: each period starts where the previous one ended, with no breaks."""

    base: dict[int, float]
    length: dict[int, float]
    duration: float

    @classmethod
    def from_events(cls, events: list[Event]) -> "Timeline":
        length: dict[int, float] = {}
        for e in events:
            length[e.period] = max(length.get(e.period, 0.0), in_period_seconds(e))
        base, total = {}, 0.0
        for p in sorted(length):
            base[p] = total
            total += length[p]
        return cls(base, length, total)

    def t(self, e: Event) -> float:
        return self.base[e.period] + in_period_seconds(e)

    def locate(self, t: float) -> tuple[int, float]:
        """(period, seconds into the period) at replay time t."""
        periods = sorted(self.base)
        for p in reversed(periods):
            if t >= self.base[p]:
                return p, min(t - self.base[p], self.length[p])
        return periods[0], 0.0

    def clock(self, t: float) -> dict:
        p, s = self.locate(t)
        minute = config.PERIOD_OFFSET_SECONDS[p] // 60 + int(s // 60)
        return {"t": round(t, 2), "clock": clock_label(p, minute)[0], "period": p, "minute": minute}

    def t_at_minute(self, minute: float) -> float:
        """Replay time of an elapsed match minute (60 -> the 60th minute of play)."""
        seconds = minute * 60
        period = max((p for p in self.base if config.PERIOD_OFFSET_SECONDS[p] <= seconds), default=min(self.base))
        return self.base[period] + max(0.0, min(seconds - config.PERIOD_OFFSET_SECONDS[period], self.length[period]))

    def periods(self) -> list[dict]:
        names = {1: "1st half", 2: "2nd half", 3: "Extra time 1", 4: "Extra time 2", 5: "Penalties"}
        return [{"period": p, "start": round(self.base[p], 1), "end": round(self.base[p] + self.length[p], 1), "label": names[p]} for p in sorted(self.base)]


def compact(e: Event, t: float, tl: Timeline) -> dict:
    """What the browser needs of an event for the ticker and the xG chart."""
    return {
        "type": "event",
        **tl.clock(t),
        "id": e.id,
        "index": e.index,
        "kind": e.type,
        "team": e.team,
        "player": e.player_display_name or e.player,
        "outcome": e.outcome,
        "xg": e.xg,
        "detail": {k: v for k, v in e.detail.items() if k in ("shot_type", "card", "replacement_display_name", "replacement")},
        "in_play": e.in_play,
    }


CAPTION_MIN_IMPORTANCE = 0.6
_EFFECT = {
    "took_lead": "take the lead",
    "equalised": "level the score",
    "extended_lead": "extend the lead",
    "reduced_deficit": "pull one back",
}


def caption(m, home: str, away: str) -> str | None:
    """A one-line commentary caption for an important moment, built only from its data (no model, instant)."""
    if m.importance < CAPTION_MIN_IMPORTANCE:
        return None
    h, a = m.score_after
    score = f"{home} {h}-{a} {away}"
    who = m.player_display_names[0] if m.player_display_names else m.team
    if m.type == "goal":
        kind = {"penalty": " from the penalty spot", "own_goal": " (own goal)", "free_kick": " from a free kick"}.get(m.stats.get("goal_kind"), "")
        effect = _EFFECT.get(m.stats.get("result_change"), "score")
        return f"{m.clock_label} Goal! {who}{kind} for {m.team} to {effect}. {score}."
    if m.type == "quick_response":
        goals = len(m.stats.get("goals", []))
        return f"{m.clock_label} {m.team} score again within minutes ({goals} goals in {int(m.stats['span_seconds'] // 60)}:{int(m.stats['span_seconds'] % 60):02d}). {score}."
    if m.type in ("red_card", "second_yellow"):
        return f"{m.clock_label} {'Red card' if m.type == 'red_card' else 'Second yellow'} for {who} ({m.team}). {score}."
    if m.type == "big_chance_missed":
        return f"{m.clock_label} Big chance missed by {who} ({m.team}), xG {m.stats['xg']:.2f}."
    if m.type == "momentum_swing":
        return f"{m.clock_label} {m.team} take control of the match on shots and xG."
    if m.type == "penalty_shootout":
        return f"Penalty shootout: {m.headline.split(': ', 1)[-1]}"
    return None


class ReplayEngine:
    def __init__(self, match: ProcessedMatch) -> None:
        self.match = match
        self.events = sorted(match.events, key=lambda e: e.index)
        self.timeline = Timeline.from_events(self.events)
        self._ids = canonical_ids(match.moments)
        self.reset()

    def reset(self) -> None:
        self.t = 0.0
        self.pos = 0
        self.ended = False
        self.detector = IncrementalDetector(self.match.meta, self._ids)

    def hello(self, speed: int) -> dict:
        m = self.match.meta
        return {
            "type": "hello",
            "match_id": m.match_id,
            "home": m.home_team,
            "away": m.away_team,
            "duration": round(self.timeline.duration, 1),
            "periods": self.timeline.periods(),
            "speed": speed,
        }

    def _moment_message(self, moment, t: float) -> dict:
        anchor = max((self.timeline.t(e) for e in self.events if e.index == moment.first_index), default=t)
        meta = self.match.meta
        return {
            "type": "moment",
            **self.timeline.clock(t),
            "moment": moment.model_dump(mode="json"),
            "anchor_t": round(anchor, 2),
            "caption": caption(moment, meta.home_team, meta.away_team),
        }

    def advance(self, t_new: float) -> list[dict]:
        """Messages for everything due up to replay time t_new, then a tick (or the end)."""
        out: list[dict] = []
        tl, det = self.timeline, self.detector
        while self.pos < len(self.events) and tl.t(self.events[self.pos]) <= t_new:
            e = self.events[self.pos]
            self.pos += 1
            t_e = tl.t(e)
            before = list(det.score)
            moments = det.feed(e)
            if e.type in _NOTABLE or e.detail.get("card"):
                out.append(compact(e, t_e, tl))
            if det.score != before:
                out.append({"type": "score", **tl.clock(t_e), "score": list(det.score), "team": e.team, "player": e.player_display_name or e.player})
            out += [self._moment_message(m, t_e) for m in moments]
        if self.pos >= len(self.events) and not self.ended:
            self.ended = True
            out += [self._moment_message(m, tl.duration) for m in det.finish()]
            self.t = tl.duration
            out.append({"type": "end", **tl.clock(tl.duration), "score": list(det.score), "moment_count": len(det._emitted)})
            return out
        self.t = min(t_new, tl.duration)
        out.append({"type": "tick", **tl.clock(self.t), "score": list(det.score)})
        return out

    def seek(self, t: float) -> dict:
        """Jump (forwards or back): rebuild the state at replay time t and return it as one catch-up message."""
        self.reset()
        msgs = self.advance(max(0.0, min(t, self.timeline.duration)))
        return {
            "type": "catchup",
            **self.timeline.clock(self.t),
            "score": list(self.detector.score),
            "events": [m for m in msgs if m["type"] == "event"],
            "moments": [m for m in msgs if m["type"] == "moment"],
            "ended": self.ended,
        }


class LiveSession:
    """Paces a ReplayEngine against the wall clock and takes pause / resume / speed / seek commands."""

    def __init__(self, engine: ReplayEngine, speed: int = 10, start_minute: float | None = None) -> None:
        self.engine = engine
        self.speed = speed if speed in SPEEDS else 10
        self.paused = False
        self._seek_to: float | None = None if start_minute is None else engine.timeline.t_at_minute(start_minute)
        self._dirty = True

    def handle(self, msg: dict) -> None:
        cmd = msg.get("cmd")
        if cmd == "pause":
            self.paused = True
        elif cmd == "resume":
            self.paused = False
        elif cmd == "speed" and msg.get("value") in SPEEDS:
            self.speed = msg["value"]
        elif cmd == "seek":
            tl = self.engine.timeline
            self._seek_to = float(msg["t"]) if "t" in msg else tl.t_at_minute(float(msg["minute"]))
        elif cmd == "restart":
            self._seek_to = 0.0
            self.paused = False
        self._dirty = True

    def _state(self) -> dict:
        return {"type": "state", "paused": self.paused, "speed": self.speed}

    async def run(self, ws) -> None:
        await ws.send_json(self.engine.hello(self.speed))
        last = time.monotonic()
        while True:
            if self._seek_to is not None:
                target, self._seek_to = self._seek_to, None
                await ws.send_json({"type": "reset", "t": round(target, 2)})
                await ws.send_json(self.engine.seek(target))
                last = time.monotonic()
            if self._dirty:
                self._dirty = False
                await ws.send_json(self._state())
            now = time.monotonic()
            if not self.paused and not self.engine.ended:
                for msg in self.engine.advance(self.engine.t + (now - last) * self.speed):
                    await ws.send_json(msg)
            last = now
            await asyncio.sleep(TICK_SECONDS)
