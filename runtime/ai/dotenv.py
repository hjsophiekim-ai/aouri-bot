from __future__ import annotations

import os
from pathlib import Path


_LAST_LOADED: list[Path] = []
_LAST_CANDIDATES: list[Path] = []


def resolve_dotenv_paths(*, cwd: Path, repo_root: Path) -> list[Path]:
    repo_root = repo_root.resolve()
    app_root = (repo_root / "aouri-bot").resolve()
    cwd = cwd.resolve()

    out: list[Path] = []
    for p in (
        app_root / ".env.local",
        app_root / ".env",
        repo_root / ".env.local",
        repo_root / ".env",
        cwd / ".env.local",
        cwd / ".env",
    ):
        if p not in out:
            out.append(p)
    return out


def get_dotenv_debug_state() -> dict[str, object]:
    return {
        "cwd": str(Path.cwd()),
        "candidates": [str(p) for p in _LAST_CANDIDATES],
        "loaded": [str(p) for p in _LAST_LOADED],
    }


def load_dotenv(paths: list[Path], *, override: bool = False) -> list[Path]:
    loaded: list[Path] = []
    global _LAST_LOADED, _LAST_CANDIDATES
    _LAST_CANDIDATES = list(paths)
    for p in paths:
        if not p.exists() or not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if "=" not in s:
                continue
            k, v = s.split("=", 1)
            key = k.strip()
            if key.startswith("export "):
                key = key[len("export ") :].strip()
            key = key.lstrip("\ufeff").strip()
            if not key:
                continue
            val = v.strip()
            if "#" in val and not (val.startswith('"') or val.startswith("'")):
                val = val.split("#", 1)[0].strip()
            if len(val) >= 2 and ((val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'"))):
                val = val[1:-1]
            if not override and key in os.environ:
                continue
            os.environ[key] = val
        loaded.append(p)
    _LAST_LOADED = list(loaded)
    return loaded

