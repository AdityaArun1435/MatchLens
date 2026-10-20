"""Prompt files: loading, rendering and a hash used in cache keys."""
import hashlib
from functools import lru_cache

from .. import config


def load(name: str) -> str:
    return (config.PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def render(template: str, **values: str) -> str:
    """Replace {{name}} placeholders (plain replace, so JSON braces in values are safe)."""
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def match_vars(match) -> dict[str, str]:
    """Placeholder values taken from the match, so no prompt file carries a literal score or team name."""
    s, meta = match.summary, match.meta
    score = f"{s.final_score[0]}-{s.final_score[1]}"
    phrase = f"the match ended {score}" + (" after extra time" if s.went_to_extra_time else "")
    return {
        "home": meta.home_team,
        "away": meta.away_team,
        "final_score": score,
        "result_phrase": phrase,
        "title_form": f"{meta.home_team} {score} {meta.away_team}",
    }


def load_filled(name: str, match) -> str:
    """Load a prompt file and fill the match placeholders."""
    return render(load(name), **match_vars(match))


# Prompt files only the recap uses: editing them must not invalidate cached explanations.
_RECAP_ONLY = ("recap_task.md", "length_short.md", "length_medium.md")


def _files(kind: str):
    return [p for p in sorted(config.PROMPTS_DIR.glob("*.md")) if not (kind == "explain" and p.name in _RECAP_ONLY)]


@lru_cache(maxsize=4)
def _hash_cached(kind: str, _: tuple) -> str:
    digest = hashlib.sha256()
    for path in _files(kind):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def prompt_hash(kind: str = "recap") -> str:
    """Hash of the prompt files a kind of output depends on; changing one of them invalidates those cached outputs."""
    stamp = tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in _files(kind))
    return _hash_cached(kind, stamp)
