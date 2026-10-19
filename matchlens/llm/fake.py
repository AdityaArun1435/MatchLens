"""Canned provider for tests."""
from collections.abc import Callable
from typing import Any

from .provider import LLMError


class FakeProvider:
    """Returns queued outputs in order (the last one repeats). Items may be dicts, exceptions or callables."""

    def __init__(self, outputs: list[Any], name: str = "fake-model") -> None:
        self.outputs = list(outputs)
        self.name = name
        self.calls: list[dict] = []

    def generate_json(self, system: str, user: str, json_schema: dict) -> dict:
        self.calls.append({"system": system, "user": user, "schema": json_schema})
        if not self.outputs:
            raise LLMError("FakeProvider has no outputs queued")
        item = self.outputs[min(len(self.calls) - 1, len(self.outputs) - 1)]
        if isinstance(item, Exception):
            raise item
        return item(system, user, json_schema) if isinstance(item, Callable) else item
