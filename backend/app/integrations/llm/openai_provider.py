"""OpenAI Chat Completions adapter (plain HTTPS via httpx, no vendor SDK).

Endpoint: ``POST {base_url}/chat/completions`` with structured output
``response_format = {"type": "json_schema", "json_schema": {"name", "schema",
"strict": true}}``. Works with any endpoint implementing that API.

Security: the API key is sent only in the Authorization header of requests to
``base_url``; it is never logged and never included in error messages. Request
and response bodies are never logged.
"""

import json
from typing import Any

import httpx

from app.integrations.llm.base import (
    LLMBadRequestError,
    LLMConfigurationError,
    LLMInvalidResponseError,
    LLMRateLimitError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
    LLMUnavailableError,
    TokenUsage,
)


class OpenAIProvider:
    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise LLMConfigurationError("OpenAI API key is not configured")
        self.model = model
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _payload(self, request: LLMRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "max_completion_tokens": request.max_output_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": request.schema_name,
                    "schema": request.response_schema,
                    "strict": True,
                },
            },
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        return payload

    async def generate(self, request: LLMRequest) -> LLMResponse:
        try:
            response = await self._client.post("/chat/completions", json=self._payload(request))
        except httpx.TimeoutException:
            raise LLMTimeoutError("OpenAI request timed out") from None
        except httpx.TransportError as exc:
            raise LLMUnavailableError(f"OpenAI connection error: {type(exc).__name__}") from None

        status = response.status_code
        if status in (401, 403):
            raise LLMConfigurationError(f"OpenAI rejected the credentials (HTTP {status})")
        if status == 404:
            raise LLMConfigurationError("OpenAI endpoint or model not found (HTTP 404)")
        if status == 429:
            raise LLMRateLimitError("OpenAI rate limit or quota exceeded (HTTP 429)")
        if status >= 500:
            raise LLMUnavailableError(f"OpenAI server error (HTTP {status})")
        if status >= 400:
            raise LLMBadRequestError(f"OpenAI rejected the request (HTTP {status})")

        try:
            body = response.json()
            usage_raw = body.get("usage") or {}
            usage = TokenUsage(
                input_tokens=int(usage_raw.get("prompt_tokens", 0)),
                output_tokens=int(usage_raw.get("completion_tokens", 0)),
            )
            choice = body["choices"][0]
            message = choice["message"]
            finish_reason = choice.get("finish_reason")
        except (ValueError, KeyError, IndexError, TypeError):
            raise LLMInvalidResponseError("OpenAI returned an unexpected response shape") from None

        if message.get("refusal"):
            raise LLMInvalidResponseError("The model refused to answer", usage=usage)
        if finish_reason == "length":
            raise LLMInvalidResponseError("The model output was truncated", usage=usage)
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMInvalidResponseError("The model returned no content", usage=usage)
        try:
            json.loads(content)
        except ValueError:
            raise LLMInvalidResponseError("The model returned invalid JSON", usage=usage) from None

        return LLMResponse(
            content=content,
            usage=usage,
            provider=self.name,
            model=str(body.get("model") or self.model),
            finish_reason=finish_reason,
            raw_metadata={"id": body.get("id")},
        )
