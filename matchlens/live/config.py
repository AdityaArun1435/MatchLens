"""Settings read from environment variables, plus the competitions we track."""
import os
from dataclasses import dataclass, field

# code -> (football-data.org id, API-Football league id). All twelve are on the football-data.org free plan.
COMPETITIONS: dict[str, tuple[int, int]] = {
    "PL": (2021, 39),
    "ELC": (2016, 40),
    "BL1": (2002, 78),
    "SA": (2019, 135),
    "PD": (2014, 140),
    "FL1": (2015, 61),
    "DED": (2003, 88),
    "PPL": (2017, 94),
    "CL": (2001, 2),
    "EC": (2018, 4),
    "WC": (2000, 1),
    "BSA": (2013, 71),
}
DEFAULT_TRACKED = "PL,PD,SA,BL1,FL1,CL,DED,PPL,ELC"


@dataclass
class Settings:
    supabase_url: str = ""
    supabase_service_key: str = ""
    football_data_token: str = ""
    api_football_key: str = ""
    cron_secret: str = ""
    tracked: list[str] = field(default_factory=lambda: DEFAULT_TRACKED.split(","))
    # API-Football free plan is 100 per day; keep a reserve. See docs/data_sources.md for the split.
    af_daily_limit: int = 95
    af_live_daily_limit: int = 70
    af_detail_daily_limit: int = 20
    af_per_minute_limit: int = 8
    # football-data.org free plan is 10 per minute; we stay well under.
    fd_per_minute_limit: int = 6
    live_min_interval_s: int = 240

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ.get
        tracked = [c.strip().upper() for c in env("TRACKED_COMPETITIONS", DEFAULT_TRACKED).split(",") if c.strip()]
        return cls(
            supabase_url=env("SUPABASE_URL", "").rstrip("/"),
            supabase_service_key=env("SUPABASE_SERVICE_KEY", ""),
            football_data_token=env("FOOTBALL_DATA_TOKEN", ""),
            api_football_key=env("API_FOOTBALL_KEY", ""),
            cron_secret=env("CRON_SECRET", ""),
            tracked=[c for c in tracked if c in COMPETITIONS],
            af_daily_limit=int(env("AF_DAILY_LIMIT", "95")),
            live_min_interval_s=int(env("LIVE_MIN_INTERVAL_S", "240")),
        )
