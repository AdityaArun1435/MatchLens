"""Runs against a real local Ollama server; skipped automatically when it is not reachable."""
import pytest

from matchlens import config, loader, service
from matchlens.llm import OllamaProvider
from matchlens.recap.context import build_context
from matchlens.recap.pipeline import run_explanation, run_recap
from matchlens.recap.validate import Validator

from .recap_fixtures import small_match

pytestmark = pytest.mark.needs_ollama


def assert_grounded(match, recap, min_importance=config.RECAP_MIN_IMPORTANCE):
    """Whatever the model wrote, what survives must pass the validators on its own."""
    v = Validator(match, build_context(match, min_importance=min_importance))
    assert recap.paragraphs
    for p in recap.paragraphs:
        assert v.check_paragraph(p.text, p.cites) == [], p.text


@pytest.mark.parametrize("audience", config.AUDIENCES)
def test_real_model_recap_on_small_match(audience):
    match = small_match()
    recap, report = run_recap(match, audience, "short", "en", OllamaProvider())
    assert report.attempts and report.method in ("llm", "fallback")
    assert_grounded(match, recap)


def test_real_model_explanation_on_small_match():
    match = small_match()
    ex, report = run_explanation(match, "m_002", "analyst", "en", OllamaProvider())
    assert ex.moment_id == "m_002" and "m_002" in ex.cites and report.attempts


@pytest.mark.needs_data
def test_real_model_recap_on_the_final():
    match = service.get_match(loader.find_match(config.DEFAULT_MATCH_QUERY, offline_only=True)["match_id"])
    recap, report = run_recap(match, "broadcaster", "medium", "en", OllamaProvider())
    assert_grounded(match, recap)
