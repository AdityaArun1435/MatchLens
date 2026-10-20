"""football-data.org v4 client. Free plan: 10 requests per minute, delayed scores, no lineups or events."""
from datetime import date

from .config import Settings
from .base import BudgetExceeded, CachedSource, minute_bucket


class FootballData(CachedSource):
    name = "fd"
    base_url = "https://api.football-data.org/v4"

    def __init__(self, store, settings: Settings, **kw):
        super().__init__(store, **kw)
        self.settings = settings

    def _headers(self) -> dict:
        return {"X-Auth-Token": self.settings.football_data_token}

    def _check_budget(self, category: str) -> None:
        if not self.store.bump_usage(self.name, minute_bucket(), self.settings.fd_per_minute_limit):
            raise BudgetExceeded("football-data.org per-minute budget used")

    def _read_quota(self, res) -> None:
        left = res.headers.get("x-requests-available-minute")
        if left and left.isdigit():
            self.remaining_quota = int(left)

    def matches(self, code: str, date_from: date, date_to: date, ttl_s: int = 240) -> dict:
        """Full response: the competition object and a `matches` list. The API allows at most a 10 day range."""
        params = {"dateFrom": date_from.isoformat(), "dateTo": date_to.isoformat()}
        return self.get(f"/competitions/{code}/matches", params, ttl_s=ttl_s)

    def standings(self, code: str, ttl_s: int = 1200) -> dict:
        return self.get(f"/competitions/{code}/standings", None, ttl_s=ttl_s)

    def finished_matches(self, code: str, ttl_s: int = 6 * 3600) -> dict:
        """Every finished match of the current season for one competition (one request)."""
        return self.get(f"/competitions/{code}/matches", {"status": "FINISHED"}, ttl_s=ttl_s)
