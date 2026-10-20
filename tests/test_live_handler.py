"""The Vercel function rejects callers without the shared secret and never runs a refresh for them."""
import importlib.util
import io
import json
from pathlib import Path

HANDLER = Path(__file__).resolve().parents[1] / "web" / "api" / "refresh.py"


def load_handler():
    spec = importlib.util.spec_from_file_location("refresh_fn", HANDLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def call(module, auth: str | None):
    class Fake(module.handler):
        def __init__(self):
            self.headers = {"Authorization": auth} if auth else {}
            self.wfile = io.BytesIO()
            self.status = None

        def send_response(self, code, message=None):
            self.status = code

        def send_header(self, *a):
            pass

        def end_headers(self):
            pass

    h = Fake()
    h.do_POST()
    return h.status, json.loads(h.wfile.getvalue())


def test_missing_or_wrong_secret_is_rejected(monkeypatch):
    module = load_handler()
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    monkeypatch.setattr(module, "run_once", lambda: pytest_fail())
    assert call(module, None)[0] == 401
    assert call(module, "Bearer nope")[0] == 401


def test_no_secret_configured_rejects_everyone(monkeypatch):
    module = load_handler()
    monkeypatch.delenv("CRON_SECRET", raising=False)
    assert call(module, "Bearer ")[0] == 401


def test_correct_secret_runs_one_tick(monkeypatch):
    module = load_handler()
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    monkeypatch.setattr(module, "run_once", lambda: {"did": ["x"]})
    assert call(module, "Bearer s3cret") == (200, {"did": ["x"]})


def test_a_failing_tick_is_reported_as_500(monkeypatch):
    module = load_handler()
    monkeypatch.setenv("CRON_SECRET", "s3cret")

    def boom():
        raise RuntimeError("Supabase down")

    monkeypatch.setattr(module, "run_once", boom)
    status, body = call(module, "Bearer s3cret")
    assert status == 500 and "Supabase down" in body["error"]


def pytest_fail():
    raise AssertionError("refresh must not run for unauthorised callers")
