from __future__ import annotations

import unittest

from runtime.law.search_service import LawReference, _rerank_and_filter_references
from runtime.questions.generator import generate_questions
from runtime.review.clause_extraction import extract_clauses
from runtime.review.rewrite_engine import propose_clause_specific_rewrite
from runtime.review.text_extract import TextExtractionResult, extract_text_from_file


class DeepReviewRegressionTests(unittest.TestCase):
    def test_txt_rejects_wordprocessingml_markers(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.txt"
            p.write_text("w:rPr w:delText", encoding="utf-8")
            res: TextExtractionResult = extract_text_from_file(p)
        self.assertFalse(res.success)

    def test_clause_extractor_blocks_wordprocessingml_markers(self) -> None:
        clauses, report = extract_clauses("제1조 <w:rPr>bad</w:rPr>")
        self.assertEqual([], clauses)
        self.assertEqual("blocked", report.strategy)

    def test_question_engine_skips_dealer_cost_question_when_terms_are_explicit(self) -> None:
        text_explicit = (
            "제1조(판촉비)\n"
            "판촉비는 사전 서면 합의된 항목에 한하여 부담하며, 항목별 상한 및 정산 기준과 증빙을 명시한다.\n"
        )
        qs = generate_questions(
            entity="퍼시스",
            contract_type="대리점/유통",
            detected_rule_ids=["RISK-006"],
            contract_text=text_explicit,
            clause_results=[{"related_rules": [{"rule_id": "RISK-006"}]}],
            max_questions=5,
        )
        qids = [q.question_id for q in qs]
        self.assertNotIn("Q-CA-001-dealer-cost", qids)

        text_vague = "제1조(판촉비)\n판촉비는 을이 부담한다.\n"
        qs2 = generate_questions(
            entity="퍼시스",
            contract_type="대리점/유통",
            detected_rule_ids=["RISK-006"],
            contract_text=text_vague,
            clause_results=[{"related_rules": [{"rule_id": "RISK-006"}]}],
            max_questions=5,
        )
        qids2 = [q.question_id for q in qs2]
        self.assertIn("Q-CA-001-dealer-cost", qids2)

    def test_law_rerank_filters_noise_and_low_overlap(self) -> None:
        refs = [
            LawReference(
                source="q",
                target="law",
                title="하도급거래 공정화에 관한 법률",
                snippet="단가 감액 관련",
                identifiers={"ID": "1"},
                drf_detail_url="x",
            ),
            LawReference(
                source="q",
                target="law",
                title="서울특별시 조례안 입법예고",
                snippet="",
                identifiers={"ID": "2"},
                drf_detail_url="y",
            ),
            LawReference(
                source="q",
                target="law",
                title="채용 공고",
                snippet="",
                identifiers={"ID": "3"},
                drf_detail_url="z",
            ),
        ]
        rr = _rerank_and_filter_references(
            references=refs,
            context_text="하도급 단가 감액 사전 협의 서면 합의",
            matched_rules=[{"rule_id": "RISK-005", "matched_keywords": ["단가", "감액"]}],
            max_items=3,
            profile="generic",
        )
        titles = [r.title for r in rr]
        self.assertIn("하도급거래 공정화에 관한 법률", titles)
        self.assertNotIn("서울특별시 조례안 입법예고", titles)
        self.assertNotIn("채용 공고", titles)

    def test_rewrite_engine_produces_clause_specific_output_even_without_pattern_hit(self) -> None:
        proposal = propose_clause_specific_rewrite(
            clause_text="손해배상에 관한 조항이 있습니다.",
            applied_rules=[{"rule_id": "RISK-001", "matched_keywords": []}],
        )
        self.assertIsNotNone(proposal)
        self.assertIn("상한", proposal.suggested_rewrite)


if __name__ == "__main__":
    unittest.main()
