"""Quick responses: goals bunched together in play time.

Two triggers, merged when they share a goal:
* brace: 2+ goals by one team within QUICK_RESPONSE_BRACE_MIN minutes
* reply: a goal that equalises or takes the lead within QUICK_RESPONSE_REPLY_MIN minutes of conceding
Times are play time (half-time and the pre-extra-time break do not count), so 45+2' to 46' is short.
"""
from collections import defaultdict

from .. import config, importance
from ..models import Moment
from .common import MatchContext, people_fields

BRACE = "brace"
EQUALISER = "equaliser_after_conceding"
LEAD_CHANGE = "lead_change_after_conceding"


def _span(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def _braces(teams: dict[str, list[int]], t: list[float], limit: float) -> list[tuple[set[int], str]]:
    found = []
    for positions in teams.values():
        i = 0
        while i < len(positions):
            j = i + 1
            while j < len(positions) and t[positions[j]] - t[positions[i]] <= limit:
                j += 1
            if j - i > 1:
                found.append((set(positions[i:j]), BRACE))
            i = j
    return found


def _replies(ctx: MatchContext, t: list[float], limit: float) -> list[tuple[set[int], str]]:
    found = []
    for k, g in enumerate(ctx.goals):
        change = ctx.result_change(g)
        if change not in ("equalised", "took_lead"):
            continue
        conceded = [c for c in range(k) if ctx.goals[c].team != g.team and t[k] - t[c] <= limit]
        if conceded:
            found.append(({conceded[-1], k}, EQUALISER if change == "equalised" else LEAD_CHANGE))
    return found


def _merge(candidates: list[tuple[set[int], str]]) -> list[tuple[list[int], list[str]]]:
    merged: list[tuple[set[int], list[str]]] = []
    for goals, reason in candidates:
        goals, reasons = set(goals), [reason]
        for other in [m for m in merged if m[0] & goals]:
            merged.remove(other)
            goals |= other[0]
            reasons = [*other[1], *[r for r in reasons if r not in other[1]]]
        merged.append((goals, reasons))
    return sorted(((sorted(g), r) for g, r in merged), key=lambda m: m[0])


def detect_quick_responses(ctx: MatchContext, brace_min: float | None = None, reply_min: float | None = None) -> list[Moment]:
    brace_s = 60 * (config.QUICK_RESPONSE_BRACE_MIN if brace_min is None else brace_min)
    reply_s = 60 * (config.QUICK_RESPONSE_REPLY_MIN if reply_min is None else reply_min)
    goals = ctx.goals
    t = [ctx.play_seconds(g.event) for g in goals]
    teams: dict[str, list[int]] = defaultdict(list)
    for pos, g in enumerate(goals):
        teams[g.team].append(pos)
    moments = []
    for positions, reasons in _merge([*_braces(teams, t, brace_s), *_replies(ctx, t, reply_s)]):
        seq = [goals[p] for p in positions]
        first, last = seq[0], seq[-1]
        span = t[positions[-1]] - t[positions[0]]
        before, after = first.score_before, last.score_after
        state = lambda s: (s[0] > s[1]) - (s[0] < s[1])  # noqa: E731
        changes = state(before) != state(after) or any(ctx.result_change(g) in ("equalised", "took_lead") for g in seq)
        lead = {BRACE: f"{last.team} scored {len(seq)} goals in {_span(span)}", EQUALISER: f"{last.team} equalised {_span(span)} after conceding", LEAD_CHANGE: f"{last.team} took the lead {_span(span)} after conceding"}[reasons[0]]
        scorers = "; ".join(f"{g.scorer.display if g.scorer else 'unknown player'} {g.event.clock_label}" for g in seq)
        moments.append(
            Moment(
                id="",
                minute=last.event.minute,
                clock_label=last.event.clock_label,
                period=last.event.period,
                type="quick_response",
                team=last.team,
                **people_fields([g.scorer for g in seq]),
                score_before=before,
                score_after=after,
                importance=importance.quick_response(
                    changes_result=changes, period=last.event.period, clock_seconds=last.event.match_clock_seconds
                ),
                headline=(
                    f"{lead}: {scorers}. Score {ctx.meta.home_team} {before[0]}-{before[1]} {ctx.meta.away_team} "
                    f"to {after[0]}-{after[1]}."
                ),
                stats={
                    "reasons": reasons,
                    "span_seconds": round(span, 1),
                    "goals": [
                        {
                            "clock": g.event.clock_label,
                            "team": g.team,
                            "scorer": g.scorer.display if g.scorer else None,
                            "goal_kind": g.kind,
                            "score_after": list(g.score_after),
                            "play_seconds": round(t[p], 1),
                        }
                        for g, p in zip(seq, positions)
                    ],
                    "result_changed": changes,
                    "thresholds": {"brace_min": brace_s / 60, "reply_min": reply_s / 60},
                },
                evidence=[eid for g in seq for eid in g.evidence],
                first_index=last.event.index,
            )
        )
    return moments
