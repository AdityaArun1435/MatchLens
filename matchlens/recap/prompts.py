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
