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


@lru_cache(maxsize=1)
def _hash_cached(_: tuple) -> str:
    digest = hashlib.sha256()
    for path in sorted(config.PROMPTS_DIR.glob("*.md")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def prompt_hash() -> str:
    """Hash of every prompt file; changing any prompt invalidates cached outputs."""
    stamp = tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in sorted(config.PROMPTS_DIR.glob("*.md")))
    return _hash_cached(stamp)
