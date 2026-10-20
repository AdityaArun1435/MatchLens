"""Shared base for the two source clients: Supabase cache first, budget check, retries with backoff."""
import hashlib
import json
import time
from datetime import datetime, timezone

import httpx


class BudgetExceeded(Exception):
    """The request budget for this source is used up. The caller skips the work and tries on a later tick."""


class SourceError(Exception):
    pass


class CachedSource:
    name = "source"
    base_url = ""

    def __init__(self, store, client: httpx.Client | None = None, sleep=time.sleep):
        self.store = store
        self.http = client or httpx.Client(timeout=12)
        self.sleep = sleep
        self.requests_made = 0
        self.remaining_quota: int | None = None  # filled from response headers when the source sends them

    # --- subclass hooks ---
    def _headers(self) -> dict:
        return {}

    def _check_budget(self, category: str) -> None:
        raise NotImplementedError

    def _error_in_body(self, body) -> str | None:
        return None

    def _read_quota(self, res: httpx.Response) -> None:
        pass

    def _cache_key(self, path: str, params: dict | None) -> str:
        raw = path + "?" + json.dumps(params or {}, sort_keys=True)
        return f"{self.name}:{hashlib.sha1(raw.encode()).hexdigest()[:20]}:{path[:60]}"

    def get(self, path: str, params: dict | None = None, ttl_s: int = 60, category: str = "other", use_cache: bool = True):
        """Return parsed JSON. A fresh cached copy costs no request. If the source fails, a stale copy beats nothing."""
        key = self._cache_key(path, params)
        if use_cache:
            hit = self.store.get_cache(key)
            if hit is not None:
                return hit
        self._check_budget(category)
        try:
            body = self._fetch(path, params)
        except SourceError:
            stale = self.store.get_cache(key, allow_stale=True)
            if stale is not None:
                return stale
            raise
        self.store.put_cache(key, self.name, body, ttl_s)
        return body

    def _fetch(self, path: str, params: dict | None, attempts: int = 3):
        last = "no attempt"
        for attempt in range(attempts):
            try:
                res = self.http.get(self.base_url + path, params=params, headers=self._headers())
            except httpx.HTTPError as exc:
                last = f"network error: {exc}"
                self.sleep(min(2**attempt, 4))
                continue
            self.requests_made += 1
            self._read_quota(res)
            if res.status_code == 429:
                wait = _retry_after(res)
                last = "rate limited (429)"
                if wait > 8:  # a function call cannot wait this long; give up and let the next tick retry
                    break
                self.sleep(wait)
                continue
            if res.status_code >= 500:
                last = f"server error {res.status_code}"
                self.sleep(min(2**attempt, 4))
                continue
            if res.status_code >= 400:
                raise SourceError(f"{self.name} {path}: HTTP {res.status_code} {res.text[:200]}")
            body = res.json()
            problem = self._error_in_body(body)
            if problem:
                raise SourceError(f"{self.name} {path}: {problem}")
            return body
        raise SourceError(f"{self.name} {path}: {last}")


def _retry_after(res: httpx.Response) -> float:
    try:
        return float(res.headers.get("retry-after", "2"))
    except ValueError:
        return 2.0


def minute_bucket(now: datetime | None = None) -> str:
    return "min:" + (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M")


def day_bucket(now: datetime | None = None, suffix: str = "") -> str:
    return "day:" + (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d") + suffix
