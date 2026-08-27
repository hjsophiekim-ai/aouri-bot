"""Layer 1 — common legal risk rules.

These rules check for risk patterns that a corporate lawyer reviews in
EVERY contract, regardless of contract type: one-sided exemption from
liability (even for the counterparty's own fault), unlimited recourse
(including legal costs), blanket incorporation of external standard terms,
ambiguous payment-guarantee/joint-liability language, competitor/other-
institution dealing restrictions, and termination rights disproportionate
to the contract term.

Unlike the type-specific checklists in clause_level.py (_apply_supplier_
product_checklist, _apply_advisory_ip_review, etc.), rules here carry NO
contract_class gate — they are meant to survive the "계약유형 HARD BLOCK"
that filters out type-mismatched Layer 2 rules. HARD BLOCK must only ever
apply to Layer 2 (type-specific) rules; Layer 1 always runs.
"""
from __future__ import annotations

import re
from typing import Any

_CLR_ITEMS: list[dict[str, Any]] = [
    {
        "id": "clr_fault_blind_exemption",
        "name": "귀책사유 불문 일방적 면책",
        "present": re.compile(
            r"귀책사유.{0,15}(여부에)?\s*(관계없이|불문하고|가리지\s*않고).{0,30}"
            r"(배상\s*책임|책임)을?\s*(지지\s*아니한다|부담하지\s*아니한다|면한다|없다)",
            re.IGNORECASE,
        ),
        "risk": "HIGH",
        "direction": "상대방의 고의·과실(귀책사유)이 있는 경우까지 면책되지 않도록, 고의 또는 중과실의 경우는 면책 예외로 명시",
        "reason": (
            "귀책사유 유무와 관계없이 일체의 배상책임을 지지 않는다는 문언은 "
            "상대방의 고의·중과실로 발생한 손해까지 면책하는 결과가 되어 "
            "민법 제397조의2(고의·중과실 면책 특약의 효력 제한 법리) 및 "
            "약관규제법상 무효 소지가 있는 과도한 면책조항이다."
        ),
        "rewrite": (
            "본 조에 따른 면책은 수탁자(또는 상대방)의 고의 또는 중대한 과실이 없는 경우에 한하여 적용된다. "
            "수탁자의 고의 또는 중대한 과실로 발생한 손해에 대하여는 본 조의 면책이 적용되지 아니한다."
        ),
        "clause_topic": "damage",
    },
    {
        "id": "clr_unlimited_recourse_with_legal_costs",
        "name": "소송비용·변호사보수 포함 무제한 구상",
        "present": re.compile(
            r"(소송\s*비용|변호사\s*보수).{0,25}(구상|배상)|구상.{0,25}(소송\s*비용|변호사\s*보수)",
            re.IGNORECASE,
        ),
        "risk": "HIGH",
        "direction": "구상 범위에 상한(예: 계약금액 한도)을 두고, 상대방의 귀책사유가 있는 경우로 한정",
        "reason": (
            "손해배상액뿐 아니라 소송비용·변호사보수까지 포함하여 상한 없이 구상할 수 있도록 "
            "규정하면 실제 발생한 손해를 초과하는 금액까지 부담할 위험이 있고, "
            "상대방이 소송 수행 방식을 통제할 수 없는 당사자에게 그 비용 전부를 전가하는 결과가 된다."
        ),
        "rewrite": (
            "구상 범위는 실제 발생한 직접손해로 한정하며, 계약금액(또는 연간 대금)을 상한으로 한다. "
            "소송비용·변호사보수는 법원이 정한 소송비용 산입 기준을 초과하지 않는 범위에서만 구상할 수 있다."
        ),
        "clause_topic": "damage",
    },
    {
        "id": "clr_recourse_generic",
        "name": "구상권 범위·한도 불명확",
        "present": re.compile(r"(제반\s*비용|배상액)을?\s*.{0,10}구상할\s*수\s*있다", re.IGNORECASE),
        "risk": "MEDIUM",
        "direction": "구상 가능 범위와 한도를 구체적으로 특정",
        "reason": "구상 대상이 되는 비용의 범위·한도가 특정되어 있지 않아 분쟁 시 과다 청구로 이어질 수 있다.",
        "rewrite": "구상 대상 비용은 실제 발생하고 객관적으로 증빙 가능한 직접손해로 한정한다.",
        "clause_topic": "damage",
        "skip_if_also_matched": "clr_unlimited_recourse_with_legal_costs",
    },
    {
        "id": "clr_competitor_restriction_notice",
        "name": "동종 거래·경쟁 관계 제한(사전통보 의무)",
        "present": re.compile(
            r"(본\s*(계약|약정)).{0,10}같거나\s*유사한\s*내용의.{0,20}(계약|약정)을\s*체결.{0,30}사전에.{0,15}통보",
            re.IGNORECASE,
        ),
        "risk": "MEDIUM",
        "direction": "사전통보 의무의 실질적 목적(이해상충 방지 등)을 명확히 하고, 통보 거부/지연에 따른 불이익이 없음을 확인",
        "reason": (
            "동종·유사 계약을 다른 상대방과 체결하기 전 상대방에게 사전 통보하도록 하는 조항은 "
            "실질적으로 거래 상대방 선택의 자유를 제약하거나, 통보 내용을 근거로 영업기밀이 "
            "상대방에게 노출될 위험이 있다."
        ),
        "rewrite": (
            "사전통보 의무는 이해상충 방지 목적에 한정하며, 통보 사실 자체가 계약 체결이나 "
            "조건 협상에 영향을 미치지 아니한다."
        ),
        "clause_topic": "other",
    },
    {
        "id": "clr_external_terms_incorporation",
        "name": "외부 표준약관·내부규정 포괄편입",
        "present": re.compile(
            r"(표준\s*(시험)?\s*약관|내부\s*규정|업무\s*규정|운영\s*규정).{0,10}(적용|준용)한다",
            re.IGNORECASE,
        ),
        "risk": "MEDIUM",
        "direction": "편입되는 약관·규정의 명칭·시행일·열람 방법을 특정하고, 계약 체결 시점 내용으로 고정(사후 일방 변경 배제)",
        "reason": (
            "상대방이 일방적으로 제정·개정할 수 있는 내부 약관·규정을 조항 내용을 특정하지 않고 "
            "그대로 편입시키면, 계약 상대방이 실제로 어떤 의무를 부담하는지 계약서만으로는 알 수 없고 "
            "상대방이 사후에 규정을 변경하여 불리하게 적용할 위험이 있다."
        ),
        "rewrite": (
            "본 약정에 편입되는 표준약관·내부규정은 본 약정 체결일 현재 시행 중인 내용을 기준으로 하며, "
            "위탁자에게 불리하게 사후 변경된 내용은 위탁자의 사전 서면 동의 없이는 적용하지 아니한다. "
            "수탁자는 위탁자의 요청 시 해당 약관·규정 전문을 즉시 제공한다."
        ),
        "clause_topic": "other",
    },
    {
        "id": "clr_payment_guarantee_ambiguous",
        "name": "지급보증/연대책임으로 확대해석될 수 있는 모호한 협조 의무",
        "present": re.compile(
            r"미수금이?\s*발생하지\s*않도록\s*적극\s*협조|연대하여\s*책임|연대\s*보증|연대\s*책임을?\s*진다",
            re.IGNORECASE,
        ),
        "risk": "MEDIUM",
        "direction": "협조 의무를 결과채무(지급보증)가 아닌 수단채무(안내·독촉 등 절차적 협조)로 명확히 한정",
        "reason": (
            "'미수금이 발생하지 않도록 적극 협조한다'는 문언은 제3자(협력사 등)의 대금 미지급 위험을 "
            "위탁자가 사실상 보증하는 것으로 확대 해석될 여지가 있다. 협조의 구체적 내용과 한계가 "
            "특정되지 않으면 위탁자가 협력사의 채무를 대신 이행해야 하는 것으로 주장될 위험이 있다."
        ),
        "rewrite": (
            "위탁자의 협조 의무는 협력사에 대한 대금 청구 안내, 연락처 제공 등 절차적 협조에 한정하며, "
            "위탁자가 협력사의 미수금 채무를 보증하거나 연대하여 지급할 의무를 부담하는 것으로 해석되지 아니한다."
        ),
        "clause_topic": "payment_settlement",
    },
]


_RX_CONTRACT_TERM_YEARS = re.compile(r"(\d)\s*년(?:간|으로)?\s*(?:한다|간의\s*유효기간)")
_RX_CONVENIENCE_TERMINATION = re.compile(
    r"(임의|수시로?)\s*해지|사전\s*통지\s*(?:후|만으로)\s*해지|[0-9]+\s*(?:일|개월)\s*전\s*(?:서면\s*)?통지.{0,15}해지",
    re.IGNORECASE,
)
_RX_CAUSE_ONLY_TERMINATION = re.compile(r"중대한\s*(?:약정|계약)\s*위반", re.IGNORECASE)


def _apply_common_legal_risk_rules(
    clause_results: list[dict[str, Any]],
    full_text: str,
) -> None:
    """[Layer 1] Common legal risk checklist — runs for EVERY contract type.

    Mirrors the shape of the type-specific checklists (present-pattern ->
    inject if the clause doesn't already exist) but carries no contract_class
    gate, so it must never be touched by the HARD BLOCK logic that scopes
    Layer 2 rules.
    """
    text = str(full_text or "")
    existing_ids = {str(cr.get("clause_id") or "") for cr in clause_results if isinstance(cr, dict)}
    matched_ids: set[str] = set()

    for item in _CLR_ITEMS:
        skip_if = item.get("skip_if_also_matched")
        if skip_if and skip_if in matched_ids:
            continue
        if item["id"] in existing_ids:
            continue
        m = item["present"].search(text)
        if not m:
            continue
        matched_ids.add(item["id"])
        start = max(0, m.start() - 40)
        end = min(len(text), m.end() + 120)
        excerpt = text[start:end].strip()
        risk = item["risk"]
        clause_results.append({
            "clause_id": item["id"],
            "article_number": None,
            "clause_title": f"[공통 법률리스크] {item['name']}",
            "clause_topic": item.get("clause_topic", "other"),
            "original_text": excerpt,
            "risk_tier": risk,
            "severity": risk,
            "high_risk": risk == "HIGH",
            "must_fix": risk == "HIGH",
            "approval_required": risk == "HIGH",
            "review_tier": "MUST" if risk == "HIGH" else "SUGGEST",
            "suggested_rewrite": item["rewrite"],
            "rewrite_reason": item["reason"],
            "suggested_direction": [item["direction"]],
            "negotiation_position": "상대방 반발 가능성이 있으나 법적 책임 범위 명확화 차원에서 협상 필요",
            "confidence": 0.85,
            "is_common_legal_risk": True,
            "has_rewrite_change": True,
            "display_kind": "redline" if risk == "HIGH" else "guidance",
            "dedup_suppressed": False,
            "keep_as_is": False,
            "user_focus_hit": False,
            "factual_hit": False,
            "ai_deep_reviewed": False,
        })

    _apply_termination_vs_term_check(clause_results, text)


def _apply_termination_vs_term_check(clause_results: list[dict[str, Any]], text: str) -> None:
    """계약기간 대비 해지권 과도 제한: 1년 이상 계약인데 임의(편의)해지권 없이
    '중대한 위반' 사유로만 해지가 가능한 경우를 탐지한다."""
    if "clr_termination_right_restricted" in {str(cr.get("clause_id") or "") for cr in clause_results if isinstance(cr, dict)}:
        return
    term_match = _RX_CONTRACT_TERM_YEARS.search(text)
    has_long_term = bool(term_match) and int(term_match.group(1)) >= 1
    has_cause_only = bool(_RX_CAUSE_ONLY_TERMINATION.search(text))
    has_convenience = bool(_RX_CONVENIENCE_TERMINATION.search(text))
    if not (has_long_term and has_cause_only and not has_convenience):
        return
    years = term_match.group(1) if term_match else "장기"
    clause_results.append({
        "clause_id": "clr_termination_right_restricted",
        "article_number": None,
        "clause_title": "[공통 법률리스크] 계약기간 대비 해지권 과도 제한",
        "clause_topic": "termination",
        "original_text": (text[max(0, (_RX_CAUSE_ONLY_TERMINATION.search(text).start() - 40)):
                                 _RX_CAUSE_ONLY_TERMINATION.search(text).end() + 100].strip()
                           if _RX_CAUSE_ONLY_TERMINATION.search(text) else ""),
        "risk_tier": "MEDIUM",
        "severity": "MEDIUM",
        "high_risk": False,
        "must_fix": False,
        "approval_required": False,
        "review_tier": "SUGGEST",
        "suggested_rewrite": (
            "위 해지 사유와 별개로, 위탁자는 상당한 기간(예: 3개월) 전 서면 통지로 본 약정을 "
            "중도 해지할 수 있다. 이 경우 이미 수행된 업무에 대한 정산 외에 위약금 등 추가 "
            "부담을 지지 아니한다."
        ),
        "rewrite_reason": (
            f"약정기간이 {years}년 이상으로 장기임에도 '중대한 위반' 등 상대방 귀책사유가 있는 "
            "경우로만 해지가 제한되어 있고, 위탁자가 사전 통지만으로 계약관계에서 벗어날 수 있는 "
            "임의(편의)해지권이 없다. 사업상 필요(거래처 변경, 사업 축소 등)로 계약관계를 종료해야 "
            "하는 경우 상대방 귀책사유가 확인될 때까지 장기간 계약에 구속될 위험이 있다."
        ),
        "suggested_direction": ["장기 계약에 임의(편의)해지권 추가"],
        "negotiation_position": "상대방 반발 가능성이 있으나 법적 책임 범위 명확화 차원에서 협상 필요",
        "confidence": 0.75,
        "is_common_legal_risk": True,
        "has_rewrite_change": True,
        "display_kind": "guidance",
        "dedup_suppressed": False,
        "keep_as_is": False,
        "user_focus_hit": False,
        "factual_hit": False,
        "ai_deep_reviewed": False,
    })
