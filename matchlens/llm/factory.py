"""Pick the provider named in config ("ollama", or "fake" for browser tests). Add new providers here and nowhere else."""
from .. import config
from .ollama import OllamaProvider
from .provider import LLMProvider


def get_provider() -> LLMProvider:
    if config.LLM_PROVIDER == "ollama":
        return OllamaProvider()
    if config.LLM_PROVIDER == "fake":  # canned answers for browser tests, see llm/e2e.py
        from .e2e import E2EProvider

        return E2EProvider()
    raise ValueError(f"Unknown LLM_PROVIDER {config.LLM_PROVIDER!r}")
