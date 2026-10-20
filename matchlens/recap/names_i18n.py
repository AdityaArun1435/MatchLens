"""Name maps for translations: English display name -> name written in Hindi or Tamil script.

One JSON file per language in data/names/ (committed). The model fills in names that are missing, once; entries that
already exist are never touched, so a hand correction in the file always wins. Set "reviewed": true after checking a file.
"""
import json
from dataclasses import dataclass, field

from .. import config
from ..llm import LLMError, LLMProvider
from ..service import ProcessedMatch
from . import prompts
from .context import build_context
from .models import names_schema

_NOTE = "First draft written by the model. Correct any name by hand and set reviewed to true; existing entries are never overwritten."


@dataclass
class NameMap:
    language: str
    names: dict[str, str] = field(default_factory=dict)
    reviewed: bool = False

    @property
    def path(self):
        return config.NAMES_DIR / f"{self.language}.json"

    def save(self) -> None:
        config.NAMES_DIR.mkdir(parents=True, exist_ok=True)
        body = {"language": self.language, "reviewed": self.reviewed, "note": _NOTE, "names": self.names}
        self.path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_map(language: str) -> NameMap:
    path = config.NAMES_DIR / f"{language}.json"
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return NameMap(language)
    return NameMap(language, dict(body.get("names", {})), bool(body.get("reviewed", False)))


def names_in_match(match: ProcessedMatch) -> list[str]:
    """Teams and every player the moment blocks name (scorers, assists, build-up passers, shootout takers, ...)."""
    names = [match.meta.home_team, match.meta.away_team]
    for shown in build_context(match, min_importance=0.0).moment_names.values():
        names += sorted(shown)
    return list(dict.fromkeys(n for n in names if n))


def in_script(text: str, language: str) -> bool:
    """True if every letter is in the language's script (spaces, hyphens and apostrophes allowed)."""
    lo, hi = config.SCRIPT_RANGES[language]
    letters = [ch for ch in text if ch.isalpha() or ord(lo) <= ord(ch) <= ord(hi)]
    return bool(letters) and all(lo <= ch <= hi for ch in letters)


def _ask(provider: LLMProvider, language: str, wanted: list[str]) -> tuple[dict[str, str], list[str]]:
    system = prompts.load("names_system")
    user = prompts.render(
        prompts.load("names_task"),
        language_name=config.LANGUAGE_LABELS[language],
        language_instructions=prompts.load(f"language_{language}"),
        names="\n".join(f"- {n}" for n in wanted),
    )
    problems: list[str] = []
    try:
        data = provider.generate_json(system, user, names_schema())
    except LLMError as exc:
        return {}, [str(exc)]
    got: dict[str, str] = {}
    for item in data.get("names", []):
        english, native = str(item.get("english", "")).strip(), str(item.get("native", "")).strip()
        if english not in wanted:
            problems.append(f"{english!r} was not asked for")
        elif not in_script(native, language):
            problems.append(f"{english!r}: {native!r} is not written in {config.LANGUAGE_LABELS[language]} script")
        else:
            got[english] = native
    return got, problems


def ensure_names(match: ProcessedMatch, language: str, provider: LLMProvider) -> tuple[NameMap, list[str], list[str]]:
    """Load the language's map and fill in what this match needs. Returns (map, names added, names still missing)."""
    name_map = load_map(language)
    wanted = [n for n in names_in_match(match) if n not in name_map.names]
    added: list[str] = []
    for _ in range(2):  # first try and one retry for the names that came back unusable
        if not wanted:
            break
        got, _problems = _ask(provider, language, wanted)
        name_map.names.update(got)
        added += list(got)
        wanted = [n for n in wanted if n not in got]
    if added:
        name_map.save()
    return name_map, added, wanted
