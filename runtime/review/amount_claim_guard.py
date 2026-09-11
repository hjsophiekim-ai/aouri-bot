"""근거 없는 금액 추정을 검토의견에서 걷어낸다.

2026-09-10 지시 항목 7 — "세무·회계는 과장 금지. 근거 없는 `수천만원/수억원
손실` 추정 금지. 계약 문구는 제안하되 세무처리는 `재경팀 확인`으로 분리."

실측 (대물교환 계약, AI 경로)
──────────────────────────
    "…가산세 및 매입세액 불공제, 국세청 추징 위험이 발생한다. 공급가액이
     **수천만~수억 원**에 달할 경우…"
    "…시가 산정 근거가 불충분하면 공급가액 부인 및 추가 세금 부담
     (**수백만~수천만 원**) 발생 가능"
    "…법인세 손금불산입 및 추징(**공급가액의 10~25%** 상당) 위험"

계약서에는 금액이 공란(`일금 [ ]원`)이었다. 즉 이 숫자들은 근거가 없다.
사내변호사 의견서에 근거 없는 추징액이 적히면, 담당자가 그 숫자를 들고
협상하거나 상부에 보고하게 된다 — 틀린 숫자는 없는 숫자보다 나쁘다.

판정 방식
────────
금액 표현을 찾고, **그 숫자가 계약 원문에 실제로 있는지** 대조한다. 없으면
그 표현만 지우고 정성적 서술로 바꾼다. finding 자체는 남긴다 — 리스크 지적은
유효하고, 신뢰할 수 없는 것은 규모 추정뿐이다.
"""
from __future__ import annotations

import re
from typing import Any

#: 규모를 단정하는 표현. 계약 원문에 근거가 없으면 지운다.
_RX_VAGUE_MAGNITUDE = re.compile(
    # "수천만~수억 원" 처럼 앞부분에 '원' 이 없는 범위 표현까지 한 덩어리로
    # 잡아야 한다 — 뒤쪽만 지우면 "수천만~" 이 문장에 남는다.
    #
    # 다만 끝에 **'원' 을 반드시 요구한다.** 그러지 않으면 "검수 조항" 의
    # "수 조" 가 금액으로 잡혀 문장이 "검계약상 급부 가액에 연동되는 규모항"
    # 으로 훼손된다(2026-09-11 실측). 금액 표현은 화폐 단위가 있어야 한다.
    r"수\s*(?:십|백|천)?\s*(?:만|억|조)"
    r"(?:\s*[~∼-]\s*수\s*(?:십|백|천)?\s*(?:만|억|조))*"
    r"\s*원"
    r"|[0-9]+\s*(?:만|억|조)\s*원\s*(?:이상|상당|규모|대)"
)

#: 비율 추정("공급가액의 10~25% 상당"). 법정 세율·약정 이율은 남긴다.
_RX_VAGUE_RATE = re.compile(
    r"(?<![0-9])[0-9]{1,2}\s*[~∼-]\s*[0-9]{1,3}\s*%\s*(?:상당|정도|수준|가량)?"
)

#: 계약 원문에서 뽑을 금액·비율. 여기 있는 값이면 근거가 있는 것이다.
_RX_CONTRACT_NUMBER = re.compile(r"[0-9][0-9,\.]*\s*(?:%|원|만원|억원|퍼센트|분의)")

#: 이 표현으로 대체한다 — 규모를 말하지 않고 노출의 성질만 남긴다.
_MAGNITUDE_REPLACEMENT = "계약상 급부 가액에 연동되는 규모"
_RATE_REPLACEMENT = "관련 법령이 정한 비율"

_TEXT_FIELDS = (
    "problem",
    "rewrite_reason",
    "legal_business_reason",
    "worst_case_scenario",
    "our_company_risk",
    "negotiation_strategy",
    "negotiation_position",
    "recommendation_text",
    "suggested_rewrite",
)


def _contract_numbers(text: str) -> set[str]:
    return {m.group(0).replace(" ", "") for m in _RX_CONTRACT_NUMBER.finditer(str(text or ""))}


def scrub_unfounded_amounts(
    clause_results: list[dict[str, Any]],
    *,
    contract_text: str,
) -> list[dict[str, Any]]:
    """계약 원문에 근거가 없는 금액·비율 추정을 제거한다.

    제거 내역을 돌려준다 — 무엇을 지웠는지 남긴다.
    """
    body = str(contract_text or "")
    grounded = _contract_numbers(body)
    removed: list[dict[str, Any]] = []

    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        hits: list[str] = []
        for field in _TEXT_FIELDS:
            value = cr.get(field)
            if not isinstance(value, str) or not value.strip():
                continue
            new_value = value
            for rx, replacement in (
                (_RX_VAGUE_MAGNITUDE, _MAGNITUDE_REPLACEMENT),
                (_RX_VAGUE_RATE, _RATE_REPLACEMENT),
            ):
                for m in list(rx.finditer(new_value)):
                    token = m.group(0)
                    # 계약 원문이 그 숫자를 쓰고 있으면 근거가 있는 것이다.
                    if token.replace(" ", "") in grounded or token.replace(" ", "") in body.replace(" ", ""):
                        continue
                    new_value = new_value.replace(token, replacement)
                    hits.append(token.strip())
            if new_value != value:
                cr[field] = new_value
        if hits:
            cr["amount_estimates_scrubbed"] = sorted(set(hits))[:6]
            removed.append({
                "clause_id": str(cr.get("clause_id") or ""),
                "removed": sorted(set(hits))[:6],
            })
    return removed


def split_finance_confirmation(cr: dict[str, Any], finance_note: str) -> None:
    """세무·회계 판단을 법무 결론과 분리해 표시한다(지시 항목 7).

    법무가 계약 문구로 할 수 있는 것은 수정문안에 남기고, 세무처리 자체의
    판단은 "재경/세무팀 확인사항" 으로 따로 세운다.
    """
    note = str(finance_note or "").strip()
    if not isinstance(cr, dict) or not note:
        return
    cr["finance_confirmation"] = note
    label = f"[재경/세무팀 확인사항] {note}"
    existing = str(cr.get("legal_business_reason") or "").strip()
    if label not in existing:
        cr["legal_business_reason"] = f"{existing}\n{label}".strip() if existing else label
