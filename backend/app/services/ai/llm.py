"""
LLMClient — фасад, через который будущий AssistantService общается с LLM.

Выбор провайдера — одна настройка (AI_PROVIDER). Здесь же будет
цикл «модель → tool calls → ToolRegistry → результаты → модель»;
сейчас реализован только сам контракт.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.core.config import settings
from app.services.ai.contracts import GenerationOptions, LLMResponse, Message, ToolSpec
from app.services.ai.provider import LLMProvider, get_provider


class LLMClient:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider or get_provider(settings.AI_PROVIDER)

    async def generate(self, messages: Sequence[Message], system: str, options: GenerationOptions | None = None) -> LLMResponse:
        return await self.provider.generate(messages, system=system, options=options)

    async def tool_call(
        self,
        messages: Sequence[Message],
        system: str,
        tools: Sequence[ToolSpec],
        options: GenerationOptions | None = None,
    ) -> LLMResponse:
        return await self.provider.tool_call(messages, system=system, tools=tools, options=options)

    def stream(self, messages: Sequence[Message], system: str, tools: Sequence[ToolSpec] = (), options: GenerationOptions | None = None):
        return self.provider.stream(messages, system=system, tools=tools, options=options)
