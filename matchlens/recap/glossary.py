"""Football glossary for Hindi and Tamil: fixed translations of key terms, checked in every translated sentence.

data/glossary/{lang}.json holds the fixed forms (committed, edit by hand). The English patterns that say when a term is
present live here, because they are about the English text the checker reads.
"""
import json
import re
import unicodedata
from functools import lru_cache

from .. import config

# term -> regex over one English sentence (case-insensitive). Keep the keys in step with the JSON files.
PATTERNS: dict[str, str] = {
    "penalty": r"\bpenalty in (?:regular|extra) time\b",
    "penalty shootout": r"\bshoot-?out\b",
    "shootout kick": r"\bkicks?\b|\bspot-?kicks?\b",
    "goalkeeper": r"\b(?:goal)?keepers?\b",
    "save": r"\bsav(?:e|es|ed|ing)\b",
    "equaliser": r"\bequali[sz](?:e|es|ed|ing|er)\b|\blevell?(?:ed|ing)\b",
    "took the lead": r"\b(?:took|take|takes|taking) the lead\b",
    "regained the lead": r"\bregain(?:ed|s)? the lead\b|\bretook the lead\b",
    "reduced the deficit": r"\breduc(?:ed|es|ing) the deficit\b|\bpulled one back\b",
    "extra time": r"\bextra time\b",
    "stoppage time": r"\bstoppage time\b|\badded time\b",
    "substitution": r"\bsubstitut\w*",
    "big chance": r"\bbig chances?\b",
    "xG": r"\bxG\b",
    "own goal": r"\bown goals?\b",
    "red card": r"\bred cards?\b",
    "second yellow": r"\bsecond yellow\b",
    "draw": r"\bdrew\b|\bdraws?\b|\bdrawn\b",
    "won on penalties": r"\bwon\b[^.]*?\bon penalties\b",
    "momentum": r"\bmomentum\b",
}
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Þ])")


@lru_cache(maxsize=4)
def _load(language: str, stamp: float) -> dict[str, dict]:
    path = config.GLOSSARY_DIR / f"{language}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))["terms"]
    except (OSError, ValueError, KeyError):
        return {}


def load_glossary(language: str) -> dict[str, dict]:
    path = config.GLOSSARY_DIR / f"{language}.json"
    return _load(language, path.stat().st_mtime if path.exists() else 0.0)


def terms_in(english: str) -> list[str]:
    """Glossary terms the English text uses, in the order of PATTERNS."""
    return [t for t, pattern in PATTERNS.items() if re.search(pattern, english, re.I)]


def forms(entry: dict) -> list[str]:
    return [unicodedata.normalize("NFC", f) for f in [entry["use"], *entry.get("accept", [])]]


def check_terms(english: str, translated: str, language: str) -> list[str]:
    """A term present in the English must appear in one of its glossary forms in the translation."""
    glossary, text = load_glossary(language), unicodedata.normalize("NFC", translated)
    errors = []
    for term in terms_in(english):
        entry = glossary.get(term)
        if entry and not any(f in text for f in forms(entry)):
            errors.append(f"must translate '{term}' as {entry['use']}")
    return errors


def prompt_lines(english: str, language: str) -> str:
    glossary = load_glossary(language)
    lines = [f"- {t} -> {glossary[t]['use']}" for t in terms_in(english) if t in glossary]
    return "\n".join(lines) or "(none in this text)"
