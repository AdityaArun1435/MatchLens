import shutil

import pytest

from matchlens import config
from matchlens.llm import FakeProvider, LLMError, LLMUnavailable
from matchlens.recap import cache, prompts
from matchlens.recap.context import build_context
from matchlens.recap.fallback import fallback_explanation, fallback_recap
from matchlens.recap.models import RecapRequest
from matchlens.recap.pipeline import get_explanation, get_recap, run_explanation, run_recap
from matchlens.recap.validate import Validator

from .recap_fixtures import small_match

GOOD = {
    "title": "A v B: 2-1 after 90 minutes, B win on penalties",
    "paragraphs": [
        {"text": "B took the lead through Ben Brook at 11' to make it 0-1.", "cites": ["m_001"]},
        {"text": "Alan Archer levelled at 26' (1-1) and put A ahead at 86' (2-1).", "cites": ["m_002", "m_005"]},
        {"text": "Dan Dale's shot was saved at 61', xG 0.40.", "cites": ["m_004"]},
    ],
}


def variant(index: int, **changes):
    out = {"title": GOOD["title"], "paragraphs": [dict(p) for p in GOOD["paragraphs"]]}
    out["paragraphs"][index].update(changes)
    return out


@pytest.fixture(scope="module")
def match():
    return small_match()


def run(match, outputs, **kw):
    provider = FakeProvider(outputs)
    recap, report = run_recap(match, "analyst", "medium", "en", provider, **kw)
    return recap, report, provider


def test_good_answer_passes_first_time_and_prompt_is_grounded(match):
    recap, report, provider = run(match, [GOOD])
    assert report.method == "llm" and not report.retried and len(report.attempts) == 1 and not report.dropped
    assert [p.text for p in recap.paragraphs[:-1]] == [p["text"] for p in GOOD["paragraphs"]]
    last = recap.paragraphs[-1]  # written from the kick list, not by the model
    assert last.cites == ["m_006"] and "Kick 1: B, Cal Cross, scored." in last.text and "shootout paragraph" in report.notes[0]
    call = provider.calls[0]
    assert "[m_001] 11'" in call["user"] and "Valid moment ids:" in call["user"]
    assert "m_003" not in call["schema"]["properties"]["paragraphs"]["items"]["properties"]["cites"]["items"]["enum"]
    assert "m_006" not in call["user"] and "m_006" not in call["schema"]["properties"]["paragraphs"]["items"]["properties"]["cites"]["items"]["enum"]
    assert "Never use these words" in call["user"] and "trophy" in call["user"] and "dramatic" in call["user"]
    assert "Analyst" in call["user"] and "Hard rules" in call["system"]
    assert "events" not in call["user"].lower().split("moments (chronological)")[0]  # no raw-event dump


def test_invented_number_triggers_retry_with_the_specific_error(match):
    bad = variant(2, text="Dan Dale's shot was saved at 61', xG 0.99.")
    recap, report, provider = run(match, [bad, GOOD])
    assert report.retried and len(report.attempts) == 2 and report.method == "llm"
    assert "Paragraph 3: number 0.99" in report.attempts[0].errors[0]
    assert "number 0.99" in provider.calls[1]["user"] and "Problems found" in provider.calls[1]["user"]
    assert len(recap.paragraphs) == 4 and not report.dropped


def test_bad_citation_is_caught_and_paragraph_dropped_when_retry_does_not_fix_it(match):
    bad = variant(1, cites=["m_099"])
    recap, report, _ = run(match, [bad, bad])
    assert report.method == "llm" and report.retried
    assert [d.index for d in report.dropped] == [2] and "unknown moment id 'm_099'" in report.dropped[0].errors[0]
    assert len(recap.paragraphs) == 3 and all("Alan Archer levelled" not in p.text for p in recap.paragraphs)


def test_paragraph_without_citations_is_rejected(match):
    recap, report, _ = run(match, [variant(0, cites=[])] * 2)
    assert any("no citations" in e for e in report.dropped[0].errors) and len(recap.paragraphs) == 3


def test_citing_a_moment_that_was_not_shown_is_rejected(match):
    hidden = variant(0, cites=["m_003"])  # momentum swing, below the recap cutoff
    recap, report, _ = run(match, [hidden, hidden])
    assert "not part of the data" in report.dropped[0].errors[0]


def test_invented_player_is_caught_then_everything_dropped_leads_to_fallback(match):
    bad = {"title": GOOD["title"], "paragraphs": [{"text": "Cristiano Ronaldo scored the winner at 86'.", "cites": ["m_005"]}]}
    recap, report, provider = run(match, [bad, bad])
    assert len(provider.calls) == 2 and report.method == "fallback" and report.retried
    assert "no valid paragraph" in report.fallback_reason
    assert any("Ronaldo" in e for e in report.attempts[0].errors)
    assert recap == fallback_recap(match, "medium")


def test_player_from_another_moment_is_caught(match):
    bad = variant(0, text="Alan Archer took the lead at 11' to make it 0-1.")  # cites m_001, which is Ben Brook's goal
    _, report, _ = run(match, [bad, bad])
    assert "Alan Archer" in report.dropped[0].errors[0] and "not named in the cited moments" in report.dropped[0].errors[0]


def test_retry_that_is_worse_does_not_replace_a_better_first_attempt(match):
    first = variant(0, text="Ben Brook scored at 11' to make it 9-9.")  # 1 bad of 4
    worse = {"title": GOOD["title"], "paragraphs": [{"text": "Nothing is right here at 99'.", "cites": ["m_001"]}]}
    recap, report, _ = run(match, [first, worse])
    assert len(recap.paragraphs) == 3 and report.method == "llm"


def test_llm_errors_twice_fall_back_with_reason(match):
    recap, report, provider = run(match, [LLMError("timeout"), LLMError("timeout")])
    assert report.method == "fallback" and report.attempts[0].llm_error == "timeout" and len(provider.calls) == 2
    assert recap.paragraphs


def test_schema_mismatch_counts_as_failed_attempt_and_retry_can_recover(match):
    recap, report, _ = run(match, [{"unexpected": 1}, GOOD])
    assert report.attempts[0].llm_error.startswith("output did not match the schema") and report.method == "llm"


def test_ollama_down_is_an_error_not_a_fallback(match):
    with pytest.raises(LLMUnavailable):
        run(match, [LLMUnavailable("Cannot reach Ollama")])


def test_title_with_player_name_is_replaced_not_fatal(match):
    out = {"title": "Ben Brook shines in 2-1", "paragraphs": GOOD["paragraphs"]}
    recap, report, _ = run(match, [out, out])
    assert report.title_replaced and recap.title.startswith("A v B: 2-1") and len(recap.paragraphs) == 4


def test_moment_ids_written_in_text_are_stripped_and_noted(match):
    out = variant(0, text="B took the lead through Ben Brook at 11' [m_001] to make it 0-1.")
    recap, report, _ = run(match, [out])
    assert "m_001" not in recap.paragraphs[0].text and any("removed moment ids" in n for n in report.notes)


# ---- fallback ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("length", ["short", "medium"])
def test_fallback_recap_passes_its_own_validator(match, length):
    recap = fallback_recap(match, length)
    ctx = build_context(match, min_importance=config.RECAP_MIN_IMPORTANCE)
    v = Validator(match, ctx)
    assert recap.paragraphs and v.check_title(recap.title) == []
    for p in recap.paragraphs:
        assert v.check_paragraph(p.text, p.cites) == [], p.text
    assert len(fallback_recap(match, "short").paragraphs) <= 4


def test_fallback_explanations_pass_validator_for_every_moment(match):
    for m in match.moments:
        ex = fallback_explanation(match, m.id)
        v = Validator(match, build_context(match, min_importance=0.0, target=m.id))
        assert v.check_text(ex.why_it_mattered, ex.cites) == [] and v.check_text(ex.context, ex.cites) == [], m.id
        assert m.id in ex.cites


def test_fallback_is_deterministic(match):
    assert fallback_recap(match, "medium") == fallback_recap(match, "medium")


# ---- explanations -----------------------------------------------------------------------------------
GOOD_EXPLAIN = {
    "moment_id": "m_002",
    "why_it_mattered": "Alan Archer's goal at 26' made it 1-1 and levelled the score.",
    "context": "B had led 0-1 since Ben Brook scored at 11'.",
    "cites": ["m_002", "m_001"],
}


def test_explanation_ok(match):
    ex, report = run_explanation(match, "m_002", "fan", "en", FakeProvider([GOOD_EXPLAIN]))
    assert report.method == "llm" and not report.retried and ex.moment_id == "m_002"


def test_explanation_must_cite_target_and_retries_then_falls_back(match):
    bad = dict(GOOD_EXPLAIN, cites=["m_001"])
    provider = FakeProvider([bad, bad])
    ex, report = run_explanation(match, "m_002", "analyst", "en", provider)
    assert report.method == "fallback" and report.retried and "must cite m_002" in report.attempts[0].errors[0]
    assert "m_002" in ex.cites and len(provider.calls) == 2


def test_explanation_invented_number_then_recovers(match):
    bad = dict(GOOD_EXPLAIN, why_it_mattered="Alan Archer's goal at 26' made it 4-4.")
    ex, report = run_explanation(match, "m_002", "analyst", "en", FakeProvider([bad, GOOD_EXPLAIN]))
    assert report.method == "llm" and report.retried and "4-4" in report.attempts[0].errors[0]


# ---- cache ------------------------------------------------------------------------------------------
@pytest.fixture()
def gen_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path)
    return tmp_path


def test_second_request_is_served_from_cache(match, gen_dir):
    provider = FakeProvider([GOOD], name="qwen3:8b")
    req = RecapRequest(audience="analyst", length="medium")
    first = get_recap(match, req, provider)
    second = get_recap(match, req, provider)
    assert not first.cached and second.cached and len(provider.calls) == 1
    assert second.recap == first.recap
    files = list(gen_dir.rglob("*.json"))
    assert len(files) == 1 and ":" not in files[0].name and "qwen3_8b" in files[0].name
    get_recap(match, RecapRequest(audience="analyst", length="medium", refresh=True), provider)
    assert len(provider.calls) == 2


def test_cache_key_separates_audience_length_language_model(match, gen_dir):
    a = cache.cache_file("recap", 1, "m", audience="analyst", length="short", language="en")
    assert a != cache.cache_file("recap", 1, "m", audience="fan", length="short", language="en")
    assert a != cache.cache_file("recap", 1, "m", audience="analyst", length="medium", language="en")
    assert a != cache.cache_file("recap", 1, "m", audience="analyst", length="short", language="hi")
    assert a != cache.cache_file("recap", 1, "other", audience="analyst", length="short", language="en")
    assert a != cache.cache_file("recap", 2, "m", audience="analyst", length="short", language="en")


def test_changing_a_prompt_file_invalidates_the_cache(match, gen_dir, tmp_path_factory, monkeypatch):
    copy = tmp_path_factory.mktemp("prompts")
    for f in config.PROMPTS_DIR.glob("*.md"):
        shutil.copy(f, copy / f.name)
    monkeypatch.setattr(config, "PROMPTS_DIR", copy)
    provider = FakeProvider([GOOD])
    req = RecapRequest()
    get_recap(match, req, provider)
    assert get_recap(match, req, provider).cached
    (copy / "audience_analyst.md").write_text("Analyst, but different.\n", encoding="utf-8")
    assert not get_recap(match, req, provider).cached and len(provider.calls) == 2
    assert prompts.prompt_hash()  # hash recomputed after the edit


def test_fallback_results_are_not_cached(match, gen_dir):
    bad = {"title": "x", "paragraphs": [{"text": "Nonsense with 99-99.", "cites": ["m_001"]}]}
    provider = FakeProvider([bad])
    first = get_recap(match, RecapRequest(), provider)
    assert first.report.method == "fallback" and not list(gen_dir.rglob("*.json"))
    get_recap(match, RecapRequest(), provider)
    assert len(provider.calls) == 4  # two attempts per request, nothing served from cache


def test_explanation_cache(match, gen_dir):
    provider = FakeProvider([GOOD_EXPLAIN])
    get_explanation(match, "m_002", "fan", "en", provider)
    assert get_explanation(match, "m_002", "fan", "en", provider).cached and len(provider.calls) == 1
