"""Download and cache the StatsBomb open data MatchLens needs into data/raw/.

Usage (PowerShell or any shell):
    python scripts/fetch_data.py
    python scripts/fetch_data.py --add 3869685:43:106   # match_id:competition_id:season_id
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from matchlens import loader  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--add", action="append", default=[], help="extra match as match_id:competition_id:season_id")
    args = parser.parse_args()
    extra = []
    for spec in args.add:
        match_id, comp, season = (int(x) for x in spec.split(":"))
        extra.append({"match_id": match_id, "competition_id": comp, "season_id": season})
    for e in loader.preload(extra):
        m = loader.load_match_meta(**e)
        print(
            f"cached {e['match_id']}: {m['home_team']['home_team_name']} {m['home_score']}-"
            f"{m['away_score']} {m['away_team']['away_team_name']} ({m['competition_stage']['name']}, {m['match_date']})"
        )


if __name__ == "__main__":
    main()
