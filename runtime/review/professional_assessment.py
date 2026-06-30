"""Professional assessment engine for dealer_rental_service_contract.

Public API:
  run_professional_assessment(text, entity) → dict with:
    - clause_results: list[dict]  (for server.py / UI)
    - role_matrix: dict
    - already_reflected: list[dict]  (반영됨 findings)
    - must_fix: list[dict]
    - partial: list[dict]
    - excluded: list[dict]
    - six_section: dict  (for legal_review_docx)
"""
from __future__ import annotations

import re
from typing import Any

from runtime.review.dealer_rental_service_rules import (
    DLRS_RULES,
    DLRS_PRIORITY_ORDER,
    ASSESSMENT_REFLECTED,
    ASSESSMENT_PARTIAL,
    ASSESSMENT_MUST_FIX,
    ASSESSMENT_NA,
    run_dlrs_assessment,
    extract_excerpt_rs,
)
from runtime.review.section_classifier import split_main_and_customer_form


# ─── Role matrix detection ────────────────────────────────────────────────────

_ROLE_DETECTED_CUSTOMER_PARTY = re.compile(
    r"공급업자와\s*(최종\s*소비자|고객)\s*간의\s*렌탈\s*계약.{0,50}직접\s*체결"
)
_ROLE_DETECTED_INVOICE = re.compile(
    r"공급업자는.{0,30}직접\s*세금계산서를\s*발행"
)
_ROLE_DETECTED_BILLING = re.compile(
    r"공급업자는.{0,30}렌탈료를\s*직접\s*청구"
)
_ROLE_DETECTED_DEALER_NO_PARTY = re.compile(
    r"대리점\s*(자신이|은)\s*계약\s*당사자가\s*(되거나|아니)"
)


def _build_role_matrix(text: str, entity: str) -> dict[str, Any]:
    t = text or ""
    has_customer_party = bool(_ROLE_DETECTED_CUSTOMER_PARTY.search(t))
    has_invoice = bool(_ROLE_DETECTED_INVOICE.search(t))
    has_billing = bool(_ROLE_DETECTED_BILLING.search(t))
    has_dealer_no_party = bool(_ROLE_DETECTED_DEALER_NO_PARTY.search(t))

    conflicts = []
    if not has_customer_party:
        conflicts.append("고객 계약 당사자 명시 불명확 — DLR-RS-001 확인 필요")
    if not has_invoice:
        conflicts.append("세금계산서 발행 주체 명시 불명확 — DLR-RS-002 확인 필요")

    return {
        "our_company": entity,
        "supplier": entity,
        "dealer": "대리점",
        "customer_contract_party": f"{entity}/공급업자" if has_customer_party else "불명확",
        "invoice_issuer": f"{entity}/공급업자" if has_invoice else "불명확",
        "billing_party": f"{entity}/공급업자" if has_billing else "불명확",
        "collection_role": "대리점은 수금지원자(법적 주체 아님)",
        "dealer_is_not_contract_party": has_dealer_no_party,
        "ownership_party": f"{entity}/공급업자",
        "conflicts": conflicts,
        "role_matrix_confirmed": has_customer_party and has_dealer_no_party,
    }


# ─── Customer form notes ──────────────────────────────────────────────────────

def _build_customer_form_notes(customer_form_text: str) -> list[dict]:
    if not customer_form_text.strip():
        return []
    return [{
        "clause_id": "customer_form_note",
        "rule_id": "customer_form_note",
        "clause_title": "별첨/고객계약 양식",
        "issue_title": "고객 렌탈계약서 양식은 본 검토 범위 외입니다",
        "source_section_type": "customer_contract_form",
        "current_assessment": "참고",
        "current_assessment_text": (
            "별첨 또는 고객 렌탈계약서 양식이 확인되었습니다. "
            "이 부분은 대리점↔공급업자 간 계약 본문이 아닌 고객용 양식으로, "
            "별도 법무 검토를 권장합니다."
        ),
        "severity": "LOW",
        "risk_tier": "LOW",
        "display_bucket": "별첨참고",
        "approval_required": False,
        "high_risk": False,
        "must_fix": False,
        "review_tier": "REFERENCE",
        "legal_risk": "",
        "business_risk": "",
        "why_this_matters": "고객용 렌탈계약서 양식은 별도 검토가 필요합니다.",
        "required_action": "",
        "proposed_clause": "",
        "original_excerpt": customer_form_text[:300],
        "original_text": customer_form_text[:300],
        "evidence_from_contract": "",
        "suggested_rewrite": "",
        "has_rewrite_change": False,
        "confidence": 1.0,
        "is_mandatory": False,
        "dedup_suppressed": False,
        "keep_as_is": True,
    }]


# ─── Main public API ──────────────────────────────────────────────────────────

def run_professional_assessment(text: str, entity: str = "퍼시스") -> dict[str, Any]:
    """Run the full professional assessment for a dealer_rental_service_contract.

    Returns a result dict consumed by server.py, legal_review_docx, and the UI.
    """
    t = text or ""
    entity_str = entity or "퍼시스"

    # 1. Split main contract vs customer form
    sections = split_main_and_customer_form(t)
    main_text = sections["main_contract"]
    customer_form_text = sections["customer_form"]

    # 2. Role matrix from main contract
    role_matrix = _build_role_matrix(main_text, entity_str)

    # 3. Run DLR-RS rules on main contract only
    all_findings = run_dlrs_assessment(main_text)

    # 4. Split by assessment tier
    must_fix = [f for f in all_findings if f["current_assessment"] == ASSESSMENT_MUST_FIX]
    partial = [f for f in all_findings if f["current_assessment"] == ASSESSMENT_PARTIAL]
    already_reflected = [f for f in all_findings if f["current_assessment"] == ASSESSMENT_REFLECTED]
    excluded_na = [f for f in all_findings if f["current_assessment"] == ASSESSMENT_NA]

    # 5. Customer form notes
    customer_notes = _build_customer_form_notes(customer_form_text)

    # 6. clause_results for UI (must_fix + partial + already_reflected + customer_notes)
    clause_results = must_fix + partial + already_reflected + customer_notes

    # 7. 6-section structure for DOCX
    six_section = {
        "role_matrix": role_matrix,
        "must_fix": must_fix,
        "partial": partial,
        "already_reflected": already_reflected,
        "customer_form_notes": customer_notes,
        "excluded": excluded_na,
        "has_customer_form": sections["has_customer_form"],
        "boundary_pos": sections["boundary_pos"],
    }

    return {
        "clause_results": clause_results,
        "role_matrix": role_matrix,
        "already_reflected": already_reflected,
        "must_fix": must_fix,
        "partial": partial,
        "excluded": excluded_na,
        "customer_form_notes": customer_notes,
        "six_section": six_section,
        "sections_meta": sections,
        "entity": entity_str,
    }
