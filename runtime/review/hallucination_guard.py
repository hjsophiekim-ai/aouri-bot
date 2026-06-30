"""Hallucination guardrails: prevent wrong-type template phrases in review output.

For each contract type code, defines phrases that must NOT appear in proposed
revisions or review findings — because they belong to a different contract type.

Rules:
  - dealer/consignment contracts  → no software/dev/SaaS phrases
  - advisory/consulting contracts → no dealer/distribution phrases
  - non-rental contracts          → no rental-specific phrases
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ─── Forbidden phrase lists ────────────────────────────────────────────────────

# These phrases belong to software development / SaaS contracts.
# They must NOT appear in dealer, consignment, purchase, rental, or construction contracts.
DEV_CONTRACT_PHRASES: list[str] = [
    "수탁자",
    "위탁자",
    "결과물",
    "산출물",
    "오픈소스",
    "무료 이미지",
    "라이선스 조건 고지",
    "제3자의 저작권",
    "제3자의 특허권",
    "저작권·특허권을 침해하지 않음을 보증",
    "저작권 침해 보증",
    "개발 완료",
    "소스코드",
    "유지보수 SLA",
    "SaaS",
    "API 연동",
    "소프트웨어 라이선스",
    "오픈소스 라이선스",
    "소프트웨어 개발 계약",
    "수탁업체",
    "위탁업체",
    "개발 산출물",
    "SBOM",
    "소프트웨어 개발",
    "시스템 개발",
    "개발용역",
    "유지보수 계약",
]

# These phrases belong to advisory/consulting service contracts.
ADVISORY_DOMAIN_PHRASES: list[str] = [
    "대리점",
    "판매대리점",
    "대리점법",
    "렌탈",
    "물류",
    "재판매가격",
    "인테리어 재시공",
    "유통망",
    "위탁판매",
    "기준단가",
    "검수마스터",
    "용역수수료",
    "거래보증금",
    "판매장려금",
    "대리점거래법",
]

# Contract types that are software/app development — allowed to use dev phrases
_SOFTWARE_TYPE_CODES: frozenset[str] = frozenset({
    "software_app_development",
    "ai_search_marketing",
})

# Contract types that are advisory — allowed to use advisory phrases
_ADVISORY_TYPE_CODES: frozenset[str] = frozenset({
    "advisory_service",
})

# ── Clause-identity-scoped forbidden phrases ──────────────────────────────────
# These phrases belong to OTHER clause types. When the LLM generates a revision
# for a specific clause (e.g. termination), these phrases signal a wrong template.

# Termination clauses must NOT reference ownership/debt collection concepts.
# Those belong to collateral/security or rental asset protection clauses.
TERMINATION_CLAUSE_FORBIDDEN: list[str] = [
    "소유권",
    "채권추심",
    "소유권 표식",
    "소유권 행사",
    "양도 담보",
    "동산 담보",
    "압류",
    "추심",
    "담보 설정",
]

# Confidentiality clauses must NOT reference HR/staffing concepts.
# Those belong to non-solicitation or employment clauses.
CONFIDENTIALITY_CLAUSE_FORBIDDEN: list[str] = [
    "인력관리",
    "인력 관리",
    "직원 채용",
    "임직원 채용",
    "스카우트",
    "고용 금지",
    "근로계약",
    "채용 금지",
    "임직원 유출",
    "인력 유출",
]

# Assignee/transfer clauses must NOT reference promotion/marketing concepts.
ASSIGNMENT_CLAUSE_FORBIDDEN: list[str] = [
    "판매촉진",
    "판촉비",
    "광고비",
    "마케팅 비용",
    "프로모션 비용",
    "판촉 활동 비용",
]

# Map clause identity name → forbidden phrase list (identity names match CI_* constants)
_CLAUSE_IDENTITY_FORBIDDEN: dict[str, list[str]] = {
    "termination": TERMINATION_CLAUSE_FORBIDDEN,
    "confidentiality": CONFIDENTIALITY_CLAUSE_FORBIDDEN,
    "assignment": ASSIGNMENT_CLAUSE_FORBIDDEN,
}


@dataclass
class GuardResult:
    is_clean: bool
    violations: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.is_clean


_DEALER_TYPE_CODES: frozenset[str] = frozenset({
    "consignment_sales_agency",
    "direct_customer_sales_support",
    "dealer_agency",
    "distribution_resale",
    "dealer_rental_service_contract",
})


def check_revision_text(
    text: str,
    *,
    contract_type_code: str,
    clause_identity: str = "",
) -> GuardResult:
    """Return GuardResult indicating whether the proposed revision is clean.

    Args:
        text: proposed revision / review text to check
        contract_type_code: canonical contract type code from contract_classifier
        clause_identity: optional clause identity name (e.g. "termination", "confidentiality")
            used to block wrong-context phrases for specific clause types
    """
    if not text:
        return GuardResult(is_clean=True)

    violations: list[str] = []

    # Check dev phrases in non-dev contracts
    if contract_type_code not in _SOFTWARE_TYPE_CODES:
        for phrase in DEV_CONTRACT_PHRASES:
            if phrase in text:
                violations.append(f"dev_phrase_in_non_dev_contract:'{phrase}'")

    # Check advisory phrases in non-advisory contracts
    if contract_type_code not in _ADVISORY_TYPE_CODES:
        for phrase in ADVISORY_DOMAIN_PHRASES:
            if phrase in text:
                # Only flag if this is a non-dealer contract (dealer contracts legitimately use these)
                if contract_type_code not in _DEALER_TYPE_CODES:
                    violations.append(f"advisory_phrase_wrong_context:'{phrase}'")

    # Check clause-identity-scoped forbidden phrases
    if clause_identity:
        forbidden = _CLAUSE_IDENTITY_FORBIDDEN.get(clause_identity, [])
        for phrase in forbidden:
            if phrase in text:
                violations.append(f"wrong_clause_context[{clause_identity}]:'{phrase}'")

    return GuardResult(is_clean=len(violations) == 0, violations=violations)


def filter_forbidden_phrases_inplace(
    text: str,
    *,
    contract_type_code: str,
) -> tuple[str, list[str]]:
    """Remove forbidden phrases and return (cleaned_text, list_of_violations)."""
    if not text:
        return text, []

    result = check_revision_text(text, contract_type_code=contract_type_code)
    if result.is_clean:
        return text, []

    t = text
    for violation in result.violations:
        # Extract quoted phrase from violation string
        parts = violation.split("'")
        if len(parts) >= 2:
            phrase = parts[1]
            if phrase and phrase in t:
                t = t.replace(phrase, "")  # remove the phrase

    return t.strip(), result.violations


def is_dev_phrase_in_text(text: str) -> bool:
    """Quick check: does text contain any dev contract phrases?"""
    if not text:
        return False
    return any(phrase in text for phrase in DEV_CONTRACT_PHRASES)
