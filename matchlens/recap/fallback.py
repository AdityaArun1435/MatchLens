"""Deterministic recap and explanation built straight from moments. No LLM; also the baseline to compare against.

Every sentence is assembled from moment headlines and summary figures, so the output passes the same validators.
"""
from .. import config
from ..models import Moment
from ..service import ProcessedMatch
from .models import MomentExplanation, Recap, RecapParagraph

_EFFECT = {
    "took_lead": "put the scoring team ahead",
    "equalised": "levelled the score",
    "extended_lead": "extended the lead",
    "reduced_deficit": "reduced the deficit",
}


def fallback_title(match: ProcessedMatch) -> str:
    s, m = match.summary, match.meta
    title = f"{m.home_team} v {m.away_team}: {s.final_score[0]}-{s.final_score[1]}"
    if s.shootout:
        sc = s.shootout["score"]
        title += f", {s.shootout['winner']} win {max(sc.values())}-{min(sc.values())} on penalties"
    return title


def _overview(match: ProcessedMatch) -> str:
    s, m = match.summary, match.meta
    h, a = s.final_score
    if s.went_to_extra_time:
        text = f"{m.home_team} v {m.away_team} finished {h}-{a} after extra time ({s.score_after_90[0]}-{s.score_after_90[1]} after 90 minutes)."
    else:
        text = f"{m.home_team} v {m.away_team} finished {h}-{a}."
    text += (
        f" Total xG was {m.home_team} {s.total_xg[m.home_team]:.2f}, {m.away_team} {s.total_xg[m.away_team]:.2f}, "
        f"with {s.shots[m.home_team]} and {s.shots[m.away_team]} shots."
    )
    return text


def _moment_text(m: Moment) -> str:
    text = m.headline
    if m.type == "goal":
        if m.stats.get("assist"):
            text += f" Assist: {m.stats['assist']}."
        if m.stats.get("xg") is not None:
            text += f" Shot xG {m.stats['xg']:.2f}."
    return text


def fallback_recap(match: ProcessedMatch, length: str, min_importance: float | None = None) -> Recap:
    cutoff = config.RECAP_MIN_IMPORTANCE if min_importance is None else min_importance
    shown = [m for m in match.moments if m.importance >= cutoff] or list(match.moments)
    if length == "short":
        top = sorted(shown, key=lambda m: -m.importance)[:3]
        shown = [m for m in shown if m in top]
    title = fallback_title(match)
    if not shown:
        return Recap(title=title, paragraphs=[])
    anchor = next((m for m in reversed(shown) if m.type == "penalty_shootout"), shown[-1])
    paragraphs = [RecapParagraph(text=_overview(match), cites=[anchor.id])]
    covered: set[str] = set()
    for m in shown:
        if m.type == "quick_response":
            goals = [g for g in shown if g.type == "goal" and g.evidence[-1] in m.evidence]
            covered |= {g.id for g in goals}
    for m in shown:
        if m.id in covered:
            continue
        cites = [m.id]
        if m.type == "quick_response":
            cites = [g.id for g in shown if g.type == "goal" and g.evidence[-1] in m.evidence] + [m.id]
        paragraphs.append(RecapParagraph(text=_moment_text(m), cites=cites))
    return Recap(title=title, paragraphs=paragraphs)


def fallback_explanation(match: ProcessedMatch, moment_id: str) -> MomentExplanation:
    moments = match.moments
    idx = next(i for i, m in enumerate(moments) if m.id == moment_id)
    m = moments[idx]
    meta = match.meta
    before = f"{meta.home_team} {m.score_before[0]}-{m.score_before[1]} {meta.away_team}"
    after = f"{meta.home_team} {m.score_after[0]}-{m.score_after[1]} {meta.away_team}"
    if m.type == "goal":
        why = f"This goal {_EFFECT.get(m.stats['result_change'], 'changed the score')}: the score went from {before} to {after}."
    else:
        why = m.headline
    if idx:
        prev = moments[idx - 1]
        context = f"Previous moment: {prev.headline}"
        cites = [m.id, prev.id]
    else:
        context = f"This was the first moment recorded in the match. The score at the time was {after}."
        cites = [m.id]
    return MomentExplanation(moment_id=m.id, why_it_mattered=why, context=context, cites=cites)
