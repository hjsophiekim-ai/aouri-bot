from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.ai.dotenv import load_dotenv, resolve_dotenv_paths


REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class AIConfig:
    provider: str
    model: str
    api_key: str | None
    endpoint: str | None
    timeout_sec: float
    max_tokens: int
    temperature: float


def _coerce_float(v: Any, default: float) -> float:
    try:
        f = float(v)
        return f if f > 0 else default
    except Exception:
        return default


def _coerce_int(v: Any, default: int) -> int:
    try:
        i = int(v)
        return i if i > 0 else default
    except Exception:
        return default


def load_ai_config() -> AIConfig:
    dotenv_disabled = (os.getenv("AOURIBOT_DOTENV_DISABLED") or "").strip().lower() in ("1", "true", "yes")
    existing = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not dotenv_disabled and (existing is None or str(existing).strip() == ""):
        load_dotenv(
            resolve_dotenv_paths(cwd=Path.cwd(), repo_root=REPO_ROOT),
            override=False,
        )

    provider_env = (os.getenv("LLM_PROVIDER") or "").strip().lower()

    # Anthropic config
    anthropic_key_raw = os.getenv("ANTHROPIC_API_KEY")
    anthropic_key = anthropic_key_raw.strip() if isinstance(anthropic_key_raw, str) and anthropic_key_raw.strip() else None
    anthropic_model_raw = os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-20250514"
    anthropic_model = str(anthropic_model_raw).strip() if str(anthropic_model_raw).strip() else "claude-sonnet-4-20250514"
    anthropic_max_tokens = _coerce_int(os.getenv("ANTHROPIC_MAX_TOKENS", "4000"), 4000)
    anthropic_timeout = _coerce_float(os.getenv("ANTHROPIC_TIMEOUT", "90"), 90.0)
    anthropic_temperature = _coerce_float(os.getenv("ANTHROPIC_TEMPERATURE", "0.2"), 0.2)

    # OpenAI config
    openai_key_raw = os.getenv("OPENAI_API_KEY")
    openai_key = openai_key_raw.strip() if isinstance(openai_key_raw, str) and openai_key_raw.strip() else None
    openai_model_raw = os.getenv("OPENAI_MODEL") or "gpt-4.1"
    openai_model = str(openai_model_raw).strip() if str(openai_model_raw).strip() else "gpt-4.1"
    openai_timeout = _coerce_float(os.getenv("OPENAI_TIMEOUT", "60"), 60.0)
    openai_max_tokens = _coerce_int(os.getenv("OPENAI_MAX_TOKENS", "4000"), 4000)
    openai_temperature = _coerce_float(os.getenv("OPENAI_TEMPERATURE", "0.2"), 0.2)

    # Provider selection
    if provider_env == "anthropic" and anthropic_key:
        return AIConfig(
            provider="anthropic",
            model=anthropic_model,
            api_key=anthropic_key,
            endpoint=None,
            timeout_sec=anthropic_timeout,
            max_tokens=anthropic_max_tokens,
            temperature=anthropic_temperature,
        )

    if provider_env == "mock":
        return AIConfig(
            provider="mock",
            model=openai_model,
            api_key=None,
            endpoint="https://api.openai.com/v1/chat/completions",
            timeout_sec=openai_timeout,
            max_tokens=openai_max_tokens,
            temperature=openai_temperature,
        )

    # Default: OpenAI, fallback to Anthropic, then mock
    if openai_key:
        return AIConfig(
            provider="openai",
            model=openai_model,
            api_key=openai_key,
            endpoint="https://api.openai.com/v1/chat/completions",
            timeout_sec=openai_timeout,
            max_tokens=openai_max_tokens,
            temperature=openai_temperature,
        )

    if anthropic_key:
        return AIConfig(
            provider="anthropic",
            model=anthropic_model,
            api_key=anthropic_key,
            endpoint=None,
            timeout_sec=anthropic_timeout,
            max_tokens=anthropic_max_tokens,
            temperature=anthropic_temperature,
        )

    # No keys found — mock with OpenAI config values preserved
    return AIConfig(
        provider="mock",
        model=openai_model,
        api_key=None,
        endpoint="https://api.openai.com/v1/chat/completions",
        timeout_sec=openai_timeout,
        max_tokens=openai_max_tokens,
        temperature=openai_temperature,
    )
