from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Описание инструмента в провайдер-независимом виде (JSON Schema)."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolResult:
    call_id: str
    name: str
    content: dict[str, Any]
    is_error: bool = False


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_result: ToolResult | None = None


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    stop_reason: str | None = None
    usage: Usage = field(default_factory=Usage)


@dataclass(frozen=True, slots=True)
class StreamChunk:
    text: str = ""
    tool_call: ToolCall | None = None
    done: bool = False


@dataclass(frozen=True, slots=True)
class GenerationOptions:
    max_output_tokens: int = 1024
    temperature: float = 0.2
    # Лимиты на пользователя (бесплатный тариф) проверяются до вызова.
    user_id: int | None = None
