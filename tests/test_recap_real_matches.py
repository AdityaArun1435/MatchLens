"""The template fallback is built from real headlines; it must pass the validator on every cached match.

This is also a false-positive check on the name and number rules using real player names and real figures.
"""
import pytest

from matchlens import config, loader, service
from matchlens.recap.context import build_context
from matchlens.recap.fallback import fallback_explanation, fallback_recap
from matchlens.recap.validate import Validator

pytestmark = pytest.mark.needs_data


def cached_ids():
    try:
        return [e["match_id"] for e in loader.load_index()]
    except FileNotFoundError:
        return []


@pytest.mark.parametrize("match_id", cached_ids() or [0])
@pytest.mark.parametrize("length", config.LENGTHS)
def test_fallback_recap_validates(match_id, length):
    match = service.get_match(match_id)
    ctx = build_context(match, min_importance=config.RECAP_MIN_IMPORTANCE)
    v = Validator(match, ctx)
    recap = fallback_recap(match, length)
    assert v.check_title(recap.title) == []
    for p in recap.paragraphs:
        assert v.check_paragraph(p.text, p.cites) == [], p.text


@pytest.mark.parametrize("match_id", cached_ids() or [0])
def test_fallback_explanations_validate_for_every_moment(match_id):
    match = service.get_match(match_id)
    for m in match.moments:
        ex = fallback_explanation(match, m.id)
        v = Validator(match, build_context(match, min_importance=0.0, target=m.id))
        assert v.check_text(ex.why_it_mattered, ex.cites) == [], (m.id, ex.why_it_mattered)
        assert v.check_text(ex.context, ex.cites) == [], (m.id, ex.context)


@pytest.mark.parametrize("match_id", cached_ids() or [0])
def test_every_moment_headline_passes_the_name_and_number_rules_when_cited_alone(match_id):
    match = service.get_match(match_id)
    ctx = build_context(match, min_importance=0.0)
    v = Validator(match, ctx)
    for m in match.moments:
        assert v.check_text(m.headline, [m.id]) == [], (m.id, m.headline)
