"""Substitutions followed by a measurable change in the team's xG / shots. Numbers only, no causation."""
from .. import config, importance
from ..models import Event, Moment
from .common import MatchContext, in_period_seconds, period_length_seconds, plural, window_shots

GROUP_GAP_SECONDS = 120  # same-team subs closer than this are one change (double substitutions)
MIN_WINDOW_SECONDS = 300  # skip subs that do not leave 5 minutes on both sides inside the period


def group_substitutions(subs: list[Event]) -> list[list[Event]]:
    groups: list[list[Event]] = []
    for s in sorted(subs, key=lambda e: e.index):
        last = groups[-1][-1] if groups else None
        if last and last.team == s.team and last.period == s.period and in_period_seconds(s) - in_period_seconds(last) <= GROUP_GAP_SECONDS:
            groups[-1].append(s)
        else:
            groups.append([s])
    return groups


def _side(shots: list[Event], team: str, lo: float, hi: float) -> tuple[float, int]:
    inside = [e for e in shots if e.team == team and lo <= in_period_seconds(e) < hi]
    return round(sum(e.xg or 0.0 for e in inside), 4), len(inside)


def detect_substitutions(
    ctx: MatchContext, xg_delta: float | None = None, shot_delta: int | None = None, window_min: int | None = None
) -> list[Moment]:
    xg_delta = config.SUB_XG_DELTA if xg_delta is None else xg_delta
    shot_delta = config.SUB_SHOT_DELTA if shot_delta is None else shot_delta
    window_s = 60 * (config.SUB_WINDOW_MIN if window_min is None else window_min)
    teams = (ctx.meta.home_team, ctx.meta.away_team)
    moments: list[Moment] = []
    for group in group_substitutions([e for e in ctx.events if e.type == "Substitution" and e.in_play]):
        first = group[0]
        team = first.team
        other = teams[1] if team == teams[0] else teams[0]
        t = in_period_seconds(first)
        w = min(window_s, t, period_length_seconds(ctx.events, first.period) - t)
        if w < MIN_WINDOW_SECONDS:
            continue
        shots = window_shots(ctx.events, first.period)
        xg_b, sh_b = _side(shots, team, t - w, t)
        xg_a, sh_a = _side(shots, team, t, t + w)
        scale = window_s / w  # express deltas per full window so the thresholds stay comparable
        d_xg, d_sh = (xg_a - xg_b) * scale, (sh_a - sh_b) * scale
        if abs(d_xg) < xg_delta and abs(d_sh) < shot_delta:
            continue
        opp_b, opp_sb = _side(shots, other, t - w, t)
        opp_a, opp_sa = _side(shots, other, t, t + w)
        off = [s.player for s in group if s.player]
        on = [s.detail.get("replacement") for s in group if s.detail.get("replacement")]
        score = ctx.score_before(first.index)
        minutes = w / 60
        moments.append(
            Moment(
                id="",
                minute=first.minute,
                clock_label=first.clock_label,
                period=first.period,
                type="substitution_impact",
                team=team,
                players=[*off, *on],
                score_before=score,
                score_after=score,
                importance=importance.substitution(xg_change_per_10=d_xg),
                headline=(
                    f"{team} substitution at {first.clock_label} ({', '.join(on)} on for {', '.join(off)}): "
                    f"in the {minutes:.0f} min before, {team} xG {xg_b:.2f} from {plural(sh_b, 'shot')}; "
                    f"in the {minutes:.0f} min after, xG {xg_a:.2f} from {plural(sh_a, 'shot')}"
                    f"{' (penalties excluded)' if config.EXCLUDE_PENALTIES_FROM_WINDOWS else ''}."
                ),
                stats={
                    "off": off,
                    "on": on,
                    "window_minutes": round(minutes, 1),
                    "before": {"xg": xg_b, "shots": sh_b},
                    "after": {"xg": xg_a, "shots": sh_a},
                    "xg_change": round(xg_a - xg_b, 4),
                    "shots_change": sh_a - sh_b,
                    "opponent_before": {"xg": opp_b, "shots": opp_sb},
                    "opponent_after": {"xg": opp_a, "shots": opp_sa},
                    "penalties_excluded": config.EXCLUDE_PENALTIES_FROM_WINDOWS,
                    "thresholds": {"xg_delta": xg_delta, "shot_delta": shot_delta},
                },
                evidence=[s.id for s in group],
                first_index=first.index,
            )
        )
    return moments
