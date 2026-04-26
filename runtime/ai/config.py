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
    existing = os.getenv("OPENAI_API_KEY")
    if existing is None or str(existing).strip() == "":
        load_dotenv(
            resolve_dotenv_paths(cwd=Path.cwd(), repo_root=REPO_ROOT),
            override=False,
        )

    api_key_raw = os.getenv("OPENAI_API_KEY")
    api_key = api_key_raw.strip() if isinstance(api_key_raw, str) and api_key_raw.strip() else None

    model_raw = os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"
    model = str(model_raw).strip() if str(model_raw).strip() else "gpt-4.1-mini"

    timeout_sec = _coerce_float(os.getenv("OPENAI_TIMEOUT", "60"), 60.0)
    max_tokens = _coerce_int(os.getenv("OPENAI_MAX_TOKENS", "1200"), 1200)
    temperature = _coerce_float(os.getenv("OPENAI_TEMPERATURE", "0.2"), 0.2)

    provider = "openai" if api_key else "mock"
    endpoint = "https://api.openai.com/v1/chat/completions"

    return AIConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        endpoint=endpoint,
        timeout_sec=timeout_sec,
        max_tokens=max_tokens,
        temperature=temperature,
    )

