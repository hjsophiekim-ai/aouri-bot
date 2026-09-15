"""조항 Hallucination Gate 2차 보정 (2026-09-15).

1차가 "없는 조항을 만들어내지 않는가" 였다면, 2차는 두 가지를 더 본다.

  · 조항번호 검증이 **모든 참조 경로**에 걸리는가 — 관련 조항, 함께 수정할
    조항, 사용자 요청 매핑, 협상포지션, UI/DOCX.
  · 번호가 **실재하더라도** 그 조항이 finding 과 다른 이야기를 하면 잡히는가
    (SEMANTIC_ANCHOR_MISMATCH).

실측 출발점: 표시 경로를 "제11조 신설" 로 정정하고도 `related_clauses` 에는
["제12조 제3항"] 이 그대로 남아, 화면의 "관련 조항" 칸에 존재하지 않는 조항이
계속 노출됐다.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from runtime.review.clause_extraction import extract_clauses
from runtime.review.clause_index import build_clause_index
from runtime.review.existence_gate import (
    STATUS_SEMANTIC_ANCHOR_MISMATCH,
    anchored_article,
    enforce_existence_gate,
    enforce_semantic_anchor,
    enforce_title_consistency,
    prune_reference_lists,
    scrub_meta_references,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
GOLDEN = FIXTURES / "sns_marketing_partnership.txt"


def _index():
    text = GOLDEN.read_text(encoding="utf-8")
    extracted = extract_clauses(text)
    clauses = extracted[0] if isinstance(extracted, tuple) else extracted
    return build_clause_index(text, clauses)


class ReferenceListPruningTest(unittest.TestCase):
    """지시 1항 — 수정 위치뿐 아니라 모든 clause reference 에 같은 검증."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.index = _index()

    def test_related_clauses_lose_the_fabricated_number(self) -> None:
        cr = {
            "clause_id": "CP-006",
            "risk_tier": "MEDIUM",
            "clause_ids": ["제12조 제3항"],
            "related_clauses": ["제12조 제3항", "제4조"],
            "clause_title": "제12조 제3항",
            "issue_title": "제12조 제3항 — 해지 시 정산 기준 보완 필요",
            "problem": "해지 시 정산 기준이 없습니다.",
            "checklist_status": "absent",
        }
        enforce_existence_gate([cr], self.index)
        blob = str(cr.get("related_clauses")) + str(cr.get("clause_ids"))
        self.assertNotIn("제12조", blob, "관련 조항 목록에 없는 조항이 남았다")
        self.assertIn("제4조", cr["related_clauses"], "실재하는 조항까지 지우면 안 된다")

    def test_negotiation_position_is_checked(self) -> None:
        """협상포지션은 담당자가 그대로 들고 가는 줄이다."""
        cr = {
            "clause_id": "N-1", "risk_tier": "HIGH",
            "issue_title": "손해배상 상한",
            "problem": "배상 상한이 없습니다.",
            "negotiation_position": "제14조의 배상 상한을 계약금액으로 제한할 것을 요구.",
        }
        report = enforce_existence_gate([cr], self.index)
        self.assertTrue(report["violations"], "협상포지션의 없는 조항을 못 잡았다")
        self.assertNotIn("제14조", str(cr.get("negotiation_position")))

    def test_prune_keeps_valid_entries_and_dedupes(self) -> None:
        cr = {"related_clauses": ["제12조", "제3조", "제12조"]}
        prune_reference_lists(cr, ["12"], replacement="제11조")
        self.assertEqual(cr["related_clauses"], ["제11조 신설", "제3조"])

    def test_meta_mapping_tables_are_scrubbed(self) -> None:
        meta = {
            "user_focus_mapping_table": [
                {"issue": "해지 정산", "clause": "제12조 제3항"},
                {"issue": "관할", "clause": "제9조"},
            ],
            "user_focus_clause_ids": ["제14조", "제5조"],
        }
        scrub_meta_references(meta, self.index)
        blob = str(meta)
        self.assertNotIn("제12조", blob)
        self.assertNotIn("제14조", blob)
        self.assertIn("제9조", blob, "실재하는 조항 매핑은 남아야 한다")


class StatuteCitationTest(unittest.TestCase):
    """법령 인용을 계약 조항으로 오인하면 정당한 논점이 통째로 사라진다.

    실측(실제 계약 AI 검증): 법률명이 조 번호 **바로 앞**에 붙은 형태만 인용으로
    인정한 탓에, 세무·저작권 논점 3건이 삭제됐다.
        "저작권법, 제46조"             → 인정
        "저작권법상 … 제22조에"         → 놓침 → 삭제
        "저작권법에 따르면 … 제46조에서" → 놓침 → 삭제
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.index = _index()

    def _reason(self, text: str) -> list:
        from runtime.review.existence_gate import verify_finding
        return verify_finding(
            {"clause_id": "T", "risk_tier": "HIGH", "legal_business_reason": text},
            self.index,
        )

    def test_statute_citations_in_prose_survive(self) -> None:
        for citation in (
            "저작권법, 제46조에 따라 별도 특약이 필요합니다.",
            "저작권법 제46조에 따라 별도 특약이 필요합니다.",
            "「저작권법」 제46조에 따라 별도 특약이 필요합니다.",
            "저작권법상 2차적저작물작성권은 제22조에 규정되어 있습니다.",
            "저작권법에 따르면 2차적저작물작성권의 양도는 제46조에서 별도로 정하고 있습니다.",
            "세금계산서 발행 시기는 부가가치세법 제34조 및 동법 시행령에 따릅니다.",
            "부가가치세법 시행령 제61조의 공급가액 산정 기준을 확인해야 합니다.",
        ):
            self.assertEqual(self._reason(citation), [], citation)

    def test_prose_without_a_statute_is_still_checked(self) -> None:
        """본문이라고 무조건 봐주지는 않는다."""
        self.assertTrue(
            self._reason("제12조의 정산 기준이 불명확합니다."),
            "법령이 없는 문장의 없는 조항을 놓쳤다",
        )

    def test_display_fields_stay_strict(self) -> None:
        """표시·목록 필드의 조 번호는 계약 조항 포인터다 — 문장범위 완화 없음."""
        from runtime.review.existence_gate import verify_finding
        for cr in (
            {"clause_id": "D1", "risk_tier": "HIGH",
             "issue_title": "저작권법에 따라 제12조 제3항을 보완"},
            {"clause_id": "D2", "risk_tier": "HIGH", "display_path": "제14조"},
            {"clause_id": "D3", "risk_tier": "HIGH", "related_clauses": ["제11조"]},
        ):
            self.assertTrue(verify_finding(cr, self.index), str(cr))


class SemanticAnchorTest(unittest.TestCase):
    """지시 2·3항 — 번호가 실재해도 조항이 다른 이야기를 하면 연결을 끊는다."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.index = _index()

    def _ip_finding_on_dispute_clause(self) -> dict:
        # 이 계약의 제9조는 "분쟁 해결 및 관할" 이다. 저작권 지적이 걸릴 곳이 아니다.
        return {
            "clause_id": "X-1", "risk_tier": "HIGH",
            "article_number": "9", "display_path": "제9조", "clause_title": "제9조",
            "issue_title": "저작재산권 양도 범위 불명확",
            "problem": "저작재산권과 2차적저작물작성권의 양도 범위가 불명확합니다.",
            "suggested_rewrite": "산출물의 저작재산권은 갑에게 양도한다.",
            "related_clauses": ["제9조"],
        }

    def test_mismatched_anchor_is_detached(self) -> None:
        cr = self._ip_finding_on_dispute_clause()
        report = enforce_semantic_anchor([cr], self.index)
        self.assertEqual(report["status"], STATUS_SEMANTIC_ANCHOR_MISMATCH)
        entry = report["mismatches"][0]
        self.assertEqual(entry["anchored_article"], "제9조")
        self.assertEqual(entry["anchored_title"], "분쟁 해결 및 관할")
        self.assertEqual(entry["remediation"], "anchor_detached")
        self.assertTrue(cr["clause_reference_unresolved"])
        self.assertIsNone(cr["article_number"])
        self.assertEqual(cr["related_clauses"], [])

    def test_detached_anchor_is_not_remapped_to_another_clause(self) -> None:
        """맞는 조항을 임의로 찾아 옮겨 붙이지 않는다 — 그것도 추측이다."""
        cr = self._ip_finding_on_dispute_clause()
        enforce_semantic_anchor([cr], self.index)
        self.assertEqual(cr["display_path"], "조항 위치 확인 필요")
        # 이 계약의 저작권 조항인 제5조로 몰래 옮기지 않았는지 확인한다.
        self.assertNotIn("제5조", str(cr.get("display_path")) + str(cr.get("clause_title")))

    def test_detached_anchor_does_not_become_a_new_clause(self) -> None:
        """조항이 실재하므로 신설로 돌리면 중복 조항을 권고하게 된다."""
        cr = self._ip_finding_on_dispute_clause()
        cr["problem"] = "저작재산권 양도 범위에 관한 규정이 없습니다."  # 부재 표현
        enforce_semantic_anchor([cr], self.index)
        self.assertFalse(cr.get("is_new_clause"))
        self.assertNotIn("신설", str(cr.get("display_path")))

    def test_matching_anchor_is_untouched(self) -> None:
        cr = {
            "clause_id": "X-2", "risk_tier": "HIGH",
            "article_number": "9", "display_path": "제9조",
            "issue_title": "관할 합의",
            "problem": "분쟁 발생 시 관할 법원이 상대방 소재지로 되어 있습니다.",
            "suggested_rewrite": "제1심 관할 법원은 서울중앙지방법원으로 한다.",
        }
        report = enforce_semantic_anchor([cr], self.index)
        self.assertEqual(report["mismatches"], [])
        self.assertEqual(cr["display_path"], "제9조")

    def test_finding_quoting_the_clause_is_untouched(self) -> None:
        """그 조항의 문언을 실제로 인용하고 있으면 연결은 옳다."""
        article5 = self.index.articles["5"].exact_text
        cr = {
            "clause_id": "X-3", "risk_tier": "HIGH",
            "article_number": "5", "display_path": "제5조",
            "issue_title": "대금 지급 지연",
            "problem": "지급 지연에 대한 이자 규정이 없습니다.",
            "original_text": article5[:80],
        }
        self.assertEqual(enforce_semantic_anchor([cr], self.index)["mismatches"], [])

    def test_new_clause_items_are_skipped(self) -> None:
        cr = {
            "clause_id": "X-4", "risk_tier": "MEDIUM",
            "is_new_clause": True, "display_path": "제11조 신설",
            "issue_title": "비밀유지 조항 신설",
        }
        self.assertEqual(enforce_semantic_anchor([cr], self.index)["mismatches"], [])

    def test_anchor_detection(self) -> None:
        self.assertEqual(anchored_article({"article_number": "7"}), "7")
        self.assertEqual(anchored_article({"display_path": "제3조 제2항"}), "3")
        self.assertEqual(anchored_article({"clause_id": "eb_x__KR-5"}), "5")
        self.assertEqual(anchored_article({"display_path": "제11조 신설"}), "")

    def test_uncertain_structure_suspends_the_check(self) -> None:
        index = build_clause_index("깨진 스캔 문서", [])
        cr = self._ip_finding_on_dispute_clause()
        self.assertEqual(enforce_semantic_anchor([cr], index)["mismatches"], [])
        self.assertIsNone(cr.get("clause_reference_unresolved"))


class GoldenPipelineSecondPassTest(unittest.TestCase):
    """지시 4·5항 — 계약유형 상태 모순 제거 + 제11조 이상은 신설로만."""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.rules.loader import RuleLoader
        from runtime.review.clause_level import build_clause_level_result
        from runtime.services.query_service import RuleQueryService

        loader = RuleLoader()
        loader.load()
        cls.bundle = build_clause_level_result(
            service=RuleQueryService(loader),
            entity="일룸",
            contract_type="마케팅계약서",
            text=GOLDEN.read_text(encoding="utf-8"),
            filename="sns_marketing_partnership.txt",
            answers=None, review_focus=None, law_service=None,
            ai_provider=None, ai_model="", ai_timeout_sec=60.0,
            ai_max_tokens=2000, ai_temperature=0.1,
        )

    def test_confirmed_type_and_uncertain_status_never_coexist(self) -> None:
        meta = self.bundle.meta
        self.assertTrue(
            meta.get("canonical_contract_type_confirmed"),
            "이 계약은 유형이 확정된다",
        )
        self.assertNotIn(
            str(meta.get("review_status") or ""),
            ("REVIEW_FAILED_CONTRACT_TYPE_UNCERTAIN", "REVIEW_FAILED_TYPE_UNCERTAIN"),
            "유형이 확정됐는데 '계약유형 미확정' 상태가 함께 서 있다",
        )

    def test_articles_above_ten_appear_only_as_new_clauses(self) -> None:
        """지시 5항 — 이 계약의 기존 조항은 제10조까지가 전부다."""
        import re

        statute = re.compile(r"(?:법|법률|령|규칙|약관|」|\))\s*[,、·:：]?$")
        offenders: list[str] = []
        fields = (
            "issue_title", "clause_title", "display_path", "problem",
            "suggested_rewrite", "recommendation_text", "original_text",
            "negotiation_position",
        )
        for cr in self.bundle.clause_results:
            if not isinstance(cr, dict) or cr.get("dedup_suppressed"):
                continue
            values = [str(cr.get(f) or "") for f in fields]
            for key in ("related_clauses", "clause_ids"):
                entries = cr.get(key)
                if isinstance(entries, list):
                    values.extend(str(x or "") for x in entries)
            for value in values:
                for m in re.finditer(r"제\s*(\d{1,3})\s*조", value):
                    if int(m.group(1)) <= 10:
                        continue
                    if statute.search(value[max(0, m.start() - 20): m.start()].rstrip()):
                        continue
                    if "신설" in value[max(0, m.start() - 30): m.start() + 30]:
                        continue
                    offenders.append(f"{cr.get('clause_id')}: {value[:70]}")
        self.assertEqual(offenders, [], "제11조 이상이 기존 조항처럼 쓰였다")

    def test_findings_survive(self) -> None:
        final = self.bundle.meta.get("final_findings") or {}
        total = int(final.get("high_count") or 0) + int(final.get("medium_count") or 0)
        self.assertGreater(total, 0, "2차 게이트가 결과를 통째로 지웠다")


if __name__ == "__main__":
    unittest.main()
