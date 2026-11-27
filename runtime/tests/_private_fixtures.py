"""실데이터 fixture 위치 — 저장소 밖 로컬 폴더.

실제 거래 상대방의 계약서·검토 출력은 저장소(public)에 커밋하지 않는다. 그런 fixture 는
`AOURIBOT_PRIVATE_FIXTURES` 환경변수가 가리키는 폴더(기본값: 사용자 홈의
`aouribot-private-fixtures`)에 두고, 파일이 없을 때만 테스트를 건너뛴다.
"""
from __future__ import annotations

import os
import unittest
from pathlib import Path

PRIVATE_FIXTURES = Path(os.environ.get("AOURIBOT_PRIVATE_FIXTURES") or (Path.home() / "aouribot-private-fixtures"))


def private_fixture(name: str) -> Path:
    """실데이터 fixture 경로. 없으면 사유를 남기고 SkipTest."""
    p = PRIVATE_FIXTURES / name
    if not p.exists():
        raise unittest.SkipTest(
            f"실데이터 fixture 없음: {p} — 저장소에 커밋하지 않는 실제 계약 자료입니다. "
            "AOURIBOT_PRIVATE_FIXTURES 폴더에 두면 실행됩니다."
        )
    return p
