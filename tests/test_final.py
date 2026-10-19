"""Facts about the 2022 World Cup final, from the cached StatsBomb data."""
import pytest

from matchlens import config, loader, service

pytestmark = pytest.mark.needs_data


@pytest.fixture(scope="module")
def final():
    match_id = loader.find_match(config.DEFAULT_MATCH_QUERY, offline_only=True)["match_id"]
    return service.get_match(match_id)


def test_teams_and_scores(final):
    s = final.summary
    assert (final.meta.home_team, final.meta.away_team) == ("Argentina", "France")
    assert s.final_score == (3, 3) and s.score_after_90 == (2, 2) and s.score_after_extra_time == (3, 3)
    assert (final.meta.home_score, final.meta.away_score) == s.final_score  # StatsBomb's own score agrees


def test_six_goals_all_with_moments(final):
    goals = [m for m in final.moments if m.type == "goal"]
    raw_goals = [e for e in final.events if e.type == "Shot" and e.outcome == "Goal" and e.in_play]
    assert len(raw_goals) == 6 and len(goals) == 6
    assert {m.evidence[-1] for m in goals} == {e.id for e in raw_goals}
    assert [m.clock_label for m in goals] == ["23'", "36'", "80'", "81'", "108'", "118'"]
    assert [m.team for m in goals] == ["Argentina"] * 2 + ["France"] * 2 + ["Argentina", "France"]


def test_shootout(final):
    sh = final.summary.shootout
    assert sh is not None and sh["winner"] == "Argentina" and sh["score"] == {"Argentina": 4, "France": 2}
    (moment,) = [m for m in final.moments if m.type == "penalty_shootout"]
    assert moment.team == "Argentina" and moment.stats["kick_count"] == 8


def test_shootout_not_in_xg_or_score(final):
    in_play_xg = sum(e.xg or 0 for e in final.events if e.type == "Shot" and e.period < 5)
    assert sum(final.summary.total_xg.values()) == pytest.approx(in_play_xg, abs=0.002)
    assert all(e.xg is None for e in final.events if e.period == 5)
    assert sum(final.summary.shots.values()) == 30


def test_every_evidence_id_exists(final):
    ids = {e.id for e in final.events}
    assert final.moments
    for m in final.moments:
        assert m.evidence and set(m.evidence) <= ids, m.id


def test_moments_ordered_with_stable_ids(final):
    assert [m.id for m in final.moments] == [f"m_{i:03d}" for i in range(1, len(final.moments) + 1)]
    assert [m.first_index for m in final.moments] == sorted(m.first_index for m in final.moments)
    assert all(0 <= m.importance <= 1 for m in final.moments)


def test_goal_score_progression(final):
    scores = [m.score_after for m in final.moments if m.type == "goal"]
    assert scores == [(1, 0), (2, 0), (2, 1), (2, 2), (3, 2), (3, 3)]


def test_second_goal_buildup_found(final):
    g = [m for m in final.moments if m.type == "goal"][1]  # Di Maria 36'
    assert g.stats["buildup_passes"] >= 4 and g.stats["assist"] == "Alexis Mac Allister"


def test_timeline_matches_totals(final):
    last = final.summary.xg_timeline[-1].cumulative_xg
    for team, xg in final.summary.total_xg.items():
        assert last[team] == pytest.approx(xg, abs=0.002)
    assert 0.99 < sum(final.summary.possession_share.values()) < 1.01


def test_period_stoppage_labels(final):
    labels = {e.clock_label for e in final.events if e.period == 2}
    assert "90+8'" in labels  # second half ran to 98:37


def test_extra_time_goal_records_the_saved_shot_before_it(final):
    g = [m for m in final.moments if m.type == "goal"][4]  # Messi 108'
    assert [(x["player"], x["outcome"]) for x in g.stats["preceding_shots"]] == [("Lautaro Martínez", "Saved")]


def test_quick_response_is_mbappes_double(final):
    (q,) = [m for m in final.moments if m.type == "quick_response"]
    goals = [m for m in final.moments if m.type == "goal"][2:4]
    assert q.team == "France" and q.stats["reasons"] == ["brace"]
    assert q.evidence == [g.evidence[-1] for g in goals]
    assert q.score_before == (2, 0) and q.score_after == (2, 2)
    first, second = (g["play_seconds"] for g in q.stats["goals"])
    assert second - first == pytest.approx(q.stats["span_seconds"], abs=0.15) and 90 < q.stats["span_seconds"] < 100  # 79:24 to 80:59
    assert first > 80 * 60  # play time includes the 7+ minutes of first-half stoppage
    assert q.importance >= 0.9


def test_big_chances_at_default_threshold(final):
    chances = [m for m in final.moments if m.type == "big_chance_missed"]
    assert [(m.player_display_names[0], m.team, m.clock_label, m.stats["outcome"]) for m in chances] == [
        ("Randal Kolo Muani", "France", "120+3'", "Saved")
    ]
    assert chances[0].stats["xg"] == 0.278 and chances[0].stats["assist"] == "Ibrahima Konaté"


def test_full_names_and_ids_kept_display_names_in_headlines(final):
    goal = [m for m in final.moments if m.type == "goal"][0]
    assert goal.players[0] == "Lionel Andrés Messi Cuccittini" and goal.player_ids[0] == 5503
    assert goal.player_display_names[0] == "Lionel Messi"
    pairs = {(f, d) for m in final.moments for f, d in zip(m.players, m.player_display_names) if f != d}
    assert ("Lionel Andrés Messi Cuccittini", "Lionel Messi") in pairs
    for m in final.moments:
        for full, display in pairs:
            assert full not in m.headline, (m.id, full)
    kolo = [e for e in final.events if e.player_id == 22097][0]
    assert kolo.player == "Randal Kolo Muani" and kolo.player_display_name == "Randal Kolo Muani"
