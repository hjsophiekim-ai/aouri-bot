"""Executive Summary Optimization — requirement.md > Executive Summary Optimization
현상 / 법리적 근거 / 수정 전략 / 기대 효과 4-필드 고정 양식으로 핵심 리스크 요약을 생성한다.
"""
from __future__ import annotations

from typing import Any

_TOPIC_LEGAL_BASIS: dict[str, str] = {
    "termination": "대리점법 제11조 및 판례상 해지권 남용 제한 원칙",
    "cost_burden": "대리점법 제12조 및 공정거래법상 거래상 지위 남용 금지",
    "payment_settlement": "하도급법 제13조 및 민법상 상계 요건(제492조)",
    "personal_data": "개인정보 보호법 제26조 수탁자 관리·감독 의무",
    "ip_ownership": "저작권법 제9조 업무상 저작물 귀속 원칙 및 도급 계약 적용",
    "safety": "산업안전보건법 및 중대재해처벌법상 도급인·수급인 안전 관리 의무",
    "safety_compliance": "산업안전보건법 및 중대재해처벌법상 안전 관리 의무",
    "damage": "민법 제393조 손해배상 범위 및 제조물책임법 제3조 입증책임 전환",
    "dealer_unfair": "공정거래법 제45조 및 대리점법 제18조 불이익 제공 금지",
    "confidentiality": "부정경쟁방지법 제2조 제2호 영업비밀 보호 및 민법 제750조",
    "training_operations": "산업안전보건법 제29조 안전보건교육 실시 의무",
}

_TOPIC_REVISION_STRATEGY: dict[str, str] = {
    "termination": (
        "즉시 해지 → '30일 서면 최고 + 2회 시정 기회 부여'로 변경, "
        "예외적 즉시 해지 사유(고의·중대한 위반)는 좁게 열거"
    ),
    "cost_burden": "비용 항목·산정기준·증빙·이의제기 절차를 사전 서면합의로 고정",
    "payment_settlement": (
        "공제·상계는 계약 또는 서면합의에 근거한 경우로 제한, "
        "정산서·증빙 제공 의무화 및 이의제기 기간 명시"
    ),
    "personal_data": (
        "수탁자 귀책 유출 시 무제한 구상권 명시, "
        "위반 시 즉시 해지권 및 손해배상 의무 확보"
    ),
    "ip_ownership": (
        "결과물 권리 위탁자 전적 귀속 명시, "
        "제3자 권리 침해 보증 및 면책·배상 의무 추가"
    ),
    "safety": (
        "안전 책임 주체·관리자 지정·사고 즉시 보고 의무 명시, "
        "발주자 귀책 사유 면책 조항 추가"
    ),
    "safety_compliance": (
        "산안법·중대재해법 준수 의무 명시, "
        "위반 시 수급인 단독 책임 및 도급인 구상권 확보"
    ),
    "damage": (
        "손해배상 한도 설정 후 고의·중과실·IP 침해·NDA 위반은 예외 처리 단서 추가"
    ),
    "dealer_unfair": (
        "불이익 제공·경영간섭 금지 조항을 구체적으로 명시, "
        "비용 전가·정산 자료 통제에 대한 방어 장치 추가"
    ),
    "confidentiality": (
        "영업비밀 범위를 명확히 정의하고, "
        "위반 시 즉시 해지 및 무제한 손해배상 의무 명시"
    ),
    "training_operations": (
        "사용자·관리자·비상대응 교육 의무를 체크리스트로 계약서에 명시"
    ),
}

_TOPIC_EXPECTED_EFFECT: dict[str, str] = {
    "termination": "규제기관 조사·과징금 리스크 30~50% 감소, 해지 분쟁 시 협상력 확보",
    "cost_burden": "불이익 제공 분쟁 예방, 비용 청구 거절 시 법적 근거 확보",
    "payment_settlement": "정산 분쟁 발생 시 이의제기 및 증거 확보로 손실 최소화",
    "personal_data": "감독기관 과징금 분쟁 시 구상권 행사 기반 확보",
    "ip_ownership": "결과물 활용 제한 리스크 제거, 제3자 침해 소송 시 구상권 확보",
    "safety": "중대재해 발생 시 형사·민사 책임 귀속 범위 명확화, 면책 가능성 증대",
    "safety_compliance": "중대재해 발생 시 도급인 형사 처벌 리스크 감소",
    "damage": "사고 발생 시 공급자 면책 가능성 40% 이상 증대",
    "dealer_unfair": "공정위 신고·과징금 리스크 예방",
    "confidentiality": "영업비밀 유출 시 민형사 청구 기반 확보",
    "training_operations": "설비 오조작·사고 발생 시 공급자 책임 한정 근거 확보",
}


def generate_executive_summary(
    clause_results: list[dict[str, Any]],
    conflicts: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """requirement.md > Executive Summary Optimization.
    현상 / 법리적 근거 / 수정 전략 / 기대 효과 4-필드 고정 양식으로 생성한다.
    """
    high = [
        cr for cr in clause_results
        if isinstance(cr, dict)
        and str(cr.get("risk_tier") or "").upper() == "HIGH"
        and not cr.get("dedup_suppressed")
    ]
    medium = [
        cr for cr in clause_results
        if isinstance(cr, dict)
        and str(cr.get("risk_tier") or "").upper() == "MEDIUM"
        and not cr.get("dedup_suppressed")
    ]
    low = [
        cr for cr in clause_results
        if isinstance(cr, dict)
        and str(cr.get("risk_tier") or "").upper() == "LOW"
        and not cr.get("dedup_suppressed")
    ]
    approval_count = sum(
        1 for cr in clause_results
        if isinstance(cr, dict) and cr.get("approval_required") and not cr.get("dedup_suppressed")
    )

    items: list[dict[str, Any]] = []
    seen_topics: set[str] = set()

    sorted_results = sorted(
        clause_results,
        key=lambda x: (
            0 if str(x.get("risk_tier", "")).upper() == "HIGH" else
            (1 if str(x.get("risk_tier", "")).upper() == "MEDIUM" else 2),
            0 if x.get("approval_required") else 1,
            0 if x.get("must_fix") else 1,
        )
        if isinstance(x, dict) else (3, 1, 1),
    )

    for cr in sorted_results:
        if not isinstance(cr, dict):
            continue
        if cr.get("dedup_suppressed") or cr.get("keep_as_is"):
            continue
        topic = str(cr.get("clause_topic") or "other")
        tier = str(cr.get("risk_tier") or "LOW").upper()
        if tier not in ("HIGH", "MEDIUM"):
            continue
        if topic in seen_topics and not cr.get("is_checklist_item"):
            continue
        seen_topics.add(topic)

        clause_id = str(cr.get("clause_id") or "")
        article_no = str(cr.get("article_number") or "")
        clause_title = str(cr.get("clause_title") or "")
        prefix = f"제{article_no}조 " if article_no else ""
        rewrite_reason = str(cr.get("rewrite_reason") or "")[:120]

        status = rewrite_reason or f"{prefix}{clause_title} — {tier} 리스크 감지"
        legal_basis = _TOPIC_LEGAL_BASIS.get(topic, "관련 법령 및 판례에 따른 계약 리스크")
        revision_strategy = _TOPIC_REVISION_STRATEGY.get(
            topic,
            (cr.get("suggested_direction") or ["수정 제안 참조"])[0]
            if cr.get("suggested_direction") else "수정 제안 참조",
        )
        expected_effect = _TOPIC_EXPECTED_EFFECT.get(
            topic, "사고·분쟁 발생 시 당사의 면책 가능성 및 협상력 증대"
        )

        items.append({
            "risk_code": f"{tier}-{clause_id}",
            "clause_id": clause_id,
            "status": status,
            "legal_basis": legal_basis,
            "revision_strategy": revision_strategy,
            "expected_effect": expected_effect,
            "risk_tier": tier,
        })
        if len(items) >= 10:
            break

    headline = ""
    if high:
        top = high[0]
        art = str(top.get("article_number") or "")
        title = str(top.get("clause_title") or "")
        reason = str(top.get("rewrite_reason") or "")[:80]
        headline = f"최우선 리스크: {'제' + art + '조 ' if art else ''}{title} — {reason}"
    elif medium:
        top = medium[0]
        title = str(top.get("clause_title") or "")
        headline = f"주요 리스크: {title} — 수정 검토 필요"

    conflict_summary = [
        f"[{c.get('conflict_type', '')}] {c.get('description', '')[:100]}"
        for c in (conflicts or [])
    ]

    return {
        "headline": headline,
        "severity_distribution": {
            "HIGH": len(high),
            "MEDIUM": len(medium),
            "LOW": len(low),
        },
        "items": items,
        "conflict_summary": conflict_summary,
        "approval_required_count": approval_count,
    }
