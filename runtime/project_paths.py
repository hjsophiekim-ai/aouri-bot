"""Canonical filesystem roots for this project.

This repo intentionally lives nested two levels deep, as two SEPARATE git
repositories with unrelated history and purpose (confirmed 2026-09-01):

    C:\\...\\aouribot            <- DOCS_REPO_ROOT: separate git repo, holds
                                    contract originals / requirement docs
                                    only. Never generate runtime/source code
                                    here.
    C:\\...\\aouribot\\aouri-bot  <- CODE_REPO_ROOT: THIS canonical code repo
                                    (server, rules, tests). All server runs,
                                    pytest invocations, edits, and commits
                                    must happen against this root.

A prior session accidentally created a stray `runtime/` tree directly under
DOCS_REPO_ROOT (a script used `cwd`-relative paths while invoked from the
wrong directory), which silently fed a hold-out validation run stale
fixture content. Any new code that needs a project-relative path MUST import
the constants below instead of using `Path.cwd()`, a bare relative path
string, or its own `Path(__file__).resolve().parents[N]` chain — a single
source of truth here means a moved file can't silently break every other
resolver.

`runtime/tests/test_repo_layout_guard.py` asserts DOCS_REPO_ROOT never grows
a stray runtime/tests/aouri-bot directory again.
"""
from __future__ import annotations

from pathlib import Path

CODE_REPO_ROOT: Path = Path(__file__).resolve().parents[1]
DOCS_REPO_ROOT: Path = CODE_REPO_ROOT.parent
