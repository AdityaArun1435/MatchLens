"""Goal moments, with the passing build-up from the same possession."""
from .. import config, importance
from ..models import Event, Moment
from .common import Goal, MatchContext, in_period_seconds

_KIND_TEXT = {
    "open_play": "",
    "penalty": " (penalty)",
    "free_kick": " (free kick)",
    "other_set_piece": "",
}


def _buildup(ctx: MatchContext, anchor: Event, team: str) -> list[Event]:
    passes = [
        e
        for e in ctx.events
        if e.index < anchor.index
        and e.possession == anchor.possession
        and e.period == anchor.period
        and e.team == team
        and e.type == "Pass"
        and e.outcome == "Complete"
    ]
    return passes[-config.BUILDUP_MAX_PASSES :]


def _preceding_shots(ctx: MatchContext, anchor: Event, team: str) -> list[Event]:
    """Earlier in-play shots by the scoring team in the same possession (the goal was a follow-up)."""
    return [
        e
        for e in ctx.events
        if e.index < anchor.index
        and e.type == "Shot"
        and e.possession == anchor.possession
        and e.period == anchor.period
        and e.team == team
    ]


def _result_change(goal: Goal, ctx: MatchContext) -> str:
    i = ctx.home_away(goal.team)
    before = goal.score_before[i] - goal.score_before[1 - i]
    if before < 0:
        return "equalised" if before == -1 else "reduced_deficit"
    return "took_lead" if before == 0 else "extended_lead"


def detect_goals(ctx: MatchContext) -> list[Moment]:
    moments = []
    for g in ctx.goals:
        e = g.event
        passes = _buildup(ctx, e, g.team)
        prior = _preceding_shots(ctx, e, g.team)
        change = _result_change(g, ctx)
        assist = None
        if e.type == "Shot" and e.detail.get("key_pass_id") in ctx.by_id:
            kp = ctx.by_id[e.detail["key_pass_id"]]
            if kp.detail.get("goal_assist"):
                assist = kp.player
        buildup_seconds = None
        if passes:
            buildup_seconds = round(in_period_seconds(e) - in_period_seconds(passes[0]), 1)
        h, a = g.score_after
        scorer = g.scorer or "unknown player"
        what = f"own goal by {scorer}" if g.kind == "own_goal" else f"{scorer}{_KIND_TEXT[g.kind]}"
        players = [p for p in (g.scorer, assist) if p]
        moments.append(
            Moment(
                id="",
                minute=e.minute,
                clock_label=e.clock_label,
                period=e.period,
                type="goal",
                team=g.team,
                players=players,
                score_before=g.score_before,
                score_after=g.score_after,
                importance=importance.goal(
                    changes_result=change in ("took_lead", "equalised"),
                    period=e.period,
                    clock_seconds=e.match_clock_seconds,
                ),
                headline=f"{g.team} goal: {what}, {e.clock_label}. {ctx.meta.home_team} {h}-{a} {ctx.meta.away_team}.",
                stats={
                    "goal_kind": g.kind,
                    "scorer": g.scorer,
                    "assist": assist,
                    "xg": e.xg,
                    "result_change": change,
                    "body_part": e.detail.get("body_part"),
                    "preceding_shots": [
                        {"player": p.player, "outcome": p.outcome, "xg": p.xg, "clock": p.clock_label} for p in prior
                    ],
                    "buildup_passes": len(passes),
                    "buildup_seconds": buildup_seconds,
                    "buildup": [
                        {"player": p.player, "to": p.detail.get("recipient"), "clock": p.clock_label} for p in passes
                    ],
                },
                evidence=[*[x.id for x in sorted([*passes, *prior], key=lambda x: x.index)], *g.evidence],
                first_index=e.index,
            )
        )
    return moments
