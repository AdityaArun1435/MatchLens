import pytest
from fastapi.testclient import TestClient

from matchlens import config, loader
from matchlens.api import app

pytestmark = pytest.mark.needs_data


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def mid():
    return loader.find_match(config.DEFAULT_MATCH_QUERY, offline_only=True)["match_id"]


def test_matches_lists_three_preloaded(client, mid):
    data = client.get("/matches").json()
    assert len(data) == 3 and mid in {m["match_id"] for m in data}


def test_summary_and_moments_filter(client, mid):
    assert client.get(f"/matches/{mid}/summary").json()["shootout"]["winner"] == "Argentina"
    all_m = client.get(f"/matches/{mid}/moments").json()
    high = client.get(f"/matches/{mid}/moments", params={"min_importance": 0.9}).json()
    assert 0 < len(high) < len(all_m) and all(m["importance"] >= 0.9 for m in high)
    assert [m["first_index"] for m in all_m] == sorted(m["first_index"] for m in all_m)


def test_events_filter(client, mid):
    ev = client.get(f"/matches/{mid}/events", params={"from_minute": 100, "to_minute": 105, "period": 3}).json()
    assert ev and all(100 <= e["minute"] <= 105 and e["period"] == 3 for e in ev)
    assert [e["index"] for e in ev] == sorted(e["index"] for e in ev)


def test_unknown_match_404(client):
    assert client.get("/matches/1/summary").status_code == 404
    assert client.get("/matches/abc/summary").status_code == 422
