"""Cache of generated outputs under data/generated/, keyed by everything that changes the output."""
import hashlib
import json
import re
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .. import config
from . import prompts

PIPELINE_VERSION = 4  # bump when validation or context logic changes in a way that alters outputs
T = TypeVar("T", bound=BaseModel)


def cache_file(kind: str, match_id: int, model: str, **parts: object) -> Path:
    key = {"v": PIPELINE_VERSION, "kind": kind, "match": match_id, "model": model, "prompts": prompts.prompt_hash("explain" if kind.startswith("explain") else "recap"), **parts}
    digest = hashlib.sha256(json.dumps(key, sort_keys=True, default=str).encode()).hexdigest()[:12]
    safe_model = re.sub(r"[^A-Za-z0-9._-]+", "_", model)  # "qwen3:8b" contains ':', illegal in Windows file names
    label = "_".join(str(v) for v in parts.values() if isinstance(v, str))
    return config.GENERATED_DIR / str(match_id) / f"{kind}_{label}_{safe_model}_{digest}.json"


def read(path: Path, model_cls: type[T]) -> T | None:
    try:
        return model_cls.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, ValidationError):
        return None


def write(path: Path, value: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.model_dump_json(indent=2), encoding="utf-8")
