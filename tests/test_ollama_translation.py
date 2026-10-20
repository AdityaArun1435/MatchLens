"""Hindi and Tamil with the real local model. Skipped when Ollama is not running. Uses temporary name maps."""
import pytest

from matchlens import config, loader, service
from matchlens.llm import OllamaProvider
from matchlens.recap import names_i18n
from matchlens.recap.models import RecapRequest
from matchlens.recap.pipeline import get_recap
from matchlens.recap.translate import TranslationChecker

from .recap_fixtures import small_match

pytestmark = pytest.mark.needs_ollama


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "generated")
    monkeypatch.setattr(config, "NAMES_DIR", tmp_path / "names")


@pytest.mark.parametrize("lang", ["hi", "ta"])
def test_real_model_writes_names_in_the_right_script(lang):
    match = small_match()
    name_map, _added, missing = names_i18n.ensure_names(match, lang, OllamaProvider())
    assert not missing, missing
    assert all(names_i18n.in_script(v, lang) for v in name_map.names.values())


@pytest.mark.parametrize("lang", ["hi", "ta"])
def test_real_model_translation_never_drops_a_paragraph_and_passes_its_own_checks(lang):
    match = small_match()
    provider = OllamaProvider()
    english = get_recap(match, RecapRequest(language="en", length="short"), provider)
    res = get_recap(match, RecapRequest(language=lang, length="short"), provider)
    assert len(res.recap.paragraphs) == len(english.recap.paragraphs)
    checker = TranslationChecker(match, lang, "analyst", names_i18n.load_map(lang))
    for src, out in zip(english.recap.paragraphs, res.recap.paragraphs):
        assert out.cites == src.cites
        if out.language == lang:
            assert checker.check(src.text, out.text) == [], out.text
        else:
            assert out.text == src.text and out.note


@pytest.mark.needs_data
@pytest.mark.parametrize("lang", ["hi", "ta"])
def test_real_model_translates_the_final(lang):
    match = service.get_match(loader.find_match(config.DEFAULT_MATCH_QUERY, offline_only=True)["match_id"])
    res = get_recap(match, RecapRequest(audience="fan", language=lang), OllamaProvider())
    assert res.report.translation.language == lang and len(res.recap.paragraphs) == len(res.source_recap.paragraphs)
    assert all(u.status in ("translated", "english_fallback") for u in res.report.translation.units)
