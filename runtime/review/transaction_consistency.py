"""거래 실질과 모순되는 템플릿 문구를 차단한다.

2026-09-10 지시 — "실제 거래와 모순되는 템플릿 금지. 현금 지급이 없는 바터
거래에서 '대금 완납 전 사용권' 문구 자동삽입 금지. 실제 계약 구조와 다른
일반 템플릿을 쓰기 전에 transaction_consistency_check."

룰·AI가 만드는 수정문안 상당수는 "현금을 주고받는 표준 용역계약"을 전제로 한
템플릿이다. 그 전제가 깨진 계약(대물교환, 무상 제공, 수수료 정산형 등)에
그대로 넣으면 계약서가 스스로 모순된다 — 예컨대 현금 대가가 아예 없다고
명시한 바터 계약에 "대금을 완납한 때 사용권이 이전된다"를 넣으면, 영원히
오지 않는 조건을 권리 이전의 요건으로 박아 넣는 셈이다.

이 모듈은 계약의 대가 구조를 먼저 판별하고, 그 구조와 양립할 수 없는 문구가
담긴 수정문안을 **적용 대상에서 제외**한다(문제 제기는 남긴다 —
`delivery_gate.withdraw_proposal` 과 같은 원칙).
"""
from __future__ import annotations

import re
from typing import Any

#: 금전 대가가 오가지 않는 교환·무상 구조 신호.
_RX_NON_MONETARY = re.compile(
    r"대물교환|물물교환|바터|barter|현물\s*교환"
    r"|현금\s*(?:지급|대가)(?:가|이)?\s*없[는다]"
    r"|별도의\s*현금\s*대가를\s*지급하지\s*아니"
    r"|금전\s*지급을\s*청구할\s*수\s*없",
    re.IGNORECASE,
)

#: 현금 대가 지급을 전제로만 성립하는 템플릿 문구.
_RX_CASH_PAYMENT_TEMPLATE = re.compile(
    r"대금(?:을|의)?\s*완납|잔금\s*지급|대금\s*지급(?:일|기한|조건)"
    r"|기성(?:금|고)|선급금|착수금|검수\s*후\s*\d+일\s*이내\s*(?:에\s*)?지급"
    r"|월\s*\d+회\s*지급|지급기일로부터|대금을\s*지급받은\s*때",
    re.IGNORECASE,
)

CONSIDERATION_NON_MONETARY = "non_monetary_exchange"
CONSIDERATION_MONETARY = "monetary"

_PROPOSAL_FIELDS = ("suggested_rewrite", "proposed_revision", "recommendation_text")


def classify_consideration_structure(text: str) -> str:
    """계약의 대가 구조를 판별한다."""
    return (
        CONSIDERATION_NON_MONETARY
        if _RX_NON_MONETARY.search(str(text or ""))
        else CONSIDERATION_MONETARY
    )


def check_transaction_consistency(
    clause_results: list[dict[str, Any]],
    *,
    contract_text: str,
) -> dict[str, Any]:
    """거래 구조와 모순되는 수정문안을 회수한다.

    회수 내역을 리포트로 돌려준다 — 조용히 사라지지 않게 하기 위함이다.
    """
    structure = classify_consideration_structure(contract_text)
    report: dict[str, Any] = {
        "consideration_structure": structure,
        "withdrawn": [],
    }
    if structure != CONSIDERATION_NON_MONETARY:
        return report

    from runtime.review.delivery_gate import withdraw_proposal

    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        proposed = " ".join(str(cr.get(k) or "") for k in _PROPOSAL_FIELDS)
        if not proposed.strip():
            continue
        m = _RX_CASH_PAYMENT_TEMPLATE.search(proposed)
        if not m:
            continue
        # 원문 자체가 그 표현을 쓰고 있다면 계약이 실제로 그렇게 정한 것이므로
        # 모순이 아니다(예: 바터이지만 일부 정산은 현금인 혼합 구조).
        if _RX_CASH_PAYMENT_TEMPLATE.search(str(cr.get("original_text") or "")):
            continue
        report["withdrawn"].append({
            "clause_id": str(cr.get("clause_id") or ""),
            "matched": m.group(0),
        })
        withdraw_proposal(
            cr,
            status="TRANSACTION_STRUCTURE_MISMATCH",
            reason=(
                "현금 대가가 오가지 않는 교환(바터) 구조인데 수정문안이 대금 지급·완납을 "
                "전제로 하고 있어 적용을 보류함"
            ),
        )
    return report
