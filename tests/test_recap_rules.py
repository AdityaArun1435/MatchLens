"""Wording rules: score-state verbs, shootout claims, banned phrases, opinion words (all without an LLM)."""
import pytest

from matchlens.llm import FakeProvider
from matchlens.recap import rules
from matchlens.recap.context import build_context
from matchlens.recap.pipeline import run_recap
from matchlens.recap.validate import Validator

from .recap_fixtures import small_match
from .test_recap_pipeline import GOOD, variant

# small_match: m_001 B goal 11' (0-1, B takes the lead) | m_002 A goal 26' (1-1, A levels) | m_005 A goal 86' (2-1, A takes
# the lead) | m_006 shootout won by B 1-0: kick 1 B Cal Cross scored, kick 2 A Dan Dale saved.


@pytest.fixture(scope="module")
def match():
    return small_match()


@pytest.fixture(scope="module")
def ctx(match):
    return build_context(match, min_importance=0.0)


def validator(match, ctx, audience="analyst"):
    return Validator(match, ctx, audience)


# ---- rule 1: score-state verbs -------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text, cites",
    [
        ("B took the lead at 11'.", ["m_001"]),
        ("A equalised at 26'.", ["m_002"]),
        ("Alan Archer levelled at 26', then A went ahead at 86'.", ["m_002", "m_005"]),
        ("B won the shootout 1-0.", ["m_006"]),
        ("A won 2-1 in normal time.", ["m_005"]),
        ("A and B drew 1-1 at 26'.", ["m_002"]),
        ("Dan Dale won a penalty.", ["m_006"]),
    ],
)
def test_true_score_claims_pass(match, ctx, text, cites):
    assert validator(match, ctx).check_score_verbs(text, cites) == []


@pytest.mark.parametrize(
    "text, cites, expect",
    [
        ("A took the lead at 11'.", ["m_001"], "A 'took the lead'"),  # B scored it
        ("B equalised at 11'.", ["m_001"], "'equalised'"),  # it was a go-ahead goal, not a levelling one
        ("A took the lead at 26'.", ["m_002", "m_005"], "'took the lead'"),  # 26' levelled; 86' is a different minute
        ("A took the lead.", ["m_004"], "no goal moment is cited"),
        ("A won the shootout.", ["m_006"], "B won it"),
        ("A won 1-1.", ["m_002"], "level score"),
        ("A and B drew 2-1.", ["m_005"], "not level"),
        ("A and B drew.", ["m_005"], "not level at 90"),
    ],
)
def test_false_score_claims_fail(match, ctx, text, cites, expect):
    errors = validator(match, ctx).check_score_verbs(text, cites)
    assert errors and any(expect in e for e in errors), errors


def test_effect_names_for_each_goal_kind(match):
    effects = {m.id: rules._effect(m) for m in match.moments if m.type == "goal"}
    assert effects == {"m_001": "put the scoring team ahead", "m_002": "levelled the score", "m_005": "put the scoring team ahead"}


# ---- rule 2: shootout claims ---------------------------------------------------------------------------
def test_shootout_kicks_are_given_to_the_model_as_an_ordered_list(ctx):
    assert "kick 1: B, Cal Cross, scored" in ctx.text
    assert "kick 2: A, Dan Dale, saved" in ctx.text


@pytest.mark.parametrize(
    "text",
    [
        "Cal Cross took the first kick and scored in the shootout.",
        "Dan Dale took the second kick and it was saved.",
        "In the shootout Cal Cross scored while Dan Dale was saved.",
        "Dan Dale's penalty was saved in the shootout.",
        "B's opening kick was scored by Cal Cross.",
    ],
)
def test_true_shootout_claims_pass(match, ctx, text):
    assert validator(match, ctx).check_shootout(text, ["m_006"]) == []


@pytest.mark.parametrize(
    "text, expect",
    [
        ("Dan Dale took the first kick in the shootout.", "Dan Dale took kick 1"),
        ("Cal Cross took the second kick.", "Cal Cross took kick 2"),
        ("Dan Dale scored in the shootout.", "Dan Dale scored"),
        ("Cal Cross missed his penalty in the shootout.", "Cal Cross missed"),
        ("A's opening kick was taken by Dan Dale.", "Dan Dale took kick 1"),
        ("The sixth kick decided it in the shootout.", "had 2 kicks"),
    ],
)
def test_false_shootout_claims_fail(match, ctx, text, expect):
    errors = validator(match, ctx).check_shootout(text, ["m_006"])
    assert errors and any(expect in e for e in errors), errors


def test_shootout_rule_ignores_text_that_does_not_cite_the_shootout(match, ctx):
    assert validator(match, ctx).check_shootout("Dan Dale scored in the shootout.", ["m_004"]) == []


def test_two_takers_in_one_sentence_each_get_their_own_outcome(match, ctx):
    ok = "In the shootout Cal Cross scored and Dan Dale was saved."
    swapped = "In the shootout Dan Dale scored and Cal Cross was saved."
    v = validator(match, ctx)
    assert v.check_shootout(ok, ["m_006"]) == []
    assert len(v.check_shootout(swapped, ["m_006"])) == 2


# ---- rule 3: banned phrases ----------------------------------------------------------------------------
@pytest.mark.parametrize("word", ["title", "trophy", "champions", "history", "historic", "hosts", "favourites", "stadium", "crowd", "record"])
@pytest.mark.parametrize("audience", ["analyst", "broadcaster", "fan"])
def test_banned_phrases_fail_for_every_audience(match, ctx, word, audience):
    errors = validator(match, ctx, audience).check_wording(f"The {word} was on the line at 11'.")
    assert any(f"'{word}'" in e for e in errors), errors


def test_banned_phrases_match_whole_words_only(match, ctx):
    assert validator(match, ctx).check_wording("B recorded a shot and the historian nodded.") == []


def test_competition_name_is_exempt_from_the_banned_list():
    assert rules.check_banned_phrases("the Champions League final", "en", ("Champions League",)) == []
    assert rules.check_banned_phrases("the Champions League final", "en")


# ---- rule 4: opinion words -----------------------------------------------------------------------------
@pytest.mark.parametrize("word", ["dramatic", "well-taken", "well taken", "brilliant", "stunning", "superb", "Well-Placed"])
@pytest.mark.parametrize("audience", ["analyst", "broadcaster"])
def test_opinion_words_fail_for_analyst_and_broadcaster(match, ctx, word, audience):
    assert validator(match, ctx, audience).check_wording(f"A {word} goal at 11'.")


@pytest.mark.parametrize("word", ["dramatic", "brilliant", "stunning"])
def test_opinion_words_are_allowed_for_the_fan(match, ctx, word):
    assert validator(match, ctx, "fan").check_wording(f"A {word} goal at 11'.") == []


def test_banned_phrases_still_fail_for_the_fan_when_mixed_with_opinions(match, ctx):
    errors = validator(match, ctx, "fan").check_wording("A brilliant night for the hosts.")
    assert len(errors) == 1 and "'hosts'" in errors[0]


# ---- the rules feed the existing retry loop ------------------------------------------------------------
def retried(match, bad, audience="analyst"):
    provider = FakeProvider([bad, GOOD])
    recap, report = run_recap(match, audience, "medium", "en", provider)
    return recap, report, provider


@pytest.mark.parametrize(
    "index, text, cites, expect",
    [
        (0, "A took the lead through Ben Brook at 11' to make it 0-1.", ["m_001"], "took the lead"),
        (3, "Cal Cross missed his penalty in the shootout, which B won 1-0.", ["m_006"], "Cal Cross missed"),
        (3, "B won the shootout 1-0 and lifted the trophy.", ["m_006"], "trophy"),
        (0, "B took the lead through Ben Brook at 11' with a stunning strike to make it 0-1.", ["m_001"], "stunning"),
    ],
)
def test_each_rule_triggers_a_retry_with_its_error_in_the_prompt(match, index, text, cites, expect):
    recap, report, provider = retried(match, variant(index, text=text, cites=cites))
    assert report.method == "llm" and report.retried and not report.dropped
    assert any(expect in e for e in report.attempts[0].errors)
    assert expect in provider.calls[1]["user"]
    assert [p.text for p in recap.paragraphs] == [p["text"] for p in GOOD["paragraphs"]]


def test_opinion_word_passes_first_time_for_the_fan(match):
    bad = variant(0, text="B took the lead through Ben Brook at 11' with a stunning strike to make it 0-1.", cites=["m_001"])
    recap, report, provider = retried(match, bad, audience="fan")
    assert not report.retried and len(provider.calls) == 1 and "stunning" in recap.paragraphs[0].text


# ---- the wrong sentences that passed Phase 2 validation, on the real 2022 final -------------------------------
@pytest.mark.needs_data
@pytest.mark.parametrize(
    "audience, text, cites",
    [
        ("analyst", "France took the lead in the first half.", ["m_003"]),
        ("analyst", "France equalised in the 80th minute with a penalty from Kylian Mbappé.", ["m_003"]),
        ("broadcaster", "Lionel Messi converted a penalty, putting the hosts ahead in the 23rd minute.", ["m_001"]),
        ("broadcaster", "Argentina claimed the title after a dramatic shootout.", ["m_010"]),
        ("fan", "Messi scored the first penalty, Dybala and Paredes scored next, with France's Mbappé scoring.", ["m_010"]),
        ("fan", "Argentina won 3-3 after extra time.", ["m_010"]),
    ],
)
def test_phase_2_false_claims_are_now_caught(audience, text, cites):
    from matchlens import service

    real = service.get_match(3869685)
    v = Validator(real, build_context(real, min_importance=0.5), audience)
    assert v.check_text(text, cites)


# ---- shootout wording that must not trip the order rule -------------------------------------------------
def test_counted_groups_are_not_ordinal_claims(match, ctx):
    v = validator(match, ctx)
    assert v.check_shootout("B won after the first two kicks of the shootout.", ["m_006"]) == []


@pytest.mark.needs_data
@pytest.mark.parametrize(
    "text, ok",
    [
        ("Kingsley Coman saw France's second penalty saved in the shootout.", True),
        ("Kingsley Coman saw France's third penalty saved in the shootout.", False),
        ("Aurélien Tchouaméni missed France's third penalty in the shootout.", True),
        ("Lionel Messi took Argentina's first penalty in the shootout.", True),
        ("Lionel Messi took France's first penalty in the shootout.", False),
    ],
)
def test_team_ordinal_claims_on_the_real_shootout(text, ok):
    from matchlens import service

    real = service.get_match(3869685)
    v = Validator(real, build_context(real, min_importance=0.5), "analyst")
    assert (v.check_shootout(text, ["m_010"]) == []) is ok
