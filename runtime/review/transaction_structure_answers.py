"""거래구조 확인 질문(Q-TXN-*)의 답변을 Contract Legal Map 필드에 반영.

범용 사내변호사형 검토 엔진 전면 보정(2026-09-04 지시) — AI가 없어도
(`ai_provider=None`, regex fallback 경로) 사용자가 질문 세션에서 실제로
답변한 판매자·소유권·대금수령 등 사실관계가 Contract Legal Map에 그대로
채워지도록 한다. `runtime/questions/storage.py::save_answers()`가 저장하는
`{question_id: value}` 형태의 구조화된 답변을 직접 사용한다 — 자유서술
review_focus 텍스트를 다시 파싱하지 않는다(더 신뢰성 높은 경로).
"""
from __future__ import annotations

from typing import Any

# Q-TXN-* question_id -> Contract Legal Map field name.
_QUESTION_TO_FIELD: dict[str, str] = {
    "Q-TXN-001-seller": "seller",
    "Q-TXN-002-owner": "owner_of_goods",
    "Q-TXN-003-revenue": "revenue_recipient",
    "Q-TXN-004-payment-collection": "payment_recipient",
    "Q-TXN-005-inventory-risk": "inventory_risk_holder",
    "Q-TXN-006-consumer-liability": "consumer_liability_holder",
    "Q-TXN-007-ip-authenticity": "ip_authenticity_liability",
    "Q-TXN-009-existing-contract-link": "existing_related_contract",
}

# Q-TXN-008(관계유형, single_choice)은 값에 따라 intermediary/
# sales_support_provider 중 해당하는 필드에 답변 텍스트를 채운다 — 두 필드
# 모두 "누구인지"를 서술하는 자리이므로, 선택된 유형에 맞는 필드에만 쓴다.
_RELATIONSHIP_TYPE_TO_FIELD: dict[str, str] = {
    "sales_support_service": "sales_support_provider",
    "intermediary": "intermediary",
}
_RELATIONSHIP_TYPE_LABELS: dict[str, str] = {
    "sales_support_service": "단순 판매지원 용역자(매매계약 당사자 아님)",
    "seller_party": "매매계약 당사자(판매자)",
    "consignment_seller": "위탁판매자(소유권은 공급자에게 있음)",
    "intermediary": "중개자",
    "unknown": "미상",
}


def apply_transaction_structure_answers(fields: dict[str, Any], answers: dict[str, Any] | None) -> None:
    """In place: Contract Legal Map `fields` dict에 Q-TXN-* 답변을 채운다.

    이미 값이 있는 필드(AI가 이미 채웠거나 이전 호출에서 채워진 경우)는
    덮어쓰지 않는다 — 사용자가 명시적으로 답변한 사실관계는 그 자체로
    신뢰도가 높으므로 채우는 쪽으로만 동작하고, 상충 시 기존 값을 보존해
    "무엇을 근거로 이 값이 됐는지" 추적 가능성을 해치지 않는다.
    """
    if not isinstance(answers, dict) or not answers:
        return
    for qid, field in _QUESTION_TO_FIELD.items():
        val = answers.get(qid)
        if not (isinstance(val, str) and val.strip()):
            continue
        if not fields.get(field):
            fields[field] = val.strip()

    relationship_answer = answers.get("Q-TXN-008-relationship-type")
    if isinstance(relationship_answer, str):
        relationship_key = relationship_answer.strip()
        relationship_label = _RELATIONSHIP_TYPE_LABELS.get(relationship_key, relationship_key)
        target_field = _RELATIONSHIP_TYPE_TO_FIELD.get(relationship_key)
        if target_field and not fields.get(target_field):
            fields[target_field] = relationship_label
        if relationship_key == "seller_party" and not fields.get("seller"):
            # 관계유형에서 "매매계약 당사자(판매자)"를 직접 골랐다면, 그
            # 자체가 seller 필드에 대한 답이기도 하다 — 다만 seller 질문에
            # 별도 텍스트 답변이 있으면 그쪽이 더 구체적이므로 이미 값이
            # 있으면 덮어쓰지 않는다(위 not fields.get 조건).
            fields["seller"] = "본인(관계유형 답변에서 매매계약 당사자로 확인)"

    dependency_answer = answers.get("Q-TXN-009-existing-contract-link")
    if isinstance(dependency_answer, str) and dependency_answer.strip() and not fields.get("dependency_on_existing_contract"):
        fields["dependency_on_existing_contract"] = dependency_answer.strip()
