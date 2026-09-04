"""대리점법/하도급법 적용가능성 판단 보정(2026-09-04 지시, 그림닷컴 사례).

`legal_applicability_review.py::build_mandatory_legal_applicability_review()`가
반환한 결과(AI 판단 또는 AI 미가동 시 stub)를 계약의 구조적 신호로
검증해, 다음 두 가지 오류를 구조적으로 방지한다:

1. 대리점법을 "상대방이 자기 명의로 재판매하지 않는다"는 이유만으로
   낮음/확인불가로 방치하는 오류 — 대리점법은 재판매뿐 아니라
   위탁판매 구조도 포함한다. 기존 대리점(위탁판매)관계가 있고 이번
   계약이 그 관계와 동일 매장·인력·POS 또는 계약기간·해지 연동으로
   경제적·운영상 연계되어 있으면, 위탁판매 여부와 무관하게 최소
   "있음(추가 확인 필요)"/MEDIUM으로 끌어올린다(floor — 이미 그보다
   높은 판단은 그대로 둔다).
2. 하도급법을 단순 "위탁"/"판매지원" 키워드만으로 MEDIUM 이상으로
   자동 승격하는 오류 — 실제 제조위탁/설계위탁/시공위탁/수리위탁 같은
   규제대상 행위 신호가 전혀 없으면 LOW로 캡한다(ceiling — 절대 값을
   올리지 않는다).

계약유형·회사명·상품명을 하드코딩하지 않는다 — 판매/위탁판매/대리판매/
중개 성격의 어떤 계약에도 적용되는 구조적 신호만 본다.
"""
from __future__ import annotations

import re
from typing import Any

from runtime.review.sales_transaction_rules import (
    _RX_CONTRACT_LINKAGE,
    _RX_EXISTING_DEALER_SIGNAL,
    _RX_SEPARATE_CONTRACT_REFERENCE,
    _RX_VOLUNTARY_PARTICIPATION_CLAUSE,
)

_RISK_RANK: dict[str, int] = {"확인 필요": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}

# 동일 매장·인력·POS(단말기) 재사용 — "별도 계약" 형식과 무관하게 기존
# 거래관계와의 운영상 연계를 보여주는 신호.
_RX_SAME_STORE_STAFF_POS_REUSE = re.compile(
    r"매장\s*(?:단말기|POS)|기존\s*(?:매장|인력|공간)(?:을|를)?\s*(?:그대로|계속)?\s*(?:활용|사용|이용)"
    r"|동일한?\s*(?:매장|인력|단말기|POS|장소|공간)",
    re.IGNORECASE,
)

# 하도급법의 실제 규제대상 행위(제조위탁/설계위탁/시공위탁/수리위탁) 신호 —
# 상담/전시/주문접수/결제대행/배송안내/재고관리 같은 단순 판매지원과
# 구분한다.
_RX_SUBCONTRACT_REGULATED_ACTIVITY = re.compile(
    r"제조\s*위탁|사양.{0,10}(?:주문|제작)|규격.{0,10}(?:주문|제작)|설계\s*(?:업무)?\s*위탁"
    r"|시공\s*(?:업무)?\s*위탁|수리\s*위탁|가공\s*위탁",
)


def _normalize_risk_level(value: str | None) -> str:
    v = str(value or "").strip().upper()
    return v if v in ("HIGH", "MEDIUM", "LOW") else "확인 필요"


def has_existing_dealer_relationship_signal(full_text: str, legal_map_fields: dict[str, Any] | None) -> bool:
    """기존 대리점(위탁판매)관계가 있다는 신호 — Contract Legal Map에
    사용자가 답변한 existing_related_contract/dependency_on_existing_contract
    가 있으면 최우선으로 신뢰하고, 없으면 원문에서 구조 신호를 찾는다."""
    fields = legal_map_fields or {}
    if str(fields.get("existing_related_contract") or "").strip():
        return True
    if str(fields.get("dependency_on_existing_contract") or "").strip():
        return True
    return bool(_RX_EXISTING_DEALER_SIGNAL.search(full_text or ""))


def has_economic_operational_linkage_signal(full_text: str) -> bool:
    """별도 계약 형식이더라도 기존 거래관계와 경제적·운영상 연계되어
    있다는 신호 — 계약기간/해지 연동, 또는 동일 매장·인력·POS 재사용."""
    t = full_text or ""
    return bool(
        (_RX_SEPARATE_CONTRACT_REFERENCE.search(t) and _RX_CONTRACT_LINKAGE.search(t))
        or _RX_SAME_STORE_STAFF_POS_REUSE.search(t)
    )


def has_autonomy_and_no_detriment_clause(full_text: str) -> bool:
    return bool(_RX_VOLUNTARY_PARTICIPATION_CLAUSE.search(full_text or ""))


def calibrate_dealer_act_applicability(
    result: dict[str, Any], full_text: str, legal_map_fields: dict[str, Any] | None,
) -> dict[str, Any]:
    """대리점법 결과 하나를 보정한다. 대리점법이 아닌 결과는 그대로 반환.
    floor만 적용한다 — 이미 이 값보다 높은 판단은 절대 낮추지 않는다."""
    if str(result.get("statute") or "") != "대리점법":
        return result
    existing_relationship = has_existing_dealer_relationship_signal(full_text, legal_map_fields)
    linkage = has_economic_operational_linkage_signal(full_text)
    if not (existing_relationship and linkage):
        return result

    current = _normalize_risk_level(result.get("risk_level"))
    floor = "MEDIUM"
    if _RISK_RANK[current] >= _RISK_RANK[floor]:
        return result

    has_autonomy_clause = has_autonomy_and_no_detriment_clause(full_text)
    out = dict(result)
    out["risk_level"] = floor
    out["applicability"] = "있음(추가 확인 필요)"
    note = (
        "[구조 보정] 기존 대리점(위탁판매)관계가 존재하고 이번 계약이 동일 매장·인력·POS 또는 "
        "계약기간·해지 연동으로 그 관계와 경제적·운영상 연계되어 있어, 상대방이 자기 명의로 "
        "재판매하지 않는다는 이유만으로 대리점법 적용을 배제할 수 없다(대리점법은 위탁판매 "
        "구조도 대상으로 한다)."
    )
    if not has_autonomy_clause:
        note += " 추가 업무 참여를 거절·종료할 경우 기존 대리점계약상 불이익이 없다는 조항이 확인되지 않아 주의가 필요하다."
    out["reasoning"] = (str(result.get("reasoning") or "").strip() + " " + note).strip()
    facts_needed = list(result.get("additional_facts_needed") or [])
    if not has_autonomy_clause:
        facts_needed = facts_needed + [
            "추가 업무 참여 거절/종료 시 기존 대리점계약상 불이익 여부",
            "추가 업무(인력·공간·비용 부담)에 대한 적정 보수 지급 여부",
        ]
    out["additional_facts_needed"] = facts_needed
    out["applicability_calibrated"] = "dealer_act_floor"
    return out


def calibrate_subcontract_act_applicability(result: dict[str, Any], full_text: str) -> dict[str, Any]:
    """하도급법 결과 하나를 보정한다. ceiling만 적용한다 — 단순 판매지원
    신호만 있고 실제 제조/설계/시공/수리 위탁 신호가 전혀 없으면 LOW로
    캡하고, 그 반대(규제대상 행위 신호가 있음)면 손대지 않는다. AI 미가동
    stub의 "확인 필요"도 이 경우에는 애매하게 남겨두지 않고 "낮음"으로
    확정한다 — 단순 판매지원만으로는 하도급법을 핵심 쟁점으로 보지
    않는다는 결론 자체가 이 계약유형의 정답이기 때문이다."""
    if str(result.get("statute") or "") != "하도급법":
        return result
    if _RX_SUBCONTRACT_REGULATED_ACTIVITY.search(full_text or ""):
        return result

    current = _normalize_risk_level(result.get("risk_level"))
    if current == "LOW":
        return result

    out = dict(result)
    out["risk_level"] = "LOW"
    out["applicability"] = "낮음"
    note = (
        "[구조 보정] 상담·전시·주문접수·결제대행·배송안내·재고관리 등 단순 판매지원 업무만 "
        "확인되고 제조·설계·시공·수리 위탁에 해당하는 규제대상 행위가 확인되지 않아, 하도급법을 "
        "핵심 적용법률로 보기는 어렵다. 별도의 제작·가공·전문용역 위탁이 추가되면 다시 판단한다."
    )
    out["reasoning"] = (str(result.get("reasoning") or "").strip() + " " + note).strip()
    out["applicability_calibrated"] = "subcontract_act_ceiling"
    return out


def calibrate_statute_applicability_results(
    results: list[dict[str, Any]], full_text: str, legal_map_fields: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """clause_level.py에서 build_mandatory_legal_applicability_review() 직후
    호출하는 진입점. 결과 리스트를 그대로 보정해 새 리스트로 반환한다."""
    out: list[dict[str, Any]] = []
    for r in results:
        if not isinstance(r, dict):
            out.append(r)
            continue
        r = calibrate_dealer_act_applicability(r, full_text, legal_map_fields)
        r = calibrate_subcontract_act_applicability(r, full_text)
        out.append(r)
    return out
