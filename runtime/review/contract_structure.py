"""Detect 'direct_customer_contract_with_dealer_service' contract structure.

This module classifies contracts where:
- The supplier (e.g. 퍼시스) directly contracts with the customer.
- The dealer performs delegated sales-support services and receives service fees.
- The dealer is NOT the customer-facing contracting party, tax invoice issuer, or collection risk bearer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


STRUCTURE_DIRECT_CUSTOMER = "direct_customer_contract_with_dealer_service"
STRUCTURE_STANDARD = "standard"

# (signal_text, weight)
_SIGNAL_WEIGHTS: list[tuple[str, int]] = [
    ("위탁판매 대리점", 4),
    ("검수마스터", 4),
    ("위탁커넥트플러스", 4),
    ("고객이 착오로 대리점에게 대금을 입금", 4),
    ("공급업자는 용역수수료를 지급", 4),
    ("위탁판매", 3),
    ("상품공급계약", 3),
    ("용역수수료", 3),
    ("기본수수료", 2),
    ("추가수수료", 2),
    ("인센티브", 1),
    ("세금계산서 발행", 1),
    ("대금 청구", 1),
    ("수금", 1),
    ("대리점은 고객과 계약", 2),
    ("대리점은 고객에게 판매", 2),
    ("최종소비자", 2),
    ("고객과 공급업자", 2),
]

_THRESHOLD = 7

# Regex patterns that further confirm the structure
_CONFIRM_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"위탁판매\s*(대리점|계약|약정)", re.IGNORECASE),
    re.compile(r"공급업자[가이]\s*고객과\s*직접", re.IGNORECASE),
    re.compile(r"검수\s*마스터|검수마스터", re.IGNORECASE),
]


@dataclass
class ContractStructureResult:
    contract_structure: str
    structure_confidence: float
    detected_structure_signals: list[str] = field(default_factory=list)
    contract_type: str = "위탁판매 대리점 계약"
    our_side_role: str = "공급업자/퍼시스"
    customer_contract_party: str = ""
    dealer_role: str = ""
    fee_model: str = ""
    primary_review_lens: str = ""
    review_priority: str = "standard"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_type": self.contract_type,
            "contract_structure": self.contract_structure,
            "structure_confidence": self.structure_confidence,
            "detected_structure_signals": self.detected_structure_signals,
            "our_side_role": self.our_side_role,
            "customer_contract_party": self.customer_contract_party,
            "dealer_role": self.dealer_role,
            "fee_model": self.fee_model,
            "primary_review_lens": self.primary_review_lens,
            "review_priority": self.review_priority,
        }


def detect_contract_structure(
    text: str,
    entity: str = "",
    contract_type: str = "",
) -> ContractStructureResult:
    """Detect whether this contract uses the direct_customer_contract_with_dealer_service structure."""
    t = text or ""
    ct = contract_type or ""
    ent = entity or ""

    # Fast exclusion: if strong non-dealer signals are present, skip
    if _is_clearly_not_dealer(t, ct):
        return ContractStructureResult(
            contract_structure=STRUCTURE_STANDARD,
            structure_confidence=0.0,
        )

    matched: list[str] = []
    score = 0
    for signal, weight in _SIGNAL_WEIGHTS:
        if signal in t:
            matched.append(signal)
            score += weight

    # Bonus for confirm patterns
    confirm_bonus = 0
    for pat in _CONFIRM_PATTERNS:
        if pat.search(t):
            confirm_bonus += 2

    total = score + confirm_bonus

    if total < _THRESHOLD:
        return ContractStructureResult(
            contract_structure=STRUCTURE_STANDARD,
            structure_confidence=min(0.4, total / _THRESHOLD * 0.4),
            detected_structure_signals=matched,
        )

    # Compute confidence (capped at 1.0)
    confidence = min(1.0, 0.5 + (total - _THRESHOLD) * 0.05)
    confidence = round(confidence, 2)

    # Determine customer_contract_party
    if "퍼시스" in ent or "퍼시스" in t:
        customer_contract_party = "공급업자/퍼시스"
    else:
        customer_contract_party = "공급업자"

    return ContractStructureResult(
        contract_structure=STRUCTURE_DIRECT_CUSTOMER,
        structure_confidence=confidence,
        detected_structure_signals=matched,
        contract_type=_infer_contract_type(ct, t),
        our_side_role=customer_contract_party,
        customer_contract_party=customer_contract_party,
        dealer_role="위탁판매 용역 수행자",
        fee_model="용역수수료 + 인센티브",
        primary_review_lens=(
            "계약당사자/청구주체/수금책임/A/S책임 정합성 + 대리점법상 불이익 제공 방지"
        ),
        review_priority="structure_mismatch_first",
    )


def _is_clearly_not_dealer(text: str, contract_type: str) -> bool:
    ct = contract_type or ""
    if any(k in ct for k in ("NDA", "비밀유지", "소프트웨어 개발", "앱개발", "SI", "임대차")):
        return True
    if re.search(r"\bNDA\b|Non[- ]Disclosure|confidentiality", ct, re.IGNORECASE):
        return True
    return False


def _infer_contract_type(contract_type: str, text: str) -> str:
    if "위탁판매" in text or "위탁판매" in contract_type:
        if "대리점" in text or "대리점" in contract_type:
            return "위탁판매 대리점 계약"
    if "대리점" in text:
        return "대리점 계약"
    return contract_type or "위탁판매 계약"
