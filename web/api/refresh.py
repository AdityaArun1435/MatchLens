"""Vercel Python function: one refresh tick. Called every minute by Supabase pg_cron (see supabase/migrations/0004).

Protected by CRON_SECRET: the caller sends `Authorization: Bearer <CRON_SECRET>`.
"""
import hmac
import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

HERE = Path(__file__).resolve().parent
# On Vercel the package is copied to ../_py by scripts/sync-python.mjs; locally it sits at the repo root.
for candidate in (HERE.parent / "_py", HERE.parent.parent):
    if (candidate / "matchlens" / "live").is_dir():
        sys.path.insert(0, str(candidate))
        break

from matchlens.live.run import run_once  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorised(self) -> bool:
        secret = os.environ.get("CRON_SECRET", "")
        sent = self.headers.get("Authorization", "")
        return bool(secret) and hmac.compare_digest(sent, f"Bearer {secret}")

    def do_POST(self):
        if not self._authorised():
            return self._send(401, {"error": "unauthorised"})
        try:
            self._send(200, run_once())
        except Exception as exc:  # report, never crash the schedule
            self._send(500, {"error": str(exc)[:300]})

    do_GET = do_POST
