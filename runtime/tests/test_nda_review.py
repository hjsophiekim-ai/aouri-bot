from __future__ import annotations

import unittest

from runtime.rules.loader import RuleLoader
from runtime.review.clause_extraction import extract_clauses
from runtime.review.jurisdiction import classify_jurisdiction_profile
from runtime.review.clause_level import _is_domestic_only
from runtime.services.query_service import ReviewInput, RuleQueryService


PORSCHE_NDA_TEXT = """\
NON-DISCLOSURE AGREEMENT

This Non-Disclosure Agreement ("Agreement") is entered into between
Porsche Design GmbH, a company incorporated under German law with its
registered office at Porschestrasse 1, 70435 Stuttgart, Germany
("Disclosing Party"), and Fursys Inc. ("Receiving Party").

1. Confidential Information
The Receiving Party agrees to keep confidential all information disclosed
by the Disclosing Party under this Agreement, including but not limited to
technical data, trade secrets, and business information.

2. Obligations
The Receiving Party shall not disclose Confidential Information to any
third party without prior written consent from the Disclosing Party.

3. Exceptions
The obligations of confidentiality shall not apply to information that is
publicly known, independently developed, or required to be disclosed by law.

4. Term
This Agreement shall remain in force for a period of three (3) years.

5. Return of Information
Upon termination, the Receiving Party shall promptly return or destroy all
Confidential Information.

6. No License
Nothing in this Agreement grants any rights to the Receiving Party.

7. Entire Agreement
This Agreement constitutes the entire agreement between the parties.

8. Governing Law and Jurisdiction
This Agreement shall be governed by and construed in accordance with
German law. Any disputes shall be subject to the exclusive jurisdiction
of the courts of Stuttgart, Germany.
"""


class TestNDAJurisdiction(unittest.TestCase):
    def test_porsche_nda_jurisdiction_classified_as_foreign(self) -> None:
        """Porsche Design GmbH (German company) must NOT be domestic_korea."""
        jur = classify_jurisdiction_profile(text=PORSCHE_NDA_TEXT)
        self.assertNotEqual(
            jur.kind, "domestic_korea",
            f"Expected non-domestic jurisdiction, got {jur.kind}. Evidence: {jur.evidence}",
        )

    def test_gmbh_detected_as_foreign_entity(self) -> None:
        """GmbH suffix must trigger foreign_entity detection."""
        jur = classify_jurisdiction_profile(text=PORSCHE_NDA_TEXT)
        self.assertTrue(
            jur.has_foreign_entity or jur.has_cross_border_signal,
            "Expected foreign_entity or cross_border signal for GmbH company",
        )

    def test_is_domestic_only_false_for_foreign_contract(self) -> None:
        """_is_domestic_only must return False for GmbH/Stuttgart contract."""
        result = _is_domestic_only(PORSCHE_NDA_TEXT, {})
        self.assertFalse(result, "_is_domestic_only should return False for foreign NDA")

    def test_stuttgart_detected_as_foreign_law_signal(self) -> None:
        """Stuttgart as jurisdiction venue must trigger foreign signal."""
        jur = classify_jurisdiction_profile(text=PORSCHE_NDA_TEXT)
        self.assertTrue(
            jur.has_cross_border_signal or jur.has_foreign_entity,
            "Stuttgart/German law not detected as cross-border signal",
        )

    def test_english_numbered_clause_extraction(self) -> None:
        """English '1. TITLE' format must be parsed as clauses when no Article X headings."""
        numbered_nda = """\
1. DEFINITIONS
All technical information shared under this agreement is confidential.

2. OBLIGATIONS
The receiving party shall not disclose any information.

3. TERM
This agreement expires after five years.
"""
        clauses, report = extract_clauses(numbered_nda)
        self.assertGreater(len(clauses), 0, "No clauses extracted from numbered English NDA")
        ids = [c.clause_id for c in clauses]
        self.assertTrue(
            any("EN-1" in cid or "EN-2" in cid or "EN-3" in cid for cid in ids),
            f"Expected EN-1/EN-2/EN-3 clause IDs, got: {ids}",
        )

    def test_nda_en_rules_loaded(self) -> None:
        """NDA-EN-001/002/003 must be present in confirmed_pattern rules."""
        service = RuleQueryService(RuleLoader())
        all_rules = service.list_rules(include_backlog=False)
        rule_ids = {r["rule_id"] for r in all_rules}
        for rid in ("NDA-EN-001", "NDA-EN-002", "NDA-EN-003"):
            self.assertIn(rid, rule_ids, f"Rule {rid} not found in loaded rules")

    def test_nda_en001_fires_on_stuttgart(self) -> None:
        """NDA-EN-001 must match when text contains 'Stuttgart'."""
        service = RuleQueryService(RuleLoader())
        result = service.analyze(
            ReviewInput(
                entity="퍼시스",
                contract_type="NDA/비밀유지",
                text=PORSCHE_NDA_TEXT,
            )
        )
        matched_ids = {r["rule_id"] for r in result.get("matched_rules", [])}
        self.assertIn(
            "NDA-EN-001",
            matched_ids,
            f"NDA-EN-001 did not fire on Stuttgart NDA. Matched: {matched_ids}",
        )

    def test_nda_en001_is_high_risk(self) -> None:
        """NDA-EN-001 must be HIGH risk when matched."""
        service = RuleQueryService(RuleLoader())
        result = service.analyze(
            ReviewInput(
                entity="퍼시스",
                contract_type="NDA/비밀유지",
                text=PORSCHE_NDA_TEXT,
            )
        )
        for r in result.get("matched_rules", []):
            if r["rule_id"] == "NDA-EN-001":
                self.assertEqual(
                    str(r.get("risk_level") or "").upper(), "HIGH",
                    f"NDA-EN-001 expected HIGH risk, got: {r.get('risk_level')}",
                )
                return
        self.skipTest("NDA-EN-001 not matched; check test_nda_en001_fires_on_stuttgart first")


if __name__ == "__main__":
    unittest.main()
