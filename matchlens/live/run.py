"""Build the real store and clients from environment variables and run one tick."""
from .apifootball import ApiFootball
from .config import Settings
from .footballdata import FootballData
from .refresh import Refresher
from .store import Store


def run_once(settings: Settings | None = None) -> dict:
    settings = settings or Settings.from_env()
    if not settings.supabase_url or not settings.supabase_service_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY are required")
    store = Store(settings.supabase_url, settings.supabase_service_key)
    return Refresher(store, FootballData(store, settings), ApiFootball(store, settings), settings).tick()
