from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.ai.dotenv import load_dotenv, resolve_dotenv_paths


REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class LawApiConfig:
    enabled: bool
    api_key: str | None
    base_url: str
    timeout_sec: float
    retry_count: int


def _coerce_float(v: Any, default: float) -> float:
    try:
        f = float(v)
        return f if f > 0 else default
    except Exception:
        return default


def _coerce_int(v: Any, default: int) -> int:
    try:
        i = int(v)
        return i if i >= 0 else default
    except Exception:
        return default


def _coerce_bool(v: Any, default: bool) -> bool:
    if v is None:
        return default
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    return default


def load_law_api_config() -> LawApiConfig:
    existing = os.getenv("LAW_API_KEY")
    if existing is None or str(existing).strip() == "":
        load_dotenv(
            resolve_dotenv_paths(cwd=Path.cwd(), repo_root=REPO_ROOT),
            override=False,
        )

    enabled = _coerce_bool(os.getenv("LAW_API_ENABLED", "false"), False)

    api_key_raw = os.getenv("LAW_API_KEY")
    api_key = api_key_raw.strip() if isinstance(api_key_raw, str) and api_key_raw.strip() else None

    base_url_raw = os.getenv("LAW_API_BASE_URL") or "https://www.law.go.kr/DRF"
    base_url = str(base_url_raw).strip().rstrip("/")
    base_url_l = base_url.lower()
    if "open.law.go.kr" in base_url_l:
        base_url = "https://www.law.go.kr/DRF"
    if base_url.lower().endswith("/drf") is False:
        if base_url.lower().endswith("law.go.kr"):
            base_url = base_url + "/DRF"
        elif base_url.lower().endswith("law.go.kr/"):
            base_url = base_url + "DRF"
    timeout_sec = _coerce_float(os.getenv("LAW_API_TIMEOUT", "20"), 20.0)
    retry_count = _coerce_int(os.getenv("LAW_API_RETRY", "2"), 2)

    if not api_key:
        enabled = False

    return LawApiConfig(
        enabled=enabled,
        api_key=api_key,
        base_url=base_url,
        timeout_sec=timeout_sec,
        retry_count=retry_count,
    )

