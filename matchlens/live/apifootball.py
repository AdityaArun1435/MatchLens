"""API-Football v3 client (api-sports.io). Free plan: 100 requests per day, 10 per minute, all endpoints."""
from .config import Settings
from .base import BudgetExceeded, CachedSource, day_bucket, minute_bucket

# 'live' and 'detail' are sub-budgets of the daily total. See docs/data_sources.md.
CATEGORY_LIMIT_ATTR = {"live": "af_live_daily_limit", "detail": "af_detail_daily_limit", "backfill": "af_backfill_daily_limit"}


class ApiFootball(CachedSource):
    name = "af"
    base_url = "https://v3.football.api-sports.io"

    def __init__(self, store, settings: Settings, **kw):
        super().__init__(store, **kw)
        self.settings = settings

    def _headers(self) -> dict:
        return {"x-apisports-key": self.settings.api_football_key}

    def _check_budget(self, category: str) -> None:
        s = self.settings
        attr = CATEGORY_LIMIT_ATTR.get(category)
        if attr and not self.store.bump_usage(self.name, day_bucket(suffix=f":{category}"), getattr(s, attr)):
            raise BudgetExceeded(f"API-Football {category} budget used for today")
        if not self.store.bump_usage(self.name, day_bucket(), s.af_daily_limit):
            raise BudgetExceeded("API-Football daily budget used")
        if not self.store.bump_usage(self.name, minute_bucket(), s.af_per_minute_limit):
            raise BudgetExceeded("API-Football per-minute budget used")

    def _read_quota(self, res) -> None:
        left = res.headers.get("x-ratelimit-requests-remaining")
        if left and left.isdigit():
            self.remaining_quota = int(left)

    def _error_in_body(self, body) -> str | None:
        errors = body.get("errors") if isinstance(body, dict) else None
        if errors:  # API-Football answers HTTP 200 with an errors object for quota and plan problems
            return str(errors)[:300]
        return None

    def live_all(self) -> list[dict]:
        return self.get("/fixtures", {"live": "all"}, use_cache=False, ttl_s=60, category="live")["response"]

    def fixtures_on(self, day: str, ttl_s: int = 10800) -> list[dict]:
        return self.get("/fixtures", {"date": day}, ttl_s=ttl_s, category="map")["response"]

    def fixture_detail(self, af_fixture_id: int, ttl_s: int = 600, category: str = "detail") -> list[dict]:
        """One call returns events, lineups and statistics for a fixture. Lookup by id works on the free plan for any season."""
        return self.get("/fixtures", {"id": af_fixture_id}, ttl_s=ttl_s, category=category)["response"]

    # The free plan cannot list fixtures by season or by dates older than yesterday, but head-to-head and
    # lookup by id are open. These three calls are how old matches get linked. See docs/data_gaps.md.
    def head_to_head(self, af_home_id: int, af_away_id: int, ttl_s: int = 30 * 86400) -> list[dict]:
        return self.get("/fixtures/headtohead", {"h2h": f"{af_home_id}-{af_away_id}"}, ttl_s=ttl_s, category="backfill")["response"]

    def league_teams(self, league_id: int, season: int = 2024, ttl_s: int = 30 * 86400) -> list[dict]:
        """Team ids of a league from the newest season the free plan allows. Promoted clubs are missing and found by search."""
        return self.get("/teams", {"league": league_id, "season": season}, ttl_s=ttl_s, category="backfill")["response"]

    def search_team(self, name: str, ttl_s: int = 30 * 86400) -> list[dict]:
        return self.get("/teams", {"search": name}, ttl_s=ttl_s, category="backfill")["response"]
