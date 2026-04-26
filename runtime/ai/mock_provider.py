from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from runtime.ai.provider import AIRequest, AIResponse, AIUsage


@dataclass(frozen=True)
class MockAIProvider:
    label: str = "mock"

    def complete(self, req: AIRequest) -> AIResponse:
        user_text = ""
        for m in reversed(req.messages):
            if m.role == "user":
                user_text = m.content
                break
        content = (
            f"[MOCK:{self.label}] model={req.model} temperature={req.temperature} max_tokens={req.max_tokens}\n"
            f"요청 요약: {user_text[:400]}"
        )
        usage = AIUsage(input_tokens=None, output_tokens=None, total_tokens=None)
        raw: dict[str, Any] = {"mode": "mock", "provider": self.label}
        return AIResponse(content=content, usage=usage, raw=raw)

