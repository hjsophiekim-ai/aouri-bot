"""Canonical State — 계약유형·당사자·문서계층·거래구조를 **한 번만** 확정한다
(2026-09-09 3차 지시 1·2항).

같은 유형의 오류가 반복된 원인은 규칙이 부족해서가 아니라, 계약유형을 여러
모듈이 **각자 판단**했기 때문이다. 실측(공사도급계약 26,738자):

    리포트 상단(detailed_contract_profile)   equipment_purchase_installation
                                             → "장비 구매·설치 계약"
    법률분석(contract_type_resolution)       construction_contract
                                             → "공사도급계약"
    세션에 남아 있던 raw contract_type       "앱개발/소프트웨어개발/SI/유지보수/SaaS"

세 값이 동시에 살아 있었고, 각 단계가 서로 다른 것을 참조했다. 그래서 상단은
장비 계약이라고 쓰면서 본문은 건설 도급으로 검토하는 리포트가 나왔다.

이 모듈이 하는 일:

    1. 구조 판정(급부·대금·완료조건·위험이전)으로 계약유형 **계열**을 정한다
    2. 세부 분류 코드가 그 계열에 속하면 그대로 쓰고, 아니면 계열 대표코드로
       **교정**하고 감사기록을 남긴다 (조용한 불일치를 만들지 않는다)
    3. 당사자 지위·문서계층·거래구조를 함께 얼려서 하나의 값으로 만든다
    4. 이후 어느 단계든 이 값을 **전달받아** 쓰고, 다시 추론하지 않는다
    5. 최종 출력이 이 값과 다르면 REVIEW_FAILED_CANONICAL_STATE_MISMATCH

두 어휘가 다른 것이 문제의 뿌리였다. 구조 판정기는 계열 7개를 쓰고
(construction_contract, supply_installation, …), 세부 분류기는 코드 20여 개를
쓴다(equipment_purchase_installation, software_app_development, …). 어느 하나를
버리면 그 어휘에 묶인 체크리스트가 전부 깨지므로, **계열-세부 포함관계**로
잇는다.

설계 — **하드코딩 금지**. 특정 계약명·회사명·조항번호를 쓰지 않는다. 판정은
구조 판정기에 위임하고, 이 모듈은 값을 하나로 모으고 검증만 한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

REVIEW_FAILED_CANONICAL_STATE_MISMATCH = "REVIEW_FAILED_CANONICAL_STATE_MISMATCH"

#: 세부 코드를 덮어쓰려면 구조 신호가 이만큼은 잡혀야 한다.
#:
#: `confidence` 로는 판별할 수 없다. 그것은 1등/2등 **비율**이라서, 신호가
#: 4개뿐이고 2등이 0개면 1.000 이 나온다. 실측(2026-09-09, fixture 12건):
#:
#:     시험·검사 용역     nda_confidentiality  conf 1.000  신호  4  ← 오탐
#:     콘텐츠 제작        nda_confidentiality  conf 0.727  신호  8  ← 오탐
#:     렌탈 표준계약      rental_lease         conf 0.615  신호  8  ← 애매
#:     공사도급(fixture)  construction_contract conf 0.935 신호 29  ← 정답
#:     공사도급(실제)     construction_contract conf 0.941 신호 32  ← 정답
#:
#: 판별력은 **절대 신호 개수**에 있다. 잘못된 교정은 그 유형 전용 체크리스트를
#: 통째로 갈아끼우므로, 압도적일 때만 덮어쓴다.
OVERRIDE_MIN_SIGNALS = 15

#: 2등 계열보다 이 배수 이상 앞서야 한다.
OVERRIDE_MIN_SIGNAL_RATIO = 3.0

#: 세부 분류 코드 → 구조 판정 계열. 여기에 없는 코드는 계열 미상으로 보고
#: 교정 대상에서 제외한다(모르는 것을 덮어쓰지 않는다).
FAMILY_OF: dict[str, str] = {
    # 공사·도급
    "construction": "construction_contract",
    # 물품공급·설치
    "equipment_purchase_installation": "supply_installation",
    "equipment_installation": "supply_installation",
    "purchase_supply": "supply_installation",
    # 용역·개발
    "software_app_development": "development_service",
    "advisory_service": "development_service",
    "content_production_service": "development_service",
    "advertising_content_production": "development_service",
    "creative_agency_service": "development_service",
    "ai_search_marketing": "development_service",
    "testing_inspection_service": "development_service",
    "store_operation_outsourcing": "development_service",
    # 비밀유지
    "nda_confidentiality": "nda_confidentiality",
    # 렌탈·임대차
    "rental": "rental_lease",
    "dealer_rental_service_contract": "rental_lease",
    # 판매대리·위탁판매
    "dealer_agency": "sales_agency",
    "consignment_sales_agency": "sales_agency",
    "distribution_resale": "sales_agency",
    "direct_customer_sales_support": "sales_agency",
    # 라이선스
    "license": "license",
}

#: 계열 → 교정 시 쓸 대표 세부코드.
FAMILY_REPRESENTATIVE: dict[str, str] = {
    "construction_contract": "construction",
    "supply_installation": "equipment_purchase_installation",
    "development_service": "advisory_service",
    "nda_confidentiality": "nda_confidentiality",
    "rental_lease": "rental",
    "sales_agency": "dealer_agency",
    "license": "license",
}


def family_of(code: str) -> str:
    """세부 분류 코드의 계열. 모르는 코드면 ""."""
    return FAMILY_OF.get(str(code or "").strip(), "")


@dataclass(frozen=True)
class CanonicalState:
    """검토 전체가 공유하는 확정값. 만들어진 뒤에는 바뀌지 않는다."""

    #: 세부 분류 코드 (체크리스트·룰 화이트리스트가 쓰는 어휘)
    contract_type: str
    #: 구조 판정 계열 (7개 중 하나)
    contract_type_family: str
    #: 사람이 읽는 계약유형명
    contract_type_label: str
    #: 우리 회사 지위 (party_role 어휘: supplier / buyer / contractor / …)
    party_role: str
    #: 우리 회사 지위 방향 (provider / recipient)
    party_role_direction: str
    #: 계약서가 우리를 부르는 이름
    party_label: str
    #: 상대방 지위
    counterparty_role: str
    #: 계약서가 상대방을 부르는 이름
    counterparty_label: str
    #: 문서 우선순위와 무력화 보고 (document_hierarchy 결과)
    document_hierarchy: dict[str, Any] = field(default_factory=dict)
    #: 거래구조 (Contract Legal Map 의 핵심 축)
    governing_transaction: dict[str, Any] = field(default_factory=dict)
    #: 어떻게 확정했는지 — 교정이 있었으면 그 사실이 남는다
    audit: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_type": self.contract_type,
            "contract_type_family": self.contract_type_family,
            "contract_type_label": self.contract_type_label,
            "party_role": self.party_role,
            "party_role_direction": self.party_role_direction,
            "party_label": self.party_label,
            "counterparty_role": self.counterparty_role,
            "counterparty_label": self.counterparty_label,
            "document_hierarchy": self.document_hierarchy,
            "governing_transaction": self.governing_transaction,
            "audit": self.audit,
        }


def reconcile_contract_type(
    *,
    detailed_code: str,
    resolved_family: str,
    resolved_confidence: float | None,
    resolved_uncertain: bool,
    resolved_top_score: int = 0,
    resolved_runner_up_score: int = 0,
) -> dict[str, Any]:
    """세부 분류 코드와 구조 판정 계열을 하나로 맞춘다.

    반환값의 `contract_type` 이 canonical 값이다. 교정이 일어났으면
    `corrected=True` 와 함께 이전 값을 남긴다 — 조용히 바꾸지 않는다.
    """
    detailed = str(detailed_code or "").strip()
    family = str(resolved_family or "").strip()
    detailed_family = family_of(detailed)
    confidence = float(resolved_confidence or 0.0)
    top = int(resolved_top_score or 0)
    runner_up = int(resolved_runner_up_score or 0)
    decisive = (
        top >= OVERRIDE_MIN_SIGNALS
        and (runner_up == 0 or top >= runner_up * OVERRIDE_MIN_SIGNAL_RATIO)
    )
    evidence = {
        "resolved_family": family,
        "resolved_confidence": confidence,
        "resolved_top_score": top,
        "resolved_runner_up_score": runner_up,
        "decisive": decisive,
    }

    # 구조 신호가 압도적이지 않으면 세부 분류를 그대로 둔다. 확신 없는 판정으로
    # 체크리스트를 갈아끼우면 더 나쁜 결과가 된다.
    if not family or resolved_uncertain or not decisive:
        return {
            "contract_type": detailed,
            "contract_type_family": detailed_family or family,
            "corrected": False,
            "reason": (
                f"구조 신호가 압도적이지 않아(1등 {top}개, 2등 {runner_up}개) "
                f"세부 분류를 유지했습니다."
                if family else "구조 판정 계열이 없습니다."
            ),
            "detailed_before": detailed,
            **evidence,
        }

    # 세부 코드가 그 계열에 속하면 세부 코드가 더 구체적이므로 유지한다.
    if detailed_family == family:
        return {
            "contract_type": detailed,
            "contract_type_family": family,
            "corrected": False,
            "reason": "세부 분류가 구조 판정 계열에 속합니다.",
            "detailed_before": detailed,
            **evidence,
        }

    # 계열을 알 수 없는 세부 코드(general / other_general / unknown 등)는
    # 계열 대표코드로 채운다 — 이것은 충돌이 아니라 미분류의 보완이다.
    representative = FAMILY_REPRESENTATIVE.get(family, family)
    if not detailed_family:
        return {
            "contract_type": representative,
            "contract_type_family": family,
            "corrected": True,
            "conflict": False,
            "reason": (
                f"세부 분류('{detailed or '미분류'}')의 계열을 알 수 없어 구조 판정 "
                f"계열의 대표코드로 확정했습니다."
            ),
            "detailed_before": detailed,
            **evidence,
        }

    # 여기까지 오면 두 판정이 **다른 계열**을 말한다. 구조 판정을 신뢰하고
    # 교정하되, 무엇이 어긋났는지 반드시 남긴다.
    return {
        "contract_type": representative,
        "contract_type_family": family,
        "corrected": True,
        "conflict": True,
        "reason": (
            f"세부 분류는 '{detailed}'({detailed_family}) 계열로 보았지만 급부·대금·"
            f"완료조건·위험이전 구조는 '{family}' 계열입니다. 제목·파일명이 아니라 "
            f"구조를 기준으로 '{representative}' 로 확정했습니다."
        ),
        "detailed_before": detailed,
        **evidence,
    }


def build_canonical_state(
    *,
    contract_type: str,
    contract_type_family: str,
    contract_type_label: str,
    party_role: str,
    party_label: str,
    counterparty_role: str,
    counterparty_label: str,
    document_hierarchy: dict[str, Any] | None = None,
    governing_transaction: dict[str, Any] | None = None,
    audit: dict[str, Any] | None = None,
) -> CanonicalState:
    """확정값을 얼린다. 이후 단계는 이 객체를 전달받아 쓴다."""
    from runtime.review.canonical_identity import normalize_role

    return CanonicalState(
        contract_type=str(contract_type or ""),
        contract_type_family=str(contract_type_family or ""),
        contract_type_label=str(contract_type_label or ""),
        party_role=str(party_role or ""),
        party_role_direction=normalize_role(party_role) or normalize_role(party_label),
        party_label=str(party_label or ""),
        counterparty_role=str(counterparty_role or ""),
        counterparty_label=str(counterparty_label or ""),
        document_hierarchy=dict(document_hierarchy or {}),
        governing_transaction=dict(governing_transaction or {}),
        audit=dict(audit or {}),
    )


def canonical_type_label(contract_type: str, contract_type_family: str) -> str:
    """계약유형명을 한 곳에서만 만든다.

    라벨을 두 표에서 각자 찾으면 같은 계약이 화면과 문서에서 다른 이름으로
    불린다. 세부 코드 라벨을 우선하고, 없으면 계열 라벨을 쓴다.
    """
    from runtime.review.contract_type_resolution import TYPE_LABELS as _FAMILY_LABELS
    from runtime.review.report_header import _CONTRACT_TYPE_LABELS as _DETAIL_LABELS

    code = str(contract_type or "").strip()
    family = str(contract_type_family or "").strip()
    label = _DETAIL_LABELS.get(code, "")
    if label:
        return label
    label = _FAMILY_LABELS.get(family, "")
    if label:
        return label
    return code or family


def check_output_consistency(
    state: CanonicalState | None,
    observed: dict[str, Any],
) -> dict[str, Any]:
    """최종 출력 직전, 출력이 canonical 값과 같은지 확인한다 (지시 2항).

    `observed` 는 출력 경로가 실제로 쓴 값이다. 하나라도 다르면 그 출력은
    다른 전제로 만들어진 것이므로 정상 완료가 아니다 — 상단은 장비 구매·설치
    라고 쓰면서 본문은 건설 도급으로 검토한 리포트가 이렇게 나왔다.
    """
    if state is None:
        return {"ok": True, "review_status": "", "mismatches": [], "detail": ""}

    checks: list[tuple[str, str, Any, Any]] = []

    def cmp(key: str, label: str, expected: Any) -> None:
        if key not in observed:
            return
        got = observed.get(key)
        if str(got or "").strip() and str(got).strip() != str(expected or "").strip():
            checks.append((key, label, expected, got))

    cmp("contract_type", "계약유형 코드", state.contract_type)
    cmp("contract_type_family", "계약유형 계열", state.contract_type_family)
    cmp("contract_type_label", "계약유형명", state.contract_type_label)
    cmp("party_role", "우리 회사 지위", state.party_role)
    cmp("counterparty_role", "상대방 지위", state.counterparty_role)

    if not checks:
        return {"ok": True, "review_status": "", "mismatches": [], "detail": ""}

    mismatches = [
        {"field": k, "label": lab, "canonical": str(exp or ""), "observed": str(got or "")}
        for k, lab, exp, got in checks
    ]
    return {
        "ok": False,
        "review_status": REVIEW_FAILED_CANONICAL_STATE_MISMATCH,
        "mismatches": mismatches,
        "detail": (
            "최종 출력이 확정값과 다릅니다: "
            + "; ".join(
                f"{m['label']} — 확정 '{m['canonical']}' vs 출력 '{m['observed']}'"
                for m in mismatches
            )
        ),
    }
