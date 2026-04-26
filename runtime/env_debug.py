from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from runtime.ai.config import load_ai_config
from runtime.ai.dotenv import get_dotenv_debug_state, load_dotenv, resolve_dotenv_paths
from runtime.law.config import load_law_api_config


def load_dotenv_for_runtime(*, repo_root: Path) -> list[str]:
    paths = resolve_dotenv_paths(cwd=Path.cwd(), repo_root=repo_root)
    loaded = load_dotenv(paths, override=False)
    return [str(p) for p in loaded]


def env_status(*, repo_root: Path) -> dict[str, Any]:
    ai = load_ai_config()
    law = load_law_api_config()
    dbg = get_dotenv_debug_state()
    app_root = (repo_root / "aouri-bot").resolve()
    return {
        "cwd": str(Path.cwd()),
        "repo_root": str(repo_root.resolve()),
        "dotenv": {
            "candidates": dbg.get("candidates"),
            "loaded": dbg.get("loaded"),
        },
        "dotenv_exists": {
            "repo_root/.env": bool((repo_root / ".env").exists()),
            "repo_root/.env.local": bool((repo_root / ".env.local").exists()),
            "aouri-bot/.env": bool((app_root / ".env").exists()),
            "aouri-bot/.env.local": bool((app_root / ".env.local").exists()),
        },
        "OPENAI_API_KEY_present": bool((os.getenv("OPENAI_API_KEY") or "").strip()),
        "LAW_API_KEY_present": bool((os.getenv("LAW_API_KEY") or "").strip()),
        "LAW_API_ENABLED": (os.getenv("LAW_API_ENABLED") or "").strip() or None,
        "selected_ai_provider": ai.provider,
        "selected_ai_model": ai.model,
        "selected_law_api_enabled": bool(law.enabled),
        "selected_law_base_url": law.base_url,
    }

