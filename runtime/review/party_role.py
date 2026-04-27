from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


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


def infer_party_role(*, contract_type: str, text: str, answers: dict[str, Any] | None) -> PartyRole:
    ct = (contract_type or "")
    t = (text or "")
    a = answers or {}
    signals: list[str] = []

    our_role = "unknown"
    counterparty_role = "unknown"

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


def infer_review_posture(*, party: PartyRole, contract_type: str, text: str) -> str:
    if party.our_role in ("buyer", "ordering_party"):
        return "buyer_favorable"
    if party.our_role in ("seller", "supplier"):
        return "seller_favorable"
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
