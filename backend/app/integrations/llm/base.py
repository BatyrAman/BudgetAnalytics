"""Provider-independent LLM contract.

Business logic depends only on ``LLMProvider`` / ``LLMRequest`` /
``LLMResponse`` and the ``LLMError`` hierarchy — never on a vendor SDK or
vendor JSON. Adding a provider (Anthropic, Gemini, Ollama, ...) means
implementing ``LLMProvider.generate`` and registering it in ``factory``.
"""

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class LLMMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class LLMRequest:
    """A request for ONE JSON object matching ``response_schema``.

    ``response_schema`` is a JSON Schema produced by ``strict_json_schema``
    (all properties required, ``additionalProperties: false``). Providers must
    ask the model for exactly this structure; the caller validates the result
    again with Pydantic, so providers never need to trust the model.
    """

    messages: tuple[LLMMessage, ...]
    response_schema: dict[str, Any]
    schema_name: str
    max_output_tokens: int
    temperature: float | None = None


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class LLMResponse:
    content: str  # raw JSON text from the model (not yet validated)
    usage: TokenUsage
    provider: str
    model: str
    finish_reason: str | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)  # ids only, never content


class LLMProvider(Protocol):
    name: str
    model: str

    async def generate(self, request: LLMRequest) -> LLMResponse: ...

    async def aclose(self) -> None: ...


# ---------------------------------------------------------------- errors
class LLMError(Exception):
    """Base error. ``retryable`` tells the client whether another attempt may
    succeed. Messages never contain prompts, answers, keys or user data."""

    retryable = False

    def __init__(self, message: str, *, usage: TokenUsage | None = None) -> None:
        super().__init__(message)
        self.usage = usage or TokenUsage()


class LLMConfigurationError(LLMError):
    """Missing/invalid key, unknown model, unsupported provider (not retryable)."""


class LLMTimeoutError(LLMError):
    retryable = True


class LLMRateLimitError(LLMError):
    retryable = True


class LLMUnavailableError(LLMError):
    """Network failure or 5xx from the provider."""

    retryable = True


class LLMBadRequestError(LLMError):
    """The provider rejected the request (4xx other than auth/rate limit)."""


class LLMInvalidResponseError(LLMError):
    """The provider answered but not with a usable JSON object (refusal,
    truncation, malformed JSON). Usage is still reported for accounting."""
