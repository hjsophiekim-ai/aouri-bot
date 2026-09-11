"""다른 계약유형의 템플릿·문구가 섞인 finding 은 결과에 내보내지 않는다.

2026-09-11 지시 — "다른 계약유형의 템플릿·문구가 섞이면 결과 생성 금지."

무엇이 문제였나
─────────────
최종 자가점검(`final_counsel_gate`)의 5번 항목이 이 오염을 **감지**하고 있었다.
그러나 감지 결과는 `REVIEW_NEEDS_ATTENTION` 이라는 상태 한 줄로만 남았고,
오염된 finding 자체는 화면과 문서에 그대로 실렸다. 담당자 입장에서는

  · NDA 검토서에 "판매장려금 지급기준" 지적이 실리고,
  · 바터 계약 검토서에 "기성고 정산" 문안이 실린다.

계약에 존재하지도 않는 제도를 근거로 한 지적이므로 협상에서 쓸 수 없고, 검토서
전체의 신뢰를 떨어뜨린다. 감지했다면 내보내지 않아야 한다.

판정 기준
────────
계약 **원문에 없는** 타 유형 전용 어휘만 오염으로 본다. 계약이 스스로 그
단어를 쓰고 있다면 그것은 이 계약의 내용이므로 오염이 아니다 — 이 구분이
없으면 정상 finding 이 대량으로 지워진다.

거래 원형(`transaction_type`)은 `legal_state` 가 확정한 canonical 값을 쓴다.
여기서 다시 추론하지 않는다.
"""
from __future__ import annotations

from typing import Any

CROSS_TYPE_TEMPLATE_BLOCKED = "CROSS_TYPE_TEMPLATE_BLOCKED"

_TEXT_FIELDS = (
    "issue_title", "problem", "rewrite_reason", "legal_business_reason",
    "suggested_rewrite", "proposed_revision", "recommendation_text",
    "negotiation_strategy", "worst_case_scenario",
)


def _blob(cr: dict[str, Any]) -> str:
    parts = [str(cr.get(k) or "") for k in _TEXT_FIELDS]
    detected = cr.get("detected_issue_list")
    if isinstance(detected, list):
        parts += [
            str(d.get("issue_title") or "") for d in detected if isinstance(d, dict)
        ]
    return " ".join(parts)


def foreign_terms_in(cr: dict[str, Any], *, transaction_type: str, contract_text: str) -> list[str]:
    """이 finding 이 쓰고 있는, 계약 원문에 없는 타 유형 전용 어휘."""
    from runtime.review.final_counsel_gate import _foreign_vocabulary_for

    terms = _foreign_vocabulary_for(str(transaction_type or ""))
    if not terms:
        return []
    body = str(contract_text or "")
    blob = _blob(cr)
    return [t for t in terms if t in blob and t not in body]


def enforce_no_cross_type_template(
    clause_results: list[dict[str, Any]],
    *,
    transaction_type: str,
    contract_text: str,
) -> list[dict[str, Any]]:
    """타 유형 템플릿이 섞인 finding 을 결과에서 제거한다.

    제거 내역을 돌려준다 — 조용히 사라지지 않게 하기 위함이다.
    """
    if not str(transaction_type or "").strip() or not str(contract_text or "").strip():
        return []

    removed: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            kept.append(cr)
            continue
        if bool(cr.get("dedup_suppressed")):
            kept.append(cr)
            continue
        terms = foreign_terms_in(
            cr, transaction_type=transaction_type, contract_text=contract_text,
        )
        if not terms:
            kept.append(cr)
            continue
        removed.append({
            "clause_id": str(cr.get("clause_id") or ""),
            "display_path": str(cr.get("display_path") or ""),
            "foreign_terms": terms,
            "transaction_type": str(transaction_type),
            "status": CROSS_TYPE_TEMPLATE_BLOCKED,
        })
    clause_results[:] = kept
    return removed
