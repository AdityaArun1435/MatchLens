"""Render a MatchSummary and Moments as the only input the model sees.

Everything the validators accept (numbers, names) is derived from the text produced here, so what the model
is allowed to say can never drift from what it was shown.
"""
from dataclasses import dataclass, field

from ..detect.common import outcome_text
from ..models import MatchSummary, Moment
from ..service import ProcessedMatch

_REASONS = {
    "brace": "two or more goals by one team within a few minutes",
    "equaliser_after_conceding": "equalised soon after conceding",
    "lead_change_after_conceding": "took the lead soon after conceding",
}
_RESULT = {
    "took_lead": "put the scoring team ahead",
    "equalised": "levelled the score",
    "extended_lead": "extended the lead",
    "reduced_deficit": "reduced the deficit",
}


@dataclass
class Context:
    text: str  # what goes into the prompt
    summary_text: str
    moment_text: dict[str, str]  # id -> rendered block (for number checks)
    moment_names: dict[str, set[str]]  # id -> player names visible in that block
    shown_ids: list[str]
    moments: dict[str, Moment] = field(default_factory=dict)


def _importance_word(x: float) -> str:
    return "high" if x >= 0.8 else "medium" if x >= 0.5 else "low"


def _score(meta, s) -> str:
    return f"{meta.home_team} {s[0]}-{s[1]} {meta.away_team}"


def summary_block(summary: MatchSummary) -> str:
    from datetime import date

    m = summary.meta
    day = date.fromisoformat(m.date)
    home, away = m.home_team, m.away_team
    lines = [
        "MATCH",
        f"competition: {m.competition} {m.season}, {m.stage}, {day.day} {day.strftime('%B %Y')}"
        + (f", {m.stadium}" if m.stadium else ""),
        f"teams: {home} (home), {away} (away)",
        f"final score after extra time, shootout not included: {_score(m, summary.final_score)}",
        f"score after 90 minutes: {_score(m, summary.score_after_90)}",
        "extra time played: yes, 30 minutes, so 120 minutes of play in total"
        if summary.went_to_extra_time
        else "extra time played: no, 90 minutes of play in total",
    ]
    if summary.shootout:
        sc = summary.shootout["score"]
        lines.append(f"penalty shootout: {home} {sc[home]}-{sc[away]} {away}, won by {summary.shootout['winner']}")
    t = summary.total_xg
    lines += [
        f"total xG (in play, shootout excluded): {home} {t[home]:.2f}, {away} {t[away]:.2f}",
        f"shots: {home} {summary.shots[home]}, {away} {summary.shots[away]}",
        f"shots on target: {home} {summary.shots_on_target[home]}, {away} {summary.shots_on_target[away]}",
        f"possession: {home} {summary.possession_share[home]:.0%}, {away} {summary.possession_share[away]:.0%}",
    ]
    return "\n".join(lines)


def _facts(m: Moment, home: str, away: str) -> tuple[list[str], set[str]]:
    s, names = m.stats, set()
    out: list[str] = []

    def add_name(n):
        if n:
            names.add(n)
        return n

    if m.type == "goal":
        kind = s["goal_kind"].replace("_", " ")
        if s["goal_kind"] == "penalty":  # always say which kind of penalty: in play (with the period) or in the shootout
            kind = "penalty in regular time" if m.period <= 2 else "penalty in extra time"
        out.append(f"goal kind: {kind}")
        if s.get("scorer"):
            out.append(f"{'player who put it in' if s['goal_kind'] == 'own_goal' else 'scorer'}: {add_name(s['scorer'])}")
        if s.get("assist"):
            out.append(f"assist: {add_name(s['assist'])}")
        if s.get("xg") is not None:
            out.append(f"xG of the shot: {s['xg']:.2f}")
        out.append(f"effect: {_RESULT.get(s['result_change'], s['result_change'])}")
        for p in s.get("preceding_shots", []):
            out.append(f"earlier shot in the same move: {add_name(p['player'])}, {outcome_text(p['outcome'])}, xG {p['xg']:.2f}")
        chain = [b["player"] for b in s.get("buildup", [])][-6:]
        if chain:
            out.append(f"build-up passes ({s['buildup_passes']}), last passers in order: " + " > ".join(map(add_name, chain)))
    elif m.type == "big_chance_missed":
        out.append(f"shot by {add_name(m.player_display_names[0])}: {outcome_text(s['outcome'])}, xG {s['xg']:.2f}, {s['shot_type'].lower()}")
        if s.get("assist"):
            out.append(f"assist: {add_name(s['assist'])}")
    elif m.type in ("red_card", "second_yellow"):
        out.append(f"card: {s['card']} for {add_name(m.player_display_names[0])}")
    elif m.type == "momentum_swing":
        w = s["window"]
        out.append(f"previous window leader: {s['previous_leader']}; new leader: {s['new_leader']}")
        out.append(f"window length: {s['window_minutes']:g} minutes; leader held for {s['held_minutes']} minutes")
        out.append("window xG and shots: " + "; ".join(f"{t} xG {v['xg']:.2f}, {v['shots']} shots" for t, v in w.items()))
        out.append("penalties excluded from these figures" if s.get("penalties_excluded") else "penalties included")
    elif m.type == "substitution_impact":
        out.append(f"off: {', '.join(map(add_name, s['off']))}; on: {', '.join(map(add_name, s['on']))}")
        b, a, ob, oa = s["before"], s["after"], s["opponent_before"], s["opponent_after"]
        out.append(f"window: {s['window_minutes']:g} minutes either side (numbers only, no causal claim)")
        out.append(f"{m.team} before: xG {b['xg']:.2f}, {b['shots']} shots; after: xG {a['xg']:.2f}, {a['shots']} shots")
        other = away if m.team == home else home
        out.append(f"{other} before: xG {ob['xg']:.2f}, {ob['shots']} shots; after: xG {oa['xg']:.2f}, {oa['shots']} shots")
    elif m.type == "quick_response":
        out.append("pattern: " + "; ".join(_REASONS.get(r, r) for r in s["reasons"]))
        out.append(f"time between first and last goal in play: {round(s['span_seconds'])} seconds")
        for g in s["goals"]:
            sc = g["score_after"]
            out.append(f"goal {g['clock']}: {g['team']}, {add_name(g['scorer'])}, score then {home} {sc[0]}-{sc[1]} {away}")
    elif m.type == "penalty_shootout":
        sc = s["shootout_score"]
        out.append(f"result: {home} {sc[home]}-{sc[away]} {away}, winner {s['winner']}")
        out.append("kicks in order (kick number: team, taker, result):")
        for k in s["kicks"]:
            result = "scored" if k["scored"] else outcome_text(k["outcome"])
            out.append(f"  kick {k['order']}: {k['team']}, {add_name(k['player'])}, {result}")
    return out, names


def moment_block(m: Moment, meta, *, target: bool = False) -> tuple[str, set[str]]:
    home, away = meta.home_team, meta.away_team
    facts, names = _facts(m, home, away)
    names |= set(m.player_display_names)
    if m.score_before == m.score_after:
        score = f"score at the time: {_score(meta, m.score_after)}"
    else:
        score = f"score: {_score(meta, m.score_before)} -> {_score(meta, m.score_after)}"
    lines = [
        f"[{m.id}] {m.clock_label} | {m.type.replace('_', ' ')} | {m.team or 'n/a'} | importance: {_importance_word(m.importance)}"
        + ("  <-- TARGET" if target else ""),
        score,
    ]
    if m.player_display_names:
        lines.append("players: " + "; ".join(m.player_display_names))
    lines.append(f"headline: {m.headline}")
    lines += [f"- {f}" for f in facts]
    return "\n".join(lines), names


def build_context(
    match: ProcessedMatch, *, min_importance: float = 0.0, target: str | None = None, exclude_types: frozenset[str] = frozenset()
) -> Context:
    """Summary plus the moments at or above `min_importance` (the target is always included).

    `exclude_types` hides whole moment types from the model, e.g. the shootout, which is written from the kick list.
    """
    shown = [m for m in match.moments if (m.importance >= min_importance or m.id == target) and m.type not in exclude_types]
    summary_text = summary_block(match.summary)
    texts, names = {}, {}
    for m in shown:
        texts[m.id], names[m.id] = moment_block(m, match.meta, target=m.id == target)
    body = "\n\n".join(texts[m.id] for m in shown)
    return Context(
        text=f"{summary_text}\n\nMOMENTS (chronological)\n\n{body}",
        summary_text=summary_text,
        moment_text=texts,
        moment_names=names,
        shown_ids=[m.id for m in shown],
        moments={m.id: m for m in shown},
    )
