"""Fixes after Phase 3: written shootout paragraph, wording lists in the prompt, glossary, penalty wording, quality."""
import json

import pytest

from matchlens import config, loader, service
from matchlens.llm import FakeProvider
from matchlens.recap import glossary, rules
from matchlens.recap.context import build_context
from matchlens.recap.models import RecapRequest
from matchlens.recap.pipeline import get_explanation, get_recap
from matchlens.recap.shootout import shootout_paragraph
from matchlens.recap.validate import Validator

from .recap_fixtures import small_match
from .test_recap_pipeline import GOOD
from .test_translate import EXPLAIN, NAMES, router


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "generated")
    monkeypatch.setattr(config, "NAMES_DIR", tmp_path / "names")


@pytest.fixture(scope="module")
def match():
    return small_match()


# ---- 1. the shootout paragraph is deterministic ----------------------------------------------------------
@pytest.mark.parametrize("audience", config.AUDIENCES)
def test_shootout_paragraph_is_built_from_the_kicks_and_passes_the_validators(match, audience):
    para = shootout_paragraph(match, audience)
    assert para.cites == ["m_006"] and "B" in para.text and "Cal Cross" in para.text and "Dan Dale" in para.text
    v = Validator(match, build_context(match, min_importance=0.0), audience)
    assert v.check_paragraph(para.text, para.cites) == []
    assert shootout_paragraph(match, audience) == para  # same input, same text


@pytest.mark.needs_data
@pytest.mark.parametrize("audience", config.AUDIENCES)
def test_shootout_paragraph_on_the_real_matches_is_correct_in_every_kick(audience):
    checked = 0
    for entry in loader.load_index():
        real = service.get_match(entry["match_id"])
        para = shootout_paragraph(real, audience)
        if para is None:
            continue
        checked += 1
        moment = next(m for m in real.moments if m.type == "penalty_shootout")
        v = Validator(real, build_context(real, min_importance=0.0), audience)
        assert v.check_paragraph(para.text, para.cites) == [], para.text
        for k in moment.stats["kicks"]:
            assert f"Kick {k['order']}" in para.text and k["player"] in para.text
    assert checked >= 1


def test_the_model_never_sees_the_shootout_and_the_paragraph_is_added_last(match):
    from matchlens.recap.pipeline import run_recap

    provider = FakeProvider([GOOD])
    recap, report = run_recap(match, "fan", "medium", "en", provider)
    assert "penalty shootout |" not in provider.calls[0]["user"] and "m_006" not in provider.calls[0]["user"]
    assert recap.paragraphs[-1].cites == ["m_006"] and recap.paragraphs[-1].text.startswith("Then came the penalty shootout.")


def test_a_match_without_a_shootout_gets_no_extra_paragraph():
    from tests.helpers import AWAY, HOME, META, ev, period_end, shot  # noqa: F401  (documents the shape only)

    from matchlens.recap.pipeline import run_recap

    full = small_match()
    no_shootout = type(full)(full.meta, [e for e in full.events if e.period != 5], [m for m in full.moments if m.type != "penalty_shootout"], full.summary)
    recap, _ = run_recap(no_shootout, "analyst", "medium", "en", FakeProvider([GOOD]))
    assert [p.cites for p in recap.paragraphs] == [p["cites"] for p in GOOD["paragraphs"]]


# ---- 2. wording lists are in the prompt -------------------------------------------------------------------
def test_banned_words_are_in_every_prompt_and_opinion_words_only_for_analyst_and_broadcaster():
    for audience in config.AUDIENCES:
        text = rules.wording_instructions(audience)
        assert all(w in text for w in ("trophy", "hosts", "stadium"))
    assert "dramatic" in rules.wording_instructions("analyst") and "dramatic" in rules.wording_instructions("broadcaster")
    assert "dramatic" not in rules.wording_instructions("fan")


def test_wording_lists_reach_the_recap_and_explain_prompts(match):
    provider = FakeProvider([GOOD])
    get_recap(match, RecapRequest(audience="broadcaster"), provider)
    assert "Never use these opinion words" in provider.calls[0]["user"]
    fan = FakeProvider([GOOD])
    get_recap(match, RecapRequest(audience="fan"), fan)
    assert "Never use these words" in fan.calls[0]["user"] and "opinion words" not in fan.calls[0]["user"]
    ex = FakeProvider([{"moment_id": "m_002", "why_it_mattered": "Alan Archer levelled the score at 26'.", "context": "B led 0-1 before it.", "cites": ["m_002"]}])
    get_explanation(match, "m_002", "analyst", "en", ex)
    assert "Never use these opinion words" in ex.calls[0]["user"]


# ---- 4. in-play penalties and shootout kicks cannot be mixed ----------------------------------------------
@pytest.fixture(scope="module")
def real_validator():
    pytest.importorskip("matchlens")
    real = service.get_match(loader.find_match(config.DEFAULT_MATCH_QUERY, offline_only=True)["match_id"])
    return lambda audience="analyst": Validator(real, build_context(real, min_importance=0.5), audience)


@pytest.mark.needs_data
def test_context_tells_the_model_which_kind_of_penalty(real_validator):
    ctx = real_validator().ctx.text
    assert "goal kind: penalty in regular time" in ctx  # 23' and 80'
    assert "goal kind: penalty in extra time" in ctx  # 118'
    assert "goal kind: penalty\n" not in ctx


@pytest.mark.needs_data
@pytest.mark.parametrize(
    "text, cites, ok",
    [
        ("Lionel Messi scored a penalty in regular time at 23'.", ["m_001"], True),
        ("Kylian Mbappé scored a penalty in extra time at 118'.", ["m_008"], True),
        ("Lionel Messi scored a penalty at 23'.", ["m_001"], False),
        ("Lionel Messi scored from the penalty spot at 23'.", ["m_001"], False),
        ("Kylian Mbappé scored a penalty in regular time at 118'.", ["m_008"], False),  # it was in extra time
        ("Argentina won 4-2 on penalties.", ["m_006"], True),
        ("Argentina won 4-2 in the shootout.", ["m_006"], True),
    ],
)
def test_penalty_wording(real_validator, text, cites, ok):
    v = real_validator()
    errors = rules.check_penalty_wording(text, cites, v.ctx.moments)
    assert (errors == []) is ok, errors


def test_a_parenthesised_headline_penalty_is_not_rewritten():
    assert rules.check_penalty_wording("France goal: Kylian Mbappé (penalty), 80'.", ["m_003"], {}) == []


# ---- 3. glossary -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("lang", ["hi", "ta"])
def test_glossary_files_cover_every_pattern(lang):
    entries = glossary.load_glossary(lang)
    assert set(entries) == set(glossary.PATTERNS) and len(entries) == 20
    for term, entry in entries.items():
        assert entry["use"] and isinstance(entry["accept"], list), term
    raw = json.loads((config.GLOSSARY_DIR / f"{lang}.json").read_text(encoding="utf-8"))
    assert raw["reviewed"] is False


def test_terms_are_found_in_the_english():
    found = glossary.terms_in(
        "France took the lead, then equalised. Mbappé scored a penalty in extra time and the shootout ended in a draw; the goalkeeper saved kick 3."
    )
    assert {"took the lead", "equaliser", "penalty", "extra time", "penalty shootout", "draw", "goalkeeper", "save", "shootout kick"} <= set(found)
    assert glossary.terms_in("Argentina 3-3 France.") == []


@pytest.mark.parametrize("lang", ["hi", "ta"])
def test_a_missing_glossary_form_is_an_error_and_a_present_one_passes(lang):
    entry = glossary.load_glossary(lang)["extra time"]
    english = "France equalised in extra time."
    eq = glossary.load_glossary(lang)["equaliser"]["use"]
    assert glossary.check_terms(english, f"{eq} {entry['use']}", lang) == []
    errors = glossary.check_terms(english, eq, lang)
    assert errors == [f"must translate 'extra time' as {entry['use']}"]
    assert glossary.check_terms(english, f"{entry['use']} {eq}".replace(eq, entry["accept"][0] if False else eq), lang) == []


def test_glossary_forms_reach_the_translate_prompt_and_the_translation_is_checked(match):
    from matchlens.recap.models import Recap, RecapParagraph
    from matchlens.recap.translate import translate_recap

    english = Recap(title="A v B", paragraphs=[RecapParagraph(text="Alan Archer equalised at 26'.", cites=["m_002"])])
    wrong = lambda source, attempt: "शब्द 26" if "Alan Archer" in source else None  # noqa: E731  (no glossary form, no name)
    provider = FakeProvider([router("hi", NAMES, GOOD, EXPLAIN, override=wrong)])
    out, report = translate_recap(match, english, "hi", "analyst", provider)
    prompt = next(c["user"] for c in provider.calls if "ENGLISH PARAGRAPH" in c["user"])
    assert "- equaliser -> बराबरी" in prompt
    assert report.units[1].status == "english_fallback" and any("must translate 'equaliser'" in e for e in report.units[1].errors)


# ---- 5. Tamil names ------------------------------------------------------------------------------------------
def test_the_known_tamil_name_errors_are_fixed():
    names = json.loads((config.ROOT / "data" / "names" / "ta.json").read_text(encoding="utf-8"))["names"]
    assert names["France"] == "பிரான்ஸ்"
    assert names["Ángel Di María"] == "ஏஞ்சல் டி மரியா"
    assert names["Marcus Thuram"] == "மார்க்கஸ் துராம்"
    assert "தூரம்" not in " ".join(names.values())  # "distance"
    assert "கோமான்" not in " ".join(names.values())  # "lord"


# ---- 6. quality ---------------------------------------------------------------------------------------------
def test_quality_per_language_is_in_config_and_in_results(match, tmp_path):
    assert config.LANGUAGE_QUALITY == {"en": "stable", "hi": "machine-translated", "ta": "experimental"}
    for lang, quality in config.LANGUAGE_QUALITY.items():
        provider = FakeProvider([router(lang, NAMES, GOOD, EXPLAIN)])
        res = get_recap(match, RecapRequest(language=lang), provider)
        assert res.quality == quality and json.loads(res.model_dump_json())["quality"] == quality
        ex = get_explanation(match, "m_002", "analyst", lang, provider)
        assert ex.quality == quality


# ---- degenerate output: the same summary repeated in every paragraph, "France 2-2 France" ----------------------
def test_a_repeated_sentence_is_rejected_in_the_later_paragraphs(match):
    from matchlens.recap.pipeline import run_recap

    same = "B took the lead through Ben Brook at 11' to make it 0-1."
    bad = {"title": GOOD["title"], "paragraphs": [{"text": same, "cites": ["m_001"]}, {"text": same + " Alan Archer levelled at 26'.", "cites": ["m_001", "m_002"]}]}
    recap, report = run_recap(match, "analyst", "medium", "en", FakeProvider([bad, GOOD]))
    assert report.retried and any("repeats a sentence" in e for e in report.attempts[0].errors)
    assert [p.text for p in recap.paragraphs[:-1]] == [p["text"] for p in GOOD["paragraphs"]]


def test_score_lines_must_be_real_scores_of_two_different_teams(match):
    v = Validator(match, build_context(match, min_importance=0.0))
    assert v.check_text("A 1-1 B at 26'.", ["m_002"]) == []
    assert any("same team twice" in e for e in v.check_text("A 1-1 A at 26'.", ["m_002"]))
    assert any("not a score shown" in e for e in v.check_text("B 3-0 A at 26'.", ["m_002"]))


# ---- coverage, no shootout in model text ------------------------------------------------------------------
def test_every_goal_must_be_cited_or_the_retry_lists_the_missing_ones(match):
    from matchlens.recap.pipeline import run_recap

    partial = {"title": GOOD["title"], "paragraphs": GOOD["paragraphs"][:1] + GOOD["paragraphs"][2:]}  # no paragraph cites m_002 and m_005
    recap, report = run_recap(match, "analyst", "medium", "en", FakeProvider([partial, GOOD]))
    assert report.retried and any(e.startswith("Coverage: no paragraph cites m_002") and "m_005" in e for e in report.attempts[0].errors)
    assert not report.notes or not any("not covered" in n for n in report.notes)
    assert {c for p in recap.paragraphs for c in p.cites} >= {"m_001", "m_002", "m_005", "m_006"}


def test_a_goal_still_uncovered_after_the_retry_is_noted_not_hidden(match):
    from matchlens.recap.pipeline import run_recap

    partial = {"title": GOOD["title"], "paragraphs": GOOD["paragraphs"][:1]}
    _, report = run_recap(match, "analyst", "medium", "en", FakeProvider([partial]))
    assert any(n.startswith("not covered after the retry") and "m_002" in n for n in report.notes)


@pytest.mark.parametrize(
    "text, cites",
    [
        ("B took the lead through Ben Brook at 11' and later won on penalties.", ["m_001"]),
        ("B took the lead through Ben Brook at 11'. The shootout went to B.", ["m_001"]),
        ("Cal Cross took the first kick.", ["m_001"]),
    ],
)
def test_model_paragraphs_may_not_mention_the_shootout(match, text, cites):
    from matchlens.recap.pipeline import run_recap

    bad = {"title": GOOD["title"], "paragraphs": [{"text": text, "cites": cites}, *GOOD["paragraphs"][1:]]}
    _, report = run_recap(match, "analyst", "medium", "en", FakeProvider([bad, GOOD]))
    assert report.retried and any("may not mention the penalty shootout" in e for e in report.attempts[0].errors)


def test_model_paragraphs_may_not_cite_the_shootout_moment(match):
    from matchlens.recap.pipeline import run_recap

    bad = {"title": GOOD["title"], "paragraphs": [{"text": "B took the lead through Ben Brook at 11'.", "cites": ["m_001", "m_006"]}, *GOOD["paragraphs"][1:]]}
    _, report = run_recap(match, "analyst", "medium", "en", FakeProvider([bad, GOOD]))
    assert any("m_006" in e for e in report.attempts[0].errors)


def test_the_written_shootout_paragraph_is_validated_and_there_is_no_warning(match):
    from matchlens.recap.pipeline import run_recap

    _, report = run_recap(match, "fan", "medium", "en", FakeProvider([GOOD]))
    assert not any("WARNING" in n for n in report.notes)


def test_won_in_a_sentence_with_an_in_play_penalty_is_not_a_shootout_claim(match):
    v = Validator(match, build_context(match, min_importance=0.0))
    assert v.check_score_verbs("A won 2-1 after a penalty in regular time.", ["m_005"]) == []
    assert any("no shootout" in e for e in rules.check_score_verbs(
        "B won the shootout.", ["m_005"], v.ctx.moments, match.moments, match.meta, type("S", (), {"shootout": None, "final_score": (2, 1), "score_after_90": (2, 1)})()))
