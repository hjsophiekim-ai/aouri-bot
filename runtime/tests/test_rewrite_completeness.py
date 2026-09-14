"""수정문안은 복사해서 그대로 넣을 수 있어야 한다 (2026-09-14 지시).

MEDIUM 도 HIGH 와 같은 기준이다. "~를 명시한다", "~를 보완한다",
"담당 변호사가 확정" 같은 설명형 문구는 완성 문구가 아니다.
"""
from __future__ import annotations

import unittest

from runtime.review.minimal_edit import _ADDITION_WHEN_UNKNOWN
from runtime.review.rewrite_completeness import (
    STATUS_INCOMPLETE_REWRITE,
    enforce_rewrite_completeness,
    is_descriptive_only,
    merge_duplicate_rewrites,
)

#: 실제 계약에 그대로 들어가는 조문(체크리스트 CP-008 템플릿).
REAL_CLAUSE = (
    "을은 갑의 사전 서면 동의 없이 본 계약에 따라 제작된 콘텐츠, 시안, 촬영물, 작업 과정, "
    "갑의 브랜드명·상표·제품명 또는 본 계약 수행 사실을 자신의 포트폴리오, 홈페이지, SNS, "
    "보도자료, 영업자료 또는 제3자 제안자료에 사용하거나 공개할 수 없다."
)


class DescriptiveDetectionTest(unittest.TestCase):
    def test_real_clause_is_complete(self) -> None:
        self.assertFalse(is_descriptive_only(REAL_CLAUSE))

    def test_descriptive_sentences_are_rejected(self) -> None:
        for text in (
            "해지 사유와 절차, 해지의 효력이 미치는 범위를 본조에 명시한다.",
            "검수 기준을 보완한다.",
            "업무의 범위·산출물·완료 기준을 본조 또는 별첨으로 특정한다.",
        ):
            self.assertTrue(is_descriptive_only(text), text)

    def test_forbidden_placeholders_are_rejected(self) -> None:
        for text in (
            "[수정문안 보류] 담당 변호사가 직접 확정해야 합니다.",
            "추후 협의하여 정한다.",
            "수정 문구 자동생성 보류: 조항 정체성 확인 필요",
            "TBD",
        ):
            self.assertTrue(is_descriptive_only(text), text)

    def test_empty_is_rejected(self) -> None:
        self.assertTrue(is_descriptive_only(""))
        self.assertTrue(is_descriptive_only(None))  # type: ignore[arg-type]

    def test_prohibition_clause_counts_as_normative(self) -> None:
        """"…할 수 없다" 로 끝나는 금지 조문도 완성 조문이다.

        1차 구현이 이 어미를 규범 어미로 보지 않아, 완성된 143자 조문(CP-008)을
        설명형으로 오판했다.
        """
        self.assertFalse(is_descriptive_only(REAL_CLAUSE))


class MinimalEditTemplateTest(unittest.TestCase):
    def test_neutral_templates_are_real_clauses(self) -> None:
        """방향 미상일 때 쓰는 문구도 전부 조문이어야 한다.

        종전에는 전부 "…를 본조에 명시한다" 였다 — 담당자가 받아서 다시
        조문을 써야 하는 설명문이었다.
        """
        bad = [
            key for key, text in _ADDITION_WHEN_UNKNOWN.items()
            if is_descriptive_only(text)
        ]
        self.assertEqual(bad, [], "설명형으로 남은 효과 범주")


class CompletenessGateTest(unittest.TestCase):
    def test_incomplete_medium_is_flagged_but_not_deleted(self) -> None:
        cr = {
            "clause_id": "M-1", "risk_tier": "MEDIUM",
            "issue_title": "해지 정산 기준 부재",
            "suggested_rewrite": "해지 사유와 절차를 본조에 명시한다.",
        }
        results = [cr]
        report = enforce_rewrite_completeness(results)
        self.assertEqual(report["status"], STATUS_INCOMPLETE_REWRITE)
        self.assertEqual(len(results), 1, "지적 자체는 지우지 않는다")
        self.assertTrue(cr["incomplete_rewrite"])
        self.assertEqual(report["incomplete"][0]["risk_tier"], "MEDIUM")

    def test_complete_medium_passes(self) -> None:
        cr = {
            "clause_id": "M-2", "risk_tier": "MEDIUM",
            "issue_title": "포트폴리오 공개 제한",
            "suggested_rewrite": REAL_CLAUSE,
        }
        report = enforce_rewrite_completeness([cr])
        self.assertEqual(report["status"], "")
        self.assertNotIn("incomplete_rewrite", cr)

    def test_keep_as_is_items_need_no_clause_text(self) -> None:
        cr = {
            "clause_id": "K-1", "risk_tier": "MEDIUM",
            "keep_as_is": True, "recommendation_text": "현행 유지",
        }
        self.assertEqual(enforce_rewrite_completeness([cr])["incomplete"], [])

    def test_identical_rewrites_are_merged_into_one(self) -> None:
        a = {"clause_id": "A", "risk_tier": "MEDIUM", "suggested_rewrite": REAL_CLAUSE}
        b = {"clause_id": "B", "risk_tier": "HIGH", "suggested_rewrite": REAL_CLAUSE}
        results = [a, b]
        merged = merge_duplicate_rewrites(results)
        self.assertEqual(len(merged), 1)
        # 등급이 높은 쪽이 남는다.
        self.assertTrue(a.get("dedup_suppressed"))
        self.assertFalse(b.get("dedup_suppressed"))
        self.assertIn("A", b.get("merged_clause_ids") or [])

    def test_different_rewrites_are_not_merged(self) -> None:
        a = {"clause_id": "A", "risk_tier": "MEDIUM", "suggested_rewrite": REAL_CLAUSE}
        b = {
            "clause_id": "B", "risk_tier": "MEDIUM",
            "suggested_rewrite": REAL_CLAUSE.replace("포트폴리오", "제안서"),
        }
        self.assertEqual(merge_duplicate_rewrites([a, b]), [])
        self.assertFalse(a.get("dedup_suppressed"))
        self.assertFalse(b.get("dedup_suppressed"))


if __name__ == "__main__":
    unittest.main()
