"""Hindi and Tamil through the HTTP API (fake model, real match data)."""
import pytest
from fastapi.testclient import TestClient

from matchlens import config, loader, service
from matchlens.api import app, provider_dep
from matchlens.llm import FakeProvider
from matchlens.recap.names_i18n import names_in_match

from .test_recap_api import EXPLAIN, GOOD
from .translate_helpers import native, router

pytestmark = pytest.mark.needs_data


@pytest.fixture(scope="module")
def mid():
    return loader.find_match(config.DEFAULT_MATCH_QUERY, offline_only=True)["match_id"]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "generated")
    monkeypatch.setattr(config, "NAMES_DIR", tmp_path / "names")
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def use(lang, mid, **kw):
    names = names_in_match(service.get_match(mid))
    provider = FakeProvider([router(lang, names, GOOD, EXPLAIN, **kw)])
    app.dependency_overrides[provider_dep] = lambda: provider
    return provider


@pytest.mark.parametrize("lang", ["hi", "ta"])
def test_recap_in_hindi_and_tamil(client, mid, lang):
    use(lang, mid)
    r = client.post(f"/matches/{mid}/recap", json={"audience": "analyst", "language": lang})
    assert r.status_code == 200
    body = r.json()
    assert body["language"] == lang and body["source_recap"]["title"] == GOOD["title"]
    assert [p["cites"] for p in body["recap"]["paragraphs"]] == [p["cites"] for p in GOOD["paragraphs"]] + [["m_010"]]
    assert all(p["language"] == lang for p in body["recap"]["paragraphs"])
    tr = body["report"]["translation"]
    assert tr["language"] == lang and tr["names_missing"] == [] and all(u["status"] == "translated" for u in tr["units"])
    assert native("Lionel Messi", lang) in body["recap"]["paragraphs"][0]["text"]
    assert client.post(f"/matches/{mid}/recap", json={"audience": "analyst", "language": lang}).json()["cached"] is True


def test_explanation_in_tamil(client, mid):
    use("ta", mid)
    r = client.get(f"/matches/{mid}/moments/m_004/explain", params={"language": "ta"})
    body = r.json()
    assert r.status_code == 200 and body["language"] == "ta" and body["explanation"]["language"] == "ta"
    assert body["source_explanation"]["context"] == EXPLAIN["context"] and body["report"]["translation"]["fallbacks"] == 0


def test_a_failed_paragraph_is_returned_in_english_with_its_note(client, mid):
    use("hi", mid, override=lambda source, attempt: "शब्द 99" if "shootout" in source else None)
    body = client.post(f"/matches/{mid}/recap", json={"language": "hi"}).json()
    last = body["recap"]["paragraphs"][-1]
    assert last["language"] == "en" and last["text"] == body["source_recap"]["paragraphs"][-1]["text"] and "Shown in English" in last["note"]
    assert len(body["recap"]["paragraphs"]) == len(GOOD["paragraphs"]) + 1
    assert body["report"]["translation"]["units"][-1]["status"] == "english_fallback"


def test_unknown_language_is_rejected(client, mid):
    assert client.post(f"/matches/{mid}/recap", json={"language": "fr"}).status_code == 422
    assert client.get(f"/matches/{mid}/moments/m_001/explain", params={"language": "fr"}).status_code == 422
