"""Provider-neutral interface for the language model."""
from typing import Protocol


class LLMError(RuntimeError):
    """The model call failed or returned something unusable."""


class LLMUnavailable(LLMError):
    """The model server cannot be reached. Carries a hint the user can act on."""


class LLMProvider(Protocol):
    name: str  # model identifier used in cache keys and reports

    def generate_json(self, system: str, user: str, json_schema: dict) -> dict:
        """Return a dict that follows `json_schema`. Raise LLMUnavailable / LLMError on failure."""
        ...
