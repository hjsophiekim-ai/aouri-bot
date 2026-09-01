from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from runtime.review.contract_classifier import FURSYS_GROUP_NAMES, is_fursys_group
from runtime.review.party_label_binding import (
    bind_party_labels_to_entities, explicit_role_from_labels, role_word_near_entity,
)


@dataclass(frozen=True)
class PartyRole:
    our_role: str
    counterparty_role: str
    our_label: str | None
    counterparty_label: str | None
    counterparty_is_large_standard_provider: bool
    signals: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "our_role": self.our_role,
            "counterparty_role": self.counterparty_role,
            "our_label": self.our_label,
            "counterparty_label": self.counterparty_label,
            "counterparty_is_large_standard_provider": self.counterparty_is_large_standard_provider,
            "signals": list(self.signals),
        }


_LG_MARKERS = ["LG전자", "엘지", "LG ", "LG\n", "LG\t", "LG-"]

# All Fursys group brand names that indicate 'supplier' role in dealer/distribution contracts
_FURSYS_GROUP_TEXT_TOKENS: list[str] = [
    "퍼시스홀딩스", "퍼시스", "fursys", "FURSYS",
    "일룸", "iloom", "ILOOM",
    "시디즈", "sidiz", "SIDIZ",
    "데스커", "desker", "DESKER",
    "바로스", "baros", "BAROS",
]


def _is_fursys_group_entity(entity: str) -> bool:
    """Return True if entity belongs to any Fursys Group brand."""
    return is_fursys_group(entity)


def _entity_has_fursys_group(entity: str, text: str) -> bool:
    """Return True if entity string OR contract text refers to any Fursys Group brand."""
    if _is_fursys_group_entity(entity):
        return True
    # Also check text for cases where entity is generic but text reveals brand
    return any(tok in (text or "") for tok in _FURSYS_GROUP_TEXT_TOKENS)


_ANSWER_ROLE_TO_LOCAL: dict[str, tuple[str, str]] = {
    "we_are_supplier": ("supplier", "dealer_or_distributor"),
    "we_are_buyer": ("buyer", "seller_or_supplier"),
    "we_are_service_recipient": ("client", "service_provider"),
    "we_are_service_provider": ("service_provider", "client"),
    "we_are_contractor": ("contractor", "ordering_party"),
    "we_are_ordering_party": ("ordering_party", "contractor_or_supplier"),
    "we_are_dealer": ("dealer", "supplier"),
}

_CANONICAL_SERVICE_RECIPIENT_TYPE_CODES = frozenset({
    "advisory_service", "software_app_development", "ai_search_marketing",
    "store_operation_outsourcing", "creative_agency_service",
    "content_production_service", "advertising_content_production",
})

_TESTING_SERVICE_KW = [
    "시험연구원", "시험기관", "검사기관", "공인시험", "공인검사",
    "인증기관", "교정기관", "시험성적서", "검사성적서",
    "시험분석", "시험 분석", "시험의뢰", "시험 의뢰", "적합성평가",
]


def infer_party_role(
    *,
    entity: str,
    contract_type: str,
    text: str,
    answers: dict[str, Any] | None,
    contract_type_code: str | None = None,
) -> PartyRole:
    """Infer our/counterparty role.

    contract_type_code: canonical type_code from
        contract_classifier.classify_contract_detailed(), when the caller has
        already computed it. When it identifies a testing/inspection service
        (where we are the party requesting testing, not the lab performing
        it), that takes priority over the local keyword heuristics below —
        those heuristics have no notion of "시험기관/수탁자" at all and would
        otherwise leave our_role stuck at a wrong or "unknown" default.
    """
    ent = (entity or "")
    ct = (contract_type or "")
    t = (text or "")
    a = answers or {}
    signals: list[str] = []

    our_role = "unknown"
    counterparty_role = "unknown"

    _answer_role = a.get("Q-ROLE-001-our-position")
    if isinstance(_answer_role, str) and _answer_role in _ANSWER_ROLE_TO_LOCAL:
        our_role, counterparty_role = _ANSWER_ROLE_TO_LOCAL[_answer_role]
        signals.append("user_confirmed_our_role")
        return PartyRole(
            our_role=our_role,
            counterparty_role=counterparty_role,
            our_label=None,
            counterparty_label=None,
            counterparty_is_large_standard_provider=False,
            signals=signals,
        )

    _label_bind = bind_party_labels_to_entities(t, ent)
    if _label_bind is not None:
        _our_lbl, _cp_lbl = _label_bind
        _explicit = explicit_role_from_labels(t, _our_lbl, _cp_lbl)
        if _explicit == "supplier":
            signals.append("explicit_label_self_declared_supplier")
            return PartyRole(
                our_role="supplier",
                counterparty_role="buyer",
                our_label=_our_lbl,
                counterparty_label=_cp_lbl,
                counterparty_is_large_standard_provider=False,
                signals=signals,
            )
        if _explicit == "buyer":
            signals.append("explicit_label_self_declared_buyer")
            return PartyRole(
                our_role="buyer",
                counterparty_role="seller_or_supplier",
                our_label=_our_lbl,
                counterparty_label=_cp_lbl,
                counterparty_is_large_standard_provider=False,
                signals=signals,
            )
    else:
        # "(이하 ...)" 정의문 없이 "매도인 퍼시스를 (을)이라 칭한다"처럼
        # 역할 명사가 회사명 바로 옆에 오는 형식에 대한 fallback.
        _near = role_word_near_entity(t, ent)
        if _near == "supplier":
            signals.append("role_word_near_entity_supplier")
            return PartyRole(
                our_role="supplier", counterparty_role="buyer", our_label=None,
                counterparty_label=None, counterparty_is_large_standard_provider=False,
                signals=signals,
            )
        if _near == "buyer":
            signals.append("role_word_near_entity_buyer")
            return PartyRole(
                our_role="buyer", counterparty_role="seller_or_supplier", our_label=None,
                counterparty_label=None, counterparty_is_large_standard_provider=False,
                signals=signals,
            )

    if contract_type_code == "nda_confidentiality":
        # NDA는 통상 상호적(mutual)이라 buyer/supplier류 방향성 role로
        # 강제 분류하면 오히려 오해를 만든다 — 아래 whole-document
        # 키워드 휴리스틱(렌탈/개발 등)으로 넘어가지 않도록 여기서 확정.
        signals.append("nda_confidentiality_neutral_role")
        return PartyRole(
            our_role="party",
            counterparty_role="party",
            our_label=None,
            counterparty_label=None,
            counterparty_is_large_standard_provider=False,
            signals=signals,
        )

    if contract_type_code == "testing_inspection_service" or _has_any(t, _TESTING_SERVICE_KW):
        our_role = "client"
        counterparty_role = "service_provider"
        signals.append("testing_inspection_service_override")
        return PartyRole(
            our_role=our_role,
            counterparty_role=counterparty_role,
            our_label=None,
            counterparty_label=None,
            counterparty_is_large_standard_provider=False,
            signals=signals,
        )

    if contract_type_code in _CANONICAL_SERVICE_RECIPIENT_TYPE_CODES:
        # 이 그룹(자문/용역/개발/마케팅 등)은 아래 whole-document 키워드
        # 휴리스틱과 달리 방향성이 대칭적이지 않다 — 아우리봇을 쓰는 회사
        # (가구 제조사)는 이런 유형에서 거의 항상 서비스를 받는 쪽(client)
        # 이므로, canonical 분류가 이미 이 유형으로 확정했다면 아래 25개
        # 키워드 분기로 다시 추측하지 않는다(2026-09-01 — "계약유형이
        # 바뀌어도 downstream에서 역할을 다시 추측하지 않게" 요청 반영).
        # purchase_supply/equipment_purchase_installation/rental/dealer_*
        # 처럼 실제로 방향이 뒤집힐 수 있는 유형은 여기 포함하지 않는다
        # (v5.1에서 이미 겪은 "type_code만으로 방향 고정" 사고 재발 방지 —
        # 그 유형들은 계속 아래 label-binding/키워드 로직이 판단한다).
        our_role = "client"
        counterparty_role = "service_provider"
        signals.append("canonical_service_recipient_type_override")
        return PartyRole(
            our_role=our_role,
            counterparty_role=counterparty_role,
            our_label=None,
            counterparty_label=None,
            counterparty_is_large_standard_provider=False,
            signals=signals,
        )

    is_our_fursys_group = _entity_has_fursys_group(ent, t)

    if is_our_fursys_group:
        if any(k in ct for k in ("대리점", "유통", "위탁", "운영대행", "위탁판매")) or _has_any(t, ["대리점", "대리점법", "재판매", "판매가격", "유통", "위탁판매", "용역수수료"]):
            our_role = "supplier"
            counterparty_role = "dealer_or_distributor"
            signals.append("entity_fursys_group_dealer_override")
        if any(k in ct for k in ("인테리어", "공사", "시공", "리모델링")) or _has_any(t, ["수급인", "도급인", "공사", "시공", "인테리어"]):
            our_role = "contractor"
            counterparty_role = "ordering_party"
            signals.append("entity_fursys_group_construction_override")
        if any(k in ct for k in ("렌탈", "렌트", "구독", "구독서비스")) or _has_any(
            t,
            [
                "렌탈료",
                "월 렌탈료",
                "구독료",
                "정기결제",
                "자동결제",
                "반납",
                "회수",
                "소유권은",
                "청약철회",
            ],
        ):
            our_role = "rental_provider"
            counterparty_role = "renter"
            signals.append("entity_fursys_group_rental_override")

    if any(k in ct for k in ("구매", "매매", "물품공급/구매/매매", "장비공급", "물품구매")) or _has_any(t, ["구매자", "매수인", "발주자"]):
        our_role = "buyer"
        counterparty_role = "seller_or_supplier"
        signals.append("contract_type_or_text_buyer")

    if any(k in ct for k in ("설치", "시운전", "납품", "검수")) or _has_any(t, ["설치", "시운전", "검수", "납품", "현장"]):
        if our_role == "unknown":
            our_role = "ordering_party"
            counterparty_role = "contractor_or_supplier"
        signals.append("installation_commissioning_keywords")

    if any(k in ct for k in ("용역", "자문", "SOW")):
        if our_role == "unknown":
            our_role = "client"
            counterparty_role = "service_provider"
        signals.append("service_contract_type")

    if _looks_like_app_dev(ct, t):
        if our_role == "unknown":
            our_role = "ordering_party"
            counterparty_role = "service_provider"
        signals.append("app_dev_keywords")

    if isinstance(a.get("Q-CA-999-template-owner"), str):
        if a["Q-CA-999-template-owner"] == "counterparty":
            signals.append("counterparty_template_owner_answer")
        elif a["Q-CA-999-template-owner"] == "ours":
            signals.append("ours_template_owner_answer")

    labels = _infer_labels_from_definitions(t)
    our_label = labels.get("our_label")
    counter_label = labels.get("counterparty_label")
    signals.extend(labels.get("signals", []))

    if is_our_fursys_group:
        if our_label is None and our_role == "supplier":
            our_label = "갑"
            counter_label = counter_label or "을"
            signals.append("entity_fursys_group_label_supplier")
        if our_label is None and our_role == "contractor":
            our_label = "을"
            counter_label = counter_label or "갑"
            signals.append("entity_fursys_group_label_contractor")
        if our_label is None and our_role == "rental_provider":
            our_label = "갑"
            counter_label = counter_label or "을"
            signals.append("entity_fursys_group_label_rental_provider")

    counterparty_is_large = any(m in t for m in _LG_MARKERS) or ("LG" in (ct or ""))
    if counterparty_is_large:
        signals.append("counterparty_large_lg_marker")

    if our_role == "unknown":
        our_role = "buyer" if _looks_like_purchase_installation(ct, t) else "neutral"
        counterparty_role = "seller_or_supplier" if our_role == "buyer" else "unknown"
        signals.append("default_role_applied")

    return PartyRole(
        our_role=our_role,
        counterparty_role=counterparty_role,
        our_label=our_label,
        counterparty_label=counter_label,
        counterparty_is_large_standard_provider=counterparty_is_large,
        signals=signals[:20],
    )


def infer_review_posture(*, party: PartyRole, contract_type: str, text: str, contract_type_code: str = "") -> str:
    if party.our_role in ("buyer", "ordering_party"):
        return "buyer_favorable"
    if party.our_role in ("seller", "supplier", "contractor", "rental_provider"):
        return "seller_favorable"
    if contract_type_code == "nda_confidentiality":
        # NDA는 구조상 매수/매도 방향성 자체가 없다 — party.our_role이
        # "party"(중립)로 이미 확정된 경우, 아래 텍스트 스캔 폴백(예: NDA
        # 서두의 프로젝트 설명에 우연히 "구매"/"설치"가 언급된 경우)이
        # buyer_favorable로 잘못 뒤집지 않도록 여기서 확정한다
        # (2026-09-01, canonical_type_code를 우선하는 원칙 일관 적용).
        return "neutral"
    if _looks_like_purchase_installation(contract_type, text):
        return "buyer_favorable"
    if _looks_like_app_dev(contract_type, text):
        return "buyer_favorable"
    return "neutral"


def _looks_like_purchase_installation(contract_type: str, text: str) -> bool:
    ct = (contract_type or "")
    t = (text or "")
    if any(k in ct for k in ("물품공급/구매/매매", "구매", "장비공급", "설치", "시운전")):
        return True
    return _has_any(t, ["장비", "설치", "시운전", "납품", "검수"]) and _has_any(t, ["대금", "매매", "구매", "계약금액"])


def _looks_like_app_dev(contract_type: str, text: str) -> bool:
    ct = (contract_type or "")
    t = (text or "")
    if any(k in ct for k in ("앱개발", "소프트웨어개발", "SI", "유지보수", "SaaS", "API")):
        return True
    return _has_any(t, ["앱 개발", "소프트웨어 개발", "시스템 개발", "개발 용역", "SI", "유지보수", "SaaS", "API 연동", "소스코드", "산출물", "SLA"])

def _has_any(text: str, keywords: list[str]) -> bool:
    s = (text or "").lower()
    return any(k.lower() in s for k in keywords)


def _infer_labels_from_definitions(text: str) -> dict[str, Any]:
    t = text or ""
    signals: list[str] = []
    out: dict[str, Any] = {"signals": signals}
    m1 = re.search(r"(갑|을)\s*\(\s*(구매자|발주자|도급인|주문자)\s*\)", t)
    m2 = re.search(r"(갑|을)\s*\(\s*(공급자|판매자|수급인|수급자|시공자)\s*\)", t)
    if m1:
        out["our_label"] = m1.group(1)
        signals.append("party_definition_our_label")
    if m2:
        out["counterparty_label"] = m2.group(1)
        signals.append("party_definition_counterparty_label")
    return out
