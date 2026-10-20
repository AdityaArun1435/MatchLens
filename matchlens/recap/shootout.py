"""The shootout paragraph, written from the kick list and not by the model.

The model kept getting kick order and takers wrong, so it never sees the shootout moment. This paragraph is added after
its paragraphs, cites only the shootout moment, and goes through the same translation as everything else.
"""
from ..detect.common import outcome_text
from ..models import Moment
from ..service import ProcessedMatch
from .models import RecapParagraph

SHOOTOUT_TYPE = "penalty_shootout"
HIDDEN_FROM_MODEL = frozenset({SHOOTOUT_TYPE})

_OPENING = {
    "analyst": "The match went to a penalty shootout. {winner} won it {high}-{low}.",
    "broadcaster": "It was settled in the penalty shootout, which {winner} won {high}-{low}.",
    "fan": "Then came the penalty shootout. {winner} won it {high}-{low}.",
}
_KICK = {
    "analyst": "Kick {n}: {team}, {taker}, {result}.",
    "broadcaster": "Kick {n}, {team}: {taker} {result}.",
    "fan": "Kick {n}: {taker} ({team}) {result}.",
}


def shootout_moment(match: ProcessedMatch) -> Moment | None:
    return next((m for m in match.moments if m.type == SHOOTOUT_TYPE), None)


def shootout_paragraph(match: ProcessedMatch, audience: str) -> RecapParagraph | None:
    moment = shootout_moment(match)
    if moment is None:
        return None
    stats = moment.stats
    score = stats["shootout_score"]
    high, low = max(score.values()), min(score.values())
    sentences = [_OPENING[audience].format(winner=stats["winner"], high=high, low=low)]
    for k in stats["kicks"]:
        result = "scored" if k["scored"] else outcome_text(k["outcome"])
        sentences.append(_KICK[audience].format(n=k["order"], team=k["team"], taker=k["player"], result=result))
    return RecapParagraph(text=" ".join(sentences), cites=[moment.id])
