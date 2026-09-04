"""판매/위탁판매/대리판매/중개/판매지원 계약의 거래구조 모호성 탐지.

범용 사내변호사형 검토 엔진 전면 보정(2026-09-04 지시, 그림닷컴 판매지원
용역계약 실사례) — 계약 제목이나 contract_type/contract_class 분류 결과에
의존하지 않고, 계약 본문 자체에서 "판매·위탁판매·대리판매·중개·판매지원"
성격의 거래 신호가 있는지, 있다면 판매자·소유권 같은 핵심 사실관계가 계약
문언 자체에서 이미 확정되어 있는지를 독립적으로 판단한다.

이 신호는 contract_class 분류가 틀려도(예: 이번 실사례처럼 "advisory"로
오분류) 그와 무관하게 동작해야 한다 — 분류 오류를 자동으로 보완하는
안전망이기 때문이다.
"""
from __future__ import annotations

import re
from typing import Any

_RX_SALES_STRUCTURE_SIGNAL = re.compile(
    r"판매|매매|위탁판매|대리판매|중개|판매지원|영업지원|매입.{0,10}판매|재판매",
    re.IGNORECASE,
)
_RX_CUSTOMER_SIGNAL = re.compile(r"고객|소비자|구매자", re.IGNORECASE)
_RX_PAYMENT_CHANNEL_SIGNAL = re.compile(
    r"결제|POS|포스|수수료|용역수수료|판매수수료|대금\s*수령",
    re.IGNORECASE,
)

# 계약 문언 자체가 이미 판매자·소유권을 명시적으로 확정하고 있다는 신호 —
# 이런 문장이 있으면 더 이상 물을 필요가 없다.
_RX_SELLER_ALREADY_RESOLVED = re.compile(
    r"판매자는\s*[\S ]{0,20}(?:이다|로\s*한다)"
    r"|매도인은\s*[\S ]{0,20}(?:이다|로\s*한다)"
    r"|(?:갑|을)(?:이|가)\s*(?:매입|구매)하여?\s*(?:재판매|다시\s*판매)"
    r"|고객과의?\s*매매계약(?:상)?\s*당사자는\s*[\S ]{0,20}(?:이다|로\s*한다)",
    re.IGNORECASE,
)
_RX_OWNERSHIP_ALREADY_RESOLVED = re.compile(
    r"소유권은\s*[\S ]{0,20}(?:에게\s*있다|에\s*귀속)"
    r"|소유권(?:은|이)\s*[\S ]{0,20}(?:이전|귀속)",
    re.IGNORECASE,
)


def detect_sales_transaction_ambiguity(text: str) -> bool:
    """판매/위탁판매/대리판매/중개/판매지원 성격의 거래 신호가 있는데,
    판매자·소유권이 계약 문언 자체에서 이미 명시적으로 확정되어 있지
    않으면 True. contract_type_code/contract_class와 무관하게 순수 텍스트
    신호로만 판단한다."""
    t = text or ""
    if not t.strip():
        return False
    has_sales_signal = bool(_RX_SALES_STRUCTURE_SIGNAL.search(t))
    has_customer_signal = bool(_RX_CUSTOMER_SIGNAL.search(t))
    has_payment_channel_signal = bool(_RX_PAYMENT_CHANNEL_SIGNAL.search(t))
    if not (has_sales_signal and (has_customer_signal or has_payment_channel_signal)):
        return False
    already_resolved = bool(_RX_SELLER_ALREADY_RESOLVED.search(t)) and bool(_RX_OWNERSHIP_ALREADY_RESOLVED.search(t))
    return not already_resolved
