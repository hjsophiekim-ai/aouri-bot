"""Negotiation ladder — "삭제 -> 제한 -> fallback" 순서의 다단계 수정안.

범용 사내변호사형 검토 고도화(2026-09-03 지시) — 지금까지 finding은
`suggested_rewrite` 단 하나의 수정안만 가졌다. 실제 협상에서는 최선안(예:
조항 삭제)과 최소수정안(협상이 결렬될 경우의 fallback)을 구분해서 제시해야
하는 경우가 많다(제3자 채무보증, 과도한 지체상금 등). 이 모듈은 그 구조를
표준화한다 — 특정 계약유형이나 조항에 종속되지 않는 순수 데이터 구조.

`negotiation_ladder`가 없는 finding은 기존처럼 `suggested_rewrite` 단일
필드만 사용하면 되므로 완전히 하위호환이다.
"""
from __future__ import annotations

from typing import Any


def build_ladder(tiers: list[tuple[str, str, str]]) -> list[dict[str, Any]]:
    """tiers: [(label, action, rewrite_text), ...] — priority 순서대로.

    label 예: "최선안", "최소수정안", "fallback".
    action: 협상 방향을 한 문장으로 요약.
    rewrite_text: 그 단계에서 실제로 제시할 수정 문안.
    """
    return [
        {
            "priority": idx + 1,
            "label": label,
            "action": action,
            "rewrite_text": rewrite_text,
        }
        for idx, (label, action, rewrite_text) in enumerate(tiers)
    ]
