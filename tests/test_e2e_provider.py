"""The canned browser-test provider must produce output the real validators accept, and /health must report it."""
import pytest
from fastapi.testclient import TestClient

from matchlens import config, loader, service
from matchlens.api import app, provider_dep
from matchlens.llm.e2e import E2EProvider
from matchlens.recap.models import RecapRequest
from matchlens.recap.pipeline import get_explanation, get_recap

pytestmark = pytest.mark.needs_data


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path)


@pytest.fixture(scope="module")
def match():
    return service.get_match(loader.find_match(config.DEFAULT_MATCH_QUERY, offline_only=True)["match_id"])


@pytest.mark.parametrize("audience", config.AUDIENCES)
def test_canned_recap_passes_validation_first_time(match, audience):
    res = get_recap(match, RecapRequest(audience=audience), E2EProvider())
    assert res.report.method == "llm" and not res.report.retried and not res.report.dropped
    assert res.recap.paragraphs[-1].cites == ["m_010"] and res.model == "e2e-fake"


def test_canned_explanation_passes_validation(match):
    res = get_explanation(match, "m_004", "analyst", "en", E2EProvider())
    assert res.report.method == "llm" and not res.report.retried


def test_health_reports_the_provider_and_quality_labels():
    app.dependency_overrides[provider_dep] = lambda: E2EProvider()
    try:
        body = TestClient(app).get("/health").json()
    finally:
        app.dependency_overrides.clear()
    assert body["status"] == "ok" and body["llm"]["available"] is True and body["llm"]["model"] == "e2e-fake"
    assert body["quality"]["ta"] == "experimental"
