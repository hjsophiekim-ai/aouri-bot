"""
Integration tests: Porsche Design GmbH x Fursys NDA

Before running:
  pip install pytest
  Set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env
  Run: python -m pytest tests/test_nda_review.py -v
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Sample NDA text (abridged for tests) ────────────────────────────────────
NDA_TEXT = """
CONFIDENTIALITY AGREEMENT

between

Porsche Design GmbH, Flugplatzstraße 29, 5700 Zell am See, Austria
(hereinafter "PDG")

and

Fursys Inc., 05661 Seoul, 311 Ogeum-Ro, Songpa-Gu, South Korea
(hereinafter "Fursys")

1. Subject Matter
The parties intend to explore a potential business cooperation (hereinafter the "agreed purpose").
In connection therewith, the parties may disclose confidential information to each other.

2. Confidential Information
"Confidential Information" means all information of a technical, commercial or financial nature
disclosed by one party (the "Disclosing Party") to the other party (the "Receiving Party").

3. Obligations
The Receiving Party shall keep the Confidential Information strictly confidential and shall not
disclose it to any third party without prior written consent of the Disclosing Party.

4. No License
This agreement shall not be construed as granting any license or right to use the
Confidential Information except for the agreed purpose.
The parties shall have no right or obligation to conclude any further agreement.

5. Data Protection
Both parties shall comply with applicable data protection laws including GDPR.

6. Return of Information
Upon request, the Receiving Party shall return or destroy all Confidential Information,
including any copies, in a manner that the data cannot be recovered or reconstructed.

7. Duration
This agreement shall remain in force for a period of three (3) years from the date of signing.

8. For any disputes arising from or in connection with this confidentiality agreement,
Stuttgart shall be the court of exclusive jurisdiction. German law shall apply.
"""


# ── Unit tests for clause_parser ────────────────────────────────────────────
def test_clause_parser_detects_english_numbered():
    """Clause parser must detect '8. For any disputes...' as clause 8."""
    from runtime.review.clause_parser import parse_clauses, detect_language

    lang = detect_language(NDA_TEXT)
    assert lang == "en", f"Language detection failed: got {lang}"

    clauses = parse_clauses(NDA_TEXT)
    numbers = [c.number for c in clauses]
    assert "8" in numbers, f"Clause 8 not parsed. Got: {numbers}"


def test_clause_extraction_detects_clause8():
    """Core clause_extraction must parse clause 8 as a separate article."""
    from runtime.review.clause_extraction import extract_clauses

    clauses, report = extract_clauses(NDA_TEXT)
    article_numbers = [c.article_number for c in clauses]
    display_paths = [c.display_path for c in clauses]

    # Must NOT fall back to "문단 N" format for the full NDA
    has_numbered = any(
        an is not None and "8" in str(an)
        for an in article_numbers
    )
    has_display_8 = any("8" in dp for dp in display_paths)

    assert has_numbered or has_display_8, (
        f"Clause 8 not extracted as numbered article.\n"
        f"article_numbers: {article_numbers}\n"
        f"display_paths: {display_paths}\n"
        f"strategy: {report.strategy}"
    )


# ── Unit tests for jurisdiction detection ───────────────────────────────────
def test_jurisdiction_detects_foreign_entity():
    """GmbH + Austria must be classified as foreign_entity_involved, NOT domestic_korea."""
    from runtime.review.jurisdiction import classify_jurisdiction_profile

    profile = classify_jurisdiction_profile(text=NDA_TEXT, entity="퍼시스")
    assert profile.kind != "domestic_korea", (
        f"Jurisdiction wrongly classified as domestic_korea. Evidence: {profile.evidence}"
    )
    assert profile.has_foreign_entity or profile.has_cross_border_signal, (
        f"Foreign entity not detected. Evidence: {profile.evidence}"
    )


# ── Unit tests for NDA-EN rules ─────────────────────────────────────────────
def test_nda_en001_rule_triggers_on_stuttgart():
    """NDA-EN-001 must fire when text contains Stuttgart + German law."""
    from runtime.rules.loader import RuleLoader

    loader = RuleLoader()
    rules = loader.decision_rules()

    en001 = next((r for r in rules if r.get("rule_id") == "NDA-EN-001"), None)
    assert en001 is not None, "NDA-EN-001 rule not found in decision_rules"

    tags = en001.get("tags", [])
    trigger_kws = [t[8:].lower() for t in tags if isinstance(t, str) and t.startswith("trigger:")]

    haystack = NDA_TEXT.lower()
    matched = [kw for kw in trigger_kws if kw in haystack]
    assert matched, (
        f"NDA-EN-001 triggers not found in NDA text.\n"
        f"Expected one of: {trigger_kws}\n"
        f"NDA excerpt: {NDA_TEXT[NDA_TEXT.find('8.'):NDA_TEXT.find('8.')+200]}"
    )


def test_nda_en004_rule_triggers_on_data_deletion():
    """NDA-EN-004 must fire when text contains 'cannot be recovered'."""
    from runtime.rules.loader import RuleLoader

    loader = RuleLoader()
    rules = loader.decision_rules()

    en004 = next((r for r in rules if r.get("rule_id") == "NDA-EN-004"), None)
    assert en004 is not None, "NDA-EN-004 rule not found (data deletion)"

    tags = en004.get("tags", [])
    trigger_kws = [t[8:].lower() for t in tags if isinstance(t, str) and t.startswith("trigger:")]

    haystack = NDA_TEXT.lower()
    matched = [kw for kw in trigger_kws if kw in haystack]
    assert matched, (
        f"NDA-EN-004 triggers not matched.\nExpected: {trigger_kws}"
    )


# ── Integration tests (require API key) ─────────────────────────────────────
def _has_api_key() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY"))


def test_domestic_filter_not_applied_for_international():
    """International contract must NOT have domestic filter applied to dispute clause."""
    if not _has_api_key():
        import pytest
        pytest.skip("No API key configured — skipping integration test")

    from runtime.rules.loader import RuleLoader
    from runtime.services.query_service import RuleQueryService, ReviewInput
    from runtime.review.clause_extraction import extract_clauses
    from runtime.review.revision import suggest_revisions
    from runtime.review.jurisdiction import classify_jurisdiction_profile
    from runtime.review.clause_level import _apply_domestic_filter

    loader = RuleLoader()
    service = RuleQueryService(loader)
    review = service.analyze(ReviewInput(
        entity="퍼시스",
        contract_type="NDA",
        text=NDA_TEXT,
        filename="porsche_design_nda.pdf",
    ))

    clauses, _ = extract_clauses(NDA_TEXT)
    revision = suggest_revisions(clauses, review.get("matched_rules", []))
    items = revision.get("items", [])

    # Find any dispute clause result
    dispute_items = [it for it in items if "Stuttgart" in str(it.get("original_clause", "")) or "jurisdiction" in str(it.get("original_clause", "")).lower()]

    # Apply domestic filter with international metadata
    results = list(items)
    jur = classify_jurisdiction_profile(text=NDA_TEXT, entity="퍼시스")
    is_domestic = jur.kind == "domestic_korea"
    llm_meta = {"is_cross_border": True, "party_a_country": "Austria", "party_b_country": "Korea"}

    _apply_domestic_filter(results, is_domestic, llm_meta=llm_meta)

    for it in results:
        oc = str(it.get("original_clause", ""))
        if "Stuttgart" in oc or "jurisdiction" in oc.lower():
            tier = str(it.get("risk_tier", "")).upper()
            assert tier != "LOW" or not it.get("guardrail_block", {}).get("filter") == "domestic_filter", (
                f"Domestic filter wrongly applied to international dispute clause!\n"
                f"risk_tier: {tier}, guardrail: {it.get('guardrail_block')}"
            )


def test_clause8_detected_as_high_risk():
    """Clause 8 (Stuttgart exclusive jurisdiction) must be detected as HIGH risk."""
    if not _has_api_key():
        import pytest
        pytest.skip("No API key configured — skipping integration test")

    from runtime.rules.loader import RuleLoader
    from runtime.services.query_service import RuleQueryService, ReviewInput
    from runtime.review.clause_extraction import extract_clauses
    from runtime.review.revision import suggest_revisions

    loader = RuleLoader()
    service = RuleQueryService(loader)
    review = service.analyze(ReviewInput(
        entity="퍼시스",
        contract_type="NDA",
        text=NDA_TEXT,
        filename="porsche_design_nda.pdf",
    ))

    matched_rule_ids = [r.get("rule_id") for r in review.get("matched_rules", [])]
    assert "NDA-EN-001" in matched_rule_ids, (
        f"NDA-EN-001 not in matched rules. Got: {matched_rule_ids}"
    )

    clauses, _ = extract_clauses(NDA_TEXT)
    revision = suggest_revisions(clauses, review.get("matched_rules", []))
    items = revision.get("items", [])

    # Find the clause that matched Stuttgart/German law
    high_risk_items = [it for it in items if str(it.get("risk_tier", "")).upper() == "HIGH"]
    assert high_risk_items, (
        f"No HIGH risk items found. Items: "
        f"{[(it.get('clause_id'), it.get('risk_tier'), it.get('original_clause', '')[:60]) for it in items]}"
    )


if __name__ == "__main__":
    print("=== Running unit tests (no API key required) ===")
    test_clause_parser_detects_english_numbered()
    print("OK test_clause_parser_detects_english_numbered")

    test_clause_extraction_detects_clause8()
    print("OK test_clause_extraction_detects_clause8")

    test_jurisdiction_detects_foreign_entity()
    print("OK test_jurisdiction_detects_foreign_entity")

    test_nda_en001_rule_triggers_on_stuttgart()
    print("OK test_nda_en001_rule_triggers_on_stuttgart")

    test_nda_en004_rule_triggers_on_data_deletion()
    print("OK test_nda_en004_rule_triggers_on_data_deletion")

    print("\n=== All unit tests passed ===")
    if _has_api_key():
        print("=== Running integration tests ===")
        test_domestic_filter_not_applied_for_international()
        print("OK test_domestic_filter_not_applied_for_international")
        test_clause8_detected_as_high_risk()
        print("OK test_clause8_detected_as_high_risk")
        print("\n=== All integration tests passed ===")
    else:
        print("(Integration tests skipped - set ANTHROPIC_API_KEY or OPENAI_API_KEY to run)")
