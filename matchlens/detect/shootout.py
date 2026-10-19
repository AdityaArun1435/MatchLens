"""The penalty shootout as a single moment holding the full kick sequence."""
from .. import importance
from ..models import Moment
from .common import MatchContext


def shootout_kicks(ctx: MatchContext):
    return [e for e in ctx.events if not e.in_play and e.type == "Shot"]


def detect_shootout(ctx: MatchContext) -> list[Moment]:
    kicks = shootout_kicks(ctx)
    if not kicks:
        return []
    teams = (ctx.meta.home_team, ctx.meta.away_team)
    tally = {t: sum(1 for k in kicks if k.team == t and k.outcome == "Goal") for t in teams}
    winner = None if tally[teams[0]] == tally[teams[1]] else max(tally, key=tally.get)
    score = ctx.score_before(kicks[0].index)
    sequence = [
        {"order": i, "team": k.team, "player": k.player, "outcome": k.outcome, "scored": k.outcome == "Goal"}
        for i, k in enumerate(kicks, start=1)
    ]
    players = list(dict.fromkeys(k.player for k in kicks if k.player))
    text = f"{teams[0]} {tally[teams[0]]}-{tally[teams[1]]} {teams[1]}"
    return [
        Moment(
            id="",
            minute=kicks[0].minute,
            clock_label="Pens",
            period=kicks[0].period,
            type="penalty_shootout",
            team=winner,
            players=players,
            score_before=score,
            score_after=score,
            importance=importance.shootout(),
            headline=f"Penalty shootout: {text}" + (f", won by {winner}." if winner else ", no winner recorded."),
            stats={
                "shootout_score": tally,
                "winner": winner,
                "kicks": sequence,
                "kick_count": len(kicks),
                "score_before_shootout": list(score),
            },
            evidence=[k.id for k in kicks],
            first_index=kicks[0].index,
        )
    ]
