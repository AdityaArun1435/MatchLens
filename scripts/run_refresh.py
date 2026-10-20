"""Run one refresh tick locally against your Supabase project. Reads .env.local if present.

    python scripts/run_refresh.py
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"'))


if __name__ == "__main__":
    load_env(ROOT / ".env.local")
    from matchlens.live.run import run_once

    print(json.dumps(run_once(), indent=2))
