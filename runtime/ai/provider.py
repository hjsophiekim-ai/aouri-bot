from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class AIMessage:
    role: str
    content: str


@dataclass(frozen=True)
class AIRequest:
    model: str
    messages: list[AIMessage]
    temperature: float
    max_tokens: int
    timeout_sec: float


@dataclass(frozen=True)
class AIUsage:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


@dataclass(frozen=True)
class AIResponse:
    content: str
    usage: AIUsage | None
    raw: dict[str, Any] | None


class AIProvider(Protocol):
    def complete(self, req: AIRequest) -> AIResponse: ...

