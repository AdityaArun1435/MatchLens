"""MatchSummary: scores, xG, shots, possession and a per-minute xG timeline."""
from collections import defaultdict

from . import config
from .detect.common import MatchContext, in_period_seconds
from .detect.shootout import shootout_kicks
from .models import MatchSummary, ShootoutKick, TimelinePoint
from .normalise import clock_label

ON_TARGET = {"Goal", "Saved", "Saved to Post"}


def _score_through(ctx: MatchContext, last_period: int) -> tuple[int, int]:
    goals = [g for g in ctx.goals if g.event.period <= last_period]
    return goals[-1].score_after if goals else (0, 0)


def possession_share(ctx: MatchContext) -> dict[str, float]:
    """Share of in-play time with each team in possession.

    A possession runs from its first event to the first event of the next possession in the same period.
    """
    seconds: dict[str, float] = defaultdict(float)
    for period in config.IN_PLAY_PERIODS:
        starts: dict[int, tuple[float, str]] = {}
        end = 0.0
        for e in ctx.events:
            if e.period != period or e.possession is None or e.possession_team is None:
                continue
            t = in_period_seconds(e)
            end = max(end, t)
            starts.setdefault(e.possession, (t, e.possession_team))
        ordered = sorted(starts.values())
        for (t0, team), nxt in zip(ordered, [*ordered[1:], (end, "")]):
            seconds[team] += max(nxt[0] - t0, 0.0)
    total = sum(seconds.values()) or 1.0
    return {t: round(seconds.get(t, 0.0) / total, 3) for t in (ctx.meta.home_team, ctx.meta.away_team)}


def xg_timeline(ctx: MatchContext) -> list[TimelinePoint]:
    teams = (ctx.meta.home_team, ctx.meta.away_team)
    points: list[TimelinePoint] = []
    running = dict.fromkeys(teams, 0.0)
    for period in config.IN_PLAY_PERIODS:
        evs = [e for e in ctx.events if e.period == period]
        if not evs:
            continue
        per_minute: dict[int, dict[str, float]] = defaultdict(lambda: dict.fromkeys(teams, 0.0))
        for e in evs:
            if e.type == "Shot" and e.in_play and e.team in teams:
                per_minute[e.minute][e.team] += e.xg or 0.0
        for minute in range(config.PERIOD_OFFSET_SECONDS[period] // 60, max(e.minute for e in evs) + 1):
            xg = {t: round(per_minute[minute][t], 4) for t in teams}
            for t in teams:
                running[t] += xg[t]
            points.append(
                TimelinePoint(
                    period=period,
                    minute=minute,
                    label=clock_label(period, minute)[0],
                    xg=xg,
                    cumulative_xg={t: round(running[t], 4) for t in teams},
                )
            )
    return points


def build_summary(ctx: MatchContext) -> MatchSummary:
    teams = (ctx.meta.home_team, ctx.meta.away_team)
    shots = [e for e in ctx.events if e.type == "Shot" and e.in_play]
    extra_time = any(e.period in (3, 4) for e in ctx.events)
    shootout = None
    kicks = shootout_kicks(ctx)
    if kicks:
        tally = {t: sum(1 for k in kicks if k.team == t and k.outcome == "Goal") for t in teams}
        shootout = {
            "kicks": [
                ShootoutKick(
                    order=i,
                    team=k.team,
                    player=k.player,
                    player_id=k.player_id,
                    player_display_name=k.player_display_name or k.player,
                    outcome=k.outcome,
                    scored=k.outcome == "Goal",
                ).model_dump()
                for i, k in enumerate(kicks, start=1)
            ],
            "score": tally,
            "winner": None if tally[teams[0]] == tally[teams[1]] else max(tally, key=tally.get),
        }
    return MatchSummary(
        meta=ctx.meta,
        final_score=_score_through(ctx, 4),
        score_after_90=_score_through(ctx, 2),
        score_after_extra_time=_score_through(ctx, 4) if extra_time else None,
        went_to_extra_time=extra_time,
        shootout=shootout,
        total_xg={t: round(sum(e.xg or 0.0 for e in shots if e.team == t), 3) for t in teams},
        shots={t: sum(1 for e in shots if e.team == t) for t in teams},
        shots_on_target={t: sum(1 for e in shots if e.team == t and e.outcome in ON_TARGET) for t in teams},
        possession_share=possession_share(ctx),
        xg_timeline=xg_timeline(ctx),
    )
