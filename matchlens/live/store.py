"""Supabase access through PostgREST with the service key. Plain httpx, no SDK.

The orchestrator talks to this small interface only, so tests swap in an in-memory fake.
"""
from datetime import datetime, timedelta, timezone

import httpx


class Store:
    def __init__(self, url: str, service_key: str, client: httpx.Client | None = None):
        self.base = f"{url}/rest/v1"
        self.http = client or httpx.Client(timeout=15)
        self.headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}

    def _check(self, res: httpx.Response) -> httpx.Response:
        if res.status_code >= 400:
            raise RuntimeError(f"Supabase {res.request.method} {res.request.url.path}: {res.status_code} {res.text[:300]}")
        return res

    # --- generic -------------------------------------------------------------------------------
    def select(self, table: str, params: dict) -> list[dict]:
        return self._check(self.http.get(f"{self.base}/{table}", params=params, headers=self.headers)).json()

    def upsert(self, table: str, rows: list[dict], on_conflict: str, ignore_duplicates: bool = False) -> None:
        if not rows:
            return
        resolution = "ignore-duplicates" if ignore_duplicates else "merge-duplicates"
        headers = {**self.headers, "Prefer": f"resolution={resolution},return=minimal", "Content-Type": "application/json"}
        self._check(self.http.post(f"{self.base}/{table}", params={"on_conflict": on_conflict}, json=rows, headers=headers))

    def update(self, table: str, match: dict, values: dict) -> None:
        params = {k: f"eq.{v}" for k, v in match.items()}
        headers = {**self.headers, "Prefer": "return=minimal", "Content-Type": "application/json"}
        self._check(self.http.patch(f"{self.base}/{table}", params=params, json=values, headers=headers))

    def rpc(self, fn: str, args: dict):
        return self._check(self.http.post(f"{self.base}/rpc/{fn}", json=args, headers=self.headers)).json()

    # --- cache and budget ----------------------------------------------------------------------
    def get_cache(self, key: str, allow_stale: bool = False) -> dict | None:
        params = {"key": f"eq.{key}", "select": "payload,expires_at,fetched_at"}
        rows = self.select("api_cache", params)
        if not rows:
            return None
        if not allow_stale and rows[0]["expires_at"] <= datetime.now(timezone.utc).isoformat():
            return None
        return rows[0]["payload"]

    def put_cache(self, key: str, source: str, payload, ttl_s: int) -> None:
        now = datetime.now(timezone.utc)
        row = {"key": key, "source": source, "payload": payload, "fetched_at": now.isoformat(),
               "expires_at": (now + timedelta(seconds=ttl_s)).isoformat()}
        self.upsert("api_cache", [row], "key")

    def bump_usage(self, source: str, bucket: str, limit: int) -> bool:
        return bool(self.rpc("bump_usage", {"p_source": source, "p_bucket": bucket, "p_limit": limit}))

    def get_usage(self, source: str, bucket: str) -> int:
        rows = self.select("api_usage", {"source": f"eq.{source}", "bucket": f"eq.{bucket}", "select": "count"})
        return rows[0]["count"] if rows else 0

    # --- domain queries ------------------------------------------------------------------------
    def fixtures_between(self, start: datetime, end: datetime) -> list[dict]:
        """Fixtures with both team names embedded as home/away objects."""
        params = {
            "select": "*,home:teams!fixtures_home_team_id_fkey(id,name,short_name,tla,af_team_id),"
                      "away:teams!fixtures_away_team_id_fkey(id,name,short_name,tla,af_team_id)",
            "and": f"(utc_date.gte.{start.isoformat()},utc_date.lt.{end.isoformat()})",
            "order": "utc_date.asc",
        }
        return self.select("fixtures", params)

    def fixtures_by_af_ids(self, af_ids: list[int]) -> list[dict]:
        if not af_ids:
            return []
        params = {"select": "id,af_fixture_id,home_team_id,away_team_id,status,utc_date",
                  "af_fixture_id": f"in.({','.join(map(str, af_ids))})"}
        return self.select("fixtures", params)

    def live_states(self, fixture_ids: list[int]) -> dict[int, dict]:
        if not fixture_ids:
            return {}
        rows = self.select("live_state", {"fixture_id": f"in.({','.join(map(str, fixture_ids))})", "select": "*"})
        return {r["fixture_id"]: r for r in rows}

    def fixtures_with_lineups(self, fixture_ids: list[int]) -> set[int]:
        if not fixture_ids:
            return set()
        rows = self.select("lineups", {"fixture_id": f"in.({','.join(map(str, fixture_ids))})", "select": "fixture_id"})
        return {r["fixture_id"] for r in rows}

    def sync_events(self, fixture_id: int, rows: list[dict]) -> None:
        """Upsert the current event list and remove events no longer reported (for example a goal ruled out by VAR)."""
        self.upsert("events", rows, "fixture_id,dedupe_key")
        keys = ",".join('"' + r["dedupe_key"].replace('"', "") + '"' for r in rows)
        params = {"fixture_id": f"eq.{fixture_id}"}
        if keys:
            params["dedupe_key"] = f"not.in.({keys})"
        self._check(self.http.delete(f"{self.base}/events", params=params, headers=self.headers))
