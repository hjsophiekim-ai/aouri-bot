"""Issue Triage — 무엇을 버리고, 무엇을 KEEP 하고, 무엇을 계약서에 넣을지 (2026-10-01 지시).

finding 을 바로 내보내지 않고 다섯으로 나눈다.

    MUST_FIX       체결 전 반드시 수정 (HIGH)
    SHOULD_FIX     수정하면 실무상 의미가 큰 권장사항 (MEDIUM)
    KEEP           현재 문구로 충분 — "문제 없음"을 명시적으로 판정한다
    FINANCE_CHECK  법무 수정이 아니라 재경·세무 확인사항
    DROP           가능성은 있으나 이 계약에서 실질 중요도가 낮음

최종 검토 결과에는 MUST/SHOULD 만 기본 노출한다. KEEP·재경 확인은 보고서의 별도
칸으로, DROP 은 기록만 남긴다.

판단 근거 — Materiality Score(0~2 × 5축, 지시 2항)
    purpose   사업 목적 달성에 영향
    money     금전손실 규모
    rights    IP·소유권·대금·당사자 등 핵심권리
    dispute   실제 분쟁 가능성 (공란·미선택·오기 > 불명확 > 세분화)
    gap       현재 문구의 보호 공백 (부재 > 불충분 > 미세조정)
  8~10 MUST · 5~7 SHOULD · 0~4 DROP

골든 답안 보호
    규칙·법률효과로 원문을 직접 확인한 finding 은 사용자가 확정한 판단(웹젠·그림닷컴·
    시험용역·공사도급 골든)이다. 점수는 **AI·기본효과·체크리스트 finding 의 등급을
    낮추는 데만** 쓴다. 등급을 올리지 않는다.

계약별 benchmark(한글날 3자 아트상품 협업계약, 팀원 판단 — 지시 17항)
    아티스트 권한보증 KEEP · 하자/A/S 책임경계 KEEP · 대금/로열티 구조 대부분 KEEP ·
    선급금 보증보험 DROP · 관할 DROP/LOW · Background IP SHOULD · 실물 소유권 SHOULD/MUST ·
    지원사업 상위기준 SHOULD · 일반 세무 디테일 FINANCE CHECK
"""
from __future__ import annotations

import re
from typing import Any

MUST_FIX = "MUST_FIX"
SHOULD_FIX = "SHOULD_FIX"
KEEP = "KEEP"
FINANCE_CHECK = "FINANCE_CHECK"
DROP = "DROP"

#: 지시 12항 — 사내변호사 우선순위(앞이 높다). 9~10위가 1~5위보다 높게 나오면 안 된다.
PRIORITY = (
    "legal_entity", "ip", "authority", "payment", "acceptance", "defect", "termination",
    "project", "confidentiality", "jurisdiction",
)
#: 최종 필터의 "핵심축" — 순위는 계약유형마다 다르지만(NDA 는 비밀유지가 1순위),
#: 관할·세무·기타 boilerplate 는 어느 계약에서도 핵심축이 아니다.
_CORE_AXES = frozenset(PRIORITY[:9])

_RX_STRONG_DISPUTE = re.compile(r"공란|선택되지|미선택|오기|모순|충돌|존재하지\s*않는|틀린\s*표현|비어\s*있")
_RX_WEAK_DISPUTE = re.compile(r"불명확|없음|미흡|누락|부재|규정되지|특정되지|명시되지|한정")
_RX_FINE_TUNING = re.compile(r"세분화|구체화|필수화|명확히\s*하면|보완하면|정비|문구\s*조정|미세")
_RX_ABSENCE = re.compile(r"없음|규정되지|공란|미선택|선택되지|누락|부재|존재하지\s*않")
_RX_PARTIAL = re.compile(r"불명확|미흡|불충분|한정|제한|일률")
_RX_MONEY_STRONG = re.compile(r"계약금액|대금[^.\n]{0,8}(?:미확정|공란)|무제한|상한\s*없|배수|전액")
_RX_MONEY = re.compile(r"대금|지급|정산|로열티|제작비|손해|배상|위약|지체상금|금전")


def _title(cr: dict[str, Any]) -> str:
    for d in cr.get("detected_issue_list") or []:
        if isinstance(d, dict) and str(d.get("issue_title") or "").strip():
            return str(d["issue_title"])
    return str(cr.get("issue_title") or cr.get("clause_title") or "")


def axis_of(cr: dict[str, Any], topic_key: str | None, relations: list[str]) -> str:
    """우선순위 축. 법률관계가 주제보다 정확하면 그것을 쓴다."""
    if cr.get("is_entity_name_correction") or "legal_entity" in relations:
        return "legal_entity"
    if "agency" in relations:
        return "authority"
    if {"ip_license", "derivative", "background_ip", "ip_assignment", "physical_ownership"} & set(relations):
        return "ip"
    if re.search(r"상위\s*(?:지원사업\s*)?협약|운영기준|운영지침", _title(cr)):
        return "project"
    if "defect_works" in relations or "defect_sale" in relations:
        return "defect"
    mapping = {"tax": "tax", "jurisdiction": "jurisdiction", "notice": "jurisdiction", "ip": "ip",
               "authority": "authority", "termination": "termination", "payment": "payment",
               "acceptance": "acceptance", "confidentiality": "confidentiality",
               "liability": "payment", "exclusivity": "payment", "prepayment_security": "payment"}
    return mapping.get(topic_key or "", "other")


def materiality(cr: dict[str, Any], axis: str, relations: list[str]) -> dict[str, int]:
    title = _title(cr)
    text = " ".join([title, str(cr.get("problem") or ""), str(cr.get("rewrite_reason") or "")])
    purpose = 2 if axis in PRIORITY[:4] else 1 if axis in _CORE_AXES else 0
    money = 2 if _RX_MONEY_STRONG.search(text) else 1 if _RX_MONEY.search(title) or axis == "payment" else 0
    rights = 2 if axis in ("legal_entity", "ip", "authority") or _RX_MONEY_STRONG.search(title) else (
        1 if axis in ("payment", "termination", "acceptance", "defect", "project") else 0)
    if _RX_STRONG_DISPUTE.search(text):
        dispute = 2
    elif _RX_FINE_TUNING.search(title):
        dispute = 0
    else:
        dispute = 1 if _RX_WEAK_DISPUTE.search(text) else 0
    if _RX_FINE_TUNING.search(title):
        gap = 0
    elif _RX_ABSENCE.search(title) or _RX_STRONG_DISPUTE.search(title):
        gap = 2
    else:
        gap = 1 if _RX_PARTIAL.search(text) else 0
    return {"purpose": purpose, "money": money, "rights": rights, "dispute": dispute, "gap": gap}


def is_protected(cr: dict[str, Any]) -> bool:
    """원문을 규칙으로 직접 확인한 finding — 점수로 등급을 내리지 않는다(골든 답안)."""
    if cr.get("is_entity_name_correction") or str(cr.get("clause_id") or "").startswith("ac_"):
        # ac_* 는 원문 문언을 정규식으로 확인한 법률효과 점검이다(authority_selection_checks).
        return True
    if cr.get("is_risk_package"):
        # 리스크 사슬은 계약 전체의 법률효과로 판정한 결과다(대물교환 선이행이 원 사례) —
        # 등급은 effect_risk_package 가 거래 원형으로 이미 정한다.
        return True
    # 점수로 등급을 내리는 대상은 AI 논점·범용 기본효과·범용 용역 템플릿뿐이다. 계약유형별
    # 체크리스트(tsr_ 시험용역, CWC 공사, sppc 공급자 보호 등)는 골든 답안이 확인한 축이다.
    generated = (
        cr.get("is_counsel_agent") or cr.get("is_effect_baseline")
        or str(cr.get("clause_id") or "").startswith(("svc_", "eb_"))
    )
    return not generated


# ── KEEP: 이미 보호되는 내용 (지시 4·15항) ────────────────────────────────────

_RX_AUTH_CONFIRM = re.compile(r"권한을?\s*위임받았음을\s*확인|대리권|권한을?\s*(?:적법하게\s*)?확보")
_RX_AUTH_WARRANT = re.compile(r"(?:동의|권한)[^.\n]{0,40}보증한다|보증한다")
_RX_AUTH_LIABILITY = re.compile(r"(?:권한\s*부재|권리관계의?\s*하자)[^.]{0,120}(?:해결|부담|배상)")
_RX_DEFECT_CLAUSE = re.compile(r"하자|A/S|보수")
_RX_DEFECT_BOUNDARY = re.compile(r"귀책|책임\s*(?:범위|경계)|구분|부담한다")
_RX_SETTLEMENT_CONCRETE = re.compile(r"월별\s*정산|다음\s*달\s*말일|익월|산정\s*(?:기준|내역)|×\s*\d+\s*%|정산\s*(?:주기|기준)")


def keep_reason(cr: dict[str, Any], axis: str, text: str, article_text: str) -> str:
    """이미 다른 조항(또는 같은 조)이 같은 보호효과를 주면 그 사유. 아니면 ""."""
    title = _title(cr)
    if axis == "authority":
        if _RX_AUTH_CONFIRM.search(article_text) and _RX_AUTH_WARRANT.search(article_text) \
                and _RX_AUTH_LIABILITY.search(article_text):
            return ("권한 확인·권리 보증·권한 하자 시 책임이 이미 같은 조에 규정되어 있다 — "
                    "추가 보증조항을 신설할 실익이 낮다")
    if axis == "defect" and _RX_DEFECT_CLAUSE.search(article_text) and _RX_DEFECT_BOUNDARY.search(article_text):
        return "하자·A/S 책임의 귀속과 경계가 이미 규정되어 있다"
    if axis == "payment" and re.search(r"정산|증빙|산정|양식|세금계산서", title) \
            and not _RX_MONEY_STRONG.search(title) and _RX_SETTLEMENT_CONCRETE.search(text):
        return "정산 주기·기한·산정 기준이 이미 구체적이다 — 정산 실무 세부는 계약 수정 사항이 아니다"
    return ""


def triage_one(
    cr: dict[str, Any],
    *,
    axis: str,
    relations: list[str],
    contract_text: str,
    article_text: str,
) -> tuple[str, str, dict[str, int]]:
    tier = str(cr.get("risk_tier") or "").upper()
    scores = materiality(cr, axis, relations)
    total = sum(scores.values())
    if cr.get("is_entity_name_correction"):
        return SHOULD_FIX if tier != "HIGH" else MUST_FIX, "법적 당사자 표기 — 서명 전 정정", scores
    if axis == "tax":
        return FINANCE_CHECK, "세금계산서·부가세·원천징수는 계약 효력에 직접 영향이 없는 재경·세무 확인사항", scores
    if axis == "jurisdiction" or cr.get("boilerplate_low_priority"):
        return DROP, "국내 법인 간 관할·통지 등 일반 boilerplate", scores
    # ac_* 결정론 점검은 이미 "현행 문언으로 부족한 경우"에만 만들어진다 — 정산 세부 KEEP 규칙이
    # 결제창 Case A/B 정리까지 KEEP 으로 덮지 않게 한다.
    kr = "" if str(cr.get("clause_id") or "").startswith("ac_") else keep_reason(
        cr, axis, contract_text, article_text)
    if kr:
        return KEEP, kr, scores
    if is_protected(cr):
        return (MUST_FIX if tier == "HIGH" else SHOULD_FIX if tier == "MEDIUM" else DROP), "", scores
    # 생성형 finding — 점수와 최종 필터(지시 16항)로 판단한다. 등급은 올리지 않는다.
    if re.search(r"배상\s*(?:책임\s*)?(?:상한|한도)|책임\s*(?:상한|한도)", _title(cr)):
        # 와이어드 지시 10항 — 상한을 둘지·얼마로 할지는 거래 규모를 보고 사업부가 정한다.
        # 법무 판단(어떤 책임을 상한에서 뺄지)은 요청 답변의 최소수정문구로 낸다.
        return FINANCE_CHECK, "손해배상 상한 금액·기준은 거래 규모를 본 사업부 결정 사항", scores
    has_redline = bool(str(cr.get("suggested_rewrite") or "").strip())
    yes = sum([
        scores["money"] + scores["rights"] > 0,      # 실제 손실 가능성
        True,                                       # 다른 조항으로 이미 해결되지 않음(KEEP 아님)
        True,                                       # 우리에게 불리한 수정안은 감사가 이미 걸렀다
        axis in _CORE_AXES,                         # 계약유형 핵심축
        has_redline,                                # 바로 넣을 문구가 있다
    ])
    if yes < 4:
        return DROP, "최종 필터 미통과(실익·핵심축·삽입 문구 중 둘 이상 부족)", scores
    if total >= 8:
        band = MUST_FIX
    elif total >= 5:
        band = SHOULD_FIX
    else:
        return DROP, f"중요도 점수 {total}/10 — 실질 중요도 낮음", scores
    if band == MUST_FIX and tier != "HIGH":
        band = SHOULD_FIX  # 점수로 올리지 않는다
    return band, f"중요도 점수 {total}/10", scores


__all__ = [
    "DROP", "FINANCE_CHECK", "KEEP", "MUST_FIX", "PRIORITY", "SHOULD_FIX",
    "axis_of", "is_protected", "keep_reason", "materiality", "triage_one",
]
