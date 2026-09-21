"""Contract Model — 검토 시작 시 **한 번만** 확정하는 7개 축.

2026-09-21 지시 1항 —
  "검토 시작 시 사용자 설명 + 계약 전문 + 조항 구조를 바탕으로 반드시 아래를
   canonical state 로 확정: 계약유형 / 우리 회사의 법적 지위 / 상대방의 법적
   지위 / 핵심 급부 / 대금 지급방향 / 하도급·재위탁 구조 / 산출물·IP 가 주된
   거래인지 부수적 이슈인지.
   한 번 확정된 canonical state 는 이후 질문 생성기, 법률 적용, finding, UI,
   DOCX 에서 다시 추론하지 마세요."

왜 또 하나의 상태 객체를 만들지 않는가
──────────────────────────────────
이 저장소에는 이미 `canonical_state`(유형·지위·문서계층), `legal_state`
(거래 원형 11축), `construction_transaction_model`(건설 지위) 이 있고, 서로
어긋나는 것이 바로 v14 가 고치려는 사고다. 여기서 **네 번째 판단 주체**를
만들면 어긋날 자리가 하나 더 늘어난다.

그래서 이 모듈은 판단하지 않는다. 이미 확정된 값을 지시가 요구한 7개 축의
모양으로 **모아서 보여 주고**, 축끼리 모순이 없는지 확인만 한다. 새로 정하는
것은 기존 상태들이 표현하지 않던 두 가지뿐이다.

  · 대금 지급방향 — 우리가 받는가, 주는가. 지위 방향에서 바로 나온다.
  · IP 가 주된 거래인가 부수적 이슈인가 — 지시 1항 후단이 명시적으로 요구한
    축이고, 기존 어느 상태에도 없었다. 이 값이 없어서 인테리어 공사도급계약이
    IP·콘텐츠 계약으로 재분류되고, IP 중심 필수질문이 나갔다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: 사용자 설명과 계약 문언이 서로 다른 사실을 말할 때 (지시 2항).
FACT_CONFLICT = "FACT_CONFLICT"

#: IP·산출물이 **주된 거래**인 유형. 이 목록 밖의 유형에서 IP 조항은 부수
#: 조항이고, 그것을 근거로 계약유형을 바꾸지 않는다(지시 1항 후단).
IP_PRIMARY_TYPES: frozenset[str] = frozenset({
    "license",
    "license_ip",
    "content_production_service",
    "advertising_content_production",
    "creative_agency_service",
    "software_app_development",
})

#: 급부 구조상 IP 가 결코 주된 거래가 될 수 없는 유형.
IP_ANCILLARY_TYPES: frozenset[str] = frozenset({
    "construction",
    "project_installation",
    "equipment_purchase_installation",
    "equipment_installation",
    "purchase_supply",
    "product_supply",
    "rental",
    "dealer_rental_service_contract",
    "dealer_agency",
    "distribution_resale",
    "consignment_sales_agency",
    "direct_customer_sales_support",
})

IP_ROLE_PRIMARY = "primary"
IP_ROLE_ANCILLARY = "ancillary"
IP_ROLE_UNKNOWN = "unknown"

PAYMENT_WE_RECEIVE = "we_receive"
PAYMENT_WE_PAY = "we_pay"
PAYMENT_UNKNOWN = "unknown"

_PAYMENT_LABELS = {
    PAYMENT_WE_RECEIVE: "우리 회사가 대금을 받는다 (급부 제공자)",
    PAYMENT_WE_PAY: "우리 회사가 대금을 지급한다 (급부 수령자)",
    PAYMENT_UNKNOWN: "대금 지급방향 미확정",
}

_IP_ROLE_LABELS = {
    IP_ROLE_PRIMARY: "산출물·지식재산이 이 계약의 주된 거래",
    IP_ROLE_ANCILLARY: "지식재산 조항은 부수적 이슈 (주된 급부가 따로 있음)",
    IP_ROLE_UNKNOWN: "판단 보류",
}


def ip_role_for(contract_type: str) -> str:
    code = str(contract_type or "").strip()
    if code in IP_PRIMARY_TYPES:
        return IP_ROLE_PRIMARY
    if code in IP_ANCILLARY_TYPES:
        return IP_ROLE_ANCILLARY
    return IP_ROLE_UNKNOWN


def payment_direction_for(role_direction: str) -> str:
    direction = str(role_direction or "").strip()
    if direction == "provider":
        return PAYMENT_WE_RECEIVE
    if direction == "recipient":
        return PAYMENT_WE_PAY
    return PAYMENT_UNKNOWN


@dataclass(frozen=True)
class ContractModel:
    """지시 1항의 7개 축. 만들어진 뒤에는 바뀌지 않는다."""

    contract_type: str
    contract_type_label: str
    our_role: str
    our_role_label: str
    our_role_direction: str
    counterparty_role: str
    counterparty_label: str
    primary_performance: str
    payment_direction: str
    payment_direction_label: str
    subcontract_structure: str
    ip_role: str
    ip_role_label: str
    #: 사용자 설명과 계약 문언이 어긋나면 그 사실과 근거.
    fact_conflict: str = ""
    #: 어떤 상태 객체에서 각 축을 가져왔는지.
    sources: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_type": self.contract_type,
            "contract_type_label": self.contract_type_label,
            "our_role": self.our_role,
            "our_role_label": self.our_role_label,
            "our_role_direction": self.our_role_direction,
            "counterparty_role": self.counterparty_role,
            "counterparty_label": self.counterparty_label,
            "primary_performance": self.primary_performance,
            "payment_direction": self.payment_direction,
            "payment_direction_label": self.payment_direction_label,
            "subcontract_structure": self.subcontract_structure,
            "ip_role": self.ip_role,
            "ip_role_label": self.ip_role_label,
            "fact_conflict": self.fact_conflict,
            "sources": dict(self.sources),
        }

    @property
    def ip_is_ancillary(self) -> bool:
        return self.ip_role == IP_ROLE_ANCILLARY


def build_contract_model(
    *,
    canonical_state: Any,
    legal_state: Any = None,
    construction_model: Any = None,
    legal_map_fields: dict[str, Any] | None = None,
) -> ContractModel:
    """이미 확정된 값들을 7개 축으로 모은다. 여기서 다시 분류하지 않는다."""
    contract_type = str(getattr(canonical_state, "contract_type", "") or "")
    label = str(getattr(canonical_state, "contract_type_label", "") or "")
    our_role = str(getattr(canonical_state, "party_role", "") or "")
    direction = str(getattr(canonical_state, "party_role_direction", "") or "")
    counterparty_role = str(getattr(canonical_state, "counterparty_role", "") or "")
    counterparty_label = str(getattr(canonical_state, "counterparty_label", "") or "")

    our_role_label = str(getattr(canonical_state, "party_label", "") or "")
    if construction_model is not None and getattr(construction_model, "role_label", ""):
        our_role_label = str(construction_model.role_label)

    fields = dict(legal_map_fields or {})
    performance = str(
        fields.get("primary_obligations")
        or fields.get("our_performance")
        or ""
    ).strip()
    if not performance and legal_state is not None:
        perf = getattr(legal_state, "each_party_performance", None)
        if isinstance(perf, dict):
            performance = str(perf.get("our_side") or "").strip()

    subcontract = "해당 없음"
    fact_conflict = ""
    if construction_model is not None and getattr(construction_model, "is_construction", False):
        if getattr(construction_model, "has_subcontracting", False):
            subcontract = (
                "우리 회사가 도급받은 공사의 일부를 전문업체에 재하도급 "
                "(재하도급 계약은 이 계약과 별도 층위)"
            )
        elif getattr(construction_model, "we_are_subcontractor", False):
            subcontract = "우리 회사가 하도급받는 쪽"
        else:
            subcontract = "재하도급 예정 없음"
        if not getattr(construction_model, "role_confident", False) and (
            "서로 다른 지위" in str(getattr(construction_model, "role_basis", ""))
        ):
            fact_conflict = str(construction_model.role_basis)

    ip_role = ip_role_for(contract_type)
    payment = payment_direction_for(direction)

    return ContractModel(
        contract_type=contract_type,
        contract_type_label=label,
        our_role=our_role,
        our_role_label=our_role_label,
        our_role_direction=direction,
        counterparty_role=counterparty_role,
        counterparty_label=counterparty_label,
        primary_performance=performance,
        payment_direction=payment,
        payment_direction_label=_PAYMENT_LABELS[payment],
        subcontract_structure=subcontract,
        ip_role=ip_role,
        ip_role_label=_IP_ROLE_LABELS[ip_role],
        fact_conflict=fact_conflict,
        sources={
            "contract_type": "canonical_state",
            "our_role": "construction_transaction_model" if construction_model is not None
            and getattr(construction_model, "is_construction", False) else "canonical_state",
            "primary_performance": "contract_legal_map",
            "payment_direction": "derived:our_role_direction",
            "ip_role": "derived:contract_type",
        },
    )


def check_model_coherence(model: ContractModel) -> list[str]:
    """7개 축이 서로 모순되지 않는지. 반환값은 모순 설명 목록."""
    problems: list[str] = []
    if not model.contract_type:
        problems.append("계약유형이 확정되지 않았습니다.")
    if model.our_role_direction and model.counterparty_role:
        if model.our_role_direction == "provider" and model.counterparty_role in (
            "supplier", "contractor", "service_provider",
        ):
            problems.append(
                f"우리 회사와 상대방이 같은 쪽입니다 "
                f"(우리={model.our_role_direction}, 상대방={model.counterparty_role})."
            )
    # 상호 NDA 처럼 급부 교환이 없는 계약에는 대금 지급방향이 없다 —
    # 없는 것을 미확정이라고 부르면 그것이 오히려 자기모순이다
    # (2026-09-21 3차 지시, 오킨 NDA 실측).
    if (
        model.payment_direction == PAYMENT_UNKNOWN
        and model.our_role_direction
        and model.our_role_direction != "mutual"
        and model.contract_type not in ("nda_confidentiality",)
    ):
        problems.append("지위는 확정됐는데 대금 지급방향이 서지 않았습니다.")
    if model.ip_role == IP_ROLE_PRIMARY and model.contract_type in IP_ANCILLARY_TYPES:
        problems.append(
            f"계약유형({model.contract_type})의 급부 구조상 IP 는 부수 조항인데 "
            "주된 거래로 판단했습니다."
        )
    return problems
