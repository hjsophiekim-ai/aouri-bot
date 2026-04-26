from __future__ import annotations

import unittest

from runtime.law.search_service import LawReference, _rerank_and_filter_references


class LawSearchRerankTest(unittest.TestCase):
    def test_rerank_filters_noise_and_low_relevance(self) -> None:
        refs = [
            LawReference(
                source="대리점법 판촉비",
                target="law",
                title="대리점거래의 공정화에 관한 법률",
                snippet="판매장려금 및 판촉비 관련",
                identifiers={},
                drf_detail_url="u1",
            ),
            LawReference(
                source="대리점법 판촉비",
                target="prec",
                title="광고 안내",
                snippet="홍보 자료",
                identifiers={},
                drf_detail_url="u2",
            ),
            LawReference(
                source="대리점법 판촉비",
                target="law",
                title="근로기준법",
                snippet="해고",
                identifiers={},
                drf_detail_url="u3",
            ),
        ]
        ctx = "위탁판매 대리점 계약이며 판촉비 및 판매장려금 비용 전가가 문제된다."
        ranked = _rerank_and_filter_references(references=refs, context_text=ctx, matched_rules=[{"rule_id": "RISK-006", "matched_keywords": ["판촉비"]}], max_items=3)
        titles = [r.title for r in ranked]
        self.assertIn("대리점거래의 공정화에 관한 법률", titles)
        self.assertNotIn("광고 안내", titles)


if __name__ == "__main__":
    unittest.main()

