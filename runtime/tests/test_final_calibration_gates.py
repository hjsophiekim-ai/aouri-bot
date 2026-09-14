"""2026-09-14 범용 최종보정 지시 5개 항목의 회귀 테스트.

    1. 문제점 ↔ 법적 이유 ↔ 수정문구가 같은 법률효과를 다뤄야 한다
    2. 비적용 법률은 downstream(협상포지션·제목까지) 완전 차단
    3. KEEP/보류 판단은 HIGH/MEDIUM 목록에서 제거
    4. 계약 역할이 실제 거래구조와 어긋나면 결과 생성 금지
    5. 최종 출력 전 교차 정합성 self-check

각 테스트는 **지시가 든 예시**를 그대로 재현한다. 그리고 같은 수만큼
"이건 지우면 안 된다" 쪽도 함께 둔다 — 이 게이트들의 실패 양식은 못 잡는
것이 아니라 **정당한 검토의견을 지우는 것**이기 때문이다(v8 아키텍처 지시:
게이트를 조일 때 과차단을 반드시 교차 확인할 것).
"""
from __future__ import annotations

import unittest

from runtime.review.accept_keep import enforce_keep_verdict_removal
from runtime.review.counterparty_role_gate import (
    REVIEW_BLOCKED_ROLE_STRUCTURE_MISMATCH,
    declared_our_side,
    enforce_role_matches_transaction_structure,
)
from runtime.review.delivery_gate import NON_REMEDIABLE_STATUSES
from runtime.review.final_counsel_gate import run_final_counsel_gate
from runtime.review.finding_coherence import (
    STATUS_SEMANTIC_MISMATCH,
    assess_finding_coherence,
    enforce_finding_coherence,
)
from runtime.review.output_filter import build_final_findings
from runtime.review.statute_applicability_gate import (
    StatuteDecision,
    scrub_inapplicable_statutes,
)


# ── 항목 1. finding 내부 정합성 ────────────────────────────────────────────

class FindingCoherenceTest(unittest.TestCase):
    def test_additional_work_issue_with_copyright_rewrite_is_removed(self) -> None:
        """지시의 예 그대로 — 추가과업 이슈에 저작권 문구가 붙으면 제외한다."""
        cr = {
            "clause_id": "AI-1",
            "risk_tier": "HIGH",
            "issue_title": "추가 과업 범위 변경 절차 미비",
            "problem": "갑이 추가 과업을 요구할 수 있으나 대가 조정 절차가 없습니다.",
            "suggested_rewrite": "본 계약에 따른 산출물의 저작재산권은 갑에게 양도한다.",
        }
        results = [cr]
        report = enforce_finding_coherence(results)
        self.assertEqual(results, [], "혼입된 finding 이 남았다")
        self.assertEqual(report["status"], STATUS_SEMANTIC_MISMATCH)
        self.assertEqual(report["removed_count"], 1)
        self.assertEqual(report["mismatches"][0]["axis"], "problem_vs_rewrite")

    def test_delivery_issue_with_content_inspection_rewrite_is_removed(self) -> None:
        """지시의 예 그대로 — 제품 인도 이슈에 콘텐츠 검수 문구는 넣지 않는다."""
        cr = {
            "clause_id": "AI-2",
            "risk_tier": "HIGH",
            "issue_title": "지체상금 상한 부재",
            "problem": "납품 지연 시 지체상금에 상한이 없어 위약금이 무한히 누적됩니다.",
            "suggested_rewrite": (
                "갑은 콘텐츠 수령일로부터 10영업일 이내에 검수 결과를 통보하며, "
                "수정 요청 횟수는 2회로 한정한다."
            ),
        }
        results = [cr]
        report = enforce_finding_coherence(results)
        self.assertEqual(results, [])
        self.assertEqual(report["mismatches"][0]["axis"], "problem_vs_rewrite")

    def test_coherent_finding_survives(self) -> None:
        cr = {
            "clause_id": "AI-3",
            "risk_tier": "HIGH",
            "issue_title": "추가 과업 범위 변경 절차 미비",
            "problem": "갑이 추가 과업을 요구할 수 있으나 대가 조정 절차가 없습니다.",
            "suggested_rewrite": (
                "추가 과업이 필요한 경우 을은 과업 범위와 추가 비용을 기재한 "
                "변경요청서를 제출하고 갑의 서면 승인을 받은 후에만 수행한다."
            ),
        }
        results = [cr]
        report = enforce_finding_coherence(results)
        self.assertEqual(len(results), 1, "정합한 finding 이 지워졌다")
        self.assertEqual(report["mismatches"], [])

    def test_contract_grounded_rule_keeps_the_problem_and_only_loses_the_text(self) -> None:
        """계약 문언을 직접 확인해 만든 rule 은 문제 제기가 유효하다 — 문안만 회수."""
        cr = {
            "clause_id": "clr_x",
            "is_common_legal_risk": True,
            "risk_tier": "HIGH",
            "issue_title": "추가 과업 범위 변경 절차 미비",
            "problem": "갑이 추가 과업을 요구할 수 있으나 대가 조정 절차가 없습니다.",
            "original_text": "갑은 을에게 추가 과업을 요구할 수 있다.",
            "suggested_rewrite": "본 계약에 따른 산출물의 저작재산권은 갑에게 양도한다.",
        }
        results = [cr]
        report = enforce_finding_coherence(results)
        self.assertEqual(len(results), 1, "결정론적 rule 이 통째로 삭제됐다")
        self.assertEqual(report["withdrawn_count"], 1)
        self.assertEqual(report["removed_count"], 0)
        self.assertNotEqual(
            cr.get("suggested_rewrite"),
            "본 계약에 따른 산출물의 저작재산권은 갑에게 양도한다.",
            "어긋난 문안이 그대로 남았다",
        )

    def test_original_text_echoed_into_recommendation_is_not_a_proposal(self) -> None:
        """제안 문안 자리에 원문이 그대로 들어와 있으면 비교 대상이 아니다.

        실측(영문 라이선스 계약): 효과 기반 finding 의 recommendation_text 에
        Article 1 전문이 들어와 있어, 그 조항의 온갖 효과가 "제안된 효과" 로
        잡히면서 정상 finding 이 삭제됐다.
        """
        original = (
            "Licensor grants to Teknion an exclusive license to assemble, market, "
            "distribute and service the Products in the Territory, and Teknion shall "
            "pay royalties as set out in Attachment B."
        )
        cr = {
            "clause_id": "eb_payment",
            "risk_tier": "MEDIUM",
            "issue_title": "지연이자 규정 부재",
            "problem": "대금 지급이 지연되어도 지연이자를 청구할 근거가 없습니다.",
            "original_text": original,
            "recommendation_text": original,
        }
        results = [cr]
        enforce_finding_coherence(results)
        self.assertEqual(len(results), 1, "원문 반향을 제안으로 오인해 삭제했다")

    def test_minimal_edit_appendix_is_compared_not_the_whole_clause(self) -> None:
        """최소수정안은 "원문 + 덧붙인 문장" 이다 — 비교 대상은 덧붙인 쪽이다."""
        original = "제9조(저작권), 제10조(초상권), 제12조(비밀유지)는 계약 종료 후에도 존속한다."
        cr = {
            "clause_id": "eb_privacy",
            "risk_tier": "MEDIUM",
            "issue_title": "개인정보 처리 근거 미규정",
            "problem": "개인정보의 수집·이용 목적, 항목, 보유기간이 규정되어 있지 않습니다.",
            "original_text": original,
            "recommendation_text": (
                original
                + " 개인정보의 수집·이용 목적, 항목, 보유기간 및 제3자 제공의 근거를 본조에 명시한다."
            ),
        }
        results = [cr]
        enforce_finding_coherence(results)
        self.assertEqual(len(results), 1, "덧붙인 문장 대신 원문을 태깅해 삭제했다")

    def test_reason_axis_is_recorded_but_never_deletes(self) -> None:
        """법적 이유는 리스크 사슬을 설명하느라 다른 영역으로 번진다 — 기록만."""
        cr = {
            "clause_id": "eb_acceptance",
            "risk_tier": "MEDIUM",
            "issue_title": "검수 판정 기준 미특정",
            "problem": "검수의 기준과 합격 간주 요건이 특정되지 않았습니다.",
            "legal_business_reason": "판정 기준이 없으면 대금 지급이 지연됩니다.",
            "suggested_rewrite": "검수의 기준·기한과 합격 간주의 요건을 본조에 명시한다.",
        }
        verdict = assess_finding_coherence(cr)
        self.assertFalse(verdict["mismatch"], "법적 이유 축이 삭제 사유로 쓰였다")
        results = [cr]
        report = enforce_finding_coherence(results)
        self.assertEqual(len(results), 1)
        self.assertEqual(report["mismatches"], [])


# ── 항목 2. 비적용 법률 downstream 차단 ────────────────────────────────────

class InapplicableStatuteScrubTest(unittest.TestCase):
    DECISION = StatuteDecision(
        statute="하도급법",
        conclusion="비적용",
        reason="우리가 그 용역업을 업으로 영위하지 않습니다.",
        disabled_topics=["하도급법", "하도급대금", "원사업자"],
    )

    def test_statute_name_is_removed_from_title_and_negotiation_position(self) -> None:
        cr = {
            "clause_id": "X-1",
            "issue_title": "하도급법상 대금 지급기한 위반",
            "negotiation_position": "하도급법 위반이라는 점을 근거로 60일 지급기한을 요구.",
            "problem": "대금 지급기한이 90일입니다.",
        }
        changed = scrub_inapplicable_statutes([cr], [self.DECISION])
        self.assertTrue(changed)
        self.assertNotIn("하도급법", cr["issue_title"])
        self.assertNotIn("하도급법", cr["negotiation_position"], "협상포지션에 법률명이 남았다")

    def test_contract_wording_in_the_rewrite_is_untouched(self) -> None:
        """수정문안은 계약서에 들어가는 문장이다 — 여기를 고치면 계약서 훼손이다."""
        cr = {
            "clause_id": "X-2",
            "issue_title": "대금 지급기한",
            "suggested_rewrite": "갑은 하도급법이 정하는 바에 따라 60일 이내에 지급한다.",
        }
        scrub_inapplicable_statutes([cr], [self.DECISION])
        self.assertIn("하도급법", cr["suggested_rewrite"])

    def test_no_blocked_statutes_means_no_change(self) -> None:
        cr = {"clause_id": "X-3", "issue_title": "하도급법상 지급기한"}
        applicable = StatuteDecision(statute="하도급법", conclusion="적용", reason="")
        self.assertEqual(scrub_inapplicable_statutes([cr], [applicable]), [])
        self.assertIn("하도급법", cr["issue_title"])


# ── 항목 3. KEEP/보류는 필수·권장 목록에서 제거 ─────────────────────────────

class KeepVerdictRemovalTest(unittest.TestCase):
    def test_keep_verdict_is_demoted_out_of_high(self) -> None:
        cr = {
            "clause_id": "K-1",
            "risk_tier": "HIGH",
            "issue_title": "면책 조항",
            "recommendation_text": "현행 조항을 유지합니다 — 상대방에게 책임을 지우고 있어 우리에게 유리합니다.",
        }
        moved = enforce_keep_verdict_removal([cr])
        self.assertEqual([m["kind"] for m in moved], ["keep_verdict"])
        self.assertEqual(cr["risk_tier"], "LOW")
        self.assertTrue(cr["keep_as_is"])
        self.assertFalse(cr["must_fix"])

    def test_held_applicability_is_not_a_must_fix(self) -> None:
        cr = {
            "clause_id": "K-2",
            "risk_tier": "MEDIUM",
            "issue_title": "대리점법 관련 검토",
            "legal_business_reason": "대리점법 적용 여부 보류 — 계속적 공급 여부 확인이 필요합니다.",
            "problem": "비용 전가 조항이 있습니다.",
        }
        moved = enforce_keep_verdict_removal([cr])
        self.assertEqual([m["kind"] for m in moved], ["applicability_held"])
        self.assertEqual(cr["risk_tier"], "LOW")

    def test_real_finding_with_a_rewrite_is_untouched(self) -> None:
        cr = {
            "clause_id": "K-3",
            "risk_tier": "HIGH",
            "issue_title": "무제한 손해배상",
            "problem": "배상 범위에 상한이 없습니다.",
            "suggested_rewrite": "배상액은 계약금액을 한도로 한다.",
        }
        self.assertEqual(enforce_keep_verdict_removal([cr]), [])
        self.assertEqual(cr["risk_tier"], "HIGH")

    def test_withdrawn_proposal_is_not_a_keep(self) -> None:
        """문안만 보류된 항목은 문제 제기가 살아 있다 — KEEP 으로 접지 않는다."""
        cr = {
            "clause_id": "K-4",
            "risk_tier": "HIGH",
            "issue_title": "무제한 손해배상",
            "problem": "배상 범위에 상한이 없습니다.",
            "advisory_only": True,
        }
        self.assertEqual(enforce_keep_verdict_removal([cr]), [])
        self.assertEqual(cr["risk_tier"], "HIGH")

    def test_demoted_item_disappears_from_the_final_list(self) -> None:
        """등급만 내리는 것으로 끝나면 안 된다 — 최종 목록에서 실제로 빠져야 한다."""
        cr = {
            "clause_id": "K-5",
            "clause_title": "제10조(면책)",
            "risk_tier": "HIGH",
            "approval_required": True,
            "issue_title": "면책 조항",
            "original_text": "을은 갑을 면책하여야 한다.",
            "problem": "상대방이 우리를 면책하는 구조입니다.",
            "legal_business_reason": "우리에게 유리합니다.",
            "recommendation_text": "현행 조항을 유지합니다.",
            "confidence": 0.9,
        }
        enforce_keep_verdict_removal([cr])
        final = build_final_findings([cr], contract_type_code="", include_low=False)
        ids = {
            str(i.get("clause_id"))
            for i in (list(final.get("high_issues") or []) + list(final.get("medium_issues") or []))
        }
        self.assertNotIn("K-5", ids, "KEEP 항목이 필수·권장 목록에 남았다")


# ── 항목 4. 역할 ↔ 실제 거래구조 ───────────────────────────────────────────

class RoleStructureGateTest(unittest.TestCase):
    TEXT = (
        '주식회사 퍼시스(이하 "공급자"라 한다)와 주식회사 대한상사(이하 "구매자"라 한다)는 '
        "다음과 같이 물품공급계약을 체결한다."
    )

    def test_contract_definition_is_read_generically(self) -> None:
        side, evidence = declared_our_side(self.TEXT, "퍼시스")
        self.assertEqual(side, "provider")
        self.assertIn("공급자", evidence)

    def test_opposite_judgement_blocks_output(self) -> None:
        report = enforce_role_matches_transaction_structure(
            {"our_role": "buyer", "counterparty_role": "supplier"},
            contract_text=self.TEXT,
            entity="퍼시스",
        )
        self.assertEqual(report["status"], REVIEW_BLOCKED_ROLE_STRUCTURE_MISMATCH)
        self.assertIn(
            REVIEW_BLOCKED_ROLE_STRUCTURE_MISMATCH,
            NON_REMEDIABLE_STATUSES,
            "차단 상태가 전달 게이트에 등록되지 않았다",
        )

    def test_matching_judgement_passes(self) -> None:
        report = enforce_role_matches_transaction_structure(
            {"our_role": "supplier", "counterparty_role": "buyer"},
            contract_text=self.TEXT,
            entity="퍼시스",
        )
        self.assertEqual(report["status"], "")

    def test_both_sides_same_direction_is_a_conflict(self) -> None:
        report = enforce_role_matches_transaction_structure(
            {"our_role": "supplier", "counterparty_role": "contractor"},
            contract_text="",
            entity="",
        )
        self.assertEqual(report["status"], REVIEW_BLOCKED_ROLE_STRUCTURE_MISMATCH)

    def test_mutual_contract_is_not_a_conflict(self) -> None:
        """상호 NDA 처럼 양쪽 지위가 대칭인 계약을 역할 충돌로 읽으면 안 된다."""
        report = enforce_role_matches_transaction_structure(
            {"our_role": "party", "counterparty_role": "party"},
            contract_text="갑과 을은 상호 비밀유지의무를 부담한다.",
            entity="",
        )
        self.assertEqual(report["status"], "")


# ── 항목 5. 최종 출력 전 교차 정합성 self-check ────────────────────────────

class CrossConsistencySelfCheckTest(unittest.TestCase):
    def _run(self, **overrides):
        base = dict(
            legal_state={
                "contract_type": "nda_confidentiality",
                "transaction_type": "confidentiality_only",
                "our_role_direction": "provider",
            },
            clause_results=[],
            final_findings={},
            statute_decisions=[{"statute": "하도급법", "conclusion": "비적용"}],
            user_review_coverage=[],
            user_review_focus=None,
            answers=None,
            contract_text="수령자는 비밀정보를 제3자에게 공개할 수 없다.",
        )
        base.update(overrides)
        return run_final_counsel_gate(**base)

    def _failed(self, report) -> set[str]:
        return {c.key for c in report.checks if not c.ok}

    def test_type_and_archetype_conflict_is_reported(self) -> None:
        report = self._run(legal_state={
            "contract_type": "nda_confidentiality",
            "transaction_type": "goods_supply",
            "our_role_direction": "provider",
        })
        self.assertIn("type_matches_archetype", self._failed(report))
        self.assertFalse(report.passed, "충돌이 있는데 정상 완료로 표시됐다")

    def test_role_structure_conflict_is_reported(self) -> None:
        report = self._run(role_structure_report={"conflicts": ["계약서는 우리를 공급자로 정의합니다."]})
        self.assertIn("role_matches_structure", self._failed(report))

    def test_leftover_statute_language_is_reported(self) -> None:
        report = self._run(
            clause_results=[{
                "clause_id": "S-1",
                "issue_title": "하도급법 위반",
                "risk_tier": "HIGH",
                "high_severity_basis": "x",
            }],
            statute_decisions_blocked=["하도급법"],
        )
        self.assertIn("no_inapplicable_statute_language", self._failed(report))

    def test_incoherent_finding_is_reported(self) -> None:
        report = self._run(coherence_report={"mismatches": [{"clause_id": "C-1", "axis": "problem_vs_rewrite"}]})
        self.assertIn("finding_rewrite_coherent", self._failed(report))

    def test_keep_left_in_must_fix_is_reported(self) -> None:
        report = self._run(clause_results=[{
            "clause_id": "K-9", "keep_as_is": True, "risk_tier": "HIGH",
        }])
        self.assertIn("no_keep_in_must_fix", self._failed(report))

    def test_clean_state_passes_every_cross_check(self) -> None:
        failed = self._failed(self._run())
        for key in (
            "type_matches_archetype", "role_matches_structure",
            "no_inapplicable_statute_language", "finding_rewrite_coherent",
            "no_keep_in_must_fix",
        ):
            self.assertNotIn(key, failed)


if __name__ == "__main__":
    unittest.main()
