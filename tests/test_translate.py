"""Phase 3: Hindi and Tamil are translations of validated English, checked paragraph by paragraph (no real model)."""
import json

import pytest

from matchlens import config
from matchlens.llm import FakeProvider
from matchlens.recap import names_i18n, translate
from matchlens.recap.models import Recap, RecapParagraph, RecapRequest
from matchlens.recap.pipeline import get_explanation, get_recap, run_explanation, run_recap
from matchlens.recap.translate import TranslationChecker, back_translate, normalise_digits, translate_recap

from .recap_fixtures import small_match
from .test_recap_pipeline import GOOD
from .translate_helpers import FILLER, native, router

NAMES = ["A", "B", "Ben Brook", "Alan Archer", "Dan Dale", "Cal Cross"]
LANGS = ["hi", "ta"]
ENGLISH = Recap(title=GOOD["title"], paragraphs=[RecapParagraph(**p) for p in GOOD["paragraphs"]])
EXPLAIN = {
    "moment_id": "m_002",
    "why_it_mattered": "Alan Archer levelled the score at 26', making it 1-1.",
    "context": "Ben Brook had put B ahead at 11'.",
    "cites": ["m_002", "m_001"],
}


@pytest.fixture(scope="module")
def match():
    return small_match()


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "generated")
    monkeypatch.setattr(config, "NAMES_DIR", tmp_path / "names")


def provider_for(lang, **kw):
    return FakeProvider([router(lang, NAMES, GOOD, EXPLAIN, **kw)])


def run(match, lang, audience="analyst", **kw):
    provider = provider_for(lang, **kw)
    recap, report = translate_recap(match, ENGLISH, lang, audience, provider)
    return recap, report, provider


# ---- name maps -----------------------------------------------------------------------------------------
@pytest.mark.parametrize("lang", LANGS)
def test_name_map_is_generated_once_and_saved_as_utf8_json(match, lang):
    name_map, added, missing = names_i18n.ensure_names(match, lang, provider_for(lang))
    assert missing == [] and set(added) == set(NAMES)
    body = json.loads((config.NAMES_DIR / f"{lang}.json").read_text(encoding="utf-8"))
    assert body["reviewed"] is False and body["names"]["Ben Brook"] == native("Ben Brook", lang)
    again = FakeProvider([lambda *a: pytest.fail("a complete map must not call the model")])
    _, added, _ = names_i18n.ensure_names(match, lang, again)
    assert added == []


def test_hand_corrections_are_never_overwritten_or_asked_for_again(match):
    config.NAMES_DIR.mkdir()
    (config.NAMES_DIR / "hi.json").write_text(
        json.dumps({"language": "hi", "reviewed": True, "names": {"Ben Brook": "बेन ब्रुक"}}, ensure_ascii=False), encoding="utf-8"
    )
    provider = provider_for("hi")
    name_map, added, _ = names_i18n.ensure_names(match, "hi", provider)
    assert name_map.names["Ben Brook"] == "बेन ब्रुक" and "Ben Brook" not in added and name_map.reviewed
    assert "- Ben Brook" not in provider.calls[0]["user"]
    assert json.loads((config.NAMES_DIR / "hi.json").read_text(encoding="utf-8"))["names"]["Ben Brook"] == "बेन ब्रुक"


def test_names_not_in_the_right_script_are_retried_then_reported_missing(match):
    provider = provider_for("hi", names_override=lambda a: {**a, "Dan Dale": "Dan Dale"})
    name_map, added, missing = names_i18n.ensure_names(match, "hi", provider)
    assert missing == ["Dan Dale"] and "Dan Dale" not in name_map.names and len(provider.calls) == 2


# ---- the happy path --------------------------------------------------------------------------------------
@pytest.mark.parametrize("lang", LANGS)
def test_good_translation_keeps_cites_numbers_and_order(match, lang):
    recap, report, provider = run(match, lang)
    assert [p.cites for p in recap.paragraphs] == [p["cites"] for p in GOOD["paragraphs"]]
    assert all(p.language == lang and p.note is None for p in recap.paragraphs)
    assert [u.status for u in report.units] == ["translated"] * 5 and report.fallbacks == 0 and report.retries == 0
    assert "0-1" in recap.paragraphs[0].text and "11" in recap.paragraphs[0].text
    assert native("Ben Brook", lang) in recap.paragraphs[0].text
    assert FILLER[lang] in recap.title


# ---- digits, numbers ------------------------------------------------------------------------------------
def test_non_western_digits_are_converted_not_rejected(match):
    assert normalise_digits("११ मिनट, ௨௬") == ("11 मिनट, 26", 4)

    def devanagari_digits(source, attempt):
        from .translate_helpers import fake_translation

        return fake_translation(source, "hi", NAMES).replace("11", "११") if "11'" in source else None

    recap, report, _ = run(match, "hi", override=devanagari_digits)
    assert "11" in recap.paragraphs[0].text and "११" not in recap.paragraphs[0].text
    assert any("converted" in n for u in report.units for n in u.notes)


def corrupt(find, replace, once=True):
    """Override: the first answer for the paragraph containing `find` has a wrong number; the retry is fine."""
    from .translate_helpers import fake_translation

    def override(source, attempt):
        if find in source and (attempt == 1 or not once):
            return fake_translation(source, "hi", NAMES).replace(find.split("'")[0], replace) if find in source else None
        return None

    return override


def test_a_changed_number_is_caught_and_the_retry_gets_the_error(match):
    recap, report, provider = run(match, "hi", override=corrupt("11'", "12"))
    unit = report.units[1]
    assert unit.status == "translated" and unit.attempts == 2 and report.retries == 1
    assert any("12" in e and "not in the English" in e for e in unit.errors) and any("11" in e and "missing" in e for e in unit.errors)
    retry = next(c["user"] for c in provider.calls if "was rejected" in c["user"])
    assert "not in the English" in retry and "missing" in retry
    assert "11" in recap.paragraphs[0].text


def test_a_number_written_as_a_word_counts_as_missing(match):
    word = lambda source, attempt: "शब्द शब्द" if attempt == 1 and "26'" in source else None  # noqa: E731
    _, report, _ = run(match, "hi", override=word)
    unit = next(u for u in report.units if u.unit == "paragraph 2")
    assert unit.attempts == 2 and any("Western digits" in e for e in unit.errors)


# ---- names, script, wording -----------------------------------------------------------------------------
def test_a_name_not_spelt_as_in_the_map_is_caught(match):
    from .translate_helpers import fake_translation

    def misspelt(source, attempt):
        if attempt == 1 and "Ben Brook" in source:
            return fake_translation(source, "hi", NAMES).replace(native("Ben Brook", "hi"), "बेन")
        return None

    recap, report, _ = run(match, "hi", override=misspelt)
    unit = report.units[1]
    assert unit.attempts == 2 and any(f"must write Ben Brook as {native('Ben Brook', 'hi')}" in e for e in unit.errors)


def test_a_name_left_in_latin_letters_is_caught(match):
    latin = lambda source, attempt: "Ben Brook 11 शब्द 0-1 बी" if attempt == 1 and "Ben Brook" in source else None  # noqa: E731
    _, report, _ = run(match, "hi", override=latin)
    assert any("Latin" in e for e in report.units[1].errors)


def test_a_name_that_is_not_in_the_english_is_caught(match):
    from .translate_helpers import fake_translation

    extra = lambda source, attempt: (  # noqa: E731
        fake_translation(source, "hi", NAMES) + " " + native("Cal Cross", "hi") if attempt == 1 and "26'" in source else None
    )
    _, report, _ = run(match, "hi", override=extra)
    assert any("who is not in the English text" in e for e in report.units[2].errors)


def test_text_in_the_wrong_script_is_caught(match):
    english_only = lambda source, attempt: source if attempt == 1 and "26'" in source else None  # noqa: E731
    _, report, _ = run(match, "hi", override=english_only)
    assert any("not written in Hindi script" in e for e in report.units[2].errors)


@pytest.fixture()
def checker(match):
    name_map, _, _ = names_i18n.ensure_names(match, "hi", provider_for("hi"))
    return lambda audience, lang="hi": TranslationChecker(match, lang, audience, names_i18n.load_map("hi"))


def test_banned_and_opinion_words_in_hindi(checker):
    source = "Ben Brook scored at 11'."
    base = f"{native('Ben Brook', 'hi')} 11 शब्द"
    assert checker("analyst").check(source, base) == []
    assert any("banned" in e for e in checker("fan").check(source, base + " ट्रॉफी"))  # banned for every audience
    assert any("opinion" in e for e in checker("analyst").check(source, base + " शानदार"))
    assert any("opinion" in e for e in checker("broadcaster").check(source, base + " शानदार"))
    assert checker("fan").check(source, base + " शानदार") == []  # opinion words are allowed for the fan


def test_tamil_world_cup_is_exempt_from_the_trophy_stem():
    from matchlens.recap.rules import check_banned_phrases

    assert check_banned_phrases("உலகக் கோப்பை இறுதிப் போட்டி", "ta") == []
    assert check_banned_phrases("அவர்கள் கோப்பை வென்றனர்", "ta")


# ---- failure: English with a note, never dropped -------------------------------------------------------------
@pytest.mark.parametrize("lang", LANGS)
def test_a_paragraph_that_fails_twice_is_shown_in_english_with_a_note(match, lang):
    always_wrong = lambda source, attempt: "शब्द 99" if "26'" in source else None  # noqa: E731
    recap, report, provider = run(match, lang, override=always_wrong)
    assert len(recap.paragraphs) == len(ENGLISH.paragraphs)
    bad = recap.paragraphs[1]
    assert bad.text == ENGLISH.paragraphs[1].text and bad.language == "en"
    assert bad.note == config.TRANSLATION_FALLBACK_NOTES[lang] and "Shown in English" in bad.note
    unit = report.units[2]
    assert unit.status == "english_fallback" and unit.attempts == 2 and report.fallbacks == 1 and unit.errors
    assert all(p.language == lang for i, p in enumerate(recap.paragraphs) if i != 1)


def test_an_unmapped_name_falls_back_without_calling_the_model_for_that_paragraph(match):
    provider = provider_for("hi", names_override=lambda a: {k: v for k, v in a.items() if k != "Cal Cross"})
    recap, report = translate_recap(match, ENGLISH, "hi", "analyst", provider)
    assert report.names_missing == ["Cal Cross"]
    unit = next(u for u in report.units if u.unit == "paragraph 4")  # "Cal Cross" is not in this paragraph
    assert unit.status == "translated"
    english = Recap(title="t", paragraphs=[RecapParagraph(text="Cal Cross scored in the shootout 1-0.", cites=["m_006"])])
    out, rep = translate_recap(match, english, "hi", "analyst", provider)
    assert rep.units[1].status == "english_fallback" and rep.units[1].attempts == 0 and "Cal Cross" in rep.units[1].errors[0]
    assert out.paragraphs[0].text == english.paragraphs[0].text and out.paragraphs[0].note


def test_a_failed_title_keeps_the_english_title(match):
    bad_title = lambda source, attempt: "शब्द 7" if source == ENGLISH.title else None  # noqa: E731
    recap, report, _ = run(match, "hi", override=bad_title)
    assert recap.title == ENGLISH.title and report.units[0].status == "english_fallback"


# ---- through the cached pipeline -------------------------------------------------------------------------------
def test_generation_is_english_only(match):
    with pytest.raises(ValueError, match="English only"):
        run_recap(match, "analyst", "medium", "hi", provider_for("hi"))
    with pytest.raises(ValueError, match="English only"):
        run_explanation(match, "m_002", "analyst", "ta", provider_for("ta"))


@pytest.mark.parametrize("lang", LANGS)
def test_get_recap_translates_the_validated_english_and_caches_each_language(match, lang):
    provider = provider_for(lang)
    res = get_recap(match, RecapRequest(language=lang), provider)
    assert res.language == lang and res.source_recap.title == GOOD["title"] and not res.cached
    assert res.report.method == "llm" and res.report.translation.language == lang and res.report.translation.fallbacks == 0
    assert [p.cites for p in res.recap.paragraphs] == [p["cites"] for p in GOOD["paragraphs"]]
    calls = len(provider.calls)
    assert get_recap(match, RecapRequest(language=lang), provider).cached and len(provider.calls) == calls
    english = get_recap(match, RecapRequest(language="en"), provider)
    assert english.cached and english.language == "en" and english.recap.paragraphs[0].language is None


def test_other_languages_do_not_share_a_cache_entry(match):
    provider = provider_for("hi")
    get_recap(match, RecapRequest(language="hi"), provider)
    assert not get_recap(match, RecapRequest(language="ta"), provider_for("ta")).cached


def test_correcting_a_name_by_hand_invalidates_the_cached_translation(match):
    provider = provider_for("hi")
    get_recap(match, RecapRequest(language="hi"), provider)
    path = config.NAMES_DIR / "hi.json"
    body = json.loads(path.read_text(encoding="utf-8"))
    body["names"]["Ben Brook"] = "बेन ब्रुक"
    path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    again = get_recap(match, RecapRequest(language="hi"), provider)
    assert not again.cached  # the router writes the old spelling, so this paragraph now needs its retry or falls back
    assert again.report.translation.units[1].attempts == 2


def test_a_template_fallback_english_is_translated_too_but_never_cached(match):
    from matchlens.llm import LLMError

    provider = FakeProvider([LLMError("boom"), router("hi", NAMES)])
    # first English call fails twice (fallback template), later calls are the translation router
    provider = FakeProvider([LLMError("boom"), LLMError("boom"), router("hi", NAMES)])
    res = get_recap(match, RecapRequest(language="hi"), provider)
    assert res.report.method == "fallback" and res.report.translation is not None
    assert not get_recap(match, RecapRequest(language="hi"), FakeProvider([LLMError("boom")])).cached


def test_explanation_fields_are_translated_with_the_same_checks(match):
    res = get_explanation(match, "m_002", "analyst", "hi", provider_for("hi"))
    assert res.language == "hi" and res.explanation.language == "hi" and res.source_explanation.why_it_mattered == EXPLAIN["why_it_mattered"]
    assert res.explanation.cites == EXPLAIN["cites"] and res.explanation.notes == []
    assert [u.unit for u in res.report.translation.units] == ["why_it_mattered", "context"]


def test_explanation_field_failure_stays_in_english_with_a_note(match):
    always_wrong = lambda source, attempt: "शब्द 99" if "Ben Brook" in source else None  # noqa: E731
    res = get_explanation(match, "m_002", "analyst", "ta", provider_for("ta", override=always_wrong))
    assert res.explanation.context == EXPLAIN["context"] and res.explanation.notes and "context" in res.explanation.notes[0]


def test_back_translation_is_returned_without_validation(match):
    assert back_translate("शब्द 11", "hi", provider_for("hi")) == "BACK: शब्द 11"
    assert translate.script_share("शब्द 11 abc", "hi") == pytest.approx(4 / 7)  # letters and combining marks; digits do not count


def test_number_words_are_given_to_the_model_as_digits_but_checked_against_the_original():
    from matchlens.recap.translate import digitise_number_words

    assert digitise_number_words("France scored two goals in 94 seconds, Mbappé twice.") == "France scored 2 goals in 94 seconds, Mbappé 2 times."
    assert digitise_number_words("Mbappé scored a brace, then a hat-trick.") == "Mbappé scored 2 goals, then 3 goals."


def test_the_model_sees_digits_where_the_english_has_number_words(match):
    english = Recap(title="t", paragraphs=[RecapParagraph(text="Ben Brook scored twice, at 11' and 26'.", cites=["m_001"])])
    provider = provider_for("hi")
    out, report = translate_recap(match, english, "hi", "analyst", provider)
    seen = [c["user"] for c in provider.calls if "ENGLISH PARAGRAPH" in c["user"]][0]
    assert "scored 2 times" in seen and report.units[1].status == "translated"


def test_a_digit_for_a_spelt_out_ordinal_or_number_is_not_an_invented_number():
    check = TranslationChecker._check_numbers
    assert check("Messi scored the second spot-kick.", "शब्द 2 शब्द") == []  # "second" -> 2
    assert check("Argentina scored four penalties, France two.", "शब्द 4 शब्द, शब्द 2") == []
    assert check("Messi scored the second spot-kick.", "शब्द 3 शब्द")  # a different number is still caught
    assert check("Messi scored at 23'.", "शब्द 23 शब्द 2")  # no number word in the English to explain the 2
    assert check("Argentina scored four penalties.", "शब्द शब्द")  # a number written as a word still counts as missing


def test_a_multi_word_name_in_the_english_may_not_shrink_to_its_last_word(match):
    """"Alan Archer" (two words in the English) needs the full Hindi name or its surname, never a stray first-name word."""
    names = names_i18n.NameMap("hi", {n: native(n, "hi") for n in NAMES})
    checker = TranslationChecker(match, "hi", "analyst", names)
    full, surname = native("Alan Archer", "hi"), native("Alan Archer", "hi").split()[-1]
    first = native("Alan Archer", "hi").split()[0]
    source = "Alan Archer levelled at 26'."
    assert checker.check(source, f"{full} 26 शब्द") == []
    assert checker.check(source, f"{surname} 26 शब्द") == []
    assert any("must write Alan Archer" in e for e in checker.check(source, f"{first} 26 शब्द"))
    assert checker.check("Archer levelled at 26'.", f"{first} 26 शब्द") == []  # one word in the English: any word will do
