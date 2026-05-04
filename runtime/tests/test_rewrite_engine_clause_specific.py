from __future__ import annotations

import unittest

from runtime.review.rewrite_engine import propose_clause_specific_rewrite
from runtime.review.party_role import PartyRole


class ClauseSpecificRewriteTest(unittest.TestCase):
    def test_clause_specific_rewrite_not_generic_template(self) -> None:
        clause = "을은 갑에게 발생하는 모든 손해에 대하여 무제한 책임을 부담하며, 간접손해 및 영업손실도 포함한다."
        applied_rules = [{"rule_id": "RISK-001", "matched_keywords": ["무제한", "간접손해"]}]
        p = propose_clause_specific_rewrite(clause_text=clause, applied_rules=applied_rules)
        self.assertIsNotNone(p)
        assert p is not None
        self.assertIn("책임", p.suggested_rewrite)
        self.assertIn("상한", p.suggested_rewrite)
        self.assertNotEqual(p.suggested_rewrite.strip(), clause.strip())
        self.assertTrue(p.rewrite_reason.strip())

    def test_clause_specific_rewrite_keeps_context(self) -> None:
        clause = "Supplier shall indemnify and hold harmless Customer from any and all claims without limitation."
        applied_rules = [{"rule_id": "RISK-002", "matched_keywords": ["indemnify", "without limitation"]}]
        p = propose_clause_specific_rewrite(clause_text=clause, applied_rules=applied_rules)
        self.assertIsNotNone(p)
        assert p is not None
        self.assertIn("Supplier", p.suggested_rewrite)
        self.assertIn("indemnify", p.suggested_rewrite.lower())
        self.assertNotIn("fallback", p.suggested_rewrite.lower())

    def test_fursys_contractor_picks_enforced(self) -> None:
        party = PartyRole(
            our_role="contractor",
            counterparty_role="ordering_party",
            our_label="을",
            counterparty_label="갑",
            counterparty_is_large_standard_provider=False,
            signals=["test"],
        )
        clause = (
            "지체상금은 지체일수 1일당 계약금액의 0.3%로 한다. "
            "갑은 을에게 지급할 대금에서 수수료 등을 공제할 수 있다. "
            "갑은 을의 위반 시 즉시 해지할 수 있다. "
            "안전사고 발생 시 을이 전적으로 책임진다."
        )
        p = propose_clause_specific_rewrite(clause_text=clause, applied_rules=[], party=party)
        self.assertIsNotNone(p)
        assert p is not None
        self.assertIn("0.1%", p.suggested_rewrite)
        self.assertIn("확정", p.suggested_rewrite)
        self.assertIn("사전 서면", p.suggested_rewrite)
        self.assertIn("30일", p.suggested_rewrite)
        self.assertIn("발주자", p.suggested_rewrite)


if __name__ == "__main__":
    unittest.main()

