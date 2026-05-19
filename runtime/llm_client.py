"""Unified LLM client supporting OpenAI and Anthropic providers."""
from __future__ import annotations

import os
from typing import Any

from runtime.ai.config import load_ai_config
from runtime.ai.factory import create_ai_provider
from runtime.ai.http_openai_compatible_provider import build_messages
from runtime.ai.provider import AIRequest


class LLMClient:
    """Thin wrapper around the existing AI provider abstraction."""

    def __init__(self) -> None:
        cfg = load_ai_config()
        self._provider = create_ai_provider(cfg)
        self._model = cfg.model
        self._max_tokens = cfg.max_tokens
        self._temperature = cfg.temperature
        self._timeout_sec = cfg.timeout_sec

    def complete(
        self,
        system: str,
        user: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        req = AIRequest(
            model=self._model,
            messages=build_messages(system, user),
            temperature=temperature if temperature is not None else self._temperature,
            max_tokens=max_tokens if max_tokens is not None else self._max_tokens,
            timeout_sec=self._timeout_sec,
        )
        resp = self._provider.complete(req)
        return resp.content or ""
