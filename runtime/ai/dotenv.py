"""Canonical `.env` loading for every aouri-bot entry point.

Why this module is anchored on `runtime.project_paths` and NOT on `Path.cwd()`
(confirmed 2026-09-08):

    C:/.../aouribot            <- DOCS_REPO_ROOT (contract originals / docs)
    C:/.../aouribot/aouri-bot  <- CODE_REPO_ROOT: the canonical code repo AND
                                    the canonical secret source

The previous resolver appended `cwd/.env.local` and `cwd/.env` to the candidate
list. That made secret resolution depend on where the process happened to be
launched from, and in practice it picked up a stray `C:/Users/<user>/.env`
whenever anything was run from the home directory. `cwd` is no longer consulted
at all: the candidate list is identical for every entry point (server, CLI
scripts, tests, pytest) regardless of the launch directory.

Precedence, first match wins for each individual key — and this is the WHOLE
list (confirmed 2026-09-08):

    1. the real process environment (an exported var always beats a file)
    2. CODE_REPO_ROOT/.env.local   <- canonical, git-ignored local override
    3. CODE_REPO_ROOT/.env         <- THE CANONICAL SECRET SOURCE

`DOCS_REPO_ROOT/.env` used to be read as a runtime fallback, because that is
where the OpenAI key physically lived. It is no longer a candidate: the docs
repo is a SEPARATE git repository holding contract originals, and a live API
key must not sit in it. `LEGACY_DOCS_DOTENV` names that file for diagnostics
only — its *existence* is reported by `dotenv_diagnostics()` so a leftover can
be spotted, but no value is ever read out of it.

A key declared with an EMPTY value in a higher-precedence file (e.g. the
template line `OPENAI_API_KEY=` in CODE_REPO_ROOT/.env) must not shadow a real
value from a lower-precedence one — see `_should_set`.

Tests must never read or write the real `.env`. Point `AOURIBOT_DOTENV_PATH` at
a fixture (`.env.test`) instead, or monkeypatch `resolve_dotenv_paths`.
`AOURIBOT_DOTENV_DISABLED=1` skips file loading entirely.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from runtime.project_paths import CODE_REPO_ROOT, DOCS_REPO_ROOT

logger = logging.getLogger(__name__)

#: Override the candidate list entirely (os.pathsep-separated). For tests.
DOTENV_PATH_ENV = "AOURIBOT_DOTENV_PATH"
#: Skip all `.env` file loading; use the process environment as-is.
DOTENV_DISABLED_ENV = "AOURIBOT_DOTENV_DISABLED"

#: Keys the runtime expects to find in the canonical `.env`.
SECRET_KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")

_LAST_LOADED: list[Path] = []
_LAST_CANDIDATES: list[Path] = []
_ENSURED = False
_WARNED = False


def dotenv_disabled() -> bool:
    return (os.getenv(DOTENV_DISABLED_ENV) or "").strip().lower() in ("1", "true", "yes", "on")


def canonical_dotenv_path() -> Path:
    """The single canonical secret source: `<code repo>/.env`."""
    return (CODE_REPO_ROOT / ".env").resolve()


def canonical_dotenv_local_path() -> Path:
    """Optional git-ignored override that sits above the canonical `.env`."""
    return (CODE_REPO_ROOT / ".env.local").resolve()


def legacy_docs_dotenv_path() -> Path:
    """The retired docs-repo `.env`. Reported by diagnostics, NEVER loaded."""
    return (DOCS_REPO_ROOT / ".env").resolve()


def resolve_dotenv_paths(*, cwd: Path | None = None, repo_root: Path | None = None) -> list[Path]:
    """Candidate `.env` files, highest precedence first.

    `cwd` and `repo_root` are accepted for call-site compatibility and are
    deliberately ignored — resolution must not depend on the launch directory.
    Use `AOURIBOT_DOTENV_PATH` to point the loader somewhere else.
    """
    override = (os.getenv(DOTENV_PATH_ENV) or "").strip()
    if override:
        out: list[Path] = []
        for chunk in override.split(os.pathsep):
            chunk = chunk.strip().strip('"')
            if not chunk:
                continue
            p = Path(chunk).expanduser()
            p = p if p.is_absolute() else (CODE_REPO_ROOT / p)
            p = p.resolve()
            if p not in out:
                out.append(p)
        return out

    # The canonical code repo is the ONLY secret source. No docs-repo fallback,
    # no cwd fallback — see the module docstring.
    out = []
    for p in (canonical_dotenv_local_path(), canonical_dotenv_path()):
        if p not in out:
            out.append(p)
    return out


def get_dotenv_debug_state() -> dict[str, object]:
    return {
        "cwd": str(Path.cwd()),
        "canonical": str(canonical_dotenv_path()),
        "candidates": [str(p) for p in _LAST_CANDIDATES],
        "loaded": [str(p) for p in _LAST_LOADED],
        "disabled": dotenv_disabled(),
    }


def dotenv_diagnostics() -> dict[str, object]:
    """Actionable state for the transition off the docs-repo `.env`.

    Reports only whether the retired docs-repo file still EXISTS — no value is
    read out of it. `secret_present` tells whether the canonical source (or the
    process environment) actually produced a usable key.
    """
    legacy = legacy_docs_dotenv_path()
    canonical = canonical_dotenv_path()
    secret_present = any((os.environ.get(k) or "").strip() for k in SECRET_KEYS)
    return {
        "canonical": str(canonical),
        "canonical_exists": canonical.exists(),
        "candidates": [str(p) for p in resolve_dotenv_paths()],
        "secret_present": secret_present,
        "legacy_docs_dotenv": str(legacy),
        # A leftover key in the docs repo is a real hazard: that repo holds
        # contract originals and has unrelated history.
        "legacy_docs_dotenv_exists": legacy.exists(),
        "legacy_docs_dotenv_is_read": False,
    }


def _warn_if_secret_missing() -> None:
    """Fail loudly instead of silently degrading to the mock provider."""
    global _WARNED
    if _WARNED or dotenv_disabled():
        return
    if any((os.environ.get(k) or "").strip() for k in SECRET_KEYS):
        return
    _WARNED = True
    msg = (
        "No API key resolved. The canonical secret source is %s "
        "(candidates: %s). cwd is never consulted."
    )
    args: list[object] = [
        canonical_dotenv_path(),
        ", ".join(str(p) for p in resolve_dotenv_paths()),
    ]
    if legacy_docs_dotenv_path().exists():
        msg += (
            " NOTE: the retired docs-repo file %s still exists but is NO LONGER"
            " READ — if your key is still only in there, move the"
            " OPENAI_API_KEY line into %s."
        )
        args += [legacy_docs_dotenv_path(), canonical_dotenv_path()]
    logger.warning(msg, *args)


def _read_text(p: Path) -> str | None:
    # utf-8-sig strips a leading BOM; the real .env on this machine is
    # UTF-8-with-BOM + CRLF, which left "\ufeffOPENAI_API_KEY" as the key name.
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return p.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        except OSError:
            return None
    return None


def _parse_line(line: str) -> tuple[str, str] | None:
    s = line.strip().lstrip("\ufeff").strip()
    if not s or s.startswith("#") or "=" not in s:
        return None
    k, v = s.split("=", 1)
    key = k.strip().lstrip("\ufeff").strip()
    if key.startswith("export "):
        key = key[len("export ") :].strip()
    # "# - LLM_PROVIDER=openai" is a comment that happens to contain "=".
    if not key or key.startswith("#"):
        return None
    val = v.strip()
    if "#" in val and not (val.startswith('"') or val.startswith("'")):
        val = val.split("#", 1)[0].strip()
    if len(val) >= 2 and ((val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'"))):
        val = val[1:-1]
    return key, val


def _should_set(key: str, *, override: bool) -> bool:
    if override:
        return True
    # A key declared with an empty placeholder value (the template line
    # `OPENAI_API_KEY=` in the canonical .env) must not permanently shadow a
    # real value coming from a lower-precedence file in the same pass.
    return not os.environ.get(key, "").strip()


def load_dotenv(paths: list[Path] | None = None, *, override: bool = False) -> list[Path]:
    """Load `.env` files into `os.environ`. Returns the files actually read."""
    global _LAST_LOADED, _LAST_CANDIDATES

    if paths is None:
        paths = resolve_dotenv_paths()
    _LAST_CANDIDATES = list(paths)

    if dotenv_disabled():
        _LAST_LOADED = []
        return []

    loaded: list[Path] = []
    for p in paths:
        if not p.exists() or not p.is_file():
            continue
        text = _read_text(p)
        if text is None:
            continue
        for line in text.splitlines():
            parsed = _parse_line(line)
            if parsed is None:
                continue
            key, val = parsed
            if _should_set(key, override=override):
                os.environ[key] = val
        loaded.append(p)
    _LAST_LOADED = list(loaded)
    return loaded


def ensure_dotenv_loaded(*, force: bool = False) -> list[Path]:
    """Idempotent process-wide load. Safe (and cheap) to call from any entry point.

    Every entry point — the server, every CLI script — must call this before
    reading an API key out of `os.environ`, because file loading in this repo is
    otherwise lazy and only happens inside `load_ai_config()` /
    `load_law_api_config()`.
    """
    global _ENSURED
    if _ENSURED and not force:
        return list(_LAST_LOADED)
    loaded = load_dotenv(resolve_dotenv_paths(), override=False)
    _ENSURED = True
    _warn_if_secret_missing()
    return loaded


def reset_dotenv_state_for_tests() -> None:
    """Clear the idempotency latch and debug state. Tests only."""
    global _ENSURED, _LAST_LOADED, _LAST_CANDIDATES, _WARNED
    _ENSURED = False
    _WARNED = False
    _LAST_LOADED = []
    _LAST_CANDIDATES = []
