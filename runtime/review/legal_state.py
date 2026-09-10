"""Canonical Legal State — 검토 전체가 참조하는 **단 하나의** 확정 상태.

2026-09-10 아키텍처 지시 항목 1 — "검토 시작 시 한 번만 확정하고, 이후
질문생성·법률적용·finding·rewrite·UI·DOCX/PDF 모두 이 상태만 사용.
downstream 에서 raw contract_type 문자열 재분류, substring 재판정, 독립
classifier 실행 금지."

왜 이 모듈이 생겼나
─────────────────
같은 유형의 오류가 반복된 이유는 룰이 부족해서가 아니라, **판단 주체가
여럿**이었기 때문이다. 실측(2026-09-10, hold-out 8종):

  · `_lm_license_1.txt` (34,000자 영문 LICENSE AGREEMENT, "Licensor",
    "Royalty", "Licensed Products") → `purchase_supply` (물품 구매·공급 계약)
    으로 분류. 원인: 계약유형 enum 에 라이선스가 **아예 없어서**, 키워드
    캐스케이드가 "공급/purchase price/warranty period" 3개에 먼저 걸렸다.
    그 뒤 모든 체크리스트가 물품매매 기준으로 돌았다.
  · `nda_basic.txt` → canonical_state.contract_type = `general`,
    family = `nda_confidentiality`. **같은 객체 안에서** 두 값이 어긋났고,
    party_role_direction 은 빈 문자열이었다.

`canonical_state.py` 는 계약유형·역할만 얼렸다. 이 모듈은 지시가 요구한
11개 축을 하나로 묶고, **효과 프로파일(clause_effect)** 을 최상위 근거로
삼는다 — 계약유형 enum 은 그 위에 얹는 보조 라벨일 뿐이다.

    거래 실질(효과 프로파일)  →  거래 원형(archetype)  →  계약유형 라벨
        ↑ 판단의 출발점                                      ↑ 보조자료

이 순서를 뒤집지 말 것. enum 을 출발점으로 되돌리면 enum 에 없는 계약유형이
다시 아무 곳에나 떨어진다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from runtime.review.clause_effect import (
    ARCHETYPE_BARTER,
    ARCHETYPE_DISTRIBUTION,
    ARCHETYPE_GOODS,
    ARCHETYPE_LABELS,
    ARCHETYPE_LEASE,
    ARCHETYPE_LICENSE,
    ARCHETYPE_NDA,
    ARCHETYPE_SERVICE,
    ARCHETYPE_UNKNOWN,
    ARCHETYPE_WORKS,
    ContractEffectProfile,
    build_effect_profile,
)

REVIEW_FAILED_LEGAL_STATE_MISMATCH = "REVIEW_FAILED_LEGAL_STATE_MISMATCH"

#: 계약유형 enum 코드 → 그 코드가 함의하는 거래 원형.
#: 여기에 없는 코드는 원형을 함의하지 않는 것으로 보고 충돌 판정에서 뺀다
#: (모르는 것을 충돌로 세지 않는다).
ARCHETYPE_OF_TYPE_CODE: dict[str, str] = {
    "nda_confidentiality": ARCHETYPE_NDA,
    "purchase_supply": ARCHETYPE_GOODS,
    "product_supply": ARCHETYPE_GOODS,
    "equipment_purchase_installation": ARCHETYPE_GOODS,
    "equipment_installation": ARCHETYPE_GOODS,
    "construction": ARCHETYPE_WORKS,
    "project_installation": ARCHETYPE_WORKS,
    "rental": ARCHETYPE_LEASE,
    "dealer_rental_service_contract": ARCHETYPE_LEASE,
    "dealer_agency": ARCHETYPE_DISTRIBUTION,
    "distribution_resale": ARCHETYPE_DISTRIBUTION,
    "consignment_sales_agency": ARCHETYPE_DISTRIBUTION,
    "direct_customer_sales_support": ARCHETYPE_DISTRIBUTION,
    "advisory_service": ARCHETYPE_SERVICE,
    "advisory": ARCHETYPE_SERVICE,
    "software_app_development": ARCHETYPE_SERVICE,
    "testing_inspection_service": ARCHETYPE_SERVICE,
    "advertising_content_production": ARCHETYPE_SERVICE,
    "content_production_service": ARCHETYPE_SERVICE,
    "creative_agency_service": ARCHETYPE_SERVICE,
    "ai_search_marketing": ARCHETYPE_SERVICE,
    "store_operation_outsourcing": ARCHETYPE_SERVICE,
    "license_ip": ARCHETYPE_LICENSE,
}

#: 원형 → enum 에 대응 코드가 없을 때 쓸 대표 코드. 라이선스·바터처럼 enum 에
#: 없던 원형에는 새 코드를 준다 — 없는 유형을 억지로 기존 코드에 끼워 넣으면
#: 그 코드의 체크리스트가 통째로 잘못 실행된다.
TYPE_CODE_OF_ARCHETYPE: dict[str, str] = {
    ARCHETYPE_NDA: "nda_confidentiality",
    ARCHETYPE_GOODS: "purchase_supply",
    ARCHETYPE_WORKS: "construction",
    ARCHETYPE_LEASE: "rental",
    ARCHETYPE_DISTRIBUTION: "dealer_agency",
    ARCHETYPE_SERVICE: "advisory_service",
    ARCHETYPE_LICENSE: "license_ip",
    ARCHETYPE_BARTER: "barter_exchange",
}

#: 새로 생긴 코드의 표시 라벨.
EXTRA_TYPE_LABELS: dict[str, str] = {
    "license_ip": "지식재산권 실시허락(라이선스) 계약",
    "barter_exchange": "대물교환(바터) 계약",
}


@dataclass
class CanonicalLegalState:
    """지시 항목 1이 요구한 11개 축. 한 번 만들고 이후 바꾸지 않는다."""

    # 1. 거래의 실질 — 효과 프로파일에서 직접 나온다(판단의 출발점)
    transaction_type: str = ARCHETYPE_UNKNOWN
    transaction_type_label: str = ""
    transaction_type_basis: str = ""

    # 2. 계약유형 — 위 실질에 맞춘 **보조 라벨**
    contract_type: str = ""
    contract_type_family: str = ""
    contract_type_label: str = ""
    contract_type_reconciled: bool = False
    contract_type_before: str = ""
    contract_type_reason: str = ""

    # 3~4. 당사자 지위
    our_role: str = ""
    our_role_direction: str = ""
    our_label: str = ""
    counterparty_role: str = ""
    counterparty_label: str = ""

    # 5. 각 당사자의 급부
    each_party_performance: dict[str, str] = field(default_factory=dict)

    # 6. 대가 구조
    consideration_structure: str = ""
    is_non_monetary: bool = False

    # 7. 소유권·위험 이전
    ownership_risk_transfer: str = ""

    # 8. 산출물
    deliverables: list[str] = field(default_factory=list)

    # 9. 계약을 구성하는 문서
    governing_contract_documents: list[str] = field(default_factory=list)

    # 10. 적용 가능 법률 후보 (applicability gate 결과)
    applicable_law_candidates: list[dict[str, Any]] = field(default_factory=list)

    # 11. 사용자가 실제로 요청한 검토 범위
    user_review_scope: list[dict[str, Any]] = field(default_factory=list)

    # 부가 — 효과 프로파일 원본(조항별 검토가 참조)
    effect_profile: dict[str, Any] = field(default_factory=dict)
    audit: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_type": self.transaction_type,
            "transaction_type_label": self.transaction_type_label,
            "transaction_type_basis": self.transaction_type_basis,
            "contract_type": self.contract_type,
            "contract_type_family": self.contract_type_family,
            "contract_type_label": self.contract_type_label,
            "contract_type_reconciled": self.contract_type_reconciled,
            "contract_type_before": self.contract_type_before,
            "contract_type_reason": self.contract_type_reason,
            "our_role": self.our_role,
            "our_role_direction": self.our_role_direction,
            "our_label": self.our_label,
            "counterparty_role": self.counterparty_role,
            "counterparty_label": self.counterparty_label,
            "each_party_performance": dict(self.each_party_performance),
            "consideration_structure": self.consideration_structure,
            "is_non_monetary": self.is_non_monetary,
            "ownership_risk_transfer": self.ownership_risk_transfer,
            "deliverables": list(self.deliverables),
            "governing_contract_documents": list(self.governing_contract_documents),
            "applicable_law_candidates": list(self.applicable_law_candidates),
            "user_review_scope": list(self.user_review_scope),
            "effect_profile": dict(self.effect_profile),
            "audit": dict(self.audit),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "CanonicalLegalState | None":
        """저장된 상태를 **재계산 없이** 되살린다.

        다운로드 경로가 분류기를 다시 돌리지 않게 하는 것이 이 메서드의
        존재 이유다(지시 항목 1·11).
        """
        if not isinstance(data, dict) or not data:
            return None
        state = cls()
        for key, value in data.items():
            if hasattr(state, key):
                setattr(state, key, value)
        return state

    @property
    def resolved(self) -> bool:
        return bool(self.contract_type and self.our_role_direction)


def reconcile_contract_type(
    *,
    detailed_code: str,
    detailed_family: str,
    profile: ContractEffectProfile,
) -> tuple[str, str, bool, str]:
    """효과 프로파일이 말하는 원형과 enum 분류를 맞춘다.

    돌려주는 값: (contract_type, family, reconciled, reason)

    원칙 — **원형이 이긴다**. enum 은 원형을 표현하기 위한 어휘일 뿐이므로,
    enum 코드가 함의하는 원형과 실제 원형이 다르면 enum 쪽을 고친다. 다만
    원형을 특정하지 못했거나(unknown) enum 코드가 원형을 함의하지 않으면
    (매핑에 없으면) 손대지 않는다 — 모르는 것을 덮어쓰지 않는다.
    """
    code = str(detailed_code or "").strip()
    family = str(detailed_family or "").strip()

    if profile.archetype == ARCHETYPE_UNKNOWN:
        return code, family, False, "거래 원형을 특정하지 못해 기존 분류를 유지했습니다."

    implied = ARCHETYPE_OF_TYPE_CODE.get(code, "")
    if implied == profile.archetype:
        return code, family, False, "계약유형이 거래 원형과 일치합니다."

    target = TYPE_CODE_OF_ARCHETYPE.get(profile.archetype, "")
    if not target:
        return code, family, False, "거래 원형에 대응하는 계약유형 코드가 없습니다."

    if not implied:
        # enum 코드가 원형을 함의하지 않는다(general/unknown/미매핑).
        # 충돌이 아니라 미분류의 보완이다.
        return (
            target,
            family or profile.archetype,
            True,
            (
                f"기존 분류('{code or '미분류'}')는 거래 원형을 특정하지 않아, "
                f"급부 구조에서 읽은 '{ARCHETYPE_LABELS.get(profile.archetype, profile.archetype)}'"
                f"로 확정했습니다."
            ),
        )

    return (
        target,
        family or profile.archetype,
        True,
        (
            f"기존 분류는 '{code}'({ARCHETYPE_LABELS.get(implied, implied)})였으나 "
            f"급부·대가 구조는 '{ARCHETYPE_LABELS.get(profile.archetype, profile.archetype)}'입니다. "
            f"계약 제목·키워드가 아니라 거래 실질을 기준으로 '{target}'로 확정했습니다."
            + (f" 근거: {profile.archetype_basis}" if profile.archetype_basis else "")
        ),
    )


def build_legal_state(
    *,
    text: str,
    clauses: list[Any] | None,
    detailed_code: str,
    detailed_family: str,
    detailed_label: str,
    our_role: str,
    our_role_direction: str,
    our_label: str,
    counterparty_role: str,
    counterparty_label: str,
    legal_map: dict[str, Any] | None = None,
    document_hierarchy: dict[str, Any] | None = None,
    applicable_law_candidates: list[dict[str, Any]] | None = None,
    user_review_scope: list[dict[str, Any]] | None = None,
) -> CanonicalLegalState:
    """검토 시작 시 **한 번만** 호출한다."""
    profile = build_effect_profile(text=str(text or ""), clauses=clauses)
    code, family, reconciled, reason = reconcile_contract_type(
        detailed_code=detailed_code, detailed_family=detailed_family, profile=profile,
    )

    label = detailed_label
    if reconciled or not label:
        label = EXTRA_TYPE_LABELS.get(code, "") or _label_for(code, family) or detailed_label

    lm = legal_map or {}
    performance = {
        "our_side": str(lm.get("our_performance") or lm.get("our_obligation") or ""),
        "counterparty": str(lm.get("counterparty_performance") or lm.get("counterparty_obligation") or ""),
    }

    # 지위가 비어 있으면 원형이 함의하는 기본값으로 채운다 — 빈 값으로 두면
    # 후속 게이트가 "지위 미확정"으로 계속 걸린다(실측: NDA·라이선스).
    resolved_direction = str(our_role_direction or "").strip()
    resolved_role = str(our_role or "").strip()
    if not resolved_direction:
        resolved_role, resolved_direction = _default_roles(profile.archetype, resolved_role)

    return CanonicalLegalState(
        transaction_type=profile.archetype,
        transaction_type_label=ARCHETYPE_LABELS.get(profile.archetype, profile.archetype),
        transaction_type_basis=profile.archetype_basis,
        contract_type=code,
        contract_type_family=family,
        contract_type_label=label,
        contract_type_reconciled=reconciled,
        contract_type_before=str(detailed_code or ""),
        contract_type_reason=reason,
        our_role=resolved_role,
        our_role_direction=resolved_direction,
        our_label=str(our_label or ""),
        counterparty_role=str(counterparty_role or ""),
        counterparty_label=str(counterparty_label or ""),
        each_party_performance=performance,
        consideration_structure=str(lm.get("consideration_structure") or lm.get("payment_structure") or ""),
        is_non_monetary=profile.is_non_monetary,
        ownership_risk_transfer=str(lm.get("ownership_risk_transfer") or lm.get("risk_transfer") or ""),
        deliverables=[str(x) for x in (lm.get("deliverables") or []) if str(x).strip()][:12],
        governing_contract_documents=[
            str(x) for x in ((document_hierarchy or {}).get("documents") or []) if str(x).strip()
        ][:12],
        applicable_law_candidates=list(applicable_law_candidates or []),
        user_review_scope=list(user_review_scope or []),
        effect_profile=profile.to_dict(),
    )


def _label_for(code: str, family: str) -> str:
    try:
        from runtime.review.canonical_state import canonical_type_label
        return canonical_type_label(code, family)
    except Exception:
        return ""


#: 원형별 기본 당사자 지위. 계약이 지위를 밝히지 않는 유형(NDA·라이선스 등)에서
#: 빈 값을 남기지 않기 위한 최소 기본값이며, 실제 지위가 파악되면 그것이 우선한다.
_DEFAULT_ROLE_BY_ARCHETYPE: dict[str, tuple[str, str]] = {
    ARCHETYPE_NDA: ("party", "mutual"),
    ARCHETYPE_LICENSE: ("licensor_or_licensee", "mutual"),
    ARCHETYPE_BARTER: ("exchange_party", "mutual"),
}


def _default_roles(archetype: str, current_role: str) -> tuple[str, str]:
    role, direction = _DEFAULT_ROLE_BY_ARCHETYPE.get(archetype, ("", ""))
    if direction:
        return (current_role or role), direction
    return current_role, ""


def check_state_consistency(
    state: CanonicalLegalState | None,
    observed: dict[str, Any],
) -> dict[str, Any]:
    """최종 출력이 확정 상태와 같은지 확인한다(지시 항목 12).

    출력 단계가 스스로 다시 분류했는지를 잡아내는 안전망이다.
    """
    if state is None:
        return {"ok": True, "mismatches": []}
    mismatches: list[dict[str, str]] = []
    for key in ("contract_type", "transaction_type", "our_role_direction"):
        want = str(getattr(state, key, "") or "")
        got = str(observed.get(key) or "")
        if want and got and want != got:
            mismatches.append({"field": key, "expected": want, "observed": got})
    return {
        "ok": not mismatches,
        "mismatches": mismatches,
        "status": REVIEW_FAILED_LEGAL_STATE_MISMATCH if mismatches else "",
    }
