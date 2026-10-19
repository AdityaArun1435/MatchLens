"""Red cards and second yellows. Plain yellows are not moments."""
from .. import importance
from ..models import Moment
from .common import MatchContext, people_fields, person_of

_TYPES = {"Red Card": "red_card", "Second Yellow": "second_yellow"}


def detect_cards(ctx: MatchContext) -> list[Moment]:
    moments = []
    for e in ctx.events:
        card = e.detail.get("card")
        if card not in _TYPES:
            continue
        score = ctx.score_before(e.index)
        second = card == "Second Yellow"
        moments.append(
            Moment(
                id="",
                minute=e.minute,
                clock_label=e.clock_label,
                period=e.period,
                type=_TYPES[card],
                team=e.team,
                **people_fields([person_of(e)]),
                score_before=score,
                score_after=score,
                importance=importance.card(second_yellow=second, after_shootout=not e.in_play),
                headline=(
                    f"{e.team}: {e.player_display_name or e.player} shown a {'second yellow' if second else 'red'} card, "
                    f"{'during the shootout period' if not e.in_play else e.clock_label}. "
                    f"Score {ctx.meta.home_team} {score[0]}-{score[1]} {ctx.meta.away_team}."
                ),
                stats={"card": card, "in_play": e.in_play, "event_type": e.type},
                evidence=[e.id],
                first_index=e.index,
            )
        )
    return moments
