"""Pick the provider named in config. Add new providers here and nowhere else."""
from .. import config
from .ollama import OllamaProvider
from .provider import LLMProvider


def get_provider() -> LLMProvider:
    if config.LLM_PROVIDER == "ollama":
        return OllamaProvider()
    raise ValueError(f"Unknown LLM_PROVIDER {config.LLM_PROVIDER!r}")
