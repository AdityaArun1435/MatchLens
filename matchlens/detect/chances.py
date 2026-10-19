"""Big chances missed: in-play shots at or above the xG threshold that did not score."""
from .. import config, importance
from ..models import Moment
from .common import MatchContext, people_fields, person_of


def detect_big_chances(ctx: MatchContext, threshold: float | None = None) -> list[Moment]:
    threshold = config.BIG_CHANCE_XG if threshold is None else threshold
    moments = []
    for e in ctx.events:
        if not (e.in_play and e.type == "Shot" and e.outcome != "Goal" and (e.xg or 0) >= threshold):
            continue
        before = ctx.score_before(e.index)
        assist = None
        evidence = [e.id]
        kp = ctx.by_id.get(e.detail.get("key_pass_id") or "")
        if kp:
            evidence.insert(0, kp.id)
            assist = person_of(kp)
        moments.append(
            Moment(
                id="",
                minute=e.minute,
                clock_label=e.clock_label,
                period=e.period,
                type="big_chance_missed",
                team=e.team,
                **people_fields([person_of(e), assist]),
                score_before=before,
                score_after=before,
                importance=importance.big_chance(xg=e.xg or 0.0, score_diff_abs=abs(before[0] - before[1])),
                headline=(
                    f"{e.team}: {e.player_display_name or e.player} shot, outcome {e.outcome}, xG {e.xg:.2f}, {e.clock_label}. "
                    f"Score {ctx.meta.home_team} {before[0]}-{before[1]} {ctx.meta.away_team}."
                ),
                stats={
                    "xg": round(e.xg or 0.0, 3),
                    "outcome": e.outcome,
                    "shot_type": e.detail.get("shot_type"),
                    "body_part": e.detail.get("body_part"),
                    "assist": assist.display if assist else None,
                    "location": e.location,
                    "threshold": threshold,
                },
                evidence=evidence,
                first_index=e.index,
            )
        )
    return moments
