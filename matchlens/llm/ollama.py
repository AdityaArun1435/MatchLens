"""Ollama provider: /api/chat with the response constrained to a JSON schema."""
import json
import re

import httpx

from .. import config
from .provider import LLMError, LLMUnavailable

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


class OllamaProvider:
    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model = model or config.OLLAMA_MODEL
        self.name = self.model
        self.base_url = (base_url or config.OLLAMA_URL).rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url, timeout=timeout or config.LLM_TIMEOUT_SECONDS, transport=transport
        )

    # ---- availability -------------------------------------------------------------------------
    def is_available(self) -> bool:
        """True if the server answers and the configured model is pulled."""
        try:
            tags = self._client.get("/api/tags", timeout=3).json()
        except (httpx.HTTPError, ValueError):
            return False
        names = {m.get("name") for m in tags.get("models", [])}
        return self.model in names or f"{self.model}:latest" in names

    # ---- generation ---------------------------------------------------------------------------
    def _payload(self, system: str, user: str, schema: dict, think: bool | None) -> dict:
        payload = {
            "model": self.model,
            "stream": False,
            "format": schema,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {
                "temperature": config.LLM_TEMPERATURE,
                "seed": config.LLM_SEED,
                "num_ctx": config.OLLAMA_NUM_CTX,
            },
        }
        if think is not None:
            payload["think"] = think
        return payload

    def _post(self, payload: dict) -> httpx.Response:
        try:
            return self._client.post("/api/chat", json=payload)
        except httpx.ConnectError as exc:
            raise LLMUnavailable(
                f"Cannot reach Ollama at {self.base_url}. Start it with the Ollama app or `ollama serve`, "
                f"then check `ollama list` shows {self.model}."
            ) from exc
        except httpx.TimeoutException as exc:
            raise LLMError(
                f"Ollama did not answer within {self._client.timeout.read:.0f}s (model {self.model}). "
                "The first call loads the model into memory; raise LLM_TIMEOUT_SECONDS if this keeps happening."
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama request failed: {exc}") from exc

    def generate_json(self, system: str, user: str, json_schema: dict) -> dict:
        think = False if config.OLLAMA_DISABLE_THINKING else None
        resp = self._post(self._payload(system, user, json_schema, think))
        if resp.status_code == 400 and think is not None and "think" in resp.text.lower():
            # model has no thinking mode; ask again without the flag
            resp = self._post(self._payload(system, user, json_schema, None))
        if resp.status_code == 404:
            raise LLMError(f"Ollama does not have model '{self.model}'. Run `ollama pull {self.model}`.")
        if resp.status_code >= 400:
            raise LLMError(f"Ollama returned {resp.status_code}: {resp.text[:300]}")
        try:
            content = resp.json()["message"]["content"]
        except (ValueError, KeyError) as exc:
            raise LLMError(f"Unexpected Ollama response: {resp.text[:300]}") from exc
        return parse_json_content(content)


def parse_json_content(content: str) -> dict:
    """Parse a model reply as a JSON object, tolerating <think> blocks and surrounding text."""
    text = _THINK_BLOCK.sub("", content).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise LLMError(f"Model did not return JSON: {text[:200]!r}") from None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError(f"Model returned invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise LLMError("Model returned JSON that is not an object")
    return data
