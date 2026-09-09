"""누락 리스크 역검증 — 위험배분에서 큰데 finding 이 하나도 없는 영역을 찾는다
(2026-09-09 지시 11항).

목적은 finding 수를 늘리는 것이 **아니다**. 조항별 검토는 원문에 쓰인 문장을
따라가므로, 계약이 아예 침묵하거나 한 줄로 넘긴 위험은 지적할 대상이 없어
그대로 빠진다. 그런데 실무에서 사고가 나는 곳이 바로 거기다:

    제3자 민원·손해 전가        조문 한 줄로 "모든 민원은 수급인 책임"
    계약범위 외 추가업무        "지시에 응하여야 한다"만 있고 대가 규정이 없음
    무귀책 손해부담             귀책 없는 손해까지 떠안는데 보험은 우리 부담
    기술자료·설계자료 귀속      포괄적으로 상대방에게 귀속되는데 대가가 없음

그래서 위험배분 매트릭스(축별 부담 주체)와 최종 finding 목록을 맞춰 보고,
**우리 부담으로 배분됐거나 아예 미배분인 축인데 그 축을 다루는 finding 이
없는 경우**를 역으로 찾아낸다.

설계 — **하드코딩 금지**. 축 정의와 문맥 패턴은 위험배분 매트릭스의 것을
그대로 재사용한다. 이 모듈은 매칭과 대조만 한다.
"""
from __future__ import annotations

from typing import Any

#: 침묵이 특히 위험한 축. 계약이 정하지 않으면(미배분) 분쟁에서 우리가
#: 불리해지는 쪽이라, 우리 부담으로 배분된 축과 같은 무게로 본다.
SILENCE_IS_RISKY = (
    "extra_work",
    "force_majeure",
    "ip_data",
    "third_party_damage",
    "termination",
)


def backcheck_missing_risks(
    matrix: dict[str, Any] | None,
    clause_results: list[dict[str, Any]],
    *,
    contract_text: str = "",
) -> dict[str, Any]:
    """매트릭스와 finding 목록을 대조해 누락 영역을 보고한다.

    finding 을 만들지는 않는다 — 무엇이 비었는지 알려주는 것이 이 단계의 일이다.
    자동으로 finding 을 주입하면 근거 없는 지적이 늘어나고, 그건 이 엔진이
    피하려는 바로 그 문제다.
    """
    from runtime.review.risk_allocation_matrix import (
        RISK_AXES,
        SIDE_OURS,
        SIDE_UNALLOCATED,
    )

    rows = list((matrix or {}).get("rows") or [])
    if not rows:
        return {
            "checked_axes": 0,
            "gaps": [],
            "summary": "위험배분 매트릭스가 없어 역검증을 수행하지 않았습니다.",
        }

    axes_by_key = {a.key: a for a in RISK_AXES}
    blobs: list[str] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if cr.get("dedup_suppressed"):
            continue
        blobs.append(" ".join(
            str(cr.get(f) or "")
            for f in ("title", "issue", "legal_business_reason", "risk_note",
                      "recommendation_text", "suggested_rewrite", "original_text")
        ))
    joined = "\n".join(blobs)

    gaps: list[dict[str, Any]] = []
    checked = 0
    for row in rows:
        key = str(row.get("key") or "")
        side = str(row.get("side") or "")
        axis = axes_by_key.get(key)
        if axis is None:
            continue
        material = side == SIDE_OURS or (
            side == SIDE_UNALLOCATED and key in SILENCE_IS_RISKY
        )
        if not material:
            continue
        checked += 1
        if axis.context.search(joined):
            continue  # 이 축을 다루는 finding 이 있다
        gaps.append({
            "axis": key,
            "axis_label": str(row.get("label") or key),
            "side": side,
            "side_label": str(row.get("side_label") or ""),
            "evidence": str(row.get("evidence") or "")[:220],
            "why": (
                "이 위험이 우리 회사 부담으로 배분되어 있는데 이를 다루는 검토 "
                "의견이 없습니다."
                if side == SIDE_OURS else
                "계약이 이 위험을 누구 부담으로도 정하지 않았고, 이를 다루는 "
                "검토 의견도 없습니다. 분쟁이 생기면 다툼의 대상이 됩니다."
            ),
            "action": "재검토 필요 — 해당 위험을 다루는 조항을 찾고, 없으면 신설을 제안하세요.",
        })

    if gaps:
        summary = (
            f"위험이 큰 {checked}축 중 {len(gaps)}축에 대한 검토 의견이 없습니다: "
            + ", ".join(str(g["axis_label"]) for g in gaps)
        )
    else:
        summary = f"위험이 큰 {checked}축 모두 검토 의견이 있습니다."

    return {
        "checked_axes": checked,
        "gaps": gaps,
        "gap_count": len(gaps),
        "summary": summary,
    }
