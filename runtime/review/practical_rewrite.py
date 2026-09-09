"""Practical First — 수정안을 협상 가능한 형태로 정리한다 (2026-09-09 지시 10항).

변호사가 상대방에게 보내는 검토의견은 다섯 가지가 갖춰져야 쓸 수 있다:

    수정 위치        어느 조항의 어느 항을 고치는가
    수정 방식        문구 교체 / 단서 추가 / 항 신설 / 삭제
    완성 문구        그대로 붙여넣을 수 있는 문장
    이유             왜 이 수정이 필요한가 (우리 회사 관점의 실익)
    협상 우선순위    꼭 고쳐야 하는지, 되면 좋은지

그리고 고객사 양식(상대방이 준 표준서식)에서는 **처음부터 가장 공격적인 문구를
넣지 않는다**. 그러면 협상이 시작되기 전에 거부당한다. 두 단계로 제시한다:

    Practical Position   상대방이 수용할 가능성이 높은 최소수정안
    Fallback Position    최소수정안이 거부될 때 물러설 선(그래도 지켜야 할 것)

설계 — **하드코딩 금지**. 특정 조항번호·회사명을 쓰지 않는다. 수정 방식은
finding 이 이미 들고 있는 정보(원문 유무, 위치, 수정문안)에서 유도한다.
"""
from __future__ import annotations

import re
from typing import Any

METHOD_REPLACE = "replace_text"
METHOD_ADD_PROVISO = "add_proviso"
METHOD_NEW_PARAGRAPH = "new_paragraph"
METHOD_NEW_CLAUSE = "new_clause"
METHOD_DELETE = "delete"

METHOD_LABELS = {
    METHOD_REPLACE: "문구 교체",
    METHOD_ADD_PROVISO: "단서 추가",
    METHOD_NEW_PARAGRAPH: "항 신설",
    METHOD_NEW_CLAUSE: "조항 신설",
    METHOD_DELETE: "삭제",
}

PRIORITY_MUST = "must_fix"
PRIORITY_SHOULD = "negotiable"
PRIORITY_NICE = "acceptable"

PRIORITY_LABELS = {
    PRIORITY_MUST: "1순위 — 꼭 고쳐야 함",
    PRIORITY_SHOULD: "2순위 — 협상 가능하면 고침",
    PRIORITY_NICE: "3순위 — 현 상태로도 수용 가능",
}

#: 협상 버킷(senior_counsel_judgment) 값을 우선순위로 옮긴다.
_BUCKET_TO_PRIORITY = {
    "must_fix": PRIORITY_MUST,
    "negotiable": PRIORITY_SHOULD,
    "acceptable": PRIORITY_NICE,
}

#: 자리표시자 원문 — 대응 조항이 없어 신설로 제안하는 finding.
_RX_PLACEHOLDER = re.compile(r"^\s*(?:\[|\()?(?:해당\s*조항\s*없음|없음|N/?A|"
                             r"신설|계약\s*전반|contract[- ]wide)")

#: 단서로 들어가는 수정문안. "다만", "단," 으로 시작하면 문구 교체가 아니라
#: 예외를 덧붙이는 것이므로 상대방이 받아들이기 쉽다.
_RX_PROVISO = re.compile(r"^\s*(?:다만|단[,.\s]|provided\s+that)", re.IGNORECASE)

#: 삭제를 제안하는 수정문안.
_RX_DELETE = re.compile(r"(?:삭제(?:한다|할|하고|요청)|delete|strike)")


def infer_method(cr: dict[str, Any]) -> str:
    """이 finding 의 수정 방식을 원문·수정문안 형태에서 유도한다."""
    # 자리표시자 판정은 redline 쪽 기준을 그대로 쓴다. 여기서 따로 만들면
    # 두 곳의 기준이 어긋나 "조항 신설"이 하나도 잡히지 않는다(2026-09-09
    # 실측: 42건 전부 "문구 교체"로 분류됐다).
    from runtime.review.redline_instruction import (
        LOCATION_CONTRACT_WIDE_NEW,
        is_placeholder_original,
    )

    original = str(cr.get("original_text") or "")
    rewrite = str(cr.get("suggested_rewrite") or "")
    location = str(cr.get("edit_location") or "")

    if (
        not original.strip()
        or is_placeholder_original(original)
        or _RX_PLACEHOLDER.match(original)
        or location == LOCATION_CONTRACT_WIDE_NEW
    ):
        return METHOD_NEW_CLAUSE
    if _RX_DELETE.search(rewrite) and len(rewrite) < 120:
        return METHOD_DELETE
    if _RX_PROVISO.match(rewrite):
        return METHOD_ADD_PROVISO
    if "신설" in location or "추가" in location:
        return METHOD_NEW_PARAGRAPH
    return METHOD_REPLACE


def _priority_for(cr: dict[str, Any]) -> str:
    bucket = str(cr.get("negotiation_bucket") or "")
    if bucket in _BUCKET_TO_PRIORITY:
        return _BUCKET_TO_PRIORITY[bucket]
    tier = str(cr.get("risk_tier") or "").upper()
    if tier in ("CRITICAL", "HIGH"):
        return PRIORITY_MUST
    if tier == "MEDIUM":
        return PRIORITY_SHOULD
    return PRIORITY_NICE


def _fallback_for(cr: dict[str, Any], method: str) -> dict[str, str]:
    """최소수정안이 거부될 때 물러설 선.

    구체적인 문구를 새로 만들지 않는다 — 근거 없는 문장을 만들어내는 것이
    이 엔진이 피하려는 문제다. 대신 "무엇은 양보할 수 있고 무엇은 지켜야
    하는가"를 수정 방식에 맞춰 알려준다.
    """
    tier = str(cr.get("risk_tier") or "").upper()
    if method == METHOD_NEW_CLAUSE:
        return {
            "position": "조항 신설이 거부되면, 같은 내용을 회의록·부속합의서로 남기는 선까지 물러섭니다.",
            "hold": "신설 자체를 포기하더라도 그 위험을 누가 부담하는지는 서면으로 확인받아야 합니다.",
        }
    if method == METHOD_DELETE:
        return {
            "position": "삭제가 거부되면 적용 범위를 우리 귀책사유가 있는 경우로 한정하는 단서를 요청합니다.",
            "hold": "무제한 적용은 받아들일 수 없습니다 — 한도나 귀책요건 중 하나는 반드시 필요합니다.",
        }
    if method == METHOD_ADD_PROVISO:
        return {
            "position": "단서 전체가 거부되면 예외 사유를 불가항력과 상대방 귀책으로 축소해 다시 제안합니다.",
            "hold": "상대방 귀책으로 인한 경우까지 우리가 부담하는 구조는 유지할 수 없습니다.",
        }
    if tier in ("CRITICAL", "HIGH"):
        return {
            "position": "제안 문구가 거부되면 한도(금액·기간·범위) 중 하나만이라도 명시하는 선으로 물러섭니다.",
            "hold": "노출을 계산할 수 없는 상태(한도·예외 전무)는 받아들일 수 없습니다.",
        }
    return {
        "position": "제안 문구가 거부되면 현행 문구를 유지하되 해석 기준을 회의록에 남깁니다.",
        "hold": "해석이 우리에게 불리하게 확장되지 않도록 범위 문구는 지켜야 합니다.",
    }


def build_practical_positions(clause_results: list[dict[str, Any]]) -> dict[str, Any]:
    """각 finding 에 다섯 항목과 Practical / Fallback 두 단계를 붙인다.

    finding 을 지우거나 등급을 바꾸지 않는다 — 표현 방식만 정리한다.
    """
    counts: dict[str, int] = {}
    method_counts: dict[str, int] = {}
    annotated = 0

    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        rewrite = str(cr.get("suggested_rewrite") or "").strip()
        reason = str(
            cr.get("rewrite_reason")
            or cr.get("legal_business_reason")
            or cr.get("issue")
            or ""
        ).strip()
        if not rewrite and not reason:
            continue

        method = infer_method(cr)
        priority = _priority_for(cr)
        location = str(
            cr.get("edit_location") or cr.get("article_no") or cr.get("clause_id") or ""
        ).strip()

        cr["practical_position"] = {
            "location": location,
            "method": method,
            "method_label": METHOD_LABELS.get(method, method),
            "text": rewrite,
            "reason": reason,
            "priority": priority,
            "priority_label": PRIORITY_LABELS.get(priority, priority),
        }
        cr["fallback_position"] = _fallback_for(cr, method)
        counts[priority] = counts.get(priority, 0) + 1
        method_counts[method] = method_counts.get(method, 0) + 1
        annotated += 1

    return {
        "annotated_count": annotated,
        "priority_counts": {
            PRIORITY_LABELS.get(k, k): v for k, v in counts.items()
        },
        "method_counts": {
            METHOD_LABELS.get(k, k): v for k, v in method_counts.items()
        },
        "missing_fields": [
            str(cr.get("clause_id") or "")
            for cr in clause_results
            if isinstance(cr, dict)
            and isinstance(cr.get("practical_position"), dict)
            and not str(cr["practical_position"].get("location") or "").strip()
        ],
    }
