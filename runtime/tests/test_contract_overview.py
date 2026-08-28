"""Tests for the contract-level overview handed to the AI reviewer before
per-clause review (requirement.md 2026-08-28: AI must see 계약 목적/기간/
대금구조/전체 조항 목차 before judging individual clauses)."""
from __future__ import annotations

import unittest
from pathlib import Path

from runtime.review.clause_extraction import extract_clauses
from runtime.review.contract_overview import build_contract_overview

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fiti_testing_service_agreement.txt"


class ContractOverviewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = FIXTURE_PATH.read_text(encoding="utf-8")
        self.clauses, _ = extract_clauses(self.text)
        self.overview = build_contract_overview(clauses=self.clauses, full_text=self.text)

    def test_article_toc_covers_all_articles_in_order(self) -> None:
        numbers = [a["article_number"] for a in self.overview.article_toc]
        self.assertEqual(numbers, [str(n) for n in range(1, 15)])

    def test_purpose_extracted_from_article_1(self) -> None:
        self.assertIsNotNone(self.overview.purpose)
        self.assertIn("목적", self.overview.purpose)

    def test_contract_term_extracted(self) -> None:
        self.assertIsNotNone(self.overview.contract_term)
        self.assertIn("2년", self.overview.contract_term)

    def test_payment_structure_extracted(self) -> None:
        self.assertIsNotNone(self.overview.payment_structure)
        self.assertIn("수수료", self.overview.payment_structure)

if __name__ == "__main__":
    unittest.main()
