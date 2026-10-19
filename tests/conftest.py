import pytest

from matchlens import config, loader


def _data_available() -> bool:
    try:
        entry = loader.find_match(config.DEFAULT_MATCH_QUERY, offline_only=True)
        loader.load_events(entry["match_id"], offline_only=True)
        return True
    except (FileNotFoundError, LookupError):
        return False


def _ollama_available() -> bool:
    from matchlens.llm import OllamaProvider

    try:
        return OllamaProvider().is_available()
    except Exception:  # noqa: BLE001 - any failure means "not available" for a skip decision
        return False


def pytest_collection_modifyitems(config, items):
    if not _data_available():
        skip = pytest.mark.skip(reason="StatsBomb data not cached; run `python scripts/fetch_data.py`")
        for item in items:
            if "needs_data" in item.keywords:
                item.add_marker(skip)
    if any("needs_ollama" in item.keywords for item in items) and not _ollama_available():
        skip = pytest.mark.skip(reason="Ollama is not running or the configured model is not pulled")
        for item in items:
            if "needs_ollama" in item.keywords:
                item.add_marker(skip)
