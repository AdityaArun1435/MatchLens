"""Checks on model output: citations, numbers and player names. Pure functions, no LLM."""
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from .. import config
from ..service import ProcessedMatch
from .context import Context

# ---- text helpers ------------------------------------------------------------------------------
_ID = re.compile(r"\[?\bm_\d+\b\]?")
_PARTICLES = {"de", "di", "da", "dos", "del", "van", "von", "der", "den", "la", "le", "el", "al", "bin", "mac", "ter"}


def strip_ids(text: str) -> tuple[str, bool]:
    """Remove moment ids the model wrote into the text (they belong in `cites`)."""
    cleaned = re.sub(r"\s{2,}", " ", _ID.sub("", text)).strip()
    cleaned = re.sub(r"\s+([.,;:!?])", r"\1", cleaned)
    return cleaned, cleaned != text.strip()


def fold(text: str) -> str:
    """Lower-case and remove accents, one output character per input character."""
    out = []
    for ch in text:
        base = "".join(c for c in unicodedata.normalize("NFD", ch) if not unicodedata.combining(c))
        out.append(base.lower() if len(base) == 1 else ch.lower())
    return "".join(out)


# ---- numbers -----------------------------------------------------------------------------------
_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
_COUNTED = r"(?:goals?|shots?|passes|minutes?|chances?|kicks?|penalties|substitutions?|players?|cards?|times|points?|saves?|efforts?)"
_WORD_COUNT = re.compile(rf"\b({'|'.join(_NUMBER_WORDS)})\b(?=[\s-]+{_COUNTED}\b)", re.I)
_WORD_MULT = {"twice": 2, "thrice": 3, "brace": 2, "hat-trick": 3, "hattrick": 3}
_WORD_MULT_RE = re.compile(r"\b(twice|thrice|brace|hat-trick|hattrick)\b", re.I)
_HALF = re.compile(r"\b[12](?:st|nd)[\s-]half\b", re.I)
_TOKEN = re.compile(
    r"(?P<stop>\d+\s?\+\s?\d+)|(?P<score>\d+\s?[-–—:]\s?\d+)|(?P<dec>\d+\.\d+)|(?P<int>\d+)(?:st|nd|rd|th)?",
)


def numbers_in(text: str) -> set[tuple]:
    """Canonical number tokens: ('m',90,3) stoppage minute, ('s',2,2) score, ('d',Decimal) decimal, ('i',n) integer."""
    text = _ID.sub(" ", text)
    text = _HALF.sub(" ", text)
    found: set[tuple] = set()
    for m in _TOKEN.finditer(text):
        if m.group("stop"):
            a, b = re.split(r"\s?\+\s?", m.group("stop"))
            found.add(("m", int(a), int(b)))
        elif m.group("score"):
            a, b = re.split(r"\s?[-–—:]\s?", m.group("score"))
            found.add(("s", int(a), int(b)))
        elif m.group("dec"):
            found.add(("d", Decimal(m.group("dec")).normalize()))
        else:
            found.add(("i", int(m.group("int"))))
    for m in _WORD_COUNT.finditer(text):
        found.add(("i", _NUMBER_WORDS[m.group(1).lower()]))
    for m in _WORD_MULT_RE.finditer(text):
        found.add(("i", _WORD_MULT[m.group(1).lower()]))
    return found


def allowed_numbers(texts: list[str]) -> set[tuple]:
    allowed: set[tuple] = set()
    for t in texts:
        allowed |= numbers_in(t)
    # a bare integer such as "3 goals" may come from a score like 3-2
    allowed |= {("i", n) for tok in allowed if tok[0] == "s" for n in tok[1:]}
    return allowed


def _show(tok: tuple) -> str:
    return {"m": lambda t: f"{t[1]}+{t[2]}'", "s": lambda t: f"{t[1]}-{t[2]}", "d": lambda t: f"{t[1]:f}", "i": lambda t: str(t[1])}[tok[0]](tok)


# ---- names -------------------------------------------------------------------------------------
@dataclass(frozen=True)
class RosterPlayer:
    display: str
    full: str


_WORD = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*")


def _variants(p: RosterPlayer, blocked: set[str]) -> set[str]:
    """Folded strings that count as a mention of this player."""
    out: set[str] = set()
    for name in (p.display, p.full):
        tokens = name.split()
        out.add(fold(name))
        if len(tokens) > 2:
            surname = fold(" ".join(tokens[1:]))  # surname phrase, e.g. "Mac Allister"
            out.update({surname, surname.replace(" ", "")})
        elif len(tokens) == 2:
            out.add(fold(tokens[1]))
        for t in tokens:
            f = fold(t)
            if len(f) >= 4 and f not in _PARTICLES:
                out.add(f)
    return {v for v in out if v and v not in blocked}


class Validator:
    def __init__(self, match: ProcessedMatch, ctx: Context) -> None:
        self.match, self.ctx = match, ctx
        meta = match.meta
        self.teams = {meta.home_team, meta.away_team}
        vocab_text = " ".join([*self.teams, meta.competition, meta.season, meta.stage, meta.stadium or ""])
        self.known_words = {w for w in _WORD.findall(vocab_text)} | set(config.NAME_CHECK_ALLOWED_WORDS)
        self.known_folded = {fold(w) for w in self.known_words}
        self.roster = self._roster(match)
        blocked = {fold(w) for w in self.known_words}
        self.variants = {p: _variants(p, blocked) for p in self.roster}
        self.roster_tokens = {fold(t) for v in self.variants.values() for s in v for t in s.split()}

    @staticmethod
    def _roster(match: ProcessedMatch) -> list[RosterPlayer]:
        seen: dict[str, RosterPlayer] = {}
        for e in match.events:
            if e.player:
                seen.setdefault(e.player, RosterPlayer(e.player_display_name or e.player, e.player))
            rep = e.detail.get("replacement")
            if rep:
                seen.setdefault(rep, RosterPlayer(e.detail.get("replacement_display_name") or rep, rep))
        return list(seen.values())

    # ---- individual checks --------------------------------------------------------------------
    def check_cites(self, cites: list[str], must_include: str | None = None) -> list[str]:
        errors = []
        if not cites:
            errors.append("has no citations; every paragraph must cite at least one moment id")
        for c in dict.fromkeys(cites):
            if c not in self.match_ids():
                errors.append(f"cites unknown moment id '{c}'")
            elif c not in self.ctx.moment_text:
                errors.append(f"cites {c}, which exists but was not part of the data you were given")
        if must_include and must_include not in cites:
            errors.append(f"must cite {must_include}")
        return errors

    def match_ids(self) -> set[str]:
        return {m.id for m in self.match.moments}

    def check_numbers(self, text: str, cites: list[str]) -> list[str]:
        texts = [self.ctx.summary_text, *(self.ctx.moment_text[c] for c in cites if c in self.ctx.moment_text)]
        allowed = allowed_numbers(texts)
        bad = sorted(numbers_in(text) - allowed, key=str)
        return [f"number {_show(t)} does not appear in the cited moments or the match summary" for t in bad]

    def _allowed_names(self, cites: list[str]) -> set[str]:
        names: set[str] = set()
        for c in cites:
            names |= self.ctx.moment_names.get(c, set())
        return names

    def check_names(self, text: str, cites: list[str]) -> list[str]:
        allowed = self._allowed_names(cites)
        folded = fold(text)
        errors: list[str] = []
        reported: set[str] = set()
        # 1. mentions of players who exist in the match but are not named in the cited moments
        allowed_variants = set().union(*(self.variants[p] for p in self.roster if p.display in allowed), set())
        hits: list[tuple[int, int, str]] = []  # (start, end, player display)
        for player, variants in self.variants.items():
            if player.display in allowed:
                continue
            for v in variants - allowed_variants:  # a surname shared with a cited player is not a violation
                for hit in re.finditer(rf"(?<![^\W\d_]){re.escape(v)}(?![^\W\d_])", folded):
                    if " " in v or text[hit.start()].isupper():
                        hits.append((hit.start(), hit.end(), player.display))
        taken: list[tuple[int, int]] = []
        for start, end, display in sorted(hits, key=lambda h: (-(h[1] - h[0]), h[0])):  # longest span first
            if any(start < e and s < end for s, e in taken):
                continue
            taken.append((start, end))
            errors.append(f"mentions {text[start:end]!r} ({display}), who is not named in the cited moments")
        # 2. capitalised names that are not on the roster at all
        for word, at_sentence_start in self._capitalised_words(text):
            f = fold(word)
            if f in self.known_folded or f in self.roster_tokens or at_sentence_start:
                continue
            errors.append(f"mentions {word!r}, which is not a player or team in the data")
        return errors

    @staticmethod
    def _capitalised_words(text: str):
        """Capitalised words (possessive 's removed) with a flag for 'first word of a sentence'."""
        for m in _WORD.finditer(text):
            word = re.sub(r"['’]s$", "", m.group())
            if not word[0].isupper() or word.lower() in _PARTICLES:
                continue
            before = text[: m.start()].rstrip(" \"'“‘(")
            yield word, (not before) or before[-1] in ".!?:\n"

    # ---- composite ----------------------------------------------------------------------------
    def check_text(self, text: str, cites: list[str]) -> list[str]:
        errors = []
        if len(text.strip()) < 15:
            errors.append("text is empty or too short")
        errors += self.check_numbers(text, cites)
        errors += self.check_names(text, cites)
        return errors

    def check_paragraph(self, text: str, cites: list[str], must_include: str | None = None) -> list[str]:
        return self.check_cites(cites, must_include) + self.check_text(text, cites)

    def check_title(self, title: str) -> list[str]:
        """Titles may use team names and summary numbers only; no player names."""
        errors = []
        if not title.strip():
            return ["title is empty"]
        allowed = allowed_numbers([self.ctx.summary_text])
        errors += [f"title number {_show(t)} is not in the match summary" for t in sorted(numbers_in(title) - allowed, key=str)]
        errors += self.check_names(title, [])
        return errors
