"""All tunable thresholds and defaults live here."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"

OPEN_DATA_BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

# Queries are resolved against matches.json by scripts/fetch_data.py (never hard-coded ids).
# FIFA World Cup: competition 43; 2022 season 106; 2018 season 3.
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
PERIOD_OFFSET_SECONDS = {1: 0, 2: 45 * 60, 3: 90 * 60, 4: 105 * 60, 5: 120 * 60}
PERIOD_END_MINUTE = {1: 45, 2: 90, 3: 105, 4: 120}
SHOOTOUT_PERIOD = 5
IN_PLAY_PERIODS = (1, 2, 3, 4)

# Detection thresholds
BIG_CHANCE_XG = 0.25
# Penalty xG (0.78) reflects a refereeing decision, not open play; keep it out of window comparisons.
EXCLUDE_PENALTIES_FROM_WINDOWS = True
MOMENTUM_WINDOW_MIN = 10
MOMENTUM_HOLD_MIN = 5
MOMENTUM_MIN_LEAD_XG = 0.15  # a leader must lead by at least this much xG (window)
SUB_WINDOW_MIN = 10
SUB_XG_DELTA = 0.4  # |after - before| xG
SUB_SHOT_DELTA = 3  # |after - before| shots
BUILDUP_MAX_PASSES = 12

# Quick responses (play time, so half-time and the break before extra time do not count)
QUICK_RESPONSE_BRACE_MIN = 5  # 2+ goals by one team within this many minutes
QUICK_RESPONSE_REPLY_MIN = 3  # equaliser or lead change within this many minutes of conceding

# Display names come from the lineups nickname field, then the full name. Overrides win over both.
# Keys are StatsBomb player ids (int) or full names (str).
DISPLAY_NAME_OVERRIDES: dict[int | str, str] = {
    22097: "Randal Kolo Muani",  # StatsBomb nickname is "Randal Kolo"
    27886: "Alexis Mac Allister",  # StatsBomb nickname is "Alexis MacAllister"
}


# --- Phase 2: local LLM -----------------------------------------------------------------------------
import os  # noqa: E402

PROMPTS_DIR = ROOT / "prompts"
GENERATED_DIR = ROOT / "data" / "generated"

LLM_PROVIDER = os.environ.get("MATCHLENS_LLM_PROVIDER", "ollama")  # "ollama"; add other providers in llm/factory.py
OLLAMA_URL = os.environ.get("MATCHLENS_OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("MATCHLENS_OLLAMA_MODEL", "qwen3:8b")
LLM_TEMPERATURE = 0.2
LLM_SEED = 7  # fixed so repeated runs are comparable
LLM_TIMEOUT_SECONDS = 600  # an 8B model on a laptop GPU can be slow on the first (cold) call
OLLAMA_NUM_CTX = 8192
OLLAMA_DISABLE_THINKING = True

AUDIENCES = ("analyst", "broadcaster", "fan")
LENGTHS = ("short", "medium")
LANGUAGES = ("en",)  # Phase 3 adds "hi" and "ta" (plus prompts/language_<code>.md)
PARAGRAPHS_PER_LENGTH = {"short": (2, 3), "medium": (4, 6)}

RECAP_MIN_IMPORTANCE = 0.5  # recap prompts only include moments at or above this; explanations see all

# Capitalised words the name check lets through (besides team names and the match's own competition/stage text)
NAME_CHECK_ALLOWED_WORDS = {
    "January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
    "November", "December", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "World", "Cup", "FIFA", "Final", "Semi", "Quarter", "Round", "Group", "Stage", "Extra", "Time",
    "Penalty", "Penalties", "Shootout", "Euro", "League", "Champions", "Argentine", "Argentinian", "French",
    "Dutch", "Brazilian", "Belgian", "Croatian", "English", "German", "Spanish", "Portuguese", "Moroccan",
    "Pens", "VAR", "I", "A",
}
