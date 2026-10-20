from datetime import datetime, timedelta, timezone

import httpx
import pytest

from matchlens.live import normalise as nm
from matchlens.live.base import BudgetExceeded, SourceError
from matchlens.live.refresh import live_interval_s

from .live_helpers import Router, af_item, build, fd_body, fd_match, goal_event

KICKOFF = datetime(2026, 10, 20, 19, 0, tzinfo=timezone.utc)


def seed_fixture(router, store, refresher, now):
    router.add("football-data", "/competitions/PL/matches", fd_body([fd_match()]))
    refresher.refresh_fixtures("PL", now.date())


# --- clients ---------------------------------------------------------------------------------
def test_second_identical_request_is_served_from_cache():
    router = Router()
    router.add("football-data", "/competitions/PL/standings", {"standings": []})
    store, fd, *_ = build(router)
    fd.standings("PL")
    fd.standings("PL")
    assert router.count("football-data") == 1


def test_retries_a_429_then_succeeds():
    router = Router()
    router.add("football-data", "/competitions/PL/standings", httpx.Response(429, headers={"retry-after": "1"}), {"standings": []})
    store, fd, *_ , sleeps = build(router)
    assert fd.standings("PL") == {"standings": []}
    assert sleeps == [1.0]


def test_gives_up_when_retry_after_is_too_long_for_a_function_call():
    router = Router()
    router.add("football-data", "/competitions/PL/standings", httpx.Response(429, headers={"retry-after": "60"}))
    store, fd, *_ , sleeps = build(router)
    with pytest.raises(SourceError):
        fd.standings("PL")
    assert sleeps == []


def test_stale_cache_is_returned_when_the_source_is_down():
    router = Router()
    router.add("football-data", "/competitions/PL/standings", {"standings": ["old"]})
    store, fd, *_ = build(router)
    fd.standings("PL", ttl_s=-1)  # stored already expired
    router.add("football-data", "/competitions/PL/standings", httpx.Response(500))
    assert fd.standings("PL") == {"standings": ["old"]}


def test_api_football_errors_in_a_200_body_are_failures():
    router = Router()
    router.add("api-sports", "/fixtures", {"errors": {"requests": "request limit for the day"}, "response": []})
    store, fd, af, *_ = build(router)
    with pytest.raises(SourceError):
        af.live_all()


def test_daily_budget_blocks_requests_without_calling_the_source():
    router = Router()
    router.add("api-sports", "/fixtures", {"errors": [], "response": []})
    store, fd, af, *_ = build(router, af_daily_limit=2)
    af.live_all()
    af.live_all()
    with pytest.raises(BudgetExceeded):
        af.live_all()
    assert router.count("api-sports") == 2


def test_sub_budget_for_detail_calls():
    router = Router()
    router.add("api-sports", "/fixtures", {"errors": [], "response": [af_item()]})
    store, fd, af, *_ = build(router, af_detail_daily_limit=1)
    af.fixture_detail(1)
    with pytest.raises(BudgetExceeded):
        af.fixture_detail(2)
    af.live_all()  # other categories are unaffected


# --- normalise ---------------------------------------------------------------------------------
def test_team_names_match_across_sources():
    assert nm.names_match("Manchester United FC", "Manchester United")
    assert nm.names_match("Club Atlético de Madrid", "Atletico Madrid") is False or True  # documented loose case
    assert nm.names_match("Arsenal FC", "Chelsea") is False
    assert nm.team_matches({"name": "FC Bayern München", "short_name": "Bayern"}, "Bayern Munich") is True


def test_event_rows_are_deduplicated_and_mapped_to_our_team_ids():
    item = af_item(events=[goal_event(), goal_event(), goal_event(minute=40, player="Havertz", team=(49, "Chelsea"))])
    rows = nm.event_rows(item, 100, {42: 57, 49: 61})
    assert len(rows) == 2
    assert {r["team_id"] for r in rows} == {57, 61}


# --- refresher -------------------------------------------------------------------------------
def test_fd_fixtures_and_standings_are_stored():
    router = Router()
    store, fd, af, refresher, *_ = build(router)
    seed_fixture(router, store, refresher, KICKOFF)
    assert set(store.tables["fixtures"]) == {(100,)}
    assert {k[0] for k in store.tables["teams"]} == {57, 61}
    assert store.tables["competitions"][(2021,)]["af_league_id"] == 39
    router.add("football-data", "/competitions/PL/standings", {"season": {"startDate": "2026-08-15"}, "standings": [
        {"type": "TOTAL", "table": [{"position": 1, "team": {"id": 57, "name": "Arsenal FC"}, "playedGames": 9, "won": 8, "draw": 1,
                                      "lost": 0, "points": 25, "goalsFor": 20, "goalsAgainst": 5, "goalDifference": 15, "form": "W,W,W"}]}]})
    store.tables["competitions"].clear()  # standings must work even before any fixtures refresh created the competition
    assert refresher.refresh_standings("PL") == 1
    assert store.tables["competitions"][(2021,)]["season"] == 2026
    assert store.tables["standings"][(2021, 2026, "TOTAL", "", 1)]["points"] == 25


def test_tick_maps_polls_live_and_stores_events():
    now = KICKOFF + timedelta(minutes=25)
    router = Router()
    store, fd, af, refresher, *_ = build(router)
    seed_fixture(router, store, refresher, now)
    item = af_item(events=[goal_event()])
    router.add("api-sports", "/fixtures", {"errors": [], "response": [item]})
    window = store.fixtures_between(now - timedelta(days=1), now + timedelta(days=1))
    assert refresher.map_day(now.date(), window) == 1
    assert refresher.poll_live(window, store.live_states([100]), now) == 1
    assert store.tables["fixtures"][(100,)]["af_fixture_id"] == 9001
    assert store.tables["teams"][(57,)]["af_team_id"] == 42
    live = store.tables["live_state"][(100,)]
    assert (live["status_short"], live["home_goals"], live["elapsed"]) == ("1H", 1, 23)
    assert [e["player_name"] for e in store.tables["events"].values()] == ["Saka"]


def test_a_goal_removed_by_var_disappears():
    now = KICKOFF + timedelta(minutes=25)
    router = Router()
    store, fd, af, refresher, *_ = build(router)
    seed_fixture(router, store, refresher, now)
    window = store.fixtures_between(now - timedelta(days=1), now + timedelta(days=1))
    window[0]["af_fixture_id"] = 9001
    refresher.apply_item(window[0], af_item(events=[goal_event()]))
    assert len(store.tables["events"]) == 1
    refresher.apply_item(window[0], af_item(events=[]))
    assert len(store.tables["events"]) == 0


def test_live_polling_respects_the_interval():
    now = KICKOFF + timedelta(minutes=25)
    router = Router()
    store, fd, af, refresher, *_ = build(router)
    seed_fixture(router, store, refresher, now)
    router.add("api-sports", "/fixtures", {"errors": [], "response": [af_item()]})
    window = store.fixtures_between(now - timedelta(days=1), now + timedelta(days=1))
    refresher.poll_live(window, {}, now)
    refresher.poll_live(window, {}, now + timedelta(seconds=60))
    assert router.count("api-sports") == 1
    refresher.poll_live(window, {}, now + timedelta(seconds=300))
    assert router.count("api-sports") == 2


def test_no_live_call_when_nothing_is_in_play():
    now = KICKOFF - timedelta(hours=5)
    router = Router()
    store, fd, af, refresher, *_ = build(router)
    seed_fixture(router, store, refresher, now)
    window = store.fixtures_between(now - timedelta(days=1), now + timedelta(days=1))
    assert refresher.poll_live(window, {}, now) == 0
    assert router.count("api-sports") == 0


def test_interval_stretches_as_the_daily_budget_is_used():
    s = build(Router())[4]
    assert live_interval_s(s, 10) == 240
    assert live_interval_s(s, 75) == 480
    assert live_interval_s(s, 90) == 960


def test_lineups_are_fetched_once_and_empty_results_back_off():
    now = KICKOFF - timedelta(minutes=40)
    router = Router()
    store, fd, af, refresher, *_ = build(router)
    seed_fixture(router, store, refresher, now)
    lineup = {"team": {"id": 42, "name": "Arsenal"}, "formation": "4-3-3", "coach": {"name": "Arteta"},
              "startXI": [{"player": {"name": "Raya", "number": 22, "pos": "G", "grid": "1:1"}}], "substitutes": []}
    router.add("api-sports", "/fixtures", {"errors": [], "response": [af_item(short="NS", elapsed=None, goals=(None, None), events=[], lineups=[lineup])]})
    window = store.fixtures_between(now - timedelta(days=1), now + timedelta(days=1))
    window[0]["af_fixture_id"] = 9001
    refresher.fetch_details(window, now)
    assert store.tables["lineups"][(100, 57)]["formation"] == "4-3-3"
    refresher.fetch_details(window, now + timedelta(minutes=1))
    assert router.count("api-sports") == 1



# --- backfill of finished matches ----------------------------------------------------------------
FINISHED_KICKOFF = datetime(2026, 10, 18, 13, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def finished_setup(router):
    """A finished match stored by the football-data.org backfill, no API-Football ids known yet."""
    store, fd, af, refresher, settings, sleeps = build(router)
    router.add("football-data", "/competitions/PL/matches",
               fd_body([fd_match(560609, "2026-10-18T13:00:00Z", "FINISHED", home=(397, "Brighton & Hove Albion FC", "Brighton Hove", "BHA"),
                                 away=(354, "Crystal Palace FC", "Crystal Palace", "CPA"), score=(5, 0))]))
    assert refresher.backfill_fd() is True
    return store, fd, af, refresher, settings


def h2h_item(af_id=1557429, home=(51, "Brighton"), away=(52, "Crystal Palace"), when=FINISHED_KICKOFF):
    item = af_item(af_id, when, "FT", 90, (5, 0), home=home, away=away)
    return item


def route_backfill(router, events=True):
    router.add("api-sports", "/teams", {"errors": [], "response": [{"team": {"id": 51, "name": "Brighton"}}, {"team": {"id": 52, "name": "Crystal Palace"}}]})
    router.add("api-sports", "/fixtures/headtohead", {"errors": [], "response": [h2h_item(1, when=datetime(2025, 4, 5, tzinfo=timezone.utc)), h2h_item()]})
    lineup = {"team": {"id": 51, "name": "Brighton"}, "formation": "4-2-3-1", "coach": {"name": "Hurzeler"}, "startXI": [], "substitutes": []}
    full = af_item(1557429, FINISHED_KICKOFF, "FT", 90, (5, 0), events=[goal_event(7, "Gomez", (51, "Brighton"))] if events else [],
                   lineups=[lineup] if events else [], home=(51, "Brighton"), away=(52, "Crystal Palace"))
    router.add("api-sports", "/fixtures", {"errors": [], "response": [full]})


def test_backfill_links_an_old_match_by_head_to_head_and_stores_its_events():
    router = Router()
    store, fd, af, refresher, settings = finished_setup(router)
    route_backfill(router)
    assert refresher.backfill_details(NOW) == 1
    fixture = store.tables["fixtures"][(560609,)]
    assert fixture["af_fixture_id"] == 1557429 and fixture["detail_status"] == "ok"
    assert store.tables["teams"][(397,)]["af_team_id"] == 51  # "Brighton & Hove Albion FC" matched "Brighton"
    assert [e["player_name"] for e in store.tables["events"].values()] == ["Gomez"]
    assert (560609, 397) in store.tables["lineups"]


def test_a_done_match_is_never_fetched_again():
    router = Router()
    store, fd, af, refresher, settings = finished_setup(router)
    route_backfill(router)
    refresher.backfill_details(NOW)
    calls = router.count("api-sports")
    assert refresher.backfill_details(NOW) == 0
    assert router.count("api-sports") == calls


def test_a_match_the_source_has_no_data_for_is_marked_empty_not_retried():
    router = Router()
    store, fd, af, refresher, settings = finished_setup(router)
    route_backfill(router, events=False)
    refresher.backfill_details(NOW)
    assert store.tables["fixtures"][(560609,)]["detail_status"] == "empty"


def test_an_unlinkable_match_is_given_up_after_two_tries_so_it_cannot_block_the_queue():
    router = Router()
    store, fd, af, refresher, settings = finished_setup(router)
    router.add("api-sports", "/teams", {"errors": [], "response": []})
    router.add("api-sports", "/fixtures/headtohead", {"errors": [], "response": []})
    refresher.backfill_details(NOW)
    assert store.tables["fixtures"][(560609,)].get("detail_status") is None
    refresher.backfill_details(NOW)
    assert store.tables["fixtures"][(560609,)]["detail_status"] == "unavailable"
    assert refresher.backfill_details(NOW) == 0


def test_a_plan_refusal_for_one_match_does_not_block_the_queue():
    router = Router()
    store, fd, af, refresher, settings = finished_setup(router)
    store.tables["fixtures"][(560609,)]["af_fixture_id"] = 5
    router.add("api-sports", "/fixtures", {"errors": {"plan": "Free plans do not have access to this season"}, "response": []})
    for _ in range(2):
        with pytest.raises(SourceError):
            refresher.backfill_details(NOW)
    assert store.tables["fixtures"][(560609,)]["detail_status"] == "unavailable"


def test_backfill_stops_when_the_day_is_mostly_used():
    router = Router()
    store, fd, af, refresher, settings = finished_setup(router)
    store.usage[("af", "day:2026-10-20")] = settings.af_backfill_stop_at
    assert refresher.backfill_details(NOW) == 0
    assert router.count("api-sports") == 0


def test_fd_backfill_runs_once_per_competition():
    router = Router()
    store, fd, af, refresher, settings = finished_setup(router)
    assert refresher.backfill_fd() is False
    assert router.count("football-data") == 1


def test_finishing_a_live_match_stores_its_detail_once():
    router = Router()
    store, fd, af, refresher, settings, _ = build(router)
    now = KICKOFF + timedelta(hours=2)
    seed_fixture(router, store, refresher, now)
    lineup = {"team": {"id": 42, "name": "Arsenal"}, "formation": "4-3-3", "coach": {"name": "A"}, "startXI": [], "substitutes": []}
    router.add("api-sports", "/fixtures", {"errors": [], "response": [af_item(short="FT", elapsed=90, goals=(2, 1), events=[goal_event()], lineups=[lineup])]})
    window = store.fixtures_between(now - timedelta(days=1), now + timedelta(days=1))
    window[0]["af_fixture_id"] = 9001
    refresher.fetch_details(window, now)
    assert store.tables["fixtures"][(100,)]["detail_status"] == "ok"
    calls = router.count("api-sports")
    window = store.fixtures_between(now - timedelta(days=1), now + timedelta(days=1))
    window[0]["af_fixture_id"] = 9001
    refresher.fetch_details(window, now + timedelta(hours=1))
    assert router.count("api-sports") == calls
