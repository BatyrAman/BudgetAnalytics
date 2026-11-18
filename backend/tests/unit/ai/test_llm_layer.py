"""LLM layer with mocked transports/providers (no network, no paid API)."""

import asyncio
import json
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.integrations.llm import (
    LLMBadRequestError,
    LLMCallFailed,
    LLMClient,
    LLMConfigurationError,
    LLMInvalidResponseError,
    LLMMessage,
    LLMRateLimitError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
    LLMUnavailableError,
    RetryPolicy,
    TokenUsage,
    build_llm_client,
    strict_json_schema,
)
from app.integrations.llm.openai_provider import OpenAIProvider
from app.schemas.advisor import AdvisorAnswer, AdvisorReport

API_KEY = "sk-test-SECRET-should-never-leak"
REQUEST = LLMRequest(
    messages=(LLMMessage("system", "rules"), LLMMessage("user", "data")),
    response_schema=strict_json_schema(AdvisorAnswer),
    schema_name="AdvisorAnswer",
    max_output_tokens=500,
)


def _completion(content: str, finish: str = "stop", **message: Any) -> dict[str, Any]:
    return {
        "id": "chatcmpl-1",
        "model": "gpt-test-2025",
        "choices": [
            {
                "message": {"role": "assistant", "content": content, **message},
                "finish_reason": finish,
            }
        ],
        "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
    }


def _provider(handler) -> OpenAIProvider:  # type: ignore[no-untyped-def]
    return OpenAIProvider(
        API_KEY, "gpt-test", "https://llm.example/v1", 5, transport=httpx.MockTransport(handler)
    )


class TestOpenAIProvider:
    async def test_request_shape_and_parsing(self) -> None:
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["auth"] = request.headers["authorization"]
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json=_completion('{"ok": true}'))

        provider = _provider(handler)
        response = await provider.generate(REQUEST)
        await provider.aclose()

        assert seen["url"] == "https://llm.example/v1/chat/completions"
        assert seen["auth"] == f"Bearer {API_KEY}"
        body = seen["body"]
        assert body["model"] == "gpt-test"
        assert body["max_completion_tokens"] == 500
        assert "temperature" not in body  # provider default unless configured
        fmt = body["response_format"]
        assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
        assert fmt["json_schema"]["name"] == "AdvisorAnswer"
        assert [m["role"] for m in body["messages"]] == ["system", "user"]
        assert response == LLMResponse(
            content='{"ok": true}',
            usage=TokenUsage(120, 30),
            provider="openai",
            model="gpt-test-2025",
            finish_reason="stop",
            raw_metadata={"id": "chatcmpl-1"},
        )

    @pytest.mark.parametrize(
        ("status", "error", "retryable"),
        [
            (401, LLMConfigurationError, False),
            (403, LLMConfigurationError, False),
            (404, LLMConfigurationError, False),
            (400, LLMBadRequestError, False),
            (429, LLMRateLimitError, True),
            (500, LLMUnavailableError, True),
            (503, LLMUnavailableError, True),
        ],
    )
    async def test_http_errors_are_mapped(self, status: int, error: type, retryable: bool) -> None:
        provider = _provider(
            lambda r: httpx.Response(status, json={"error": {"message": f"key {API_KEY}"}})
        )
        with pytest.raises(error) as info:
            await provider.generate(REQUEST)
        assert info.value.retryable is retryable
        assert API_KEY not in str(info.value)  # provider error bodies are never echoed

    async def test_timeout_and_network_errors(self) -> None:
        def timeout(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("slow", request=request)

        def refused(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        with pytest.raises(LLMTimeoutError):
            await _provider(timeout).generate(REQUEST)
        with pytest.raises(LLMUnavailableError):
            await _provider(refused).generate(REQUEST)

    @pytest.mark.parametrize(
        "body",
        [
            _completion("not json"),
            _completion(""),
            _completion('{"a": 1}', finish="length"),
            _completion("", refusal="I can't help with that"),
            {"unexpected": True},
        ],
    )
    async def test_unusable_answers(self, body: dict[str, Any]) -> None:
        with pytest.raises(LLMInvalidResponseError) as info:
            await _provider(lambda r: httpx.Response(200, json=body)).generate(REQUEST)
        if "usage" in body:
            assert info.value.usage == TokenUsage(120, 30)  # still billed -> still counted

    def test_missing_key(self) -> None:
        with pytest.raises(LLMConfigurationError):
            OpenAIProvider("", "gpt-test")


class ScriptedProvider:
    """Mock provider returning/raising a scripted sequence."""

    name = "scripted"
    model = "scripted-1"

    def __init__(self, script: list[Any], delay: float = 0) -> None:
        self.script = list(script)
        self.calls = 0
        self.delay = delay

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return LLMResponse(item, TokenUsage(10, 5), self.name, self.model)

    async def aclose(self) -> None:
        pass


async def _no_sleep(_: float) -> None:
    return None


class TestClient:
    async def test_retries_retryable_errors_then_succeeds(self) -> None:
        provider = ScriptedProvider([LLMRateLimitError("429"), LLMUnavailableError("503"), "{}"])
        client = LLMClient(provider, 5, RetryPolicy(max_retries=2), sleep=_no_sleep)
        result = await client.generate(REQUEST, "test")
        assert provider.calls == 3 and result.attempts == 3

    async def test_gives_up_after_max_retries(self) -> None:
        provider = ScriptedProvider([LLMUnavailableError("x")] * 3)
        client = LLMClient(provider, 5, RetryPolicy(max_retries=2), sleep=_no_sleep)
        with pytest.raises(LLMCallFailed) as info:
            await client.generate(REQUEST, "test")
        assert provider.calls == 3 and info.value.attempts == 3

    async def test_non_retryable_errors_are_not_retried(self) -> None:
        provider = ScriptedProvider([LLMConfigurationError("bad key"), "{}"])
        client = LLMClient(provider, 5, RetryPolicy(max_retries=3), sleep=_no_sleep)
        with pytest.raises(LLMCallFailed):
            await client.generate(REQUEST, "test")
        assert provider.calls == 1

    async def test_overall_timeout(self) -> None:
        provider = ScriptedProvider(["{}"], delay=1)
        client = LLMClient(provider, timeout_seconds=0.05, retry=RetryPolicy(max_retries=0))
        with pytest.raises(LLMCallFailed) as info:
            await client.generate(REQUEST, "test")
        assert isinstance(info.value.error, LLMTimeoutError)

    async def test_usage_of_failed_attempts_is_counted(self) -> None:
        provider = ScriptedProvider([LLMInvalidResponseError("bad", usage=TokenUsage(100, 50))])
        client = LLMClient(provider, 5, RetryPolicy(max_retries=0), sleep=_no_sleep)
        with pytest.raises(LLMCallFailed) as info:
            await client.generate(REQUEST, "test")
        assert info.value.usage == TokenUsage(100, 50)

    def test_backoff_is_bounded_and_grows(self) -> None:
        policy = RetryPolicy(base_delay_seconds=1, max_delay_seconds=4)
        for attempt, cap in [(1, 1), (2, 2), (3, 4), (6, 4)]:
            assert all(0 <= policy.delay(attempt) <= cap for _ in range(50))


class TestStrictSchema:
    @pytest.mark.parametrize("model", [AdvisorReport, AdvisorAnswer])
    def test_every_object_is_closed_and_fully_required(self, model: type) -> None:
        schema = strict_json_schema(model)

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                if node.get("type") == "object" and "properties" in node:
                    assert node["additionalProperties"] is False
                    assert set(node["required"]) == set(node["properties"])
                for key in ("maxLength", "minLength", "maxItems", "pattern", "default"):
                    assert key not in node
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(schema)

    def test_property_names_matching_keywords_are_kept(self) -> None:
        from pydantic import BaseModel, Field

        class Odd(BaseModel):
            format: str = Field(max_length=5)
            default: int

        schema = strict_json_schema(Odd)
        assert set(schema["properties"]) == {"format", "default"}
        assert "maxLength" not in schema["properties"]["format"]


class TestFactory:
    def _settings(self, **values: Any) -> Settings:
        return Settings(
            _env_file=None,
            DATABASE_URL="postgresql+asyncpg://u:p@h/db",
            SECRET_KEY="x" * 40,
            **values,
        )  # type: ignore[call-arg]

    def test_none_disables_llm(self) -> None:
        assert build_llm_client(self._settings(AI_PROVIDER="none")) is None

    def test_openai_from_configuration(self) -> None:
        client = build_llm_client(
            self._settings(AI_PROVIDER="openai", OPENAI_API_KEY=API_KEY, AI_MODEL="gpt-x")
        )
        assert client is not None and (client.provider_name, client.model) == ("openai", "gpt-x")

    def test_openai_requires_key(self) -> None:
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            self._settings(AI_PROVIDER="openai")

    def test_cost_limits_require_prices(self) -> None:
        with pytest.raises(ValueError, match="PRICE"):
            self._settings(AI_DAILY_COST_LIMIT_PER_USER_USD="1")

    def test_api_key_is_not_in_settings_repr(self) -> None:
        settings = self._settings(AI_PROVIDER="openai", OPENAI_API_KEY=API_KEY)
        assert API_KEY not in repr(settings)
