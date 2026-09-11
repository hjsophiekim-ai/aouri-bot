"""canonical 단일 사용 + 문제점·문안 일치 (2026-09-11 범용 보정 7개 항목).

  1. 역할·계약유형·적용법률은 확정된 canonical 값만 쓰고 재추론하지 않는다.
  2. 비적용 법률을 **근거로** 한 주장은 결과에 남지 않는다.
  3. 문제점과 수정문구의 법률효과가 다르면 즉시 hard fail.
  4. 다른 계약유형의 템플릿·문구가 섞이면 결과 생성 금지.
  5. 이미 보호조항이 있으면 중복 HIGH/MEDIUM 을 만들지 않는다.
  6. 우리에게 유리하고 위법하지 않은 조항은 KEEP.
  7. 최종 UI/DOCX 는 동일한 canonical finding 만 쓴다.
"""
from __future__ import annotations

import unittest

from runtime.review.accept_keep import (
    has_alternating_party_roles,
    weakens_our_favorable_clause,
)
from runtime.review.clause_direction import burden_direction
from runtime.review.cross_clause_protection import reconcile_absence_claims
from runtime.review.cross_type_template_gate import (
    enforce_no_cross_type_template,
    foreign_terms_in,
)
from runtime.review.finding_integrity_gates import enforce_clause_semantic_gate
from runtime.review.statute_applicability_gate import (
    StatuteDecision,
    deactivate_inapplicable_statute_findings,
)


class CanonicalStatuteReuseTest(unittest.TestCase):
    """항목 1·7 — 적용법률을 다운로드 경로에서 다시 판단하지 않는다."""

    def test_stored_decisions_are_restored_not_recomputed(self) -> None:
        from runtime.api.server import _statute_decisions_for

        meta = {"statute_applicability_gate": {"decisions": [{
            "statute": "하도급법",
            "conclusion": "비적용",
            "reason": "용역위탁 요건 미충족",
            "disabled_topics": ["하도급대금", "원사업자"],
            "facts_needed": [],
        }]}}
        decisions = _statute_decisions_for(
            meta, entity="일룸", text="영상 콘텐츠 제작 및 가구 공급", contract_type_code="",
        )
        self.assertEqual(len(decisions), 1, "저장된 판단 대신 6개 법률을 다시 평가했다")
        self.assertEqual(decisions[0].statute, "하도급법")
        self.assertTrue(decisions[0].blocked)
        self.assertIn("하도급대금", decisions[0].disabled_topics)

    def test_old_sessions_without_stored_decisions_still_get_a_judgment(self) -> None:
        from runtime.api.server import _statute_decisions_for

        decisions = _statute_decisions_for(
            None, entity="일룸", text="가구를 공급한다", contract_type_code="",
        )
        self.assertTrue(decisions, "저장값이 없으면 새로 판단해야 한다")


class InapplicableStatuteGroundsTest(unittest.TestCase):
    """항목 2 — 비적용 법률을 근거로 한 주장은 남지 않는다."""

    _NOT_APPLICABLE = [StatuteDecision(
        statute="하도급법",
        conclusion="비적용",
        reason="용역위탁 요건 미충족",
        disabled_topics=["하도급대금", "원사업자", "대물변제"],
    )]

    def test_ai_generated_statute_claim_is_removed_entirely(self) -> None:
        results = [{
            "clause_id": "ai-1",
            "problem": "하도급대금을 어음으로 지급하는 것은 위반 소지가 있습니다.",
            "risk_tier": "HIGH",
        }]
        removed = deactivate_inapplicable_statute_findings(results, self._NOT_APPLICABLE)
        self.assertEqual(len(removed), 1)
        self.assertEqual(results, [], "비적용 법률 근거 finding 이 남았다")

    def test_a_mere_fact_note_no_longer_escapes_the_gate(self) -> None:
        """종전에는 "확인이 필요합니다" 한 마디로 게이트를 빠져나갔다."""
        results = [{
            "clause_id": "ai-2",
            "problem": "원사업자 지위 해당 여부에 대한 확인이 필요합니다.",
            "risk_tier": "MEDIUM",
        }]
        removed = deactivate_inapplicable_statute_findings(results, self._NOT_APPLICABLE)
        self.assertEqual(len(removed), 1)
        self.assertEqual(results, [])

    def test_contract_grounded_risk_survives_without_the_statutory_ground(self) -> None:
        """근거를 차단하는 것과 위험을 지우는 것은 다르다.

        계약 원문을 직접 확인해 만든 지적은 그 법이 적용되지 않아도 계약상
        위험으로 성립한다 — 법률 근거만 떼어낸다.
        """
        results = [{
            "clause_id": "clr-1",
            "is_common_legal_risk": True,
            "rule_id": "clr_x",
            "original_text": "대금은 어음으로 지급할 수 있다.",
            "problem": "대금 지급수단이 어음으로 열려 있어 회수 위험이 있습니다. 하도급대금 지급기한 규정에도 저촉됩니다.",
            "suggested_rewrite": "대금은 현금으로 지급한다.",
            "risk_tier": "HIGH",
        }]
        removed = deactivate_inapplicable_statute_findings(results, self._NOT_APPLICABLE)
        self.assertEqual(removed, [], "계약상 위험까지 지웠다")
        self.assertEqual(len(results), 1)
        self.assertIn("하도급대금", results[0]["statute_grounds_removed"])
        self.assertNotIn("하도급대금", results[0]["problem"])
        self.assertIn("회수 위험", results[0]["problem"], "위험 설명이 사라졌다")
        self.assertEqual(
            results[0]["suggested_rewrite"], "대금은 현금으로 지급한다.",
            "조문 문안은 훼손하지 않는다",
        )


class SemanticHardFailTest(unittest.TestCase):
    """항목 3 — 효과 불일치는 유형과 무관하게 hard fail."""

    def _mismatched(self, cid: str) -> dict:
        return {
            "clause_id": cid,
            "original_text": "을은 대금을 청구할 수 없다.",
            "original_effect_tags": ["payment_obligation"],
            "rewrite_effect_tags": ["confidentiality"],
            "suggested_rewrite": "비밀유지 의무를 부담한다.",
            "risk_tier": "HIGH",
        }

    def test_every_contract_type_hard_fails(self) -> None:
        for code in ("", "nda_confidentiality", "advertising_content_production",
                     "construction", "dealer_agency", "license_ip"):
            with self.subTest(code=code):
                results = [self._mismatched("x")]
                report = enforce_clause_semantic_gate(results, contract_type_code=code)
                self.assertTrue(report["hard_delete"])
                self.assertEqual(results, [], f"{code} 에서 불일치 finding 이 남았다")


class CrossTypeTemplateGateTest(unittest.TestCase):
    """항목 4 — 타 유형 템플릿이 섞이면 결과에 넣지 않는다."""

    _BARTER = "본 계약은 가구를 공급하고 영상 콘텐츠 제작으로 대가를 갈음한다."

    def test_foreign_vocabulary_absent_from_the_contract_is_contamination(self) -> None:
        cr = {"clause_id": "x", "problem": "기성고에 따른 정산 기준이 없습니다."}
        terms = foreign_terms_in(
            cr, transaction_type="non_monetary_exchange", contract_text=self._BARTER,
        )
        self.assertIn("기성고", terms)

    def test_contaminated_finding_is_removed(self) -> None:
        results = [
            {"clause_id": "bad", "problem": "판매장려금 지급 기준이 불명확합니다."},
            {"clause_id": "good", "problem": "가구 인도 시점의 소유권 이전이 불명확합니다."},
        ]
        removed = enforce_no_cross_type_template(
            results, transaction_type="non_monetary_exchange", contract_text=self._BARTER,
        )
        self.assertEqual([r["clause_id"] for r in removed], ["bad"])
        self.assertEqual([r["clause_id"] for r in results], ["good"])

    def test_a_word_the_contract_itself_uses_is_not_contamination(self) -> None:
        body = self._BARTER + " 판매장려금은 지급하지 아니한다."
        results = [{"clause_id": "x", "problem": "판매장려금 조항의 의미가 불명확합니다."}]
        removed = enforce_no_cross_type_template(
            results, transaction_type="non_monetary_exchange", contract_text=body,
        )
        self.assertEqual(removed, [], "계약이 스스로 쓰는 단어를 혼입으로 봤다")


class DuplicateProtectionTest(unittest.TestCase):
    """항목 5 — 이미 보호조항이 있으면 HIGH/MEDIUM 을 만들지 않는다."""

    _CAPPED = (
        "제30조 [지체상금]\n"
        "1. 매 지체일수마다 지체상금률(1/1000)을 계약금액에 곱하여 산출한다.\n"
        "5. 지체상금으로 발생할 수 있는 최대금액은 계약금액의 10% 까지로 한다.\n"
    )

    def test_existing_protection_drops_the_finding_out_of_high_and_medium(self) -> None:
        cr = {
            "clause_id": "clr_late_penalty_rate_uncapped",
            "display_path": "제30조",
            "issue_title": "지체상금 누계 상한이 없음",
            "rewrite_reason": "지체상금에 누계 상한이 없어 무제한 누적된다.",
            "risk_tier": "HIGH",
            "severity": "HIGH",
        }
        report = reconcile_absence_claims([cr], contract_text=self._CAPPED)
        self.assertEqual(report["corrected_count"], 1)
        self.assertEqual(cr["risk_tier"], "LOW", "여전히 HIGH/MEDIUM 에 남아 있다")
        self.assertFalse(cr.get("dedup_suppressed"), "삭제하면 정합성 게이트가 깨진다")


class FavorableClauseKeepTest(unittest.TestCase):
    """항목 6 — 유리하고 적법한 조항에 없던 제한을 붙이지 않는다."""

    def test_adding_a_consultation_requirement_to_our_right_is_keep(self) -> None:
        original = "을은 갑에게 발생한 모든 손해를 배상하여야 한다."
        proposed = (
            "을은 갑에게 발생한 모든 손해를 배상하여야 한다. "
            "다만 배상 범위는 상호 협의하여 정한다."
        )
        self.assertTrue(
            weakens_our_favorable_clause(original, proposed, our_labels=("갑",))
        )

    def test_a_clause_we_bear_may_still_be_narrowed(self) -> None:
        original = "갑은 을에게 발생한 모든 손해를 배상하여야 한다."
        proposed = original + " 다만 배상은 귀책 범위 내로 한한다."
        self.assertEqual(burden_direction(original, ("갑",)), "we_bear")
        self.assertFalse(
            weakens_our_favorable_clause(original, proposed, our_labels=("갑",)),
            "우리가 부담자인 조항을 축소하는 것은 우리 이익이다",
        )

    def test_mutual_contracts_are_never_treated_as_favorable(self) -> None:
        """상호 NDA 는 조항 문면만 보면 상대방 부담으로 읽힌다."""
        body = (
            '"웹젠"과 "상대사" 중 "비밀정보"를 제공하는 자를 "제공자"라고 하고, '
            '제공받는 자를 "수신자"라고 한다. 양사가 상호 정보를 주고받을 때에는 '
            "해당 정보 별로 제공자와 수신자를 분별한다."
        )
        self.assertTrue(has_alternating_party_roles(body))
        original = '"수신자"는 본 계약 위반 시 손해를 배상하여야 한다.'
        proposed = original + " 다만 배상은 고의·중과실이 있는 경우에 한한다."
        self.assertFalse(
            weakens_our_favorable_clause(
                original, proposed, our_labels=("을", "퍼시스"), contract_text=body,
            ),
            "상호 계약을 우리에게 유리한 구조로 오판했다",
        )

    def test_our_burden_is_recognised_when_the_clause_uses_self_cost_wording(self) -> None:
        """"자신의 책임과 비용으로 … 이행하여야" 는 부담 문형이다.

        실측(웹젠 물품공급 제4조): 이 문형을 놓쳐 우리가 부담자인 하자담보
        조항이 "상대방 부담"으로 읽히고, 이를 제한하는 수정안이 KEEP 됐다.
        """
        original = (
            '"을"은 하자담보 기간 중 발생하는 모든 불량에 대하여 "을"은 자신의 '
            "책임과 비용으로 수리, 교환, 환불의 하자담보책임을 이행하여야 한다."
        )
        self.assertEqual(burden_direction(original, ("을", "퍼시스")), "we_bear")


if __name__ == "__main__":
    unittest.main()
