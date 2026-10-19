"""Wording rules on model output that need no LLM: score-state verbs, shootout claims, banned phrases, opinion words.

Each public function takes plain text (one paragraph) and returns a list of error strings, empty when the text is fine.
The checks are deliberately lenient when a sentence is ambiguous (no team or minute named) and strict when it is
explicit, so a false alarm costs a retry but a real mistake never passes silently.
"""
import re

from .. import config
from ..models import Moment
from .text_utils import fold

_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Þ])")


def sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE.split(text.strip()) if s]


_HYPHEN = r"[-\s]?"


def _word(phrase: str) -> str:
    """Regex for a whole word or phrase on folded text; a hyphen also matches a space or nothing."""
    body = _HYPHEN.join(re.escape(part) for part in phrase.split("-"))
    return rf"(?<![^\W\d_]){body}(?![^\W\d_])"


# ---- rule 3 and 4: banned phrases and opinion words ----------------------------------------------------
def _find_listed(text: str, words: tuple[str, ...], exempt: tuple[str, ...] = ()) -> list[str]:
    folded = fold(text)
    for phrase in exempt:  # e.g. "Champions League" inside the competition name is data, not outside knowledge
        if phrase:
            folded = folded.replace(fold(phrase), " " * len(phrase))
    return [w for w in words if re.search(_word(fold(w)), folded)]


def check_banned_phrases(text: str, language: str, exempt: tuple[str, ...] = ()) -> list[str]:
    words = config.BANNED_PHRASES.get(language, ())
    return [
        f"uses the banned word {w!r}: it is outside knowledge or not in the data, so leave it out"
        for w in _find_listed(text, words, exempt)
    ]


def check_opinion_words(text: str, audience: str, language: str) -> list[str]:
    if audience in config.OPINION_ALLOWED_AUDIENCES:
        return []
    words = config.OPINION_WORDS.get(language, ())
    return [
        f"uses the opinion word {w!r}: describe the goal or shot by its facts only (kind, scorer, assist, minute)"
        for w in _find_listed(text, words)
    ]


# ---- rule 1: score-state verbs ---------------------------------------------------------------------------
_LEAD = re.compile(
    r"\b(?:took|take|takes|taking|regained|regains|retook|retakes)\s+the\s+lead\b|\bwent\s+(?:back\s+)?(?:ahead|in\s+front)\b|\bgoes\s+ahead\b",
    re.I,
)
_LEVEL = re.compile(r"\bequali[sz](?:e[sd]?|ing|er)\b|\blevel(?:l?ed|l?ing)\b", re.I)
_WON = re.compile(r"\bwon\b(?!\s+(?:a|an|the\s+ball|possession|back|corners?|free)\b)", re.I)
_DREW = re.compile(r"\bdrew\b|\ba\s+draw\b", re.I)
_SCORE = re.compile(r"(?<![\d:])(?<!\d\.)(\d+)\s?[-–]\s?(\d+)(?!\d)(?!\.\d)")
_MINUTE = re.compile(r"(?<![\d:.])(\d{1,3})(?:\s?\+\s?(\d{1,2}))?(?:st|nd|rd|th)?\s?(?:'|’|′|\s?minutes?\b)|\bminute\s+(\d{1,3})\b", re.I)
_LABEL = re.compile(r"(\d+)(?:\+(\d+))?")


def _effect(m: Moment) -> str:
    """What the goal did for the side that scored it: lead, level, extended or reduced."""
    (bh, ba), (ah, aa) = m.score_before, m.score_after
    own, opp = (0, 1) if ah > bh else (1, 0)
    b, a = (bh, ba), (ah, aa)
    if a[own] == a[opp]:
        return "levelled the score"
    if b[own] <= b[opp] and a[own] > a[opp]:
        return "put the scoring team ahead"
    return "extended the lead" if b[own] > b[opp] else "reduced the deficit"


def _scorer_team(m: Moment, home: str, away: str) -> str:
    return home if m.score_after[0] > m.score_before[0] else away


def _label_of(m: Moment) -> tuple[int, int]:
    hit = _LABEL.match(m.clock_label)
    return (int(hit.group(1)), int(hit.group(2) or 0)) if hit else (-1, 0)


def _minutes_in(sentence: str) -> set[tuple[int, int]]:
    out = set()
    for m in _MINUTE.finditer(sentence):
        out.add((int(m.group(3)), 0) if m.group(3) else (int(m.group(1)), int(m.group(2) or 0)))
    return out


def team_near(sentence: str, pos: int, teams: list[str]) -> str | None:
    """The team named closest before `pos`. A team named only after the verb is not the subject, so it is ignored."""
    best: tuple[int, str] | None = None
    for team in teams:
        for m in re.finditer(rf"(?<![^\W\d_]){re.escape(team)}(?![^\W\d_])", sentence):
            if m.start() < pos and (best is None or m.start() > best[0]):
                best = (m.start(), team)
    return best[1] if best else None


def cited_goals(cites: list[str], moments: dict[str, Moment], all_moments: list[Moment]) -> list[Moment]:
    """Goal moments among the cites, plus the goals behind any cited quick-response moment."""
    out: list[Moment] = []
    for c in cites:
        m = moments.get(c)
        if m is None:
            continue
        if m.type == "goal":
            out.append(m)
        elif m.type == "quick_response":
            out += [g for g in all_moments if g.type == "goal" and g.evidence[-1] in m.evidence]
    return list({g.id: g for g in out}.values())


def _goal_lines(goals: list[Moment]) -> str:
    return "; ".join(f"{g.clock_label} {g.headline} ({_effect(g)})" for g in goals) or "no goal moment is cited"


def _check_lead_or_level(sentence, hit, kind, goals, teams, home, away) -> list[str]:
    wanted = "put the scoring team ahead" if kind == "lead" else "levelled the score"
    pool = goals
    minutes = _minutes_in(sentence)
    if minutes and any(_label_of(g) in minutes for g in goals):
        pool = [g for g in goals if _label_of(g) in minutes]
    team = team_near(sentence, hit.start(), teams)
    if team:
        pool = [g for g in pool if _scorer_team(g, home, away) == team]
    if any(_effect(g) == wanted for g in pool):
        return []
    who = f"{team} " if team else ""
    return [f"says {who}'{hit.group(0)}' but the cited goal(s) show: {_goal_lines(pool or goals)}. Cite the goal that did it or reword"]


def _check_won(sentence, hit, teams, home, away, summary) -> list[str]:
    passive = re.match(r"\s+by\b", sentence[hit.end():])  # "won by Argentina": the winner follows the verb
    team = team_near(sentence, hit.end() if passive else hit.start(), teams)
    if passive:
        team = next((t for t in teams if re.search(rf"\bby\s+{re.escape(t)}", sentence[hit.end():])), None)
    shootout = summary.shootout
    if re.search(r"shoot-?out|penalties|\bpens\b|penalty", sentence, re.I):
        if shootout is None:
            return [f"says '{hit.group(0)}' in a penalty shootout, but there was no shootout"]
        if team and team != shootout["winner"]:
            return [f"says {team} won the shootout, but {shootout['winner']} won it"]
        return []
    if any(a == b for a, b in _scores(sentence)):
        return [f"says '{hit.group(0)}' with a level score; a level score is a draw (the shootout decides who goes through)"]
    winners = {home if h > a else away for h, a in (summary.final_score, summary.score_after_90) if h != a}
    if shootout:
        winners.add(shootout["winner"])
    if team and team not in winners:
        return [f"says {team} won, but the data does not show {team} winning"]
    return []


def _scores(sentence: str) -> list[tuple[int, int]]:
    return [(int(a), int(b)) for a, b in _SCORE.findall(sentence)]


def _check_drew(sentence, hit, summary) -> list[str]:
    scores = _scores(sentence)
    if scores:
        bad = [f"{a}-{b}" for a, b in scores if a != b]
        return [f"says '{hit.group(0)}' next to the score {bad[0]}, which is not level"] if bad else []
    if summary.final_score[0] != summary.final_score[1] and summary.score_after_90[0] != summary.score_after_90[1]:
        return [f"says '{hit.group(0)}' but the match was not level at 90 minutes or after extra time"]
    return []


def check_score_verbs(text: str, cites: list[str], moments: dict[str, Moment], all_moments: list[Moment], meta, summary) -> list[str]:
    home, away = meta.home_team, meta.away_team
    teams = [home, away]
    goals = cited_goals(cites, moments, all_moments)
    errors: list[str] = []
    for s in sentences(text):
        for pattern, kind in ((_LEAD, "lead"), (_LEVEL, "level")):
            for hit in pattern.finditer(s):
                errors += _check_lead_or_level(s, hit, kind, goals, teams, home, away)
        for hit in _WON.finditer(s):
            errors += _check_won(s, hit, teams, home, away, summary)
        for hit in _DREW.finditer(s):
            errors += _check_drew(s, hit, summary)
    return errors


# ---- rule 2: shootout claims -----------------------------------------------------------------------------
_ORDINALS = {
    "first": 1, "opening": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
    "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5, "6th": 6, "7th": 7, "8th": 8,
}
_KICK_NOUN = r"(?:kick|kicks|penalty|penalties|spot-?kick|attempt|taker|effort)"
_ORDER = re.compile(
    rf"\b(?:(?P<w>first|opening|second|third|fourth|fifth|sixth|seventh|eighth|1st|2nd|3rd|4th|5th|6th|7th|8th|last|final)\s+(?:(?!(?:one|two|three|four|five|six|seven|eight|\d+)\b)\w+\s+)?(?={_KICK_NOUN}\b)"
    r"|(?P<w2>first|second|third|fourth|fifth|sixth|seventh|eighth)\b(?!\s+(?:half|goal|minute|minutes|time|leg|period|yellow|card|booking|assist|chance|shot|\d))"
    r"|kick\s+(?P<n>[1-9]))",
    re.I,
)
_SHOOTOUT_WORDS = re.compile(r"shoot-?out|penalties|\bpens\b|\bkicks?\b|spot-?kick", re.I)
_SCORED = re.compile(r"\b(?:scor(?:ed|es|ing)|converted|converts|converting|netted|nets|put\s+away|slotted)\b", re.I)
_NOT_SCORED = re.compile(
    r"\b(?:saved|saves|saving|missed|misses|missing|failed|fails|off\s+target|hit\s+the\s+(?:post|bar|crossbar)|over\s+the\s+bar|blazed|skied)\b",
    re.I,
)
_CLAUSE = re.compile(r";|\bwhile\b|\bwhereas\b|\bbut\b", re.I)


def kick_table(kicks: list[dict]) -> list[tuple[int, str, str, bool]]:
    """(number, team, taker display name, scored) in order, from the shootout moment's stats."""
    return [(k["order"], k["team"], k["player"], bool(k["scored"])) for k in kicks]


def _taker_mentions(clause: str, takers: dict[str, set[str]]) -> list[tuple[int, str]]:
    """(position, taker name) for each taker named in the clause, longest variant first, no overlaps."""
    folded = fold(clause)
    spans: list[tuple[int, int, str]] = []
    for name, variants in takers.items():
        for v in variants:
            for m in re.finditer(rf"(?<![^\W\d_]){re.escape(v)}(?![^\W\d_])", folded):
                spans.append((m.start(), m.end(), name))
    taken: list[tuple[int, int]] = []
    out = []
    for s, e, name in sorted(spans, key=lambda x: (-(x[1] - x[0]), x[0])):
        if not any(s < te and ts < e for ts, te in taken):
            taken.append((s, e))
            out.append((s, name))
    return sorted(out)


def _outcomes(clause: str) -> list[tuple[int, bool]]:
    found = [(m.start(), True) for m in _SCORED.finditer(clause)] + [(m.start(), False) for m in _NOT_SCORED.finditer(clause)]
    return sorted(found)


def _outcome_for_each(mentions: list[tuple[int, str]], outcomes: list[tuple[int, bool]]) -> list[bool | None]:
    """Pair each taker with the outcome word after it (before the next taker), else the next taker's, else the one before."""
    result: list[bool | None] = [None] * len(mentions)
    for i in range(len(mentions) - 1, -1, -1):
        pos = mentions[i][0]
        nxt = mentions[i + 1][0] if i + 1 < len(mentions) else 10**9
        after = [o for o in outcomes if pos < o[0] < nxt]
        if after:
            result[i] = after[0][1]
        elif i + 1 < len(mentions) and result[i + 1] is not None:
            result[i] = result[i + 1]
        else:
            before = [o for o in outcomes if o[0] < pos]
            result[i] = before[-1][1] if before else None
    return result


def _ordinal_value(token: str, n_kicks: int) -> int:
    t = token.lower()
    return n_kicks if t in ("last", "final") else _ORDINALS[t]


def _team_ordinals(clause: str, teams: list[str]) -> list[tuple[int, int, str, int | None]]:
    """"France's third penalty" -> (start, end, team, 3). None as the number means the team's last kick."""
    names = "|".join(re.escape(x) for x in teams)
    pattern = re.compile(
        rf"(?P<team>{names})['’]s\s+(?P<w>first|second|third|fourth|fifth|last|final)\s+(?:\w+\s+)?{_KICK_NOUN}\b", re.I
    )
    out = []
    for m in pattern.finditer(clause):
        word = m.group("w").lower()
        team = next(x for x in teams if x.lower() == m.group("team").lower())
        out.append((m.start(), m.end(), team, None if word in ("last", "final") else _ORDINALS[word]))
    return out


def _check_team_ordinal(mentions, kicks, claim) -> list[str]:
    start, _, team, number = claim
    own = [k for k in kicks if k[1] == team]
    if not own or (number is not None and number > len(own)):
        return [f"refers to {team}'s kick number {number}, but {team} took {len(own)} kicks"]
    order, _, taker, _ = own[-1] if number is None else own[number - 1]
    before = [m for m in mentions if m[0] < start]
    near = before[-1] if before else (mentions[0] if mentions else None)
    if near is not None and near[1] != taker:
        return [f"says {near[1]} took {team}'s kick number {number or len(own)}, but that was {taker} (kick {order} of the shootout)"]
    return []


def _check_order(clause, mentions, kicks, teams, claim_pos, number) -> list[str]:
    if number > len(kicks):
        return [f"refers to kick {number}, but the shootout had {len(kicks)} kicks"]
    _, team, taker, _scored = kicks[number - 1]
    before = [m for m in mentions if m[0] < claim_pos]  # "Messi scored the first penalty": the subject comes first
    near_taker = before[-1] if before else (mentions[0] if mentions else None)
    if near_taker is not None:
        if near_taker[1] != taker:
            actual = next((k[0] for k in kicks if k[2] == near_taker[1]), None)
            return [f"says {near_taker[1]} took kick {number}, but kick {number} was {taker} ({team}); {near_taker[1]} took kick {actual}"]
        return []
    named = team_near(clause, claim_pos, teams)
    if named and named != team:
        return [f"says {named} took kick {number}, but kick {number} was taken by {team} ({taker})"]
    return []


def check_shootout_claims(text: str, cites: list[str], moments: dict[str, Moment], variants: dict[str, set[str]], meta) -> list[str]:
    """`variants` maps each shootout taker's name to the folded strings that count as a mention of them."""
    shootout = next((m for m in moments.values() if m.type == "penalty_shootout"), None)
    if shootout is None:
        return []
    kicks = kick_table(shootout.stats["kicks"])
    takers = {name: variants[name] for _, _, name, _ in kicks if name in variants}
    if shootout.id not in cites:
        return []
    only_shootout = set(cites) == {shootout.id}
    teams = [meta.home_team, meta.away_team]
    errors: list[str] = []
    for s in sentences(text):
        if not (only_shootout or _SHOOTOUT_WORDS.search(s)):
            continue
        for clause_match in _split_clauses(s):
            clause, offset = clause_match
            mentions = _taker_mentions(clause, takers)
            errors += _check_taker_outcomes(mentions, clause, kicks)
            claims = _team_ordinals(clause, teams)
            for claim in claims:
                errors += _check_team_ordinal(mentions, kicks, claim)
            for hit in _ORDER.finditer(clause):
                if any(c[0] <= hit.start() < c[1] for c in claims):
                    continue  # already checked as "<team>'s Nth kick"
                number = _order_number(hit, len(kicks))
                errors += _check_order(clause, mentions, kicks, teams, hit.start(), number)
    return list(dict.fromkeys(errors))


def _split_clauses(sentence: str) -> list[tuple[str, int]]:
    out, last = [], 0
    for m in _CLAUSE.finditer(sentence):
        out.append((sentence[last : m.start()], last))
        last = m.end()
    out.append((sentence[last:], last))
    return out


def _order_number(hit: re.Match, n_kicks: int) -> int:
    if hit.group("n"):
        return int(hit.group("n"))
    return _ordinal_value(hit.group("w") or hit.group("w2"), n_kicks)


def _check_taker_outcomes(mentions, clause, kicks) -> list[str]:
    errors = []
    outcomes = _outcome_for_each(mentions, _outcomes(clause))
    by_name = {k[2]: k for k in kicks}
    for (_, name), claimed in zip(mentions, outcomes):
        if claimed is None:
            continue
        number, team, _, scored = by_name[name]
        if claimed != scored:
            said, was = ("scored", "was saved or missed") if claimed else ("missed or was saved", "scored")
            errors.append(f"says {name} {said} in the shootout, but kick {number} ({team}, {name}) {was}")
    return errors
