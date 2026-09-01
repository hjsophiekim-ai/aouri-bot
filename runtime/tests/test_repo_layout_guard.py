"""Guard against the 2026-09-01 folder-confusion incident: a script invoked
with the wrong cwd created a stray runtime/ tree directly under the OUTER
docs/contract repo (DOCS_REPO_ROOT), which silently fed a hold-out
validation run stale fixture content.

This repo intentionally nests two unrelated git repositories — see
runtime/project_paths.py. That nesting is fine; what must never happen
again is a code-shaped directory appearing under DOCS_REPO_ROOT itself.
"""
from __future__ import annotations

import unittest

from runtime.project_paths import CODE_REPO_ROOT, DOCS_REPO_ROOT


class RepoLayoutGuardTest(unittest.TestCase):
    def test_code_repo_root_is_named_aouri_bot(self) -> None:
        self.assertEqual(CODE_REPO_ROOT.name, "aouri-bot")

    def test_docs_repo_root_has_no_stray_code_directories(self) -> None:
        offenders = [
            str(p) for p in (DOCS_REPO_ROOT / "runtime", DOCS_REPO_ROOT / "tests")
            if p.exists()
        ]
        # 3중 중첩(aouri-bot 안에 또 aouri-bot) 방지.
        nested = CODE_REPO_ROOT / "aouri-bot"
        if nested.exists():
            offenders.append(str(nested))
        self.assertEqual(
            offenders,
            [],
            f"DOCS_REPO_ROOT({DOCS_REPO_ROOT})는 계약서/문서 저장소 전용이어야 "
            f"하는데 코드성 디렉터리가 발견됨 — canonical code repo"
            f"({CODE_REPO_ROOT}) 밖에 실수로 생성된 것인지 확인할 것: {offenders}",
        )
