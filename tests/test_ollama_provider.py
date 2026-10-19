import json

import httpx
import pytest

from matchlens import config
from matchlens.llm import FakeProvider, LLMError, LLMUnavailable, OllamaProvider
from matchlens.llm.ollama import parse_json_content

SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}


def provider(handler) -> OllamaProvider:
    return OllamaProvider(model="m:8b", transport=httpx.MockTransport(handler))


def reply(content: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json={"message": {"content": content}})


def test_request_carries_schema_low_temperature_and_no_thinking():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(json.loads(req.content), path=req.url.path)
        return reply('{"a": "x"}')

    assert provider(handler).generate_json("sys", "usr", SCHEMA) == {"a": "x"}
    assert seen["path"] == "/api/chat" and seen["format"] == SCHEMA and seen["think"] is False
    assert seen["stream"] is False and seen["model"] == "m:8b"
    assert seen["options"]["temperature"] == config.LLM_TEMPERATURE
    assert [m["role"] for m in seen["messages"]] == ["system", "user"]


def test_retries_without_think_for_models_that_do_not_support_it():
    bodies = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        bodies.append(body)
        if "think" in body:
            return httpx.Response(400, text='{"error":"\\"m:8b\\" does not support thinking"}')
        return reply('{"a": "ok"}')

    assert provider(handler).generate_json("s", "u", SCHEMA) == {"a": "ok"}
    assert "think" in bodies[0] and "think" not in bodies[1]


def test_server_down_raises_unavailable_with_hint():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(LLMUnavailable, match="ollama serve"):
        provider(handler).generate_json("s", "u", SCHEMA)


def test_missing_model_hints_pull():
    with pytest.raises(LLMError, match="ollama pull m:8b"):
        provider(lambda r: httpx.Response(404, text="model not found")).generate_json("s", "u", SCHEMA)


def test_timeout_is_an_llm_error():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    with pytest.raises(LLMError, match="did not answer"):
        provider(handler).generate_json("s", "u", SCHEMA)


def test_parse_strips_think_blocks_and_surrounding_text():
    assert parse_json_content('<think>hmm {"x":1}</think>\n{"a": 1}') == {"a": 1}
    assert parse_json_content('Here you go: {"a": 1} done') == {"a": 1}
    for bad in ("no json", "[1, 2]", "{broken"):
        with pytest.raises(LLMError):
            parse_json_content(bad)


def test_is_available_checks_model_is_pulled():
    ok = lambda r: httpx.Response(200, json={"models": [{"name": "m:8b"}]})  # noqa: E731
    assert provider(ok).is_available()
    other = lambda r: httpx.Response(200, json={"models": [{"name": "other:1b"}]})  # noqa: E731
    assert not provider(other).is_available()

    def down(req):
        raise httpx.ConnectError("x")

    assert not provider(down).is_available()


def test_fake_provider_returns_in_order_then_repeats_and_records_calls():
    fake = FakeProvider([{"n": 1}, {"n": 2}])
    assert [fake.generate_json("s", "u", {})["n"] for _ in range(3)] == [1, 2, 2]
    assert len(fake.calls) == 3 and fake.calls[0]["user"] == "u"
    boom = FakeProvider([LLMUnavailable("down")])
    with pytest.raises(LLMUnavailable):
        boom.generate_json("s", "u", {})
