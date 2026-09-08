"""Every entry point must auto-activate AI from the canonical `.env`.

The requirement (2026-09-08): running the program must enable AI with NO manual
key moving and NO environment injection. `.env` loading in this repo is lazy —
it happens inside `load_ai_config()` / `load_law_api_config()` — so any entry
point that reads a secret straight out of `os.environ` has to eagerly load
first. `scripts/review_contract_to_docx.py` did not, and silently ran the rule
engine for every invocation.

These tests are static (AST) plus one opt-in smoke check against the real
canonical `.env`. Nothing here reads, writes, or prints a secret value.
"""
from __future__ import annotations

import ast
import os
import unittest
from pathlib import Path

from runtime.ai.dotenv import canonical_dotenv_path
from runtime.project_paths import CODE_REPO_ROOT

#: Reads of these via os.environ/os.getenv require a prior eager load.
_SECRET_NAMES = {
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "LAW_API_KEY",
    "LAW_API_ID",
}

#: Any of these establishes the environment before a secret is read.
_EAGER_CALLS = {"ensure_dotenv_loaded", "load_dotenv", "load_ai_config", "load_law_api_config"}

#: Opt-out marker for the handful of scripts that read the environment BEFORE
#: loading on purpose (the before/after validation reports). A file carrying it
#: must say why in the same comment block.
_EXEMPT_MARKER = "AOURIBOT_DOTENV_EAGER_EXEMPT"


def _entry_points() -> list[Path]:
    files = [CODE_REPO_ROOT / "runtime" / "app.py"]
    files += sorted((CODE_REPO_ROOT / "scripts").glob("*.py"))
    return [p for p in files if p.is_file()]


def _secret_read_lines(tree: ast.AST) -> list[int]:
    """Line numbers of `os.environ[...]` / `.get(...)` / `os.getenv(...)` reads
    whose key is a known secret name."""
    lines: list[int] = []

    def is_os_attr(node: ast.AST, attr: str) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and node.attr == attr
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
        )

    for node in ast.walk(tree):
        # os.environ["KEY"]
        if isinstance(node, ast.Subscript) and is_os_attr(node.value, "environ"):
            sl = node.slice
            if isinstance(sl, ast.Constant) and sl.value in _SECRET_NAMES:
                lines.append(node.lineno)
        # os.getenv("KEY") / os.environ.get("KEY")
        if isinstance(node, ast.Call) and node.args:
            first = node.args[0]
            if not (isinstance(first, ast.Constant) and first.value in _SECRET_NAMES):
                continue
            func = node.func
            if is_os_attr(func, "getenv"):
                lines.append(node.lineno)
            elif (
                isinstance(func, ast.Attribute)
                and func.attr == "get"
                and is_os_attr(func.value, "environ")
            ):
                lines.append(node.lineno)
    return lines


def _eager_call_lines(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
            if name in _EAGER_CALLS:
                lines.append(node.lineno)
    return lines


class EntryPointEagerLoadTest(unittest.TestCase):
    def test_entry_points_discovered(self) -> None:
        self.assertTrue(_entry_points(), "no entry points found to audit")

    def test_secret_reads_are_preceded_by_an_eager_load(self) -> None:
        failures: list[str] = []
        audited: list[str] = []
        exempt: list[str] = []
        for path in _entry_points():
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src)
            reads = _secret_read_lines(tree)
            if not reads:
                continue
            rel = path.relative_to(CODE_REPO_ROOT).as_posix()
            if _EXEMPT_MARKER in src:
                exempt.append(rel)
                continue
            audited.append(rel)
            eager = _eager_call_lines(tree)
            if not eager:
                failures.append(
                    f"{rel}: reads a secret at L{min(reads)} but never calls "
                    f"one of {sorted(_EAGER_CALLS)}"
                )
            elif min(eager) > min(reads):
                failures.append(
                    f"{rel}: eager load at L{min(eager)} runs AFTER the first "
                    f"secret read at L{min(reads)}"
                )
        self.assertEqual(failures, [], "entry points that can silently miss the key:\n" + "\n".join(failures))
        # Keep the opt-out list small and visible; it is not a dumping ground.
        self.assertLessEqual(
            len(exempt), 2, f"too many {_EXEMPT_MARKER} opt-outs: {exempt}"
        )
        # `audited` may legitimately be empty: an entry point that goes through
        # is_ai_enabled()/load_ai_config() instead of a raw os.environ read has
        # nothing to audit. The detector's own teeth are pinned separately by
        # test_detector_catches_a_late_eager_load.

    def test_detector_catches_a_late_eager_load(self) -> None:
        """The audit above must actually fail on the original bug shape."""
        bad = (
            "import os\n"
            "from runtime.ai.dotenv import ensure_dotenv_loaded\n"
            "def main():\n"
            "    if os.environ.get('OPENAI_API_KEY'):\n"
            "        pass\n"
            "    ensure_dotenv_loaded()\n"
        )
        tree = ast.parse(bad)
        reads = _secret_read_lines(tree)
        eager = _eager_call_lines(tree)
        self.assertEqual(reads, [4], "failed to spot the raw OPENAI_API_KEY read")
        self.assertEqual(eager, [6], "failed to spot the eager load call")
        self.assertGreater(min(eager), min(reads), "ordering check would not have fired")

    def test_detector_accepts_the_fixed_shape(self) -> None:
        good = (
            "import os\n"
            "from runtime.ai.dotenv import ensure_dotenv_loaded\n"
            "ensure_dotenv_loaded()\n"
            "def main():\n"
            "    k = os.getenv('OPENAI_API_KEY')\n"
        )
        tree = ast.parse(good)
        self.assertLess(min(_eager_call_lines(tree)), min(_secret_read_lines(tree)))

    def test_detector_recognises_all_read_forms(self) -> None:
        src = (
            "import os\n"
            "a = os.environ['OPENAI_API_KEY']\n"
            "b = os.environ.get('LAW_API_KEY')\n"
            "c = os.getenv('ANTHROPIC_API_KEY')\n"
            "d = os.getenv('NOT_A_SECRET')\n"
        )
        self.assertEqual(_secret_read_lines(ast.parse(src)), [2, 3, 4])

    def test_exemptions_state_a_reason(self) -> None:
        for path in _entry_points():
            src = path.read_text(encoding="utf-8")
            if _EXEMPT_MARKER not in src:
                continue
            idx = src.index(_EXEMPT_MARKER)
            block = src[idx : idx + 400]
            self.assertIn(
                "on purpose",
                block,
                f"{path.name}: {_EXEMPT_MARKER} must explain why in the same comment block",
            )

    def test_server_entry_loads_before_binding(self) -> None:
        app = CODE_REPO_ROOT / "runtime" / "app.py"
        tree = ast.parse(app.read_text(encoding="utf-8"))
        eager = _eager_call_lines(tree)
        run_server = [
            n.lineno
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "run_server"
        ]
        self.assertTrue(eager, "runtime/app.py must eagerly load the canonical .env")
        self.assertTrue(run_server, "runtime/app.py must call run_server()")
        self.assertLess(
            min(eager), min(run_server), "the .env must be loaded before the server binds"
        )


class CanonicalDotenvActivatesAITest(unittest.TestCase):
    """Smoke check against the REAL canonical `.env` (read-only).

    Skips when the canonical file has no key configured, so a fresh clone and
    CI stay green. Never prints the value and never writes the file.
    """

    def setUp(self) -> None:
        self._old_env = dict(os.environ)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._old_env)
        from runtime.ai.dotenv import reset_dotenv_state_for_tests

        reset_dotenv_state_for_tests()

    def _canonical_declares_openai_key(self) -> bool:
        p = canonical_dotenv_path()
        if not p.is_file():
            return False
        for enc in ("utf-8-sig", "utf-8", "cp949"):
            try:
                text = p.read_text(encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            return False
        for line in text.splitlines():
            s = line.strip().lstrip("﻿").strip()
            if s.startswith("OPENAI_API_KEY=") and s.split("=", 1)[1].strip():
                return True
        return False

    def test_cold_process_activates_openai_from_canonical_env(self) -> None:
        if not self._canonical_declares_openai_key():
            self.skipTest("canonical .env has no OPENAI_API_KEY configured on this machine")

        from runtime.ai.config import load_ai_config
        from runtime.ai.dotenv import ensure_dotenv_loaded, reset_dotenv_state_for_tests
        from runtime.ai.factory import is_ai_enabled

        # Simulate a cold process: no key in the environment, no override.
        for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LLM_PROVIDER",
                  "AOURIBOT_DOTENV_PATH", "AOURIBOT_DOTENV_DISABLED"):
            os.environ.pop(k, None)
        reset_dotenv_state_for_tests()

        loaded = ensure_dotenv_loaded()
        self.assertIn(canonical_dotenv_path(), loaded)

        cfg = load_ai_config()
        self.assertTrue(
            (os.getenv("OPENAI_API_KEY") or "").strip(),
            "canonical .env did not populate OPENAI_API_KEY",
        )
        self.assertEqual(cfg.provider, "openai")
        self.assertTrue(is_ai_enabled(cfg), "AI must auto-activate from the canonical .env")

    def test_docs_repo_env_holds_no_secret_any_more(self) -> None:
        """The retired docs-repo .env must not carry a live key.

        Only checks for a NON-EMPTY value on a secret line; the value itself is
        never read into a variable that gets reported.
        """
        from runtime.project_paths import DOCS_REPO_ROOT

        legacy = DOCS_REPO_ROOT / ".env"
        if not legacy.is_file():
            self.skipTest("no docs-repo .env present")
        for enc in ("utf-8-sig", "utf-8", "cp949"):
            try:
                text = legacy.read_text(encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            self.skipTest("docs-repo .env is not decodable")

        leftover: list[str] = []
        for line in text.splitlines():
            s = line.strip().lstrip("﻿").strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            key, value = s.split("=", 1)
            key = key.strip().lstrip("﻿").strip()
            if key in _SECRET_NAMES and value.strip():
                leftover.append(key)
        self.assertEqual(
            leftover,
            [],
            "live secret(s) still in the retired docs-repo .env "
            f"(keys, not values): {leftover} — move them into {canonical_dotenv_path()}",
        )


if __name__ == "__main__":
    unittest.main()
