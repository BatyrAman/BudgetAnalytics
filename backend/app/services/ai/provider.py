"""
LLMProvider — единственная точка контакта с конкретным LLM API.

Реализации (OpenAIProvider, AnthropicProvider, GeminiProvider)
будут жить в отдельных модулях и регистрироваться в
PROVIDERS; бизнес-логика и tools от них не зависят.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from typing import Protocol, runtime_checkable

from app.core.errors import AppError
from app.services.ai.contracts import GenerationOptions, LLMResponse, Message, StreamChunk, ToolSpec


class AIUnavailableError(AppError):
    status_code = 503
    code = "AI_UNAVAILABLE"
    message = "AI assistant is not configured"


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    async def generate(
        self,
        messages: Sequence[Message],
        *,
        system: str,
        options: GenerationOptions | None = None,
    ) -> LLMResponse:
        """Обычный ответ без инструментов."""

    def stream(
        self,
        messages: Sequence[Message],
        *,
        system: str,
        tools: Sequence[ToolSpec] = (),
        options: GenerationOptions | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Потоковый ответ (для SSE в чате)."""

    async def tool_call(
        self,
        messages: Sequence[Message],
        *,
        system: str,
        tools: Sequence[ToolSpec],
        options: GenerationOptions | None = None,
    ) -> LLMResponse:
        """Ответ, в котором модель может запросить вызов инструментов."""


class DisabledProvider:
    """Провайдер по умолчанию: AI выключен, любые вызовы → 503."""

    name = "disabled"

    async def generate(self, messages, *, system, options=None) -> LLMResponse:
        raise AIUnavailableError()

    async def stream(self, messages, *, system, tools=(), options=None):
        raise AIUnavailableError()
        yield  # pragma: no cover - делает функцию async-генератором

    async def tool_call(self, messages, *, system, tools, options=None) -> LLMResponse:
        raise AIUnavailableError()


ProviderFactory = Callable[[], LLMProvider]

PROVIDERS: dict[str, ProviderFactory] = {"disabled": DisabledProvider}


def register_provider(name: str, factory: ProviderFactory) -> None:
    PROVIDERS[name] = factory


def get_provider(name: str) -> LLMProvider:
    factory = PROVIDERS.get(name)
    if factory is None:
        raise AIUnavailableError(f"Unknown AI provider '{name}'")
    return factory()
