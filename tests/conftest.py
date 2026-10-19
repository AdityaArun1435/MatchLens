import pytest

from matchlens import config, loader


def _data_available() -> bool:
    try:
        entry = loader.find_match(config.DEFAULT_MATCH_QUERY, offline_only=True)
        loader.load_events(entry["match_id"], offline_only=True)
        return True
    except (FileNotFoundError, LookupError):
        return False


def pytest_collection_modifyitems(config, items):
    if _data_available():
        return
    skip = pytest.mark.skip(reason="StatsBomb data not cached; run `python scripts/fetch_data.py`")
    for item in items:
        if "needs_data" in item.keywords:
            item.add_marker(skip)
