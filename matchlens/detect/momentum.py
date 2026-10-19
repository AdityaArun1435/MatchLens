"""Momentum swings from a rolling xG / shots window, evaluated inside one period at a time."""
from dataclasses import dataclass

from .. import config, importance
from ..models import Event, Moment
from .clock import label_for_period_second
from .common import MatchContext, in_period_seconds, period_length_seconds, plural, window_shots


@dataclass(frozen=True)
class Window:
    xg: dict[str, float]
    shots: dict[str, int]
    shot_ids: tuple[str, ...]
    start: float
    end: float


def window_stats(shots: list[Event], teams: tuple[str, str], start: float, end: float) -> Window:
    """xG and shots per team for shots with start < in-period time <= end."""
    inside = [e for e in shots if start < in_period_seconds(e) <= end]
    return Window(
        xg={t: round(sum(e.xg or 0.0 for e in inside if e.team == t), 4) for t in teams},
        shots={t: sum(1 for e in inside if e.team == t) for t in teams},
        shot_ids=tuple(e.id for e in inside),
        start=start,
        end=end,
    )


def window_leader(w: Window, teams: tuple[str, str], min_lead_xg: float) -> str | None:
    """Team with the higher window xG, or None if the gap is below min_lead_xg."""
    diff = w.xg[teams[0]] - w.xg[teams[1]]
    if abs(diff) < min_lead_xg:
        return None
    return teams[0] if diff > 0 else teams[1]


def _runs(leaders: list[str | None]) -> list[tuple[str | None, int, int]]:
    """Collapse a per-minute leader list into (leader, first_step, last_step) runs, steps 1-based."""
    runs: list[tuple[str | None, int, int]] = []
    for k, leader in enumerate(leaders, start=1):
        if runs and runs[-1][0] == leader:
            runs[-1] = (leader, runs[-1][1], k)
        else:
            runs.append((leader, k, k))
    return runs


def detect_momentum(
    ctx: MatchContext,
    window_min: int | None = None,
    hold_min: int | None = None,
    min_lead_xg: float | None = None,
) -> list[Moment]:
    window_min = config.MOMENTUM_WINDOW_MIN if window_min is None else window_min
    hold_min = config.MOMENTUM_HOLD_MIN if hold_min is None else hold_min
    min_lead_xg = config.MOMENTUM_MIN_LEAD_XG if min_lead_xg is None else min_lead_xg
    teams = (ctx.meta.home_team, ctx.meta.away_team)
    moments: list[Moment] = []
    for period in config.IN_PLAY_PERIODS:  # state is reset for each period: no window spans a boundary
        period_events = [e for e in ctx.events if e.period == period]
        if not period_events:
            continue
        shots = window_shots(ctx.events, period)
        steps = int(period_length_seconds(ctx.events, period) // 60)
        windows = [window_stats(shots, teams, max(0.0, 60 * k - 60 * window_min), 60.0 * k) for k in range(1, steps + 1)]
        leaders = [window_leader(w, teams, min_lead_xg) for w in windows]
        confirmed = [r for r in _runs(leaders) if r[0] is not None and r[2] - r[1] + 1 >= hold_min]
        for prev, cur in zip(confirmed, confirmed[1:]):
            if prev[0] == cur[0]:
                continue
            k = cur[1]
            w = windows[k - 1]
            new, old = cur[0], prev[0]
            other = teams[1] if new == teams[0] else teams[0]
            minute = config.PERIOD_OFFSET_SECONDS[period] // 60 + k - 1
            label = label_for_period_second(period, 60 * k)
            anchor = max(
                (e for e in period_events if in_period_seconds(e) <= 60 * k),
                key=lambda e: e.index,
                default=period_events[0],
            )
            score = ctx.score_before(anchor.index)
            lead = round(w.xg[new] - w.xg[other], 4)
            moments.append(
                Moment(
                    id="",
                    minute=minute,
                    clock_label=label,
                    period=period,
                    type="momentum_swing",
                    team=new,
                    players=[],
                    score_before=score,
                    score_after=score,
                    importance=importance.momentum(lead_xg=lead),
                    headline=(
                        f"Window leader changes from {old} to {new} at {label}: last {(w.end - w.start) / 60:.0f} min "
                        f"xG {new} {w.xg[new]:.2f}, {other} {w.xg[other]:.2f}; shots {new} {w.shots[new]}, {other} {w.shots[other]}"
                        f"{' (penalties excluded)' if config.EXCLUDE_PENALTIES_FROM_WINDOWS else ''}."
                    ),
                    stats={
                        "previous_leader": old,
                        "new_leader": new,
                        "window_minutes": round((w.end - w.start) / 60, 1),
                        "held_minutes": cur[2] - cur[1] + 1,
                        "window": {t: {"xg": w.xg[t], "shots": w.shots[t]} for t in teams},
                        "lead_xg": lead,
                        "lead_shots": w.shots[new] - w.shots[other],
                        "penalties_excluded": config.EXCLUDE_PENALTIES_FROM_WINDOWS,
                        "thresholds": {"window_min": window_min, "hold_min": hold_min, "min_lead_xg": min_lead_xg},
                    },
                    evidence=list(w.shot_ids),
                    first_index=anchor.index,
                )
            )
    return moments
