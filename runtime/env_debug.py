from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from runtime.ai.config import load_ai_config
from runtime.ai.dotenv import (
    canonical_dotenv_path,
    dotenv_diagnostics,
    ensure_dotenv_loaded,
    get_dotenv_debug_state,
    legacy_docs_dotenv_path,
    resolve_dotenv_paths,
)
from runtime.law.config import load_law_api_config


def load_dotenv_for_runtime(*, repo_root: Path | None = None) -> list[str]:
    """Load the canonical .env. `repo_root` is ignored (kept for compatibility)."""
    return [str(p) for p in ensure_dotenv_loaded()]


def env_status(*, repo_root: Path) -> dict[str, Any]:
    ai = load_ai_config()
    law = load_law_api_config()
    dbg = get_dotenv_debug_state()
    app_root = (repo_root / "aouri-bot").resolve()
    return {
        "cwd": str(Path.cwd()),
        "repo_root": str(repo_root.resolve()),
        "dotenv": {
            "canonical": str(canonical_dotenv_path()),
            "candidates": dbg.get("candidates") or [str(p) for p in resolve_dotenv_paths()],
            "loaded": dbg.get("loaded"),
            "disabled": dbg.get("disabled"),
        },
        "dotenv_exists": {
            "aouri-bot/.env": bool((app_root / ".env").exists()),
            "aouri-bot/.env.local": bool((app_root / ".env.local").exists()),
            # Reported for visibility only — the docs repo is NOT a secret
            # source any more and no value is read from it.
            "repo_root/.env (RETIRED, not read)": bool((repo_root / ".env").exists()),
            "repo_root/.env.local (RETIRED, not read)": bool((repo_root / ".env.local").exists()),
        },
        "dotenv_diagnostics": dotenv_diagnostics(),
        "legacy_docs_dotenv": {
            "path": str(legacy_docs_dotenv_path()),
            "exists": legacy_docs_dotenv_path().exists(),
            "is_runtime_fallback": False,
        },
        "OPENAI_API_KEY_present": bool((os.getenv("OPENAI_API_KEY") or "").strip()),
        "LAW_API_KEY_present": bool((os.getenv("LAW_API_KEY") or "").strip()),
        "LAW_API_ENABLED": (os.getenv("LAW_API_ENABLED") or "").strip() or None,
        "selected_ai_provider": ai.provider,
        "selected_ai_model": ai.model,
        "selected_law_api_enabled": bool(law.enabled),
        "selected_law_base_url": law.base_url,
    }

