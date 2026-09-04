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

from runtime.review.canonical_transaction_facts import QUESTION_TO_FIELD as _QUESTION_TO_FIELD

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

    명시적 사용자 답변은 항상 덮어쓴다(2026-09-04 지시 — "explicit user
    answer > confirmed document text > AI inference > rule inference").
    기존에는 이미 값이 있으면(AI가 먼저 채웠거나 이전 호출에서 채워진 경우)
    보존만 했는데, 이 경우 AI가 잘못 추정한 값("미확인" 또는 오추정 당사자
    명)이 사용자가 나중에 명시적으로 답변한 사실관계보다 우선시되는 문제가
    있었다 — 계약서만으로 확정할 수 없는 거래실질을 사용자가 보충한
    답변이므로, 그 어떤 추정보다 신뢰도가 높다.
    """
    if not isinstance(answers, dict) or not answers:
        return
    for qid, field in _QUESTION_TO_FIELD.items():
        val = answers.get(qid)
        if not (isinstance(val, str) and val.strip()):
            continue
        fields[field] = val.strip()

    relationship_answer = answers.get("Q-TXN-008-relationship-type")
    if isinstance(relationship_answer, str):
        relationship_key = relationship_answer.strip()
        relationship_label = _RELATIONSHIP_TYPE_LABELS.get(relationship_key, relationship_key)
        target_field = _RELATIONSHIP_TYPE_TO_FIELD.get(relationship_key)
        if target_field:
            fields[target_field] = relationship_label
        if relationship_key == "seller_party" and not (isinstance(answers.get("Q-TXN-001-seller"), str) and answers["Q-TXN-001-seller"].strip()):
            # 관계유형에서 "매매계약 당사자(판매자)"를 직접 골랐다면, 그
            # 자체가 seller 필드에 대한 답이기도 하다 — 다만 seller 질문에
            # 별도 텍스트 답변이 있으면 그쪽이 더 구체적이므로 그 답을
            # 우선한다(위에서 이미 fields["seller"]에 반영됨).
            fields["seller"] = "본인(관계유형 답변에서 매매계약 당사자로 확인)"

    dependency_answer = answers.get("Q-TXN-009-existing-contract-link")
    if isinstance(dependency_answer, str) and dependency_answer.strip():
        fields["dependency_on_existing_contract"] = dependency_answer.strip()
