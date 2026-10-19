import pytest
from fastapi.testclient import TestClient

from matchlens import config, loader
from matchlens.api import app, provider_dep
from matchlens.llm import FakeProvider, LLMError, LLMUnavailable

pytestmark = pytest.mark.needs_data

GOOD = {
    "title": "Argentina v France: 3-3, Argentina win 4-2 on penalties",
    "paragraphs": [
        {"text": "Lionel Messi scored a penalty at 23' to put Argentina 1-0 ahead.", "cites": ["m_001"]},
        {"text": "Kylian Mbappé scored twice in 94 seconds, at 80' and 81', making it 2-2.", "cites": ["m_003", "m_004", "m_005"]},
        {"text": "Argentina won the shootout 4-2.", "cites": ["m_010"]},
    ],
}
EXPLAIN = {
    "moment_id": "m_004",
    "why_it_mattered": "Kylian Mbappé's goal at 81' levelled the score at 2-2.",
    "context": "It came after his penalty at 80' made it 2-1.",
    "cites": ["m_004", "m_003"],
}


@pytest.fixture(scope="module")
def mid():
    return loader.find_match(config.DEFAULT_MATCH_QUERY, offline_only=True)["match_id"]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def use(provider):
    app.dependency_overrides[provider_dep] = lambda: provider
    return provider


def test_recap_returns_recap_report_model_and_timing(client, mid):
    provider = use(FakeProvider([GOOD], name="fake:1b"))
    r = client.post(f"/matches/{mid}/recap", json={"audience": "fan", "length": "short", "language": "en"})
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == "fake:1b" and body["audience"] == "fan" and body["generation_seconds"] >= 0
    assert body["report"]["method"] == "llm" and body["report"]["attempts"][0]["items_valid"] == 3
    assert [p["cites"] for p in body["recap"]["paragraphs"]][0] == ["m_001"]
    assert "Fan" in provider.calls[0]["user"]
    again = client.post(f"/matches/{mid}/recap", json={"audience": "fan", "length": "short"}).json()
    assert again["cached"] is True and len(provider.calls) == 1


def test_recap_default_body_and_validation_failures_are_reported(client, mid):
    bad = {"title": GOOD["title"], "paragraphs": [{"text": "Ronaldo scored at 23'.", "cites": ["m_001"]}, GOOD["paragraphs"][2]]}
    use(FakeProvider([bad]))
    body = client.post(f"/matches/{mid}/recap").json()
    assert body["audience"] == "analyst" and body["report"]["retried"]
    assert len(body["report"]["dropped"]) == 1 and "Ronaldo" in body["report"]["dropped"][0]["errors"][0]
    assert len(body["recap"]["paragraphs"]) == 1


def test_ollama_not_running_is_a_clear_503(client, mid):
    use(FakeProvider([LLMUnavailable("Cannot reach Ollama at http://localhost:11434. Start it with the Ollama app or `ollama serve`")]))
    r = client.post(f"/matches/{mid}/recap")
    assert r.status_code == 503 and "ollama serve" in r.json()["detail"]
    r = client.get(f"/matches/{mid}/moments/m_001/explain")
    assert r.status_code == 503


def test_unexpected_model_server_error_is_502(client, mid):
    use(FakeProvider([LLMError("Ollama returned 500")]))
    # LLMError inside the pipeline becomes a failed attempt and then a fallback, never a 5xx
    r = client.post(f"/matches/{mid}/recap")
    assert r.status_code == 200 and r.json()["report"]["method"] == "fallback"


def test_bad_parameters_and_unknown_ids(client, mid):
    use(FakeProvider([GOOD]))
    assert client.post(f"/matches/{mid}/recap", json={"audience": "pundit"}).status_code == 422
    assert client.post(f"/matches/{mid}/recap", json={"language": "hi"}).status_code == 422  # Phase 3
    assert client.post("/matches/1/recap").status_code == 404
    assert client.get(f"/matches/{mid}/moments/m_999/explain").status_code == 404
    assert client.get(f"/matches/{mid}/moments/m_001/explain", params={"audience": "x"}).status_code == 422


def test_explain_endpoint(client, mid):
    provider = use(FakeProvider([EXPLAIN]))
    r = client.get(f"/matches/{mid}/moments/m_004/explain", params={"audience": "broadcaster", "language": "en"})
    assert r.status_code == 200
    body = r.json()
    assert body["explanation"]["moment_id"] == "m_004" and body["report"]["method"] == "llm"
    assert "TARGET" in provider.calls[0]["user"]
    assert client.get(f"/matches/{mid}/moments/m_004/explain", params={"audience": "broadcaster"}).json()["cached"] is True
