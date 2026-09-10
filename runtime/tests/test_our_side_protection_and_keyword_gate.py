"""우리측 유리조항 보호 + keyword-only matching 금지 회귀테스트 (2026-09-10 지시).

지시:
  · "우리 회사에 유리한 기존 조항을 약화시키지 말 것. 굳이 상대방 청구권이나
     비용청구권을 새로 열어주는 수정 금지."
  · "Keyword-only matching 금지 — 통지가 있다고 개인정보 finding 연결 금지."
  · "실제 거래와 모순되는 템플릿 금지."
  · "상기 제10조 참조 반복 삽입" 금지.
"""
from __future__ import annotations

import unittest

from runtime.review.clause_level import _apply_global_sentence_dedup
from runtime.review.our_side_protection import (
    detect_weakening,
    enforce_our_side_protection,
)
from runtime.review.senior_counsel_judgment import annotate_liability_nature

_NO_CLAIM_CLAUSE = (
    '"을사"는 어떠한 경우에도 본 계약을 이유로 "갑사"에게 제작비, 출연료, '
    "채널 운영비, 광고비 기타 명목의 금전 지급을 청구할 수 없다."
)


class OurSideProtectionTest(unittest.TestCase):
    def test_rewrite_reopening_a_foreclosed_claim_is_withdrawn(self) -> None:
        """원문이 상대방의 청구를 원천 차단하는데 수정안이 단서로 되살리면,
        협상 테이블에 우리 쪽 양보안을 먼저 들고 가는 셈이 된다."""
        cr = {
            "clause_id": "KR-5-p4",
            "original_text": _NO_CLAIM_CLAUSE,
            "risk_tier": "HIGH",
            "rewrite_reason": "정산 기준 미비",
            "suggested_rewrite": (
                _NO_CLAIM_CLAUSE
                + " 단, 쌍방이 사전에 서면으로 합의한 비용 항목에 한하여 증빙자료를 첨부한 "
                "경우에만 청구가 가능하며, 일방적 비용 전가는 금지된다."
            ),
        }
        withdrawn = enforce_our_side_protection([cr])
        self.assertEqual(len(withdrawn), 1)
        self.assertTrue(cr["our_side_right_protected"])
        # [2026-09-10 항목 7] 자리표시자를 남기지 않는다 — 약화 문안을 걷어내고
        # 우리 권리를 되돌리지 않는 최소수정안으로 교체한다.
        rewrite = str(cr["suggested_rewrite"] or "")
        self.assertNotIn("청구가 가능", rewrite, "약화 문안이 남았다")
        self.assertNotIn("[수정문안 보류]", rewrite)
        self.assertFalse(
            detect_weakening(_NO_CLAIM_CLAUSE, rewrite),
            "교체된 문안이 여전히 우리 권리를 약화시킨다",
        )

    def test_absolute_prohibition_qualified_by_any_proviso_is_weakening(self) -> None:
        """'청구가 가능' 이라는 말을 쓰지 않아도, 전면 금지에 단서를 달면
        조항은 조건부로 약해진다(실측 변형)."""
        proposed = (
            _NO_CLAIM_CLAUSE
            + " 단, 쌍방이 사전에 서면으로 합의한 비용 항목에 한하여, 항목별 상한, 정산 기준 및 "
            "증빙 자료를 명시하고, 일방의 동의 없는 비용 전가는 불가하다."
        )
        self.assertTrue(detect_weakening(_NO_CLAIM_CLAUSE, proposed))

    def test_proviso_on_a_non_absolute_prohibition_is_not_flagged(self) -> None:
        """전면 금지가 아닌 일반 부정형에까지 과잉 발동하지 않는다."""
        original = "을은 갑의 사전 서면 동의 없이 본건 콘텐츠를 제3자에게 제공할 수 없다."
        self.assertFalse(
            detect_weakening(original, original + " 다만 법령상 요구되는 경우에 한하여 제공할 수 있다.")
        )

    def test_neutral_rewrite_is_untouched(self) -> None:
        cr = {
            "clause_id": "KR-5-p4",
            "original_text": _NO_CLAIM_CLAUSE,
            "suggested_rewrite": _NO_CLAIM_CLAUSE + " 본 항은 계약 종료 후에도 존속한다.",
        }
        self.assertEqual(enforce_our_side_protection([cr]), [])
        self.assertIsNotNone(cr["suggested_rewrite"])

    def test_existing_exception_in_original_is_not_weakening(self) -> None:
        """원문이 이미 예외를 두고 있으면 계약이 그렇게 정한 것이다."""
        original = _NO_CLAIM_CLAUSE + " 다만 사전 합의한 비용은 청구할 수 있다."
        self.assertFalse(
            detect_weakening(original, original + " 단, 증빙을 첨부한 경우에만 청구가 가능하다.")
        )


class LegalComplianceOverridesOurSideProtectionTest(unittest.TestCase):
    """[2026-09-10 추가 지시] "우리에게 유리하니 그대로 두자"가 법을 어겨도
    된다는 뜻은 아니다. 우리 계약서가 하도급법·대리점법·대규모유통업법·
    공정거래법 등 강행법규에 어긋나게 갑질하는 내용이면, 유리하더라도 법령을
    준수하도록 고쳐야 한다."""

    def _weakening_finding(self, **kw) -> dict:
        cr = {
            "clause_id": "KR-5-p4",
            "original_text": _NO_CLAIM_CLAUSE,
            "suggested_rewrite": (
                _NO_CLAIM_CLAUSE + " 단, 수급사업자가 실제로 지출한 비용은 청구할 수 있다."
            ),
        }
        cr.update(kw)
        return cr

    def test_unlawful_favorable_clause_is_still_fixed(self) -> None:
        cr = self._weakening_finding(
            legal_business_reason=(
                "하도급법 제4조(부당한 하도급대금 결정 금지) 위반 소지 — 수급사업자에게 "
                "부당하게 비용을 전가하는 조항으로 시정명령 대상이 될 수 있습니다."
            ),
        )
        # 하도급법이 적용되는 계약(게이트가 '적용'으로 판단)
        withdrawn = enforce_our_side_protection(
            [cr], statute_decisions=[{"statute": "하도급법", "conclusion": "적용"}],
        )
        self.assertEqual(withdrawn, [], "강행법규 위반 시정은 보호 대상이 아니다")
        self.assertIsNotNone(cr["suggested_rewrite"], "법령 준수 수정안이 회수됐다")
        self.assertTrue(cr["legal_compliance_override"])

    def test_statute_ruled_inapplicable_cannot_justify_weakening(self) -> None:
        """비적용으로 확정된 법률을 근거로 우리 권리를 깎지 않는다."""
        cr = self._weakening_finding(
            legal_business_reason="하도급법 제4조 위반 소지가 있어 시정이 필요합니다.",
        )
        withdrawn = enforce_our_side_protection(
            [cr], statute_decisions=[{"statute": "하도급법", "conclusion": "비적용"}],
        )
        self.assertEqual(len(withdrawn), 1)
        self.assertFalse(
            detect_weakening(_NO_CLAIM_CLAUSE, str(cr["suggested_rewrite"] or "")),
            "비적용 법률을 근거로 우리 권리가 약화됐다",
        )

    def test_generic_fairness_critique_does_not_override(self) -> None:
        """'형평성·균형' 같은 일반론은 강행법규 근거가 아니다."""
        cr = self._weakening_finding(
            legal_business_reason="일방적이고 불균형한 조항이므로 형평성 차원에서 조정이 필요합니다.",
        )
        withdrawn = enforce_our_side_protection(
            [cr], statute_decisions=[{"statute": "하도급법", "conclusion": "적용"}],
        )
        self.assertEqual(len(withdrawn), 1)
        self.assertFalse(
            detect_weakening(_NO_CLAIM_CLAUSE, str(cr["suggested_rewrite"] or "")),
            "일반론을 근거로 우리 권리가 약화됐다",
        )

    def test_statute_named_without_violation_language_does_not_override(self) -> None:
        """법률명만 스쳐도 예외가 열리면 보호가 무력해진다."""
        cr = self._weakening_finding(
            legal_business_reason="공정거래법상 일반적인 거래관행을 참고하여 정산 절차를 보완합니다.",
        )
        withdrawn = enforce_our_side_protection(
            [cr], statute_decisions=[{"statute": "공정거래법", "conclusion": "적용"}],
        )
        self.assertEqual(len(withdrawn), 1)

    def test_undecided_statute_is_treated_as_potentially_applicable(self) -> None:
        """게이트가 판단하지 않은 법률은 '적용되지 않는다'는 뜻이 아니다."""
        cr = self._weakening_finding(
            legal_business_reason=(
                "대규모유통업법상 부당한 비용 전가에 해당하여 위법 소지가 있습니다."
            ),
        )
        withdrawn = enforce_our_side_protection([cr], statute_decisions=[])
        self.assertEqual(withdrawn, [])
        self.assertTrue(cr.get("legal_compliance_override"))


class GlobalSentenceDedupTest(unittest.TestCase):
    def test_duplicate_rewrite_is_suppressed_not_spliced_with_a_cross_reference(self) -> None:
        """수정문안은 상대방에게 그대로 건네는 조문 텍스트다. 그 안에 편집자
        주석("상기 제N조 참조")을 끼워 넣으면 협상에 쓸 수 없다(실측 문서에서
        16회 등장)."""
        shared = "당사자는 상대방에게 지체 없이 서면으로 통지하여야 하며, 필요한 자료를 제공한다."
        a = {"clause_id": "KR-10-p4", "article_number": "10", "display_path": "제10조 제4항",
             "suggested_rewrite": shared}
        b = {"clause_id": "KR-11-p2", "article_number": "11", "display_path": "제11조 제2항",
             "suggested_rewrite": shared}
        _apply_global_sentence_dedup([a, b])

        self.assertEqual(a["suggested_rewrite"], shared, "대표 항의 문안이 훼손됐다")
        self.assertEqual(b["suggested_rewrite"], shared, "수정문안 본문에 손대면 안 된다")
        self.assertNotIn("상기 제", str(a["suggested_rewrite"]))
        self.assertNotIn("상기 제", str(b["suggested_rewrite"]))
        self.assertTrue(b["dedup_suppressed"], "중복 항목은 목록에서 한 번만 보여야 한다")
        self.assertEqual(b["dedup_duplicate_of"], "KR-10-p4")

    def test_distinct_rewrites_are_both_kept(self) -> None:
        a = {"clause_id": "A", "suggested_rewrite": "당사자는 서면으로 통지하여야 한다. 통지 방법은 등기우편으로 한다."}
        b = {"clause_id": "B", "suggested_rewrite": "손해배상의 범위는 직접손해로 한정하며 총액 상한을 둔다."}
        _apply_global_sentence_dedup([a, b])
        self.assertFalse(a.get("dedup_suppressed"))
        self.assertFalse(b.get("dedup_suppressed"))


class StatutoryNoteTest(unittest.TestCase):
    def test_privacy_finding_does_not_get_safety_law_boilerplate(self) -> None:
        """개인정보 과징금 때문에 걸린 항목에 산업안전보건법·중대재해처벌법
        설명이 붙어서는 안 된다(실측: 영상 콘텐츠 바터 계약의 초상권 항목)."""
        cr = {
            "clause_id": "KR-10-p1",
            "problem": "개인정보 보호법 위반 시 과징금이 부과될 수 있다",
            "legal_business_reason": "개인정보보호법 제17조(제3자 제공)",
        }
        annotate_liability_nature([cr])
        note = str(cr["legal_business_reason"])
        self.assertIn("개인정보 보호법상 개인정보처리자의 의무", note)
        self.assertNotIn("산업안전보건법", note)
        self.assertNotIn("중대재해", note)

    def test_safety_finding_still_names_safety_statutes(self) -> None:
        cr = {
            "clause_id": "KR-8-p1",
            "problem": "산업안전보건법상 사업주 의무를 수급인에게 전가한다",
            "legal_business_reason": "안전 비용은 수급인이 부담한다",
        }
        annotate_liability_nature([cr])
        self.assertIn("산업안전보건법", str(cr["legal_business_reason"]))

    def test_annotation_is_idempotent_across_statute_families(self) -> None:
        """설명문 자체가 법률명을 담고 있어, 두 번째 호출에서 그것까지
        매칭되면 지목 법률이 늘고 문단이 두 번 붙는다."""
        cr = {
            "clause_id": "x",
            "problem": "개인정보 보호법 위반 시 과징금",
            "legal_business_reason": "기존 설명.",
        }
        annotate_liability_nature([cr])
        first = cr["legal_business_reason"]
        annotate_liability_nature([cr])
        self.assertEqual(cr["legal_business_reason"], first)


if __name__ == "__main__":
    unittest.main()
