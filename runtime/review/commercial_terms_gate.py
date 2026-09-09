"""핵심 상업조건 확정 여부 검사 (2026-09-09 지시 항목 9).

시니어 사내변호사는 독소조항을 찾기 전에 **계약의 뼈대가 채워져 있는지**를
먼저 본다. 금액·기간·지급시기가 비어 있으면 그 계약은 조항 문구를 다듬을
단계가 아니다.

실측 사례(호텔 신축 공사도급계약 갑지):

    3. 착 공 일   : 금융기표일                     ← 외부조건 연동
    4. 준공 예정일 : 실착공일로부터 [ ] 개월         ← 공란
    5. 계 약 금 액 : 일금       정 (\\        원)   ← 공란
    13. 지체 상금률 : 총계약금액 1/1,000(계약금액의 10%이내)

계약금액이 공란인데 지체상금·계약이행보증·하자보증이 모두 "계약금액의 N%"로
정의되어 있다 — **금전 리스크 전부가 미확정**이다. 이것이 이 계약의 최대
리스크인데, 조항 단위 키워드 탐지기는 이를 통째로 놓친다(조항 문구 자체에는
문제가 없기 때문이다).

설계: 특정 계약서를 하드코딩하지 않는다. 계약유형군별로 "이 유형이라면
반드시 확정되어야 하는 항목"을 정의하고, 라벨을 찾아 그 뒤의 값이 실제
수치인지 / 공란인지 / 외부조건에 연동됐는지를 판정한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

STATUS_PRESENT = "확정"
STATUS_BLANK = "공란"
STATUS_EXTERNAL = "외부조건 연동"
STATUS_ABSENT = "항목 없음"

REVIEW_STATUS_TERMS_UNSETTLED = "REVIEW_FAILED_COMMERCIAL_TERMS_UNSETTLED"


@dataclass(frozen=True)
class EssentialTerm:
    key: str
    label: str
    #: 라벨을 찾는 패턴 (계약서마다 표기가 달라 여러 개를 허용)
    label_pattern: re.Pattern[str]
    #: 값이 "확정됐다"고 보기 위해 필요한 최소 신호
    value_pattern: re.Pattern[str]
    #: 이 항목이 비면 계약 체결 여부에 영향을 주는가 (HIGH) — 아니면 사실확인
    blocking: bool = True


def _p(*alts: str) -> re.Pattern[str]:
    return re.compile("|".join(alts), re.IGNORECASE)


#: 값이 비어 있다는 신호. 계약서 서식은 공란을 여러 방식으로 표현한다.
_RX_BLANK_VALUE = _p(
    r"\[\s*\]", r"\[\s+\]", r"（\s*）", r"\(\s*\)",
    r"일금\s*정", r"일금\s{2,}정",
    r"[₩\\]\s*(?:원|정)", r"[₩\\]\s{2,}",
    r"_{2,}", r"…{2,}", r"\.{4,}",
    r"○{2,}", r"[Oo]{3,}",
)

#: 확정된 수치·날짜 신호.
_RX_CONCRETE_NUMBER = re.compile(r"\d")
_RX_CONCRETE_DATE = _p(
    r"\d{4}\s*[.\-년]\s*\d{1,2}\s*[.\-월]\s*\d{1,2}",
    r"\d{1,2}\s*개?\s*월", r"\d{1,3}\s*일", r"\d{1,4}\s*년",
)
_RX_CONCRETE_AMOUNT = _p(
    r"\d{1,3}(?:,\d{3})+", r"\d+\s*(?:억|천만|백만|만)\s*원", r"[₩\\]\s*\d",
    r"\d+\s*원",
)
_RX_CONCRETE_RATE = _p(r"\d+(?:\.\d+)?\s*%", r"\d+\s*/\s*\d+", r"\d+\s*분의\s*\d+")

#: 시점이 계약 외부의 사건에 매여 있다는 신호 — 날짜가 확정되지 않은 것과
#: 실질이 같지만, 원인이 달라 별도 상태로 구분한다(협상 포인트가 다르다).
_RX_EXTERNAL_CONDITION = _p(
    r"금융\s*기표", r"대출\s*실행", r"기표일", r"인허가\s*(?:완료|취득)",
    r"승인\s*(?:후|일)", r"착공\s*지시", r"별도\s*통보", r"협의(?:하여|후)\s*정",
    r"추후\s*협의", r"쌍방\s*합의(?:하여|로)\s*정",
)

_ESSENTIAL_TERMS: tuple[EssentialTerm, ...] = (
    EssentialTerm(
        "contract_amount", "계약금액",
        _p(r"계\s*약\s*금\s*액", r"도급\s*금액", r"공사\s*금액", r"총\s*계약\s*금액"),
        _RX_CONCRETE_AMOUNT,
    ),
    EssentialTerm(
        "start_date", "착공일/개시일",
        _p(r"착\s*공\s*일", r"개\s*시\s*일", r"계약\s*개시"),
        _RX_CONCRETE_DATE,
    ),
    EssentialTerm(
        "completion_date", "준공일/완료일",
        _p(r"준\s*공\s*(?:예정)?\s*일", r"완\s*료\s*일", r"납\s*품\s*기\s*일"),
        _RX_CONCRETE_DATE,
    ),
    EssentialTerm(
        # 준공일과 실질이 겹친다(둘 중 하나만 확정돼도 이행 기준이 생긴다).
        # 그래서 blocking=False — 중복 HIGH 를 만들지 않는다.
        "duration", "공사기간/계약기간",
        _p(r"공\s*사\s*기\s*간", r"계\s*약\s*기\s*간", r"용\s*역\s*기\s*간"),
        _RX_CONCRETE_DATE,
        blocking=False,
    ),
    EssentialTerm(
        "payment_schedule", "지급시기",
        _p(r"기\s*성\s*금", r"정\s*산\s*금", r"지\s*급\s*시\s*기", r"대\s*금\s*지\s*급"),
        _RX_CONCRETE_DATE,
        blocking=False,
    ),
    EssentialTerm(
        "performance_bond", "계약이행보증",
        _p(r"계약\s*이행\s*보증", r"이행\s*보증(?:금|서)?"),
        _RX_CONCRETE_RATE,
        blocking=False,
    ),
    EssentialTerm(
        "warranty_bond", "하자담보책임",
        _p(r"하자\s*담보", r"하자\s*보수\s*보증"),
        _RX_CONCRETE_RATE,
        blocking=False,
    ),
)

#: 계약유형군 → 그 유형에서 필수인 항목 key. 특정 계약서가 아니라 **유형**
#: 기준이므로 처음 보는 계약서에도 적용된다.
_TERMS_BY_FAMILY: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("construction", "works", "공사", "도급", "installation", "설치"),
        ("contract_amount", "start_date", "completion_date", "duration",
         "payment_schedule", "performance_bond", "warranty_bond"),
    ),
    (
        ("supply", "purchase", "물품", "구매", "공급"),
        ("contract_amount", "completion_date", "payment_schedule"),
    ),
    (
        ("development", "service", "용역", "개발", "outsourcing"),
        ("contract_amount", "start_date", "completion_date", "payment_schedule"),
    ),
    (
        ("rental", "lease", "렌탈", "임대"),
        ("contract_amount", "start_date", "duration", "payment_schedule"),
    ),
)

#: NDA 등 금전 급부가 없는 계약군은 이 게이트의 대상이 아니다 — 계약금액이
#: 없는 것이 정상이므로 검사하면 전부 오탐이 된다.
_EXEMPT_FAMILIES: tuple[str, ...] = (
    "nda", "confidential", "비밀유지", "mou", "loi", "letter_of_intent",
)


#: 일시금 계약금액 대신 **요율·단가**로 대가를 정하는 구조. 판매수수료·
#: 정률 용역료 계약에는 총액이 없는 것이 정상이므로, 이런 구조가 확인되면
#: 계약금액 공란을 리스크로 보지 않는다(실측 오탐: 판매지원 용역계약의
#: "판매금액의 10%를 용역수수료로 지급" — 총액이 없는 것이 계약의 설계다).
_RX_RATE_BASED_CONSIDERATION = _p(
    r"(?:수수료|용역료|보수|대가)[^.\n]{0,30}?\d+(?:\.\d+)?\s*%",
    r"\d+(?:\.\d+)?\s*%[^.\n]{0,20}?(?:수수료|용역료|보수)",
    r"수수료율|요율|단가[^.\n]{0,20}?(?:표|기준)",
    r"commission[^.\n]{0,30}?\d+(?:\.\d+)?\s*%",
    r"(?:판매|결제)\s*금액의\s*\d+",
)


def has_rate_based_consideration(text: str) -> bool:
    """총액 대신 요율로 대가를 정하는 구조인지."""
    return bool(_RX_RATE_BASED_CONSIDERATION.search(text or ""))


def _terms_for(contract_type_code: str) -> tuple[EssentialTerm, ...]:
    code = str(contract_type_code or "").strip().lower()
    if any(x in code for x in _EXEMPT_FAMILIES):
        return ()
    keys: tuple[str, ...] = ()
    for needles, ks in _TERMS_BY_FAMILY:
        if any(n in code for n in needles):
            keys = ks
            break
    if not keys:
        # 유형을 특정하지 못하면 금전 계약의 최소 공통 항목만 본다.
        keys = ("contract_amount", "payment_schedule")
    return tuple(t for t in _ESSENTIAL_TERMS if t.key in keys)


def _value_window(text: str, m: re.Match[str]) -> str:
    """라벨 뒤에서 값이 적히는 범위. 줄바꿈 1회까지만 따라간다 —
    다음 항목까지 넘어가면 옆 항목의 숫자를 자기 값으로 착각한다."""
    start = m.end()
    seg = text[start:start + 90]
    # 다음 번호 항목("6. ", "제7조")이 시작되면 거기서 끊는다.
    cut = re.search(r"\n\s*(?:\d{1,2}\s*[.)]|제\s*\d+\s*조)", seg)
    if cut:
        seg = seg[: cut.start()]
    return seg


#: "○○일로부터 14일 이내" 처럼 **기준사건 + 확정된 기간**은 정상적인 상업조건이다.
#: 이것을 외부조건 미확정으로 보면 건설·납품계약의 표준 지급조건이 전부 오탐이 된다.
_RX_BOUNDED_PERIOD = re.compile(
    r"\d+\s*(?:일|영업일|개월|주)\s*(?:이내|이후|안에|내에|전까지)"
)

_STATUS_RANK = {STATUS_PRESENT: 0, STATUS_EXTERNAL: 1, STATUS_BLANK: 2, STATUS_ABSENT: 3}


def _classify_window(term: EssentialTerm, window: str) -> str:
    # 확정 판정을 **먼저** 한다. 기준사건을 참조하더라도 기간이 확정돼 있으면
    # 그것은 확정된 조건이다("사용승인일로부터 14일 이내 지급").
    if term.value_pattern.search(window) or _RX_BOUNDED_PERIOD.search(window):
        return STATUS_PRESENT
    if _RX_EXTERNAL_CONDITION.search(window):
        return STATUS_EXTERNAL
    if _RX_BLANK_VALUE.search(window) or not _RX_CONCRETE_NUMBER.search(window):
        return STATUS_BLANK
    return STATUS_PRESENT


#: 라벨 직후의 콜론 — 이 항목의 **값을 정의하는** 자리라는 신호.
#: 갑지(계약조건 요약표)와 정의 문장은 모두 "계 약 금 액 : …" 형태다.
#: 라벨과 콜론 사이에 접미어가 붙는 경우("하자담보**책임** :", "지체상금**률** :")가
#: 있어 라벨 문자(한글·영문·공백)만 최대 8자까지 허용한다. 숫자·기호가 끼면
#: 참조문("계약금액의 10% …")이므로 정의문으로 보지 않는다.
_RX_DEFINITION_COLON = re.compile(r"^[가-힣A-Za-z\s]{0,8}[:：]")


def scan_commercial_terms(
    text: str, *, contract_type_code: str = "",
) -> list[dict[str, Any]]:
    """핵심 상업조건별 확정 상태를 반환한다.

    라벨은 계약서 여러 곳에 나온다. 중요한 구분은 **정의문과 참조문**이다:

        5. 계 약 금 액 : 일금    정 (\\    원)      ← 정의문 (값이 공란)
        계약이행보증 : 계약금액의 10% 현금            ← 참조문 (금액을 인용)

    참조문에는 숫자가 있으니 "가장 확정적인 출현"을 취하면 공란인 정의문이
    가려진다. 그래서 정의문(라벨 직후 콜론)만 판정 대상으로 삼고, 정의문이
    없으면 본문 산문으로 추측하지 않고 '항목 없음'으로 둔다.
    """
    hay = text or ""
    rows: list[dict[str, Any]] = []
    for term in _terms_for(contract_type_code):
        chosen: tuple[str, str] | None = None
        for m in term.label_pattern.finditer(hay):
            tail = hay[m.end():m.end() + 6]
            if not _RX_DEFINITION_COLON.match(tail):
                continue  # 참조문 — 값을 정의하는 자리가 아니다
            window = _value_window(hay, m)
            status = _classify_window(term, window)
            evidence = re.sub(r"\s+", " ", (m.group(0) + window)).strip()[:120]
            chosen = (status, evidence)
            break  # 첫 정의문(통상 갑지)이 그 항목의 값이다
        if chosen is None:
            if term.key == "contract_amount" and has_rate_based_consideration(hay):
                rows.append({
                    "key": term.key, "label": term.label, "status": STATUS_PRESENT,
                    "blocking": term.blocking,
                    "evidence": "요율 기반 대가 구조 — 총액 대신 수수료율로 정함",
                })
                continue
            rows.append({
                "key": term.key, "label": term.label, "status": STATUS_ABSENT,
                "blocking": term.blocking, "evidence": "",
            })
            continue
        rows.append({
            "key": term.key, "label": term.label, "status": chosen[0],
            "blocking": term.blocking, "evidence": chosen[1],
        })
    return rows


def unsettled_terms(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """finding 대상 = **공란**과 **외부조건 연동**만.

    STATUS_ABSENT("항목 없음")은 제외한다. 정의문을 못 찾았다는 뜻일 뿐,
    산문형 계약서에서는 흔한 일이라 이것까지 지적하면 노이즈가 된다.
    지시 항목 9 가 든 예시도 전부 공란·외부조건이다("[ ]개월, 금액 미기재,
    외부조건에 연동된 착공일"). 실측 오탐: 판매지원 용역계약에서 착공일·
    준공일 '항목 없음'으로 HIGH 가 생성됐다.
    """
    return [
        r for r in (rows or [])
        if str(r.get("status")) in (STATUS_BLANK, STATUS_EXTERNAL)
    ]


#: 갑지 항목은 조문이 아니라 표지의 기입란이다. 수정 위치를 "표지 항목"으로
#: 명시해야 지시 항목 10(수정 위치·방식·원문·문구·이유)을 만족하고,
#: REVIEW_FAILED_INCOMPLETE_REDLINE 게이트도 통과한다.
def _redline_for(*, label: str, evidence: str, replacement: str, reason: str) -> dict[str, Any]:
    original = (evidence or f"({label} 항목)").strip()
    return {
        "edit_location": f"계약서 표지(갑지) — {label} 기입란",
        "edit_type": "replace",
        "target_text": original,
        "replacement_text": replacement,
        "final_clause_text": replacement,
        "reason": reason,
    }


def build_commercial_terms_findings(
    text: str,
    *,
    contract_type_code: str = "",
    our_party: str = "우리 회사",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """미확정 상업조건을 finding 으로 만든다. 반환: (findings, rows)

    blocking 항목이 비면 HIGH — "계약 체결 여부에 영향을 주는 수준"(항목 7)에
    정확히 해당한다. 금액이 미확정이면 그 금액에 연동된 지체상금·보증금·
    하자보증의 실제 노출 규모를 산정할 수 없기 때문이다.
    """
    rows = scan_commercial_terms(text, contract_type_code=contract_type_code)
    bad = unsettled_terms(rows)
    # 공사기간은 준공일과 같은 이행 기준 축이다 — 준공일 항목이 이미
    # 보고되므로(확정이든 공란이든) 공사기간을 따로 지적하지 않는다.
    if any(r["key"] == "completion_date" for r in rows):
        bad = [r for r in bad if r["key"] != "duration"]
    if not bad:
        return [], rows

    findings: list[dict[str, Any]] = []

    # 금액 미확정은 다른 모든 금전조항의 전제이므로 하나로 묶어 최우선 제시한다.
    amount = next((r for r in bad if r["key"] == "contract_amount"), None)
    linked = [
        r["label"] for r in rows
        if r["key"] in ("performance_bond", "warranty_bond") and r["status"] == STATUS_PRESENT
    ]
    if amount is not None:
        reason = (
            f"계약금액이 '{amount['status']}' 상태다. "
            + (
                f"그런데 {', '.join(linked)}이(가) 모두 '계약금액의 N%'로 정의되어 있어, "
                "계약금액이 확정되지 않으면 이들 금전 노출의 실제 규모를 산정할 수 없다. "
                if linked else ""
            )
            + "지체상금·보증금·손해배상 상한이 모두 계약금액에 연동되는 구조에서는 "
            "금액 미확정 자체가 최대 리스크다."
        )
        findings.append({
            "clause_id": "ct_contract_amount_unsettled",
            "display_path": "계약서 표지(갑지)",
            "article_number": None,
            "risk_tier": "HIGH",
            "severity": "HIGH",
            "issue_title": "계약금액이 확정되지 않음 — 연동된 금전 노출 전부가 미확정",
            "clause_title": "계약서 표지(갑지) [계약금액 미확정]",
            "original_text": amount["evidence"] or "(계약금액 항목)",
            "problem": "계약의 핵심 급부 대가가 공란이다.",
            "rewrite_reason": reason,
            "legal_business_reason": reason,
            "suggested_rewrite": (
                "계약금액: 일금 ○○○원(₩000,000,000, 부가가치세 별도)\n"
                "— 서명 전 확정 필수. 확정이 어려우면 최소한 산정 기준(내역서·단가·"
                "물량 기준일)과 확정 시점, 확정 전까지 지체상금·보증금 산정의 기준이 "
                "되는 잠정금액을 명시한다."
            ),
            "negotiation_position": (
                "금액 확정 없이는 서명 불가. 확정이 지연되면 '금액 확정 시까지 "
                "지체상금·보증금 조항의 효력을 정지'하는 단서를 요구한다."
            ),
            "commercial_term_key": "contract_amount",
            "is_commercial_terms_finding": True,
            "redline_instruction": _redline_for(
                label=amount["label"], evidence=amount["evidence"],
                replacement=(
                    "계약금액: 일금 ○○○원(₩000,000,000, 부가가치세 별도) "
                    "— 서명 전 확정. 확정 전이면 산정 기준(내역서·단가·물량 기준일)과 "
                    "확정 시점, 확정 전까지의 잠정금액을 함께 명시한다."
                ),
                reason=reason,
            ),
        })

    others = [r for r in bad if r["key"] != "contract_amount"]
    for r in others:
        blocking = bool(r.get("blocking"))
        if r["status"] == STATUS_EXTERNAL:
            reason = (
                f"{r['label']}이(가) 계약 외부의 사건에 연동되어 있어 시점이 확정되지 않는다. "
                "그 사건이 발생하지 않으면 우리 회사의 이행 의무와 지체 판단 기준이 "
                "모두 불확정 상태로 남는다."
            )
            rewrite = (
                f"{r['label']}: 구체적 일자로 특정한다. 외부조건에 연동해야 한다면 "
                "① 그 조건의 최장 대기기간(예: 계약체결일로부터 ○개월), "
                "② 기간 내 미충족 시 각 당사자의 해지권과 정산 방법, "
                "③ 그 기간 동안 발생한 비용의 부담 주체를 함께 정한다."
            )
        elif r["status"] == STATUS_BLANK:
            reason = f"{r['label']}이(가) 공란이다. 이행 기준과 지체 판단의 출발점이 없다."
            rewrite = f"{r['label']}: 구체적 일자·기간·금액으로 특정한다."
        else:
            reason = (
                f"{r['label']}에 관한 규정을 계약에서 찾지 못했다. "
                "이 계약유형에서는 통상 명시되는 항목이므로 누락 여부를 확인해야 한다."
            )
            rewrite = f"{r['label']} 조항을 신설한다."
        findings.append({
            "clause_id": f"ct_{r['key']}_unsettled",
            "display_path": "계약서 표지(갑지)" if r["status"] != STATUS_ABSENT else None,
            "article_number": None,
            "risk_tier": "HIGH" if blocking else "MEDIUM",
            "severity": "HIGH" if blocking else "MEDIUM",
            "issue_title": f"{r['label']} {r['status']}",
            "clause_title": f"계약서 표지(갑지) [{r['label']} {r['status']}]",
            "original_text": r["evidence"] or f"({r['label']} 항목)",
            "problem": f"{r['label']}이(가) {r['status']} 상태다.",
            "rewrite_reason": reason,
            "legal_business_reason": reason,
            "suggested_rewrite": rewrite,
            "negotiation_position": (
                "핵심 상업조건이므로 문구 협상보다 먼저 확정한다. "
                "확정 전 서명이 불가피하면 미확정 항목에 연동된 제재조항(지체상금·"
                "보증금 몰취)의 효력 발생 시점을 확정 이후로 미루도록 요구한다."
            ),
            "commercial_term_key": r["key"],
            "is_commercial_terms_finding": True,
            "redline_instruction": _redline_for(
                label=r["label"], evidence=r["evidence"],
                replacement=rewrite, reason=reason,
            ),
        })
    return findings, rows
