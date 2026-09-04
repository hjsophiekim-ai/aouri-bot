"""정부지원·보조금·투자금·보험금 등 조건부 자금 구조 결정론적 탐지.

범용 사내변호사형 검토 고도화(2026-09-03 지시) — `contract_legal_map.py`의
Transaction Map 필드(`conditional_funding_structure`,
`refund_or_clawback_obligation_holder`)는 AI 전용이라 AI 미가동 시 항상
None이다(Layer 1은 AI 없이도 항상 동작해야 한다는 기존 요구사항과 충돌).
이 모듈은 `common_legal_risk.py`의 다른 Layer 1 체크와 같은 방식(regex 기반,
조항번호/계약유형 무관)으로 조건부 자금 구조를 별도로 점검한다.

정부지원금·보조금·투자금·보험금 등 제3자가 비용을 부담하는 언어가 있으면,
지원자격 유지조건/지급 전제조건/중도탈락/clawback·환수/반환주체 구분/
정책변경·지원중단/별도 참여계약 관계 중 몇 가지가 실제로 다뤄지는지 확인하고,
충분히 다뤄지지 않았으면 MEDIUM finding과 함께 "확인이 필요한 사실관계"
목록을 생성한다(신규 질문 제출 플로우를 만들지 않고 `legal_applicability_
review.py`의 `additional_facts_needed` 필드 패턴을 재사용).
"""
from __future__ import annotations

import re
from typing import Any

_RX_CONDITIONAL_FUNDING_TRIGGER = re.compile(
    r"정부\s*지원|보조금|지원사업|지원금|국고보조|투자금(?:을|이)?\s*(?:지급|지원)|보험금"
    r"|government\s+(?:grant|program|subsidy|support)|state\s+aid|public\s+funding"
    r"|support\s+company\s+under\s+the",
    re.IGNORECASE,
)

_RX_ELIGIBILITY_CONDITION = re.compile(
    r"자격\s*(?:유지|상실|박탈)|remain(?:s)?\s+(?:eligible|in\s+the)|eligib(?:le|ility)",
    re.IGNORECASE,
)
_RX_PAYMENT_PRECONDITION = re.compile(
    r"(?:만|경우에\s*한하여)\s*지급|only\s+when|only\s+if|provided,?\s*however,?\s*that",
    re.IGNORECASE,
)
_RX_DROPOUT = re.compile(
    r"중도\s*(?:탈락|포기|종료)|withdraw(?:al)?\s+from\s+the\s+program|drop(?:s|ped)?\s+out",
    re.IGNORECASE,
)
_RX_CLAWBACK = re.compile(
    r"환수|clawback|repay(?:ment)?\s+of\s+(?:the\s+)?(?:grant|subsidy|support|fund(?:ing)?)",
    re.IGNORECASE,
)
_RX_POLICY_CHANGE = re.compile(
    r"정책\s*변경|지원\s*(?:중단|종료)|program\s+is\s+(?:terminated|discontinued)|change\s+in\s+(?:government\s+)?policy",
    re.IGNORECASE,
)
_RX_PARTICIPATION_AGREEMENT = re.compile(
    r"participation\s+agreement|참여\s*(?:계약|협약)|별도\s*협약",
    re.IGNORECASE,
)
_RX_FAULT_BASED_REPAY_SPLIT = re.compile(
    r"(?:consultant|컨설턴트|을)[^.\n]{0,30}(?:귀책|fault|breach)[^.\n]{0,60}(?:반환|repay|refund)"
    r"|(?:company|갑)[^.\n]{0,30}(?:귀책|fault|breach)[^.\n]{0,60}(?:반환|repay|refund)",
    re.IGNORECASE,
)

_SUBCHECKS: list[tuple[str, re.Pattern[str], str]] = [
    ("eligibility_condition", _RX_ELIGIBILITY_CONDITION, "지원자격 유지조건의 구체적 내용(무엇을 하면 자격을 잃는지)"),
    ("dropout", _RX_DROPOUT, "중도탈락 시 처리 방법"),
    ("clawback", _RX_CLAWBACK, "clawback/환수 발생 요건과 범위"),
    ("fault_based_repay_split", _RX_FAULT_BASED_REPAY_SPLIT, "Consultant 귀책 시와 Company 귀책 시 반환주체 구분"),
    ("policy_change", _RX_POLICY_CHANGE, "정책변경·지원중단 시 처리 방법"),
    ("participation_agreement", _RX_PARTICIPATION_AGREEMENT, "별도 Participation Agreement와 본 계약의 관계"),
]


def _apply_conditional_funding_review(clause_results: list[dict[str, Any]], full_text: str) -> None:
    existing = {str(cr.get("clause_id") or "") for cr in clause_results if isinstance(cr, dict)}
    if "clr_conditional_funding_unclear" in existing:
        return
    text = full_text or ""
    if not _RX_CONDITIONAL_FUNDING_TRIGGER.search(text):
        return

    missing: list[str] = []
    present: list[str] = []
    for name, pat, question in _SUBCHECKS:
        if pat.search(text):
            present.append(name)
        else:
            missing.append(question)

    # 지급 전제조건(eligibility/payment precondition) 자체는 확인됐어도,
    # "실패 시 무슨 일이 일어나는가"(중도탈락/clawback/반환주체구분/정책변경)
    # 4개 중 과반이 빠져 있으면 조건부 자금 구조가 실질적으로 불명확한
    # 것으로 본다.
    _failure_side = {"dropout", "clawback", "fault_based_repay_split", "policy_change"}
    _failure_missing = [q for name, _, q in _SUBCHECKS if name in _failure_side and name not in present]
    if len(_failure_missing) < 2:
        return

    has_eligibility = "eligibility_condition" in present
    has_precondition = bool(_RX_PAYMENT_PRECONDITION.search(text))

    clause_results.append({
        "clause_id": "clr_conditional_funding_unclear",
        "article_number": None,
        "paragraph_number": None,
        "display_path": None,
        "clause_title": "[공통 법률리스크] 정부지원·조건부 자금 구조 중 중도탈락/환수/반환주체 불명확",
        "clause_number_uncertain": True,
        "clause_topic": "other",
        "original_text": "(조건부 자금 관련 조항 전반)",
        "risk_tier": "MEDIUM",
        "severity": "MEDIUM",
        "high_risk": False,
        "must_fix": False,
        "approval_required": False,
        "review_tier": "SUGGEST",
        "suggested_rewrite": (
            "지원자격 상실·중도탈락·정책변경으로 지원금 지급이 중단되거나 환수되는 경우, 그 원인이 "
            "Consultant(또는 계약이행 당사자)의 귀책사유인지 Company의 귀책사유인지에 따라 반환주체를 "
            "명확히 구분하고, 관련 Participation Agreement가 있다면 본 계약과의 관계(우선순위, 충돌 시 "
            "처리)를 명시한다."
        ),
        "rewrite_reason": (
            "정부지원(제3자 지원기관 포함)·보조금·투자금 등 조건부 자금 구조는 있으나, 지급이 중단되거나 "
            "환수되는 상황에서 반환주체와 처리 방법이 계약상 충분히 다뤄지지 않는다."
        ),
        "legal_business_reason": (
            "지원자격 유지조건" + ("(있음)" if has_eligibility else "(불명확)") + ", 지급 전제조건"
            + ("(있음)" if has_precondition else "(불명확)")
            + "은 확인되나, 중도탈락·clawback/환수·귀책사유별 반환주체 구분·정책변경 대응 중 다수가 "
            "명시되어 있지 않아, 실제 지원 중단·환수가 발생했을 때 누가 얼마를 반환해야 하는지 예측할 "
            "수 없다."
        ),
        "suggested_direction": [
            "지원금 지급 중단·환수 시나리오별(누구의 귀책인지) 반환주체를 명시하고, 별도 참여계약과의 "
            "관계를 확인",
        ],
        "negotiation_position": "실제 지원사업 운영기관과의 별도 협약(Participation Agreement 등) 제출을 요청해 반환주체·환수 조건을 먼저 확인.",
        "additional_facts_needed": _failure_missing,
        "confidence": 0.7,
        "is_common_legal_risk": True,
        "has_rewrite_change": True,
        "display_kind": "guidance",
        "dedup_suppressed": False,
        "keep_as_is": False,
        "user_focus_hit": False,
        "factual_hit": False,
        "ai_deep_reviewed": False,
    })
