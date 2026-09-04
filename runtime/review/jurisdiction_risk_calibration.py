"""관할/준거법/중재 리스크 과대평가 방지(2026-09-04 지시).

아우리봇이 관할·준거법·중재 조항을 "있느냐 없느냐"만으로 판단해 지나치게
자주 HIGH를 매기던 문제를 구조적으로 고친다. 이 조항 자체는 대부분의
계약에서 정상적으로 존재하는 절차적 조항이며, 우리 회사에 실제로 중대한
영향을 주는 경우(불리한 해외관할·낯선 외국법으로 인한 비용/집행 리스크·
비대칭 관할·상충되는 복수 조항·실제 집행곤란성)에만 검토 대상이 되어야
한다.

`severity_reclassifier.py::demote_adequate_governing_law_dispute_clause`와
다른 축이다 — 그 함수는 "이 조항 자체"가 이미 완결돼 있는지만 본다. 이
모듈은 계약 전체 텍스트를 검색해 실제 준거법/분쟁해결 구조(국내법인지,
국내법원·서울중재인지, 비대칭인지, 여러 조항이 서로 다른 나라를
지정하는지)를 판정하고, 그 결과로 이 finding의 severity 상한을 계산한다 —
새 finding을 만들지 않고, 오직 이미 존재하는 finding의 severity를
"낮추기만"(never upgrade) 한다.
"""
from __future__ import annotations

import re

_SEV_RANK: dict[str, int] = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}

# 계약서 템플릿은 흔히 채워넣을 자리를 대괄호로 표시한다(예: "governed by
# the laws of [Republic of Korea]", "arbitration in [Seoul]") — 대괄호가
# "of"/"in"과 국가·도시명 사이에 끼어들면 아래 정규식들이 매치에 실패하므로,
# 판정 전에 대괄호만 제거한 사본으로 검사한다(실질 문언은 그대로 유지).
def _strip_placeholder_brackets(text: str) -> str:
    return re.sub(r"[\[\]]", "", text or "")

# 이 finding이 실제로 준거법/관할/중재를 다루는지 판정하는 주제 마커 —
# clause_title/rewrite_reason/legal_business_reason(무엇을 문제삼는지 서술한
# 필드)와 clause_text(원문) 양쪽에서 확인한다.
JURISDICTION_TOPIC_MARKER = re.compile(
    r"준거법|관할|중재|governing\s+law|jurisdiction|arbitration|dispute\s+resolution",
    re.IGNORECASE,
)

# 대한민국을 준거법으로 명시하는 문장 — 한국어/영어 공통.
_RX_KOREAN_GOVERNING_LAW = re.compile(
    r"준거법[은는이가]?\s*[\S ]{0,15}(?:대한민국|한국)\s*(?:법|법률)"
    r"|governed\s+(?:and\s+interpreted\s+)?by\s+the\s+laws?\s+of\s+(?:the\s+)?(?:republic\s+of\s+)?korea",
    re.IGNORECASE,
)

# 준거법 지정 문장이 존재하는지(국가 무관) — 어느 나라 법인지는 위
# _RX_KOREAN_GOVERNING_LAW와 대조해서 판단한다.
_RX_HAS_GOVERNING_LAW = re.compile(
    r"준거법[은는이가]?\s*[\S ]{0,20}(?:법|법률)(?:으로|을|를)?\s*(?:한다|정한다|지정한다)"
    r"|governed\s+(?:and\s+interpreted\s+)?by\s+the\s+laws?\s+of"
    r"|이\s*계약(?:서)?은\s*[\S ]{0,20}법(?:을|에)\s*따(?:라|른다)",
    re.IGNORECASE,
)

# 국내(서울) 법원/중재로 특정되는 문장, 또는 당사자 간 합의관할·통상적인
# 중재조항(중재기관·규칙에 따른 해결) — 이런 문구만 있으면 기본적으로
# 문제삼지 않는다.
_RX_DOMESTIC_FORUM = re.compile(
    r"(?:서울|대한민국|한국)[\S ]{0,15}(?:법원|중재)"
    r"|(?:법원|중재)[\S ]{0,15}(?:서울|대한민국|한국)"
    r"|arbitration.{0,20}(?:in\s+seoul)|seoul.{0,20}arbitration",
    re.IGNORECASE,
)
_RX_MUTUAL_AGREED_JURISDICTION = re.compile(
    r"합의\s*관할|양\s*당사자.{0,15}합의(?:한|하는)?\s*(?:법원|관할)",
)
_RX_ORDINARY_ARBITRATION = re.compile(
    r"중재(?:규칙|절차)?[\S ]{0,20}(?:에\s*따라|의하여)\s*(?:중재로?)?\s*(?:해결|진행)"
    r"|대한상사중재원|KCAB|ICC\s+(?:arbitration|rules)|SIAC|arbitration\s+rules",
    re.IGNORECASE,
)

# 분쟁해결 메커니즘(중재/관할법원)이 존재하는지 여부 — 국가 무관.
_RX_HAS_DISPUTE_MECHANISM = re.compile(
    r"중재(?:에\s*의하여|로)\s*(?:최종\s*)?해결"
    r"|관할\s*법원(?:은|으로)\s*[\S ]{0,20}(?:로|으로)\s*한다"
    r"|settled\s+by\s+arbitration|final(?:ly)?\s+settled\s+by\s+arbitration"
    r"|exclusive\s+jurisdiction",
    re.IGNORECASE,
)

# ── 예외(캡을 걸지 않고 상위 severity를 그대로 인정) 신호 4가지 ──────────
# 1) 비대칭 관할 — 일방 당사자에게만 관할/중재 선택권이 있다.
_RX_ASYMMETRIC_FORUM = re.compile(
    r"(?:갑|을)\s*(?:만|에게만)\s*[\S ]{0,15}(?:관할|중재|법원)[\S ]{0,10}(?:선택|지정)할?\s*수\s*있"
    r"|(?:갑|을)[\"'“”]?\s*(?:의)?\s*(?:본점\s*)?소재지(?:를)?\s*관할(?:하는)?\s*법원"
    r"|only\s+[A-Z][\w\s]{1,30}\s+may\s+(?:bring|initiate|commence)\s+(?:suit|proceedings|action)"
    r"|at\s+the\s+sole\s+discretion\s+of\s+(?:only\s+)?(?:one\s+party|[A-Z][\w]+)\b",
    re.IGNORECASE,
)
# 2) 복수의 상충되는 관할/준거법/중재 조항 — 함수 본문에서 별도 계산.
# 3) 실제 집행 곤란성 — 승인/집행 거부, 상호주의 부재 등 명시적 신호.
_RX_ENFORCEMENT_DIFFICULTY = re.compile(
    r"집행(?:이|을)?\s*(?:곤란|어렵|불가능)|승인\s*(?:및|·)?\s*집행.{0,10}(?:곤란|거부)"
    r"|no\s+reciprocal\s+enforcement|difficult\s+to\s+enforce"
    r"|non[- ]recognition\s+of\s+(?:foreign\s+)?judgment(?:s)?"
    r"|not\s+(?:be\s+)?recognized\s+or\s+enforced",
    re.IGNORECASE,
)
# 4) 낯선 외국법/해외관할로 인한 중대한 비용·소송상 불리함이 명시적으로
#    서술된 경우 — 외국관할이라는 사실만으로는 부족하고, 실제로 불리하다는
#    신호가 함께 있어야 한다.
_RX_ADVERSE_FOREIGN_LITIGATION = re.compile(
    r"매우\s*불리|현저히\s*불리|극히\s*불리|소송\s*비용이?\s*(?:막대|과다|현저)"
    r"|prohibitively\s+(?:expensive|costly)|unduly\s+burdensome"
    r"|significant(?:ly)?\s+(?:litigation|legal)\s+costs?",
    re.IGNORECASE,
)

# 준거법 지정 문장에서 국가명을 뽑아 서로 다른 나라를 지정하는 조항이
# 2개 이상이면 "상충되는 복수 조항"으로 본다.
_RX_GOVERNING_LAW_COUNTRY = re.compile(
    r"governed\s+(?:and\s+interpreted\s+)?by\s+the\s+laws?\s+of\s+(?:the\s+)?([A-Za-z][A-Za-z\s]{2,30}?)(?=[,.;\n]|$)"
    r"|준거법[은는이가]?\s*[\S ]{0,10}?([가-힣]{2,10})\s*(?:법|법률)(?:으로|을|를)?\s*(?:한다|정한다|지정한다)",
    re.IGNORECASE,
)
_RX_ARBITRATION_SEAT = re.compile(
    r"arbitration\s+in\s+([A-Za-z][A-Za-z\s]{2,20})"
    r"|중재\s*(?:는|은)?[\S ]{0,10}?([가-힣]{2,10})(?:에서)\s*(?:진행|개최|한다)",
    re.IGNORECASE,
)


def _has_conflicting_jurisdiction_clauses(full_text: str) -> bool:
    """계약 전체에서 준거법 또는 중재지가 서로 다른 나라/도시를 가리키는
    문장이 2개 이상이면 True — 하나의 계약 안에서 조항끼리 충돌하는
    구조는 사용자가 명시한 예외 사유 중 하나다."""
    t = _strip_placeholder_brackets(full_text or "")
    countries = {
        (m.group(1) or m.group(2) or "").strip().lower()
        for m in _RX_GOVERNING_LAW_COUNTRY.finditer(t)
        if (m.group(1) or m.group(2))
    }
    countries.discard("")
    if len(countries) >= 2:
        return True
    seats = {
        (m.group(1) or m.group(2) or "").strip().lower()
        for m in _RX_ARBITRATION_SEAT.finditer(t)
        if (m.group(1) or m.group(2))
    }
    seats.discard("")
    return len(seats) >= 2


def calibrate_jurisdiction_finding_severity(
    severity: str,
    clause_text: str,
    full_text: str,
    clause_title: str = "",
    rewrite_reason: str = "",
    legal_business_reason: str = "",
) -> tuple[str, bool, str]:
    """관할/준거법/중재를 다루는 finding의 severity 상한을 계산한다.

    반환값: (new_severity, changed, reason). 절대 severity를 올리지 않는다
    (never upgrade) — 오직 상위 레이어(rule engine/AI)가 이미 매긴 값을
    구조적으로 과도한 경우에만 낮춘다.

    판정 순서:
      1. 이 finding이 준거법/관할/중재 주제가 아니면 손대지 않는다.
      2. 비대칭 관할·복수의 상충 조항·집행곤란·명시적 해외소송 불리함 중
         하나라도 있으면 캡을 걸지 않는다(상위 판단을 그대로 인정).
      3. 준거법/분쟁해결이 명확히 외국(비한국)이면 MEDIUM까지만 허용.
      4. 그 외(국내법+국내법원/서울중재, 합의관할, 통상적 중재조항, 또는
         외국 여부를 특정할 신호가 전혀 없는 경우)는 LOW로 캡한다 —
         "관할/준거법/중재는 원칙적으로 HIGH 금지"라는 기본 원칙을 반영.
    """
    sev = (severity or "LOW").upper()
    if sev not in ("HIGH", "MEDIUM"):
        return sev, False, ""

    haystack_finding = " ".join(s for s in (clause_title, rewrite_reason, legal_business_reason) if s)
    ct = clause_text or ""
    if not (JURISDICTION_TOPIC_MARKER.search(haystack_finding) or JURISDICTION_TOPIC_MARKER.search(ct)):
        return sev, False, ""

    ft = _strip_placeholder_brackets(full_text or ct)

    asymmetric = bool(_RX_ASYMMETRIC_FORUM.search(ft))
    conflicting = _has_conflicting_jurisdiction_clauses(ft)
    enforcement_difficulty = bool(_RX_ENFORCEMENT_DIFFICULTY.search(ft))
    adverse_foreign_litigation = bool(_RX_ADVERSE_FOREIGN_LITIGATION.search(ft))
    if asymmetric or conflicting or enforcement_difficulty or adverse_foreign_litigation:
        return sev, False, ""

    korean_law = bool(_RX_KOREAN_GOVERNING_LAW.search(ft))
    has_governing_law = bool(_RX_HAS_GOVERNING_LAW.search(ft))
    domestic_forum = bool(_RX_DOMESTIC_FORUM.search(ft)) or bool(_RX_MUTUAL_AGREED_JURISDICTION.search(ft))
    ordinary_arbitration = bool(_RX_ORDINARY_ARBITRATION.search(ft))
    has_dispute_mechanism = bool(_RX_HAS_DISPUTE_MECHANISM.search(ft))

    foreign_law = has_governing_law and not korean_law
    foreign_forum = has_dispute_mechanism and not domestic_forum and not ordinary_arbitration
    is_foreign = foreign_law or foreign_forum

    ceiling = "MEDIUM" if is_foreign else "LOW"

    if _SEV_RANK[ceiling] < _SEV_RANK[sev]:
        return ceiling, True, f"jurisdiction_risk_calibrated_to_{ceiling.lower()}"
    return sev, False, ""
