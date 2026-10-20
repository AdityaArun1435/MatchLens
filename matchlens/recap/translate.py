"""Hindi and Tamil: translate an already validated English recap or explanation, one unit at a time, then check it.

Nothing is generated directly in Hindi or Tamil. Each paragraph (and the title) goes to the model on its own with the
spellings of the names it contains. The translation is accepted only if it keeps exactly the English numbers (as Western
digits), uses the mapped spellings for the English names, is written in the right script, and passes the banned-phrase
and opinion lists for its language. One retry with the errors; after that the paragraph is shown in English with a note.
Nothing is dropped.
"""
import re
import time
import unicodedata

from .. import config
from ..llm import LLMError, LLMProvider, LLMUnavailable
from ..service import ProcessedMatch
from . import glossary, prompts
from .context import build_context
from .models import (
    MomentExplanation,
    Recap,
    RecapParagraph,
    TranslationReport,
    UnitTranslation,
    translation_schema,
)
from .names_i18n import NameMap, ensure_names
from .rules import check_banned_phrases, check_opinion_words
from .text_utils import fold
from .validate import _NUMBER_WORDS, _WORD_COUNT, _WORD_MULT_RE, Validator, _show, allowed_numbers, numbers_in, strip_ids

MAX_ATTEMPTS = 2  # first try + one retry
_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z'’]+")


# ---- text helpers ------------------------------------------------------------------------------------
def normalise_digits(text: str) -> tuple[str, int]:
    """Replace any non-Western digit (Devanagari, Tamil, ...) by 0-9. Returns the text and how many were replaced."""
    out, changed = [], 0
    for ch in text:
        if ch.isdigit() and not ("0" <= ch <= "9"):
            out.append(str(unicodedata.digit(ch)))
            changed += 1
        else:
            out.append(ch)
    return "".join(out), changed


def digitise_number_words(text: str) -> str:
    """"two goals" -> "2 goals", "twice" -> "2 times". Applied to the text the model sees, never to the check: the
    model keeps writing number words in Hindi and Tamil, which the numbers check cannot read, so it gets digits to copy."""
    text = _WORD_COUNT.sub(lambda m: str(_NUMBER_WORDS[m.group(1).lower()]), text)
    text = re.sub(r"(?:\ba\s+)?\bbrace\b", "2 goals", text, flags=re.I)
    text = re.sub(r"(?:\ba\s+)?\bhat-?trick\b", "3 goals", text, flags=re.I)
    return _WORD_MULT_RE.sub(lambda m: "2 times" if m.group(1).lower() == "twice" else "3 times", text)


_ORDINAL_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}
_WORD_NUMBER = re.compile(r"\b(" + "|".join([*_NUMBER_WORDS, *_ORDINAL_WORDS, "twice", "thrice", "brace"]) + r")\b", re.I)


def word_numbers(text: str) -> set[tuple]:
    """Integers the English wrote as words anywhere (two, second, twice): a digit for these is not an invented number."""
    values = {**_NUMBER_WORDS, **_ORDINAL_WORDS, "twice": 2, "thrice": 3, "brace": 2}
    return {("i", values[m.group(1).lower()]) for m in _WORD_NUMBER.finditer(text)}


def script_share(text: str, language: str) -> float:
    """Share of the letters (and combining marks) in `text` that belong to the language's script."""
    lo, hi = config.SCRIPT_RANGES[language]
    marks = [ch for ch in text if ch.isalpha() or unicodedata.category(ch).startswith("M")]
    return sum(1 for ch in marks if lo <= ch <= hi) / len(marks) if marks else 0.0


def _native_forms(native: str, display: str = "", spaced: bool = False) -> set[str]:
    """Strings that count as a mention of a mapped name.

    The English wrote one word ("Messi"): the full name or any word of it with 3 or more characters. The English wrote
    several ("Lionel Messi", "Di María"): the full name, or the name without its first word (the surname phrase), so
    "Di María" may not shrink to "María". If the map and the English disagree on the number of words, be lenient.
    """
    native = unicodedata.normalize("NFC", native)
    words = native.split()
    if spaced and len(words) == len(display.split()) and len(words) > 1:
        return {native, " ".join(words[1:])}
    return {native} | {w for w in words if len(w) >= 3}


# ---- the checker ---------------------------------------------------------------------------------------
class TranslationChecker:
    def __init__(self, match: ProcessedMatch, language: str, audience: str, name_map: NameMap) -> None:
        self.language, self.audience, self.names = language, audience, name_map
        self.teams = [match.meta.home_team, match.meta.away_team]
        self._variants = Validator(match, build_context(match, min_importance=0.0)).variants

    def expected_names(self, english: str) -> list[tuple[list[str], bool]]:
        """Names mentioned in the English text as (display names, spaced): a shared surname is one group, and `spaced` is
        True when the English wrote more than one word ("Di María", "Lionel Messi"), so the translation must too."""
        folded = fold(english)
        spans: list[tuple[int, int, frozenset[str]]] = []
        holders: dict[str, set[str]] = {}
        for player, variants in self._variants.items():
            if player.display not in self.names.names:
                continue
            for v in variants:
                holders.setdefault(v, set()).add(player.display)
        for v, who in holders.items():
            for m in re.finditer(rf"(?<![^\W\d_]){re.escape(v)}(?![^\W\d_])", folded):
                spans.append((m.start(), m.end(), frozenset(who)))
        taken: list[tuple[int, int]] = []
        groups: list[tuple[list[str], bool]] = []
        for s, e, who in sorted(spans, key=lambda x: (-(x[1] - x[0]), x[0])):
            if not any(s < te and ts < e for ts, te in taken):
                taken.append((s, e))
                groups.append((sorted(who), " " in folded[s:e]))
        for team in self.teams:
            if re.search(rf"(?<![^\W\d_]){re.escape(team)}(?![^\W\d_])", english):
                groups.append(([team], False))
        unique = {(tuple(g), spaced): (g, spaced) for g, spaced in groups}
        return list(unique.values())

    def missing_spellings(self, english: str) -> list[str]:
        """English names in the text that have no entry in the name map (the model cannot be told how to write them)."""
        folded = fold(english)
        missing = []
        for player, variants in self._variants.items():
            if player.display in self.names.names:
                continue
            if any(re.search(rf"(?<![^\W\d_]){re.escape(v)}(?![^\W\d_])", folded) for v in variants if " " in v):
                missing.append(player.display)
        missing += [
            t for t in self.teams
            if t not in self.names.names and re.search(rf"(?<![^\W\d_]){re.escape(t)}(?![^\W\d_])", english)
        ]
        return list(dict.fromkeys(missing))

    def check(self, english: str, translated: str) -> list[str]:
        errors: list[str] = []
        text = unicodedata.normalize("NFC", translated)
        if len(text.strip()) < 3:
            return ["the translation is empty"]
        if script_share(text, self.language) < config.SCRIPT_MIN_SHARE:
            errors.append(f"is not written in {config.LANGUAGE_LABELS[self.language]} script")
        errors += self._check_numbers(english, text)
        errors += self._check_names(english, text)
        errors += self._check_latin(text)
        errors += glossary.check_terms(english, text, self.language)
        errors += check_banned_phrases(text, self.language)
        errors += check_opinion_words(text, self.audience, self.language)
        return errors

    @staticmethod
    def _check_numbers(english: str, text: str) -> list[str]:
        """Every English number must be in the translation, and the translation may add none, except a digit for a
        number word or ordinal the English spelt out ("second" -> 2), which the English check cannot count."""
        want, got = numbers_in(english), numbers_in(text)
        allowed = allowed_numbers([english]) | word_numbers(english)
        errors = [
            f"number {_show(t)} from the English is missing: write every number as Western digits, exactly as in the English, never in words"
            for t in sorted(want - got, key=str)
        ]
        errors += [f"number {_show(t)} is not in the English text" for t in sorted(got - allowed, key=str)]
        return errors

    def _check_names(self, english: str, text: str) -> list[str]:
        errors: list[str] = []
        expected_displays: set[str] = set()
        for group, spaced in self.expected_names(english):
            expected_displays.update(group)
            natives = [self.names.names[d] for d in group if d in self.names.names]
            if not natives:
                errors.append(f"no spelling for {' / '.join(group)} in the name map")
                continue
            forms = {f for d in group if d in self.names.names for f in _native_forms(self.names.names[d], d, spaced)}
            if not any(f in text for f in forms):
                errors.append(f"must write {' / '.join(group)} as {' or '.join(natives)}")
        for display, native in self.names.names.items():
            if display not in expected_displays and unicodedata.normalize("NFC", native) in text:
                errors.append(f"mentions {native} ({display}), who is not in the English text")
        return errors

    @staticmethod
    def _check_latin(text: str) -> list[str]:
        bad = [
            w for w in _LATIN_WORD.findall(text)
            if w not in config.TRANSLATION_LATIN_ALLOWED and not w.isupper() and not re.fullmatch(r"m_\d+", w)
        ]
        return [f"leaves {w!r} in Latin letters" for w in dict.fromkeys(bad)]

    def glossary(self, english: str) -> str:
        lines = []
        for group, _spaced in self.expected_names(english):
            for display in group:
                native = self.names.names.get(display)
                if native:
                    words, nwords = display.split(), native.split()
                    if len(words) > 1 and len(words) == len(nwords):  # also offer the name without its first word: "Di María"
                        lines.append(f"- {display} / {' '.join(words[1:])} -> {native} / {' '.join(nwords[1:])}")
                    else:
                        lines.append(f"- {display} -> {native}")
        return "\n".join(lines) or "(no names in this text)"


# ---- one unit --------------------------------------------------------------------------------------------
def _retry_prompt(user: str, errors: list[str]) -> str:
    listing = "\n".join(f"- {e}" for e in errors)
    return user + "\n\n" + prompts.render(prompts.load("translate_retry"), errors=listing)


def translate_unit(
    provider: LLMProvider, checker: TranslationChecker, unit: str, kind: str, english: str
) -> tuple[str | None, UnitTranslation]:
    """Translate one piece of text. Returns (translation or None, what happened)."""
    lang = checker.language
    absent = checker.missing_spellings(english)
    if absent:
        err = f"no {config.LANGUAGE_LABELS[lang]} spelling for {', '.join(absent)} in data/names/{lang}.json"
        return None, UnitTranslation(unit=unit, status="english_fallback", attempts=0, errors=[err])
    system = prompts.load("translate_system")
    user = prompts.render(
        prompts.load("translate_task"),
        kind=kind, kind_upper=kind.upper(), language_name=config.LANGUAGE_LABELS[lang],
        language_instructions=prompts.load(f"language_{lang}"), glossary=checker.glossary(english),
        terms=glossary.prompt_lines(english, lang),
        source=digitise_number_words(english),
    )
    log: list[str] = []
    notes: list[str] = []
    prompt = user
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            data = provider.generate_json(system, prompt, translation_schema())
            text = str(data.get("translation", "")).strip()
            errors = []
        except LLMUnavailable:
            raise
        except LLMError as exc:
            text, errors = "", [f"the model gave no usable answer: {exc}"]
        if text:
            text, _ = strip_ids(text)
            text, changed = normalise_digits(text)
            if changed:
                notes.append(f"converted {changed} non-Western digit(s) to 0-9")
            errors = checker.check(english, text)
        if not errors:
            return text, UnitTranslation(unit=unit, status="translated", attempts=attempt, errors=log, notes=notes)
        log += [f"attempt {attempt}: {e}" for e in errors]
        prompt = _retry_prompt(user, errors)
    return None, UnitTranslation(unit=unit, status="english_fallback", attempts=MAX_ATTEMPTS, errors=log, notes=notes)


# ---- recap and explanation ---------------------------------------------------------------------------------
def translate_recap(
    match: ProcessedMatch, english: Recap, language: str, audience: str, provider: LLMProvider
) -> tuple[Recap, TranslationReport]:
    started = time.perf_counter()
    name_map, added, missing = ensure_names(match, language, provider)
    report = TranslationReport(language=language, names_added=added, names_missing=missing)
    checker = TranslationChecker(match, language, audience, name_map)

    title, unit = translate_unit(provider, checker, "title", "title", english.title)
    report.units.append(unit)
    paragraphs: list[RecapParagraph] = []
    for i, para in enumerate(english.paragraphs, start=1):
        text, unit = translate_unit(provider, checker, f"paragraph {i}", "paragraph", para.text)
        report.units.append(unit)
        if text is None:
            paragraphs.append(
                RecapParagraph(text=para.text, cites=para.cites, language="en", note=config.TRANSLATION_FALLBACK_NOTES[language])
            )
        else:
            paragraphs.append(RecapParagraph(text=text, cites=para.cites, language=language))
    report.seconds = round(time.perf_counter() - started, 2)
    return Recap(title=title or english.title, paragraphs=paragraphs), report


def translate_explanation(
    match: ProcessedMatch, english: MomentExplanation, language: str, audience: str, provider: LLMProvider
) -> tuple[MomentExplanation, TranslationReport]:
    started = time.perf_counter()
    name_map, added, missing = ensure_names(match, language, provider)
    report = TranslationReport(language=language, names_added=added, names_missing=missing)
    checker = TranslationChecker(match, language, audience, name_map)
    done: dict[str, str] = {}
    notes: list[str] = []
    for field, label in (("why_it_mattered", "why_it_mattered"), ("context", "context")):
        source = getattr(english, field)
        text, unit = translate_unit(provider, checker, label, "text", source)
        report.units.append(unit)
        done[field] = text if text is not None else source
        if text is None:
            notes.append(f"{label}: {config.TRANSLATION_FALLBACK_NOTES[language]}")
    report.seconds = round(time.perf_counter() - started, 2)
    result = english.model_copy(update={**done, "language": language, "notes": notes})
    return result, report


# ---- back-translation, for a human to judge meaning drift (never used to accept or reject) ---------------
def back_translate(text: str, language: str, provider: LLMProvider) -> str:
    system = prompts.load("back_translate_system")
    user = prompts.render(
        prompts.load("back_translate_task"), language_name=config.LANGUAGE_LABELS[language], source=text
    )
    try:
        return str(provider.generate_json(system, user, translation_schema()).get("translation", "")).strip()
    except LLMUnavailable:
        raise
    except LLMError as exc:
        return f"(back-translation failed: {exc})"
