"""Severity reclassification rules.

Applies post-hoc on top of initial rule-based severity to enforce the
legal requirement document. Only upgrades severity — never downgrades.

HIGH triggers (any match → force HIGH):
  - Legal party / contracting party mismatch (invoice, customer contract, collection)
  - Overbroad liability ("모든 책임", "일체 책임")
  - Unilateral setoff without due process signals
  - Arbitrary supply cutoff / volume reduction
  - Retaliation risk for rights exercise

MEDIUM triggers (if currently LOW → upgrade to MEDIUM):
  - Cost burden without ceiling/process
  - Termination/renewal cause overly broad
  - Incentive as pure discretion
  - Setoff with limited (but existing) process

Setoff clause special rule (제16조 equivalent):
  - If setoff keywords are present and severity is LOW → force MEDIUM
"""
from __future__ import annotations

import re

# ─── Pattern definitions ──────────────────────────────────────────────────────

_HIGH_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Invoice/tax party mismatch
    (re.compile(r"세금계산서.*발행.*대리점|대리점.*세금계산서.*발행"), "invoice_party_mismatch"),
    (re.compile(r"대리점은.*각종\s*법률이\s*규정.*의무를\s*수행"), "invoice_legal_obligation_mismatch"),
    # Customer contract party mismatch
    (re.compile(r"대리점은\s*고객과\s*계약\s*시"), "customer_contract_party_mismatch"),
    (re.compile(r"대리점은\s*고객과\s*상품공급계약서를\s*작성"), "customer_contract_party_mismatch"),
    (re.compile(r"대리점이.*계약.*당사자"), "customer_contract_party_mismatch"),
    # Collection liability mismatch
    (re.compile(r"대금\s*수금\s*업무를\s*성실히\s*수행"), "collection_liability_overbroad"),
    (re.compile(r"수요자의\s*대금지급이\s*이루어질\s*수\s*있도록"), "collection_liability_overbroad"),
    (re.compile(r"수금.*책임.*대리점|대리점.*수금.*책임"), "collection_liability_direct"),
    # Overbroad liability
    (re.compile(r"모든\s*책임은?\s*(대리점|을)"), "overbroad_all_liability"),
    (re.compile(r"일체\s*책임|일체의\s*책임"), "overbroad_all_liability"),
    (re.compile(r"어떠한\s*경우에도.*전부\s*배상"), "overbroad_full_indemnity"),
    (re.compile(r"전액\s*배상.*어떠한\s*경우"), "overbroad_full_indemnity"),
    # Unilateral setoff without process
    (re.compile(r"용역수수료에서\s*차감|거래보증금에서\s*상계|정책지원금에서\s*상계"), "unilateral_setoff_no_process"),
    (re.compile(r"용역수수료.*차감.*통지\s*없이|사전\s*통지\s*없이.*상계"), "unilateral_setoff_no_notice"),
    # Supply cutoff / volume reduction
    (re.compile(r"공급을?\s*중단|물량을?\s*현저히\s*축소"), "supply_cutoff_volume_reduction"),
    (re.compile(r"즉시\s*해지.*유통질서|유통질서.*즉시\s*해지"), "termination_supply_cutoff"),
    # Rights exercise retaliation
    (re.compile(r"대리점단체.*불이익|분쟁조정.*신청.*불이익|공정위.*신고.*불이익"), "rights_exercise_retaliation"),
]

_MEDIUM_MIN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Cost burden without ceiling or process
    (re.compile(r"추가\s*시공비|긴급생산.*착불비"), "cost_burden_no_ceiling"),
    (re.compile(r"반품.*비용.*대리점\s*부담|취소.*비용.*대리점\s*부담"), "return_cancel_cost_burden"),
    # Termination/renewal cause overly broad
    (re.compile(r"유통질서\s*훼손|이미지\s*훼손"), "termination_image_clause"),
    (re.compile(r"윤리규정\s*위반.*해지|해지.*윤리규정"), "termination_ethics_clause"),
    # Incentive fully discretionary
    (re.compile(r"시혜적\s*혜택|공급(?:자|업자)의\s*재량에\s*따라\s*지급"), "incentive_discretionary"),
    # Setoff with some process but limited
    (re.compile(r"상계.*통지|통지.*상계"), "setoff_with_notice_only"),
]

# Keywords that trigger the setoff MEDIUM upgrade (제16조 type clauses)
_SETOFF_KEYWORDS: list[str] = [
    "상계", "차감", "공제",
    "거래보증금", "용역수수료에서", "정책지원금에서",
]


# ─── Main reclassification function ───────────────────────────────────────────

def reclassify_severity(
    current_severity: str,
    clause_text: str,
    contract_type_code: str = "",
    clause_identity: str = "",
) -> tuple[str, list[str]]:
    """Reclassify severity upward based on text content.

    Args:
        current_severity: current severity label ("HIGH", "MEDIUM", "LOW")
        clause_text: full text of the clause to analyse
        contract_type_code: canonical contract type code
        clause_identity: clause identity from dealer_direct_findings

    Returns:
        (new_severity, list_of_upgrade_reasons)
        Never returns a lower severity than the input.
    """
    sev = (current_severity or "LOW").upper()
    if sev not in ("HIGH", "MEDIUM", "LOW"):
        sev = "LOW"

    reasons: list[str] = []
    t = clause_text or ""

    if not t:
        return sev, reasons

    # Apply HIGH upgrade rules
    for pat, reason_code in _HIGH_PATTERNS:
        if pat.search(t):
            if sev != "HIGH":
                sev = "HIGH"
                reasons.append(f"auto_upgrade_HIGH:{reason_code}")
            elif reason_code not in " ".join(reasons):
                reasons.append(f"confirmed_HIGH:{reason_code}")

    # Apply MEDIUM upgrade rules (only if still LOW)
    if sev == "LOW":
        for pat, reason_code in _MEDIUM_MIN_PATTERNS:
            if pat.search(t):
                sev = "MEDIUM"
                reasons.append(f"auto_upgrade_MEDIUM:{reason_code}")
                break

    return sev, reasons


def reclassify_setoff_clause(current_severity: str, clause_text: str) -> str:
    """Special rule for setoff/offset clauses (e.g. 제16조).

    Always returns at least MEDIUM when setoff keywords are present.
    This implements requirement: "제16조 상계 조항을 LOW로 처리한 것은 잘못"
    """
    sev = (current_severity or "LOW").upper()
    t = clause_text or ""
    if sev == "LOW" and any(kw in t for kw in _SETOFF_KEYWORDS):
        return "MEDIUM"
    return sev


_RX_SYMMETRIC_MUTUAL_TERMINATION = re.compile(
    r"(양\s*당사자|각\s*당사자|상호|쌍방).{0,60}(?:상대방에게)?.{0,30}\d+\s*(?:일|개월)\s*전.{0,20}"
    r"(?:서면으로?\s*)?통지.{0,30}해지",
    re.DOTALL,
)
_RX_ASYMMETRIC_TERMINATION_EXCLUSION = re.compile(
    r"갑에?\s*한하여|을은\s*그러하지\s*아니|일방만|편면적|갑만\s*해지|을만\s*해지",
)


def demote_symmetric_mutual_termination(severity: str, clause_text: str) -> tuple[str, bool]:
    """A termination right granted *symmetrically* to both parties by the same
    short-notice mechanism (e.g. "양 당사자는 상대방에게 30일 전 서면으로
    통지하여 계약을 해지할 수 있다") is a balanced, mutually-available exit
    right, not a one-sided commercial risk — real negotiation on it is usually
    about adding a settlement/handover clause for in-flight work, not about
    the termination right itself. Left at AI-assigned HIGH, it can crowd out
    genuine one-sided economic risks (direct-dealing restriction + penalty,
    minimum purchase commitment, etc.) at the top of the HIGH tier. Cap it at
    MEDIUM unless the clause text itself carries an asymmetric-exclusion
    marker (one party is exempted from the same right, so it is not actually
    symmetric).

    Returns (new_severity, demoted). Never upgrades — only ever HIGH -> MEDIUM.
    """
    sev = (severity or "LOW").upper()
    if sev != "HIGH":
        return sev, False
    t = clause_text or ""
    if not _RX_SYMMETRIC_MUTUAL_TERMINATION.search(t):
        return sev, False
    if _RX_ASYMMETRIC_TERMINATION_EXCLUSION.search(t):
        return sev, False
    return "MEDIUM", True


_RX_HAS_GOVERNING_LAW = re.compile(
    r"준거법[은는이가]?\s*[\S ]{0,20}(?:법|법률)(?:으로|을|를)?\s*한다"
    r"|governed\s+(?:and\s+interpreted\s+)?by\s+the\s+laws?\s+of"
    r"|이\s*계약(?:서)?은\s*[\S ]{0,20}법(?:을|에)\s*따(?:라|른다)",
    re.IGNORECASE,
)
_RX_HAS_DISPUTE_MECHANISM = re.compile(
    r"중재(?:에\s*의하여|로)\s*(?:최종\s*)?해결"
    r"|관할\s*법원(?:은|으로)\s*[\S ]{0,20}(?:로|으로)\s*한다"
    r"|settled\s+by\s+arbitration|final(?:ly)?\s+settled\s+by\s+arbitration"
    r"|exclusive\s+jurisdiction",
    re.IGNORECASE,
)
_RX_GOVERNING_LAW_DISPUTE_TOPIC_MARKER = re.compile(
    r"준거법|governing\s+law|관할\s*법원|중재|arbitration|dispute\s+resolution|jurisdiction",
    re.IGNORECASE,
)
_RX_ABSENCE_CLAIM_MARKER = re.compile(
    r"없다|부재|누락|명시되어\s*있지\s*않|규정되어\s*있지\s*않|정해져\s*있지\s*않|규정하고\s*있지\s*않"
    r"|미특정|미설정|특정되지\s*않|설정되지\s*않|불명확"
    r"|\bmissing\b|\babsent\b|does\s+not\s+specify|not\s+specified|no\s+provision|\blacks?\b"
    r"|\bunspecified\b|\bunclear\b",
    re.IGNORECASE,
)


def demote_adequate_governing_law_dispute_clause(
    severity: str,
    clause_text: str,
    clause_title: str = "",
    rewrite_reason: str = "",
    legal_business_reason: str = "",
) -> tuple[str, bool]:
    """범용 사내변호사형 검토 고도화(2026-09-03 지시) — GLOBAL_CROSS_CLAUSE_
    VALIDATION은 "이 조항에 준거법/분쟁해결이 없다"는 주장이 실제로는 다른
    조항에 이미 있을 때만 억제한다. 이 함수는 그와 다른 축이다: 준거법/
    분쟁해결 조항 그 자체가 이미 준거법 지정 + 완결된 분쟁해결 메커니즘
    (중재기관/관할법원 + 지역)을 모두 갖추고 있는데도, 그 조항 자체를 검토한
    finding이 (absence를 주장하지 않는 스타일 비판이라도) HIGH로 남아있는
    경우를 LOW로 강등한다 — KOTRA 3자 컨설팅계약 Article 9.2(준거법: 대한민국
    법, 분쟁해결: 서울 중재)가 그 자체로 완결돼 있음에도 HIGH로 과대평가된
    사례가 이 클래스의 전형이다.

    "이 조항에 X가 없다"는 absence claim이 있는 경우는 이 함수의 대상이
    아니다(그 경우는 GLOBAL_CROSS_CLAUSE_VALIDATION이 계약 전체를 검색해
    처리하거나, 실제로 다른 조항에도 없으면 진짜 문제이므로 그대로 둔다).

    Returns (new_severity, demoted). Never upgrades — only ever HIGH -> LOW.
    """
    sev = (severity or "LOW").upper()
    if sev != "HIGH":
        return sev, False
    haystack = " ".join(s for s in (clause_title, rewrite_reason, legal_business_reason) if s)
    if not _RX_GOVERNING_LAW_DISPUTE_TOPIC_MARKER.search(haystack):
        return sev, False
    if _RX_ABSENCE_CLAIM_MARKER.search(haystack):
        return sev, False
    t = clause_text or ""
    if not (_RX_HAS_GOVERNING_LAW.search(t) and _RX_HAS_DISPUTE_MECHANISM.search(t)):
        return sev, False
    return "LOW", True


def reclassify_for_consignment_dealer(
    severity: str,
    clause_text: str,
    clause_title: str = "",
) -> tuple[str, list[str]]:
    """Combined reclassification for consignment_sales_agency contracts.

    Applies both the general reclassifier and setoff special rule.
    """
    new_sev, reasons = reclassify_severity(severity, clause_text)
    # Additional setoff check
    setoff_sev = reclassify_setoff_clause(new_sev, clause_text)
    if setoff_sev != new_sev:
        reasons.append("auto_upgrade_MEDIUM:setoff_clause_rule")
        new_sev = setoff_sev
    return new_sev, reasons
