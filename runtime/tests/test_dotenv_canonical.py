from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import runtime.ai.dotenv as dotenv_mod
from runtime.ai.dotenv import (
    DOTENV_DISABLED_ENV,
    DOTENV_PATH_ENV,
    canonical_dotenv_local_path,
    canonical_dotenv_path,
    dotenv_diagnostics,
    ensure_dotenv_loaded,
    legacy_docs_dotenv_path,
    load_dotenv,
    reset_dotenv_state_for_tests,
    resolve_dotenv_paths,
)
from runtime.project_paths import CODE_REPO_ROOT, DOCS_REPO_ROOT

_SENTINEL = "sk-test-DOTENV-FIXTURE-NEVER-REAL"


class DotenvResolutionTest(unittest.TestCase):
    """Resolution must be identical from every cwd, and must never read cwd/.env.

    Every test here isolates itself with AOURIBOT_DOTENV_PATH pointing at a
    throwaway `.env.test` inside a TemporaryDirectory. The real `.env` files are
    never opened, written, moved or deleted by this module —
    `test_real_dotenv_files_are_not_modified` asserts that.
    """

    def setUp(self) -> None:
        self._old_env = dict(os.environ)
        self._old_cwd = Path.cwd()
        # conftest.py disables dotenv loading suite-wide so no test can make a
        # billed AI call. These tests exercise the loader itself against a
        # throwaway fixture, so they lift the flag for their own duration.
        os.environ.pop(DOTENV_DISABLED_ENV, None)
        reset_dotenv_state_for_tests()

    def tearDown(self) -> None:
        os.chdir(self._old_cwd)
        os.environ.clear()
        os.environ.update(self._old_env)
        reset_dotenv_state_for_tests()

    def test_canonical_is_code_repo_env(self) -> None:
        self.assertEqual(canonical_dotenv_path(), (CODE_REPO_ROOT / ".env").resolve())

    def test_default_candidates_are_cwd_independent(self) -> None:
        os.environ.pop(DOTENV_PATH_ENV, None)
        expected = [
            (CODE_REPO_ROOT / ".env.local").resolve(),
            (CODE_REPO_ROOT / ".env").resolve(),
        ]
        with TemporaryDirectory() as td:
            try:
                for cwd in (td, str(CODE_REPO_ROOT), str(DOCS_REPO_ROOT), str(Path.home())):
                    os.chdir(cwd)
                    self.assertEqual(resolve_dotenv_paths(), expected, f"cwd={cwd}")
            finally:
                # Windows cannot remove a directory that is still the cwd.
                os.chdir(self._old_cwd)

    def test_canonical_has_highest_file_precedence_after_local_override(self) -> None:
        os.environ.pop(DOTENV_PATH_ENV, None)
        candidates = resolve_dotenv_paths()
        self.assertEqual(candidates[1], canonical_dotenv_path())

    def test_cwd_dotenv_is_never_read(self) -> None:
        """A stray .env in the launch directory must be ignored entirely.

        The old resolver appended cwd/.env, which picked up ~/.env whenever
        anything was run from the home directory.
        """
        with TemporaryDirectory() as td:
            stray = Path(td) / ".env"
            stray.write_text("AOURIBOT_STRAY_MARKER=leaked\n", encoding="utf-8")
            os.environ.pop(DOTENV_PATH_ENV, None)
            try:
                os.chdir(td)
                self.assertNotIn(stray.resolve(), resolve_dotenv_paths())
                ensure_dotenv_loaded()
            finally:
                # Windows cannot remove a directory that is still the cwd.
                os.chdir(self._old_cwd)
            self.assertIsNone(os.environ.get("AOURIBOT_STRAY_MARKER"))

    def test_empty_declaration_does_not_shadow_later_file(self) -> None:
        """`OPENAI_API_KEY=` in the higher-precedence file must not win."""
        with TemporaryDirectory() as td:
            first = Path(td) / "first.env.test"
            second = Path(td) / "second.env.test"
            first.write_text("OPENAI_API_KEY=\nOPENAI_MODEL=gpt-4.1\n", encoding="utf-8")
            second.write_text(f"OPENAI_API_KEY={_SENTINEL}\n", encoding="utf-8")
            os.environ.pop("OPENAI_API_KEY", None)
            os.environ[DOTENV_PATH_ENV] = os.pathsep.join([str(first), str(second)])
            loaded = ensure_dotenv_loaded()
            self.assertEqual(loaded, [first.resolve(), second.resolve()])
            self.assertEqual(os.environ["OPENAI_API_KEY"], _SENTINEL)

    def test_bom_and_crlf_key_is_parsed(self) -> None:
        """The real .env is UTF-8-with-BOM + CRLF; the key must not keep the BOM."""
        with TemporaryDirectory() as td:
            f = Path(td) / ".env.test"
            f.write_bytes(
                b"\xef\xbb\xbfOPENAI_API_KEY=" + _SENTINEL.encode() + b"\r\nLAW_API_ID=abc\r\n"
            )
            os.environ.pop("OPENAI_API_KEY", None)
            os.environ.pop("LAW_API_ID", None)
            os.environ[DOTENV_PATH_ENV] = str(f)
            ensure_dotenv_loaded()
            self.assertEqual(os.environ["OPENAI_API_KEY"], _SENTINEL)
            self.assertEqual(os.environ["LAW_API_ID"], "abc")

    def test_commented_line_containing_equals_is_ignored(self) -> None:
        with TemporaryDirectory() as td:
            f = Path(td) / ".env.test"
            f.write_text("# - LLM_PROVIDER=anthropic\nLLM_PROVIDER=openai\n", encoding="utf-8")
            os.environ.pop("LLM_PROVIDER", None)
            os.environ[DOTENV_PATH_ENV] = str(f)
            ensure_dotenv_loaded()
            self.assertEqual(os.environ["LLM_PROVIDER"], "openai")

    def test_process_env_beats_file(self) -> None:
        with TemporaryDirectory() as td:
            f = Path(td) / ".env.test"
            f.write_text("OPENAI_API_KEY=from-file\n", encoding="utf-8")
            os.environ["OPENAI_API_KEY"] = _SENTINEL
            os.environ[DOTENV_PATH_ENV] = str(f)
            ensure_dotenv_loaded()
            self.assertEqual(os.environ["OPENAI_API_KEY"], _SENTINEL)

    def test_override_true_lets_file_win(self) -> None:
        with TemporaryDirectory() as td:
            f = Path(td) / ".env.test"
            f.write_text(f"OPENAI_API_KEY={_SENTINEL}\n", encoding="utf-8")
            os.environ["OPENAI_API_KEY"] = "stale"
            os.environ[DOTENV_PATH_ENV] = str(f)
            load_dotenv(resolve_dotenv_paths(), override=True)
            self.assertEqual(os.environ["OPENAI_API_KEY"], _SENTINEL)

    def test_disabled_flag_skips_file_loading(self) -> None:
        with TemporaryDirectory() as td:
            f = Path(td) / ".env.test"
            f.write_text("AOURIBOT_DISABLED_MARKER=leaked\n", encoding="utf-8")
            os.environ[DOTENV_PATH_ENV] = str(f)
            os.environ[DOTENV_DISABLED_ENV] = "1"
            self.assertEqual(ensure_dotenv_loaded(), [])
            self.assertIsNone(os.environ.get("AOURIBOT_DISABLED_MARKER"))

    def test_ensure_is_idempotent(self) -> None:
        with TemporaryDirectory() as td:
            f = Path(td) / ".env.test"
            f.write_text(f"OPENAI_API_KEY={_SENTINEL}\n", encoding="utf-8")
            os.environ.pop("OPENAI_API_KEY", None)
            os.environ.pop(DOTENV_DISABLED_ENV, None)
            os.environ[DOTENV_PATH_ENV] = str(f)
            first = ensure_dotenv_loaded()
            f.write_text("OPENAI_API_KEY=changed-on-disk\n", encoding="utf-8")
            second = ensure_dotenv_loaded()
            self.assertEqual(first, second)
            self.assertEqual(os.environ["OPENAI_API_KEY"], _SENTINEL)

    def test_real_dotenv_files_are_not_modified(self) -> None:
        """Guard: the suite must never create, delete or rewrite a real .env."""
        real = [CODE_REPO_ROOT / ".env", DOCS_REPO_ROOT / ".env"]

        def snapshot() -> dict[Path, object]:
            out: dict[Path, object] = {}
            for p in real:
                if p.exists():
                    st = p.stat()
                    out[p] = (True, st.st_size, st.st_mtime_ns)
                else:
                    out[p] = (False, None, None)
            return out

        before = snapshot()
        with TemporaryDirectory() as td:
            f = Path(td) / ".env.test"
            f.write_text("X=1\n", encoding="utf-8")
            os.environ[DOTENV_PATH_ENV] = str(f)
            os.environ.pop(DOTENV_DISABLED_ENV, None)
            ensure_dotenv_loaded()
        self.assertEqual(before, snapshot())


class DocsRepoDotenvRetiredTest(unittest.TestCase):
    """The docs repo `.env` is retired as a secret source (2026-09-08).

    `<docs repo>/.env` was read as a runtime fallback because the OpenAI key
    physically lived there. The docs repo is a SEPARATE git repository holding
    contract originals, so a live API key must not sit in it. These tests pin
    that it is neither a candidate nor ever loaded.
    """

    def setUp(self) -> None:
        self._old_env = dict(os.environ)
        # conftest.py disables dotenv loading suite-wide so no test can make a
        # billed AI call. These tests exercise the loader itself against a
        # throwaway fixture, so they lift the flag for their own duration.
        os.environ.pop(DOTENV_DISABLED_ENV, None)
        reset_dotenv_state_for_tests()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._old_env)
        reset_dotenv_state_for_tests()

    def test_docs_repo_env_is_not_a_candidate(self) -> None:
        os.environ.pop(DOTENV_PATH_ENV, None)
        candidates = resolve_dotenv_paths()
        for retired in ((DOCS_REPO_ROOT / ".env"), (DOCS_REPO_ROOT / ".env.local")):
            self.assertNotIn(retired.resolve(), candidates, f"{retired} must not be a candidate")

    def test_only_canonical_code_repo_files_are_candidates(self) -> None:
        os.environ.pop(DOTENV_PATH_ENV, None)
        candidates = resolve_dotenv_paths()
        self.assertEqual(
            candidates,
            [canonical_dotenv_local_path(), canonical_dotenv_path()],
            "candidate list must be exactly .env.local -> .env under the code repo",
        )
        for c in candidates:
            self.assertTrue(
                str(c).startswith(str(CODE_REPO_ROOT.resolve())),
                f"{c} is outside the canonical code repo",
            )

    def test_docs_repo_values_are_never_loaded(self) -> None:
        """Hermetic proof: a key present only in a docs-repo .env must not load.

        Uses fake code/docs roots so the real `.env` files are never touched.
        """
        with TemporaryDirectory() as td:
            fake_docs = Path(td) / "aouribot"
            fake_code = fake_docs / "aouri-bot"
            fake_code.mkdir(parents=True)
            (fake_code / ".env").write_text("AOURIBOT_FROM_CODE=code-value\n", encoding="utf-8")
            (fake_docs / ".env").write_text(
                "AOURIBOT_FROM_DOCS=docs-value\nAOURIBOT_FROM_CODE=docs-should-lose\n",
                encoding="utf-8",
            )
            os.environ.pop(DOTENV_PATH_ENV, None)
            os.environ.pop(DOTENV_DISABLED_ENV, None)
            os.environ.pop("AOURIBOT_FROM_CODE", None)
            os.environ.pop("AOURIBOT_FROM_DOCS", None)
            with mock.patch.object(dotenv_mod, "CODE_REPO_ROOT", fake_code), \
                 mock.patch.object(dotenv_mod, "DOCS_REPO_ROOT", fake_docs):
                loaded = ensure_dotenv_loaded()
                self.assertEqual(loaded, [(fake_code / ".env").resolve()])
                self.assertNotIn((fake_docs / ".env").resolve(), loaded)
            self.assertEqual(os.environ.get("AOURIBOT_FROM_CODE"), "code-value")
            self.assertIsNone(
                os.environ.get("AOURIBOT_FROM_DOCS"),
                "a key that exists only in the docs-repo .env must never reach os.environ",
            )

    def test_empty_canonical_key_no_longer_falls_back_to_docs(self) -> None:
        """The exact old behaviour: `OPENAI_API_KEY=` in code + real key in docs."""
        with TemporaryDirectory() as td:
            fake_docs = Path(td) / "aouribot"
            fake_code = fake_docs / "aouri-bot"
            fake_code.mkdir(parents=True)
            (fake_code / ".env").write_text("OPENAI_API_KEY=\n", encoding="utf-8")
            (fake_docs / ".env").write_text(f"OPENAI_API_KEY={_SENTINEL}\n", encoding="utf-8")
            os.environ.pop(DOTENV_PATH_ENV, None)
            os.environ.pop(DOTENV_DISABLED_ENV, None)
            os.environ.pop("OPENAI_API_KEY", None)
            with mock.patch.object(dotenv_mod, "CODE_REPO_ROOT", fake_code), \
                 mock.patch.object(dotenv_mod, "DOCS_REPO_ROOT", fake_docs):
                ensure_dotenv_loaded()
            self.assertEqual(
                (os.environ.get("OPENAI_API_KEY") or "").strip(),
                "",
                "docs-repo .env must not supply OPENAI_API_KEY any more",
            )

    def test_diagnostics_flags_legacy_file_without_reading_it(self) -> None:
        os.environ.pop(DOTENV_PATH_ENV, None)
        diag = dotenv_diagnostics()
        self.assertEqual(diag["canonical"], str(canonical_dotenv_path()))
        self.assertEqual(diag["legacy_docs_dotenv"], str(legacy_docs_dotenv_path()))
        self.assertIs(diag["legacy_docs_dotenv_is_read"], False)
        self.assertNotIn(str(legacy_docs_dotenv_path()), diag["candidates"])

    def test_missing_secret_warns_loudly(self) -> None:
        """A missing key must log a WARNING, not silently degrade to mock."""
        with TemporaryDirectory() as td:
            f = Path(td) / ".env.test"
            f.write_text("OPENAI_MODEL=gpt-4.1\n", encoding="utf-8")
            for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", DOTENV_DISABLED_ENV):
                os.environ.pop(k, None)
            os.environ[DOTENV_PATH_ENV] = str(f)
            with self.assertLogs("runtime.ai.dotenv", level="WARNING") as cm:
                ensure_dotenv_loaded()
            joined = "\n".join(cm.output)
            self.assertIn(str(canonical_dotenv_path()), joined)


class AIConfigDotenvTest(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = dict(os.environ)
        # conftest.py disables dotenv loading suite-wide so no test can make a
        # billed AI call. These tests exercise the loader itself against a
        # throwaway fixture, so they lift the flag for their own duration.
        os.environ.pop(DOTENV_DISABLED_ENV, None)
        reset_dotenv_state_for_tests()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._old_env)
        reset_dotenv_state_for_tests()

    def test_openai_key_loaded_from_fixture(self) -> None:
        from runtime.ai.config import load_ai_config
        from runtime.ai.factory import is_ai_enabled

        with TemporaryDirectory() as td:
            f = Path(td) / ".env.test"
            f.write_text(
                f"OPENAI_API_KEY={_SENTINEL}\nOPENAI_MODEL=gpt-4.1\n", encoding="utf-8"
            )
            for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LLM_PROVIDER", DOTENV_DISABLED_ENV):
                os.environ.pop(k, None)
            os.environ[DOTENV_PATH_ENV] = str(f)
            cfg = load_ai_config()
            self.assertEqual(cfg.provider, "openai")
            self.assertEqual(cfg.api_key, _SENTINEL)
            self.assertTrue(is_ai_enabled(cfg))

    def test_exported_anthropic_key_no_longer_blocks_openai_load(self) -> None:
        """Regression: the old guard skipped .env loading if EITHER key was set.

        `existing = OPENAI_API_KEY or ANTHROPIC_API_KEY` meant an exported
        Anthropic key suppressed the whole file load, leaving OPENAI_API_KEY
        permanently empty for the rest of the process.
        """
        from runtime.ai.config import load_ai_config

        with TemporaryDirectory() as td:
            f = Path(td) / ".env.test"
            f.write_text(f"OPENAI_API_KEY={_SENTINEL}\n", encoding="utf-8")
            for k in ("OPENAI_API_KEY", "LLM_PROVIDER", DOTENV_DISABLED_ENV):
                os.environ.pop(k, None)
            os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-fixture"
            os.environ[DOTENV_PATH_ENV] = str(f)
            cfg = load_ai_config()
            self.assertEqual(os.environ.get("OPENAI_API_KEY"), _SENTINEL)
            self.assertEqual(cfg.provider, "openai")


if __name__ == "__main__":
    unittest.main()
