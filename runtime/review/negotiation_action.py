"""legal_risk(법적 심각도)와 negotiation_priority(실제 협상 우선순위)를
분리하는 판단 레이어(2026-09-04 지시, Senior In-house Counsel).

아우리봇은 "모든 불리한 문구를 최대한 제거하는 외부 로펌"이 아니라
"거래를 성사시키면서 우리 회사의 치명적 리스크만 줄이고, 상대방의
협상력과 거래목적까지 고려해 실제 수정 우선순위를 정하는 Senior
사내변호사"처럼 작동해야 한다는 지시를 반영한다.

legal_risk == HIGH라도 negotiation_priority == ACCEPT일 수 있고(우리 회사가
실제로 부담하지 않는 상대방 전용 리스크), 반대로 legal_risk == MEDIUM인데
negotiation_priority == MUST_FIX일 수도 있다(예: 무제한 상호 indemnity처럼
법적으로는 중간 등급이지만 체결 즉시 우리 회사가 실제로 노출되는 구조).
"""
from __future__ import annotations

import re
from typing import Any

from runtime.review.legal_effect_taxonomy import infer_legal_effects

# 정부/지원기관 상대 계약에서 "지원조건/관리권한"류로 보아 자동 MUST_FIX를
# 금지해야 하는 finding — 정당한 자금 통제 메커니즘이지 독소조항이 아니다.
_FUNDING_CONDITION_CLAUSE_IDS = {
    "clr_conditional_funding_unclear",
}

# 상대방(특히 정부/지원기관)의 정당한 자금 통제 메커니즘을 "전부 삭제"하는
# 방향의 수정안은 거래 자체를 무너뜨릴 수 있어 협상 실현가능성이 낮다는
# 신호(2026-09-04 지시, 요구 8).
_RX_WHOLESALE_DELETION = re.compile(
    r"전부\s*삭제|완전히\s*배제|조건\s*자체를?\s*삭제|delete\s+(?:the\s+)?(?:entire|whole)\s+clause",
    re.IGNORECASE,
)

# 상대방의 정당한 보호장치로 보아 기본적으로 ACCEPT 후보로 두는 신호.
_RX_LEGITIMATE_COUNTERPARTY_PROTECTION = re.compile(
    r"검수권|감사권|상호\s*(?:비밀유지|기밀유지|indemnif)|일반적인\s*비밀유지|"
    r"\baudit\s+right\b|\binspection\s+right\b|\bmutual\s+confidentiality\b",
    re.IGNORECASE,
)

# "우리 회사에 실제로 무제한/전이형 부담"을 시사하는 legal-effect 태그 —
# 이 중 하나라도 걸리면(그리고 direct/contingent exposure이면) MUST_FIX 후보.
_HIGH_TRANSFER_EFFECT_TAGS = {
    "uncapped_liability",
    "third_party_debt_guarantee",
    "counterparty_broad_self_liability_shield",
    "cross_default",
}


def classify_negotiation_action(cr: dict[str, Any], *, counterparty_role: str) -> dict[str, str]:
    """finding 하나를 받아 legal_risk/business_exposure/negotiation_priority를
    계산해 반환한다. 원본 dict는 변경하지 않는다(호출부에서 병합)."""
    legal_risk = str(cr.get("risk_tier") or cr.get("severity") or "LOW").upper()
    exposure = str(cr.get("exposure_category") or "indirect_operational")
    clause_id = str(cr.get("clause_id") or "")
    text = str(cr.get("original_text") or "")

    # 1. 상대방 전용 리스크(우리 회사가 부담하지 않음) — 원칙적으로 ACCEPT.
    if exposure == "counterparty_only":
        priority = "ACCEPT"
    else:
        tags = set(infer_legal_effects(text))
        has_high_transfer = bool(tags & _HIGH_TRANSFER_EFFECT_TAGS)

        # 2. 우리 회사가 direct/contingent로 실제 부담하고, 무제한/전이형
        #    효과가 있으면 MUST_FIX.
        if exposure in ("direct", "contingent") and legal_risk == "HIGH" and has_high_transfer:
            priority = "MUST_FIX"
        # 3. 정부/지원기관의 정당한 자금 통제 메커니즘은 자동 MUST_FIX 금지.
        elif counterparty_role == "government_or_funding_agency" and clause_id in _FUNDING_CONDITION_CLAUSE_IDS:
            priority = "NEGOTIATE_IF_POSSIBLE"
        elif legal_risk == "HIGH":
            priority = "MUST_FIX"
        elif legal_risk == "MEDIUM":
            priority = "NEGOTIATE_IF_POSSIBLE"
        else:
            priority = "ACCEPT"

        # 5. 상대방의 정당한 보호장치 신호가 있으면 한 단계 낮춘다(단, 이미
        #    MUST_FIX인 경우는 낮추지 않음 — 예: 실제로 무제한 indemnity라면
        #    "상호"라는 단어만으로 면제하지 않는다).
        if priority == "NEGOTIATE_IF_POSSIBLE" and _RX_LEGITIMATE_COUNTERPARTY_PROTECTION.search(text):
            priority = "ACCEPT"

    recommended_starting_tier = (
        "practical" if counterparty_role in ("government_or_funding_agency", "customer") else "ideal"
    )

    # 정부/지원기관의 정당한 자금 통제 메커니즘(clr_conditional_funding_unclear
    # 등)에 대해 rewrite/negotiation_ladder가 "전부 삭제"류를 제안하면,
    # 그 수정안이 거래 목적 자체를 무너뜨릴 수 있다는 실현가능성 경고를
    # 별도로 남긴다(수정안 자체를 바꾸지는 않는다 — 방어적 신호일 뿐).
    negotiation_feasibility = ""
    if counterparty_role == "government_or_funding_agency" and clause_id in _FUNDING_CONDITION_CLAUSE_IDS:
        ladder = cr.get("negotiation_ladder")
        ladder_text = " ".join(
            f"{t.get('action', '')} {t.get('rewrite_text', '')}"
            for t in ladder if isinstance(t, dict)
        ) if isinstance(ladder, list) else ""
        rewrite_text = str(cr.get("suggested_rewrite") or cr.get("proposed_revision") or "")
        if _RX_WHOLESALE_DELETION.search(ladder_text) or _RX_WHOLESALE_DELETION.search(rewrite_text):
            negotiation_feasibility = "LOW"

    return {
        "legal_risk": legal_risk,
        "business_exposure": exposure,
        "negotiation_priority": priority,
        "recommended_starting_tier": recommended_starting_tier,
        "negotiation_feasibility": negotiation_feasibility,
    }
