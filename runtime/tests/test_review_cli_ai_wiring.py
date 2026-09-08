"""Regression tests for `scripts/review_contract_to_docx.py` AI wiring.

Two bugs found on 2026-09-08 made this CLI ALWAYS fall back to the rule engine,
even with a valid key configured:

  1. Lazy dotenv: `.env` loading in this repo only happens inside
     `load_ai_config()` / `load_law_api_config()`. The script gated on a raw
     `os.environ.get("OPENAI_API_KEY")` read that ran BEFORE any of that, so it
     always saw an empty string.
  2. Bad import: `from runtime.ai.provider import create_provider` — that
     symbol does not exist (the factory is `runtime.ai.factory.create_ai_provider`).
     A bare `except Exception` swallowed the ImportError and printed
     "AI 비활성화 — 규칙 기반 모드" on every single run.

These tests are static/subprocess-level on purpose: they pin the wiring without
running the full review pipeline, and they never touch a real `.env`.
"""
from __future__ import annotations

import ast
import importlib
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from runtime.project_paths import CODE_REPO_ROOT

_SCRIPT = CODE_REPO_ROOT / "scripts" / "review_contract_to_docx.py"
_SENTINEL = "sk-test-CLI-FIXTURE-NEVER-REAL"


def _source() -> str:
    return _SCRIPT.read_text(encoding="utf-8")


def _tree() -> ast.Module:
    return ast.parse(_source())


class ReviewCliImportsTest(unittest.TestCase):
    def test_script_exists(self) -> None:
        self.assertTrue(_SCRIPT.is_file(), f"missing {_SCRIPT}")

    def test_every_runtime_import_resolves(self) -> None:
        """Bug 2: an import of a non-existent symbol must not be possible.

        Walks every `from runtime.* import X` in the script — including the
        lazy ones inside `main()` and inside try/except blocks, which is
        exactly where the swallowed ImportError hid — and asserts the symbol
        really exists.
        """
        missing: list[str] = []
        for node in ast.walk(_tree()):
            if not isinstance(node, ast.ImportFrom):
                continue
            module = node.module or ""
            if not module.startswith("runtime"):
                continue
            try:
                mod = importlib.import_module(module)
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                missing.append(f"L{node.lineno}: module {module!r} not importable ({exc})")
                continue
            for alias in node.names:
                if not hasattr(mod, alias.name):
                    missing.append(f"L{node.lineno}: {module}.{alias.name} does not exist")
        self.assertEqual(missing, [], "unresolvable imports in the CLI:\n" + "\n".join(missing))

    def test_does_not_import_create_provider_from_ai_provider(self) -> None:
        """The exact bad import must never come back."""
        for node in ast.walk(_tree()):
            if isinstance(node, ast.ImportFrom) and node.module == "runtime.ai.provider":
                names = {a.name for a in node.names}
                self.assertNotIn(
                    "create_provider",
                    names,
                    "runtime.ai.provider.create_provider does not exist — "
                    "use runtime.ai.factory.create_ai_provider",
                )

    def test_uses_the_canonical_ai_factory(self) -> None:
        src = _source()
        self.assertIn("from runtime.ai.factory import create_ai_provider, is_ai_enabled", src)
        self.assertIn("is_ai_enabled(ai_cfg)", src)


class ReviewCliDotenvOrderTest(unittest.TestCase):
    def test_ensure_dotenv_loaded_is_called_at_module_level(self) -> None:
        tree = _tree()
        calls = [
            n.lineno
            for n in tree.body
            if isinstance(n, ast.Expr)
            and isinstance(n.value, ast.Call)
            and isinstance(n.value.func, ast.Name)
            and n.value.func.id == "ensure_dotenv_loaded"
        ]
        self.assertTrue(
            calls, "ensure_dotenv_loaded() must be called at module level, before any env read"
        )

    def test_ensure_dotenv_loaded_precedes_every_env_read(self) -> None:
        """Bug 1: the eager load must come before the first os.environ access."""
        tree = _tree()
        ensure_lines = [
            n.lineno
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "ensure_dotenv_loaded"
        ]
        self.assertTrue(ensure_lines, "ensure_dotenv_loaded() is not called at all")
        first_ensure = min(ensure_lines)

        env_reads: list[int] = []
        for node in ast.walk(tree):
            # os.environ[...] / os.environ.get(...) / os.getenv(...)
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id == "os" and node.attr in ("environ", "getenv"):
                    env_reads.append(node.lineno)
        self.assertTrue(env_reads, "expected the CLI to read os.environ somewhere")
        self.assertLess(
            first_ensure,
            min(env_reads),
            "ensure_dotenv_loaded() must run before the first os.environ/os.getenv read "
            f"(load at L{first_ensure}, first read at L{min(env_reads)})",
        )

    def test_no_raw_openai_key_gate(self) -> None:
        src = _source()
        self.assertNotIn(
            'if os.environ.get("OPENAI_API_KEY")',
            src,
            "gate on is_ai_enabled() instead of a raw OPENAI_API_KEY read",
        )

    def test_import_eagerly_loads_dotenv_in_a_subprocess(self) -> None:
        """End-to-end: merely importing the script must populate os.environ.

        Runs in a subprocess from an unrelated cwd, with the real keys stripped
        from the environment and AOURIBOT_DOTENV_PATH pointed at a fixture, so
        no real `.env` is read or written.
        """
        driver = (
            "import importlib.util, os, sys, json\n"
            f"spec = importlib.util.spec_from_file_location('_cli', r'{_SCRIPT}')\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            "print(json.dumps({'key': os.environ.get('OPENAI_API_KEY')}))\n"
        )
        with TemporaryDirectory() as td:
            fixture = Path(td) / ".env.test"
            fixture.write_text(f"OPENAI_API_KEY={_SENTINEL}\n", encoding="utf-8")
            driver_path = Path(td) / "driver.py"
            driver_path.write_text(driver, encoding="utf-8")

            env = dict(os.environ)
            env.pop("OPENAI_API_KEY", None)
            env.pop("ANTHROPIC_API_KEY", None)
            env.pop("AOURIBOT_DOTENV_DISABLED", None)
            env["AOURIBOT_DOTENV_PATH"] = str(fixture)

            proc = subprocess.run(
                [sys.executable, str(driver_path)],
                capture_output=True,
                text=True,
                env=env,
                cwd=td,
                timeout=180,
            )
            self.assertEqual(proc.returncode, 0, f"driver failed:\n{proc.stderr}")
            last = [ln for ln in proc.stdout.splitlines() if ln.strip().startswith("{")][-1]
            self.assertEqual(
                __import__("json").loads(last)["key"],
                _SENTINEL,
                "importing the CLI did not eagerly load the .env",
            )


class ReviewCliFallbackReportingTest(unittest.TestCase):
    def test_provider_failure_is_logged_not_silently_swallowed(self) -> None:
        """The old `except Exception: print(...)` hid a real ImportError."""
        src = _source()
        self.assertIn(
            "logger.exception",
            src,
            "a provider-creation failure must be logged with a traceback, "
            "not reduced to a one-line print",
        )

    def test_disabled_ai_reports_why(self) -> None:
        src = _source()
        self.assertIn("API key 미설정", src)


if __name__ == "__main__":
    unittest.main()
