"""All tunable thresholds and defaults live here."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"

OPEN_DATA_BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

# Resolved and verified from competitions.json / matches.json by fetch_data.py.
# FIFA World Cup: competition 43; 2022 season 106; 2018 season 3.
PRELOADED_MATCHES: dict[int, str] = {}  # filled from data/raw/index.json at runtime
DEFAULT_MATCH_QUERY = {
    "competition_id": 43,
    "season_id": 106,
    "home": "Argentina",
    "away": "France",
    "stage": "Final",
}
EXTRA_MATCH_QUERIES = [
    {"competition_id": 43, "season_id": 3, "home": "France", "away": "Argentina", "stage": "16"},
    {"competition_id": 43, "season_id": 106, "home": "Netherlands", "away": "Argentina", "stage": "Quarter"},
]

# Match clock: seconds added to a period's own timestamp to get match time.
# Regular time and extra time offsets (period -> start in seconds).
PERIOD_OFFSET_SECONDS = {1: 0, 2: 45 * 60, 3: 90 * 60, 4: 105 * 60}
PERIOD_END_MINUTE = {1: 45, 2: 90, 3: 105, 4: 120}
SHOOTOUT_PERIOD = 5
IN_PLAY_PERIODS = (1, 2, 3, 4)

# Detection thresholds
BIG_CHANCE_XG = 0.3
MOMENTUM_WINDOW_MIN = 10
MOMENTUM_HOLD_MIN = 5
MOMENTUM_MIN_LEAD_XG = 0.15  # a leader must lead by at least this much xG (window)
SUB_WINDOW_MIN = 10
SUB_XG_DELTA = 0.4  # |after - before| xG
SUB_SHOT_DELTA = 3  # |after - before| shots
BUILDUP_MAX_PASSES = 12
