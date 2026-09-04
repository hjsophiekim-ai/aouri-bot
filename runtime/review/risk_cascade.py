"""Risk Cascade — 계약 전체를 관통하는 리스크 연쇄(contract-level risk cluster).

범용 사내변호사형 검토 고도화(2026-09-03 지시) — 개별 조항 finding만으로는
"하나의 사건이 여러 조항을 통해 어떻게 최종 손실로 이어지는가"가 보이지
않는다(예: KOTRA 3자 컨설팅계약의 이행지연→지체상금→서비스미완료→지원금
환수/반환채무→Company 보증책임 연쇄). 이 모듈은 이미 만들어진 clause_results
(개별 finding)와 Contract Legal Map의 Transaction Map 필드를 조합해, 특정
계약이나 조항번호에 의존하지 않는 범용 체인 템플릿으로 그 연쇄를 감지한다.

각 결과는 clause_results에 추가되는 개별 finding이 아니라, 계약 전체
수준의 "risk cluster" 객체다 — review 결과의 별도 필드(risk_cascades)로
노출한다.
"""
from __future__ import annotations

from typing import Any

_LATE_PENALTY_IDS = frozenset({"clr_late_penalty_rate_uncapped"})
_GUARANTEE_IDS = frozenset({"clr_third_party_debt_guarantee"})
_CROSS_DEFAULT_IDS = frozenset({"clr_breach_triggers_related_contract_termination"})


def _cr_ids(clause_results: list[dict[str, Any]], ids: frozenset[str]) -> list[dict[str, Any]]:
    return [
        cr for cr in clause_results
        if isinstance(cr, dict)
        and cr.get("clause_id") in ids
        and not bool(cr.get("dedup_suppressed"))
    ]


def _display_paths(items: list[dict[str, Any]]) -> list[str]:
    return [str(i.get("display_path") or i.get("clause_id") or "") for i in items if i]


def build_risk_cascades(
    clause_results: list[dict[str, Any]],
    legal_map_fields: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """clause_results + Transaction Map 필드를 조합해 계약 전체 리스크
    연쇄를 감지한다. 특정 계약유형에 대한 게이트 없이 모든 계약에 동일하게
    적용된다 — 각 체인은 clause_results 안의 legal-effect/clause_id 신호와
    legal_map_fields의 유무만으로 매칭된다.
    """
    fields = legal_map_fields or {}
    cascades: list[dict[str, Any]] = []

    penalty_hits = _cr_ids(clause_results, _LATE_PENALTY_IDS)
    guarantee_hits = _cr_ids(clause_results, _GUARANTEE_IDS)
    cross_default_hits = _cr_ids(clause_results, _CROSS_DEFAULT_IDS)

    has_conditional_funding = bool(fields.get("conditional_funding_structure"))
    has_refund_holder = bool(fields.get("refund_or_clawback_obligation_holder"))
    has_guarantee_structure = bool(fields.get("guarantee_structure"))

    # 체인 1: 이행지연 -> 지체상금 -> 서비스 미완료/해지 -> 환수/반환채무 -> 보증책임.
    # 지체상금 finding과 (보증 finding 또는 legal_map의 환수/보증 구조 신호)가
    # 함께 있을 때만 매칭 — 둘 다 없으면 "돈이 어디로 흘러가는지"를 실제로
    # 추적할 근거가 없으므로 만들어내지 않는다.
    if penalty_hits and (guarantee_hits or has_refund_holder or has_guarantee_structure):
        funding_step = (
            "지원금·정산금 환수(clawback)" if has_conditional_funding else "선급금 반환의무 발생"
        )
        chain = [
            "이행지연 발생",
            "지체상금 부과(상한이 없으면 지연 기간에 비례해 무제한 누적 가능)",
            "서비스 미완료 또는 계약 해지",
            funding_step,
            "상대방의 반환채무 불이행 가능성",
        ]
        if guarantee_hits:
            chain.append("우리 회사의 보증책임 실현 — 계약금액 상당의 금전 노출")
            terminal_loss = "상대방이 자력이 없으면 우리 회사가 반환채무를 대신 변제해야 할 수 있다."
        else:
            terminal_loss = "반환의무 이행 여부가 불명확해 우리 회사의 정산·회수 리스크로 남는다."
        cascades.append({
            "id": "risk_cascade_delay_to_guarantee",
            "trigger": "이행지연·지체상금",
            "chain": chain,
            "terminal_loss": terminal_loss,
            "related_clause_ids": list(dict.fromkeys(_display_paths(penalty_hits + guarantee_hits))),
            "severity": "HIGH" if guarantee_hits else "MEDIUM",
        })

    # 체인 2: 제3자(상대방) 채무불이행 -> 우리 회사 책임 실현 — 체인 1이
    # 이미 이 관계를 포함해 만들어졌다면 같은 내용을 중복 표시하지 않는다.
    if (guarantee_hits or has_guarantee_structure) and not any(
        c["id"] == "risk_cascade_delay_to_guarantee" for c in cascades
    ):
        cascades.append({
            "id": "risk_cascade_third_party_default_to_our_liability",
            "trigger": "제3자(상대방)의 채무불이행",
            "chain": [
                "상대방이 자신의 채무(반환·이행 등)를 이행하지 않음",
                "우리 회사가 그 채무에 대한 보증·연대책임을 부담",
            ],
            "terminal_loss": "우리가 통제할 수 없는 상대방의 불이행 결과를 우리 회사가 금전적으로 떠안는다.",
            "related_clause_ids": list(dict.fromkeys(_display_paths(guarantee_hits))),
            "severity": "HIGH" if guarantee_hits else "MEDIUM",
        })

    # 체인 3: 위반 -> (경미한 위반 포함) 관련계약 즉시해지.
    if cross_default_hits:
        cascades.append({
            "id": "risk_cascade_breach_to_termination",
            "trigger": "계약 위반(경미한 위반 포함 가능)",
            "chain": [
                "일방의 계약 위반 발생",
                "위반의 경중을 가리지 않고 본 계약 및 관련 계약이 함께 해지될 위험",
            ],
            "terminal_loss": "경미한 위반만으로도 핵심 거래관계 전체를 잃을 수 있다.",
            "related_clause_ids": list(dict.fromkeys(_display_paths(cross_default_hits))),
            "severity": "MEDIUM",
        })

    return cascades
