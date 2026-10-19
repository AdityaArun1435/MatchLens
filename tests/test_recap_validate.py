import pytest

from matchlens.recap.context import build_context
from matchlens.recap.validate import Validator, numbers_in, strip_ids

from .recap_fixtures import small_match


@pytest.fixture(scope="module")
def match():
    return small_match()


@pytest.fixture(scope="module")
def v(match):
    return Validator(match, build_context(match, min_importance=0.0))


def test_fixture_moments_are_what_the_tests_expect(match):
    assert [(m.id, m.type, m.clock_label) for m in match.moments] == [
        ("m_001", "goal", "11'"), ("m_002", "goal", "26'"), ("m_003", "momentum_swing", "25'"),
        ("m_004", "big_chance_missed", "61'"), ("m_005", "goal", "86'"), ("m_006", "penalty_shootout", "Pens"),
    ]


def ids_of(match, type_, n=0):
    return [m.id for m in match.moments if m.type == type_][n]


def test_valid_paragraph_passes(match, v):
    g = ids_of(match, "goal", 0)
    assert v.check_paragraph("Ben Brook scored for B at 11' to make it 0-1.", [g]) == []


def test_unknown_and_unshown_citations(match, v):
    errs = v.check_cites(["m_099"])
    assert errs == ["cites unknown moment id 'm_099'"]
    assert v.check_cites([]) and "no citations" in v.check_cites([])[0]
    ctx = build_context(match, min_importance=0.9)  # hides lower moments
    hidden = next(m.id for m in match.moments if m.importance < 0.9)
    errs = Validator(match, ctx).check_cites([hidden])
    assert errs and "not part of the data" in errs[0]
    assert v.check_cites(["m_001"], must_include="m_002") == ["must cite m_002"]


def test_invented_numbers_are_caught(match, v):
    g = ids_of(match, "goal", 0)
    assert any("0.99" in e for e in v.check_numbers("Ben Brook scored with an xG of 0.99 at 11'.", [g]))
    assert any("5-4" in e for e in v.check_numbers("It finished 5-4 to B.", [g]))
    assert any("73" in e for e in v.check_numbers("Ben Brook scored in the 73rd minute.", [g]))
    assert any("90+3'" in e for e in v.check_numbers("Late drama at 90+3'.", [g]))
    assert any("four" in e or "4" in e for e in v.check_numbers("B scored four goals.", [g]))


def test_numbers_from_cited_moments_summary_and_variants_pass(match, v):
    g = ids_of(match, "goal", 0)
    assert v.check_numbers("Ben Brook scored at 11', in the 11th minute, 0-1 to B (xG 0.31).", [g]) == []
    assert v.check_numbers("It was 0–1 and later 2–1 after 90 minutes.", [g]) == []  # en dash, summary scores
    assert v.check_numbers("Ben Brook scored at 11', xG 0.310.", [g]) == []


def test_number_must_be_in_cited_moments_not_just_any_moment(match, v):
    first, second = ids_of(match, "goal", 0), ids_of(match, "goal", 1)
    clock_of_second = next(m.clock_label for m in match.moments if m.id == second)
    assert v.check_numbers(f"A equalised at {clock_of_second}", [first]), "minute of an uncited moment must fail"
    assert v.check_numbers(f"A equalised at {clock_of_second}", [second]) == []


def test_number_extraction_kinds():
    assert numbers_in("90+3' and 2-2, xG 0.78, 56%, 81st minute") == {
        ("m", 90, 3), ("s", 2, 2), ("d", __import__("decimal").Decimal("0.78")), ("i", 56), ("i", 81),
    }
    assert ("i", 2) in numbers_in("scored two goals") and ("i", 2) in numbers_in("scored twice")
    assert numbers_in("one of the best, in the 2nd half") == set()  # not counts


def test_invented_player_and_unlisted_player_are_caught(match, v):
    g = ids_of(match, "goal", 0)
    assert any("Ronaldo" in e for e in v.check_names("Ben Brook scored and Ronaldo assisted.", [g]))
    assert any("Alan Archer" in e for e in v.check_names("Alan Archer replied.", [g])), "real player, not in cited moment"
    assert v.check_names("Ben Brook scored. Brook was alone.", [g]) == []  # surname of a cited player
    assert v.check_names("Ben Brook, B's attacker, scored; A's keeper dived.", [g]) == []


def test_name_matching_ignores_accents_case_and_possessive(match, v):
    g = ids_of(match, "goal", 0)
    assert v.check_names("BEN BROOK's finish and ben brook again", [g]) == []


def test_title_may_not_name_players_or_invent_numbers(match, v):
    assert v.check_title("A v B: 2-1 after 90 minutes") == []
    assert v.check_title("Brook wins it for B") != []
    assert v.check_title("A v B ends 7-6") != []


def test_ids_in_text_are_stripped():
    text, changed = strip_ids("Ben Brook scored [m_001] at 11' (m_002).")
    assert changed and "m_00" not in text and text.startswith("Ben Brook scored")
    assert strip_ids("Plain text.") == ("Plain text.", False)


@pytest.mark.parametrize("text", [
    "Ronaldo scored at 11'.",                      # lone invented surname opening the sentence
    "Neymar's finish at 11' made it 0-1.",
    "B led at 11'. Neymar then missed.",
    "Cristiano Ronaldo scored at 11'.",
])
def test_invented_name_is_caught_even_at_the_start_of_a_sentence(match, v, text):
    g = ids_of(match, "goal", 0)
    assert any("not a player or team" in e or "who is not named" in e for e in v.check_names(text, [g])), text


@pytest.mark.parametrize("text", [
    "Meanwhile, Ben Brook had scored at 11'.",
    "Then Ben Brook scored at 11' for a 0-1 lead.",
    "Brilliantly, B went ahead at 11'.",
    "Moments earlier, A had nothing at 0-0 and Ben Brook struck at 11'.",
    "After 11' it was 0-1. Late on, A pushed.",
    "A trailed 0-1 after Ben Brook scored at 11'.",
])
def test_ordinary_sentence_openers_are_not_flagged(match, v, text):
    g = ids_of(match, "goal", 0)
    assert v.check_names(text, [g]) == [], text
