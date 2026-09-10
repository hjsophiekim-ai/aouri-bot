"""공통 Legal Reasoning Engine 아키텍처 회귀테스트 (2026-09-10 지시).

지시의 핵심 목표 — "아우리봇은 계약유형별 체크리스트 묶음이 아니라, 하나의
공통 Legal Reasoning Engine 이 거래실질과 법률효과를 먼저 이해하고, 계약유형별
규칙은 보조자료로만 활용하는 구조로 바꿔야 합니다."

이 파일은 그 구조 자체를 고정한다. 개별 계약의 정답 문구가 아니라 **판단
순서**와 **불변식**을 검사하므로, 계약유형이 늘어도 이 테스트는 그대로 유효하다.

    거래 실질(효과 프로파일)  →  거래 원형  →  계약유형 라벨
        ↑ 판단의 출발점                          ↑ 보조자료

이 순서가 뒤집히면 enum 에 없는 계약유형(라이선스·바터)이 다시 키워드
캐스케이드의 아무 가지에나 떨어진다.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from runtime.questions.effect_questions import build_effect_questions
from runtime.questions.question_scope import (
    filter_questions_by_transaction_type,
    is_question_in_scope,
)
from runtime.review.clause_effect import (
    ARCHETYPE_BARTER,
    ARCHETYPE_DISTRIBUTION,
    ARCHETYPE_LICENSE,
    ARCHETYPE_NDA,
    ARCHETYPE_UNKNOWN,
    CLAUSE_EFFECTS,
    EFFECT_IP,
    EFFECT_LIABILITY,
    EFFECT_PAYMENT,
    EFFECT_TERMINATION,
    build_effect_profile,
    classify_clause_effects,
)
from runtime.review.clause_extraction import extract_clauses
from runtime.review.effect_baseline_review import run_effect_baseline_review
from runtime.review.final_counsel_gate import run_final_counsel_gate
from runtime.review.legal_state import (
    CanonicalLegalState,
    build_legal_state,
    check_state_consistency,
    reconcile_contract_type,
)
from runtime.review.minimal_edit import (
    FACT_CONFIRMATION_REQUIRED,
    apply_minimal_edit,
    minimal_edit_for,
)

FIXTURES = Path(__file__).parent / "fixtures"


class ClauseEffectTaxonomyTest(unittest.TestCase):
    """항목 2 — 계약유형보다 먼저 법률효과를 이해한다."""

    def test_taxonomy_has_the_fourteen_categories(self) -> None:
        self.assertEqual(len(CLAUSE_EFFECTS), 14)

    def test_effects_are_recognised_without_any_contract_type(self) -> None:
        """같은 효과는 어느 계약유형에서든 같은 범주로 분류된다."""
        cases = [
            ("손해배상", "귀책 당사자는 상대방이 입은 모든 손해를 배상한다.", EFFECT_LIABILITY),
            ("대금지급", "을은 납품일로부터 60일 이내에 대금을 지급한다.", EFFECT_PAYMENT),
            ("계약해지", "갑은 사전 통지 없이 즉시 해지할 수 있다.", EFFECT_TERMINATION),
            ("저작권", "본건 콘텐츠의 저작권은 갑에게 귀속한다.", EFFECT_IP),
        ]
        for title, text, expected in cases:
            with self.subTest(title=title):
                self.assertIn(expected, classify_clause_effects(title=title, text=text))

    def test_english_clauses_are_classified_too(self) -> None:
        self.assertIn(
            EFFECT_LIABILITY,
            classify_clause_effects(
                title="Indemnification", text="Licensee shall indemnify and hold harmless."
            ),
        )
        self.assertIn(
            EFFECT_IP,
            classify_clause_effects(
                title="Intellectual Property", text="All copyright shall remain with Licensor."
            ),
        )


class ArchetypeResolutionTest(unittest.TestCase):
    """유형 enum 없이 거래 원형을 읽어내는가 — 8개 유형 전부."""

    EXPECTED = {
        "nda_basic.txt": ARCHETYPE_NDA,
        "webzen_nda.txt": ARCHETYPE_NDA,
        "_lm_license_1.txt": ARCHETYPE_LICENSE,
        "barter_content_furniture.txt": ARCHETYPE_BARTER,
        "dealer_agency.txt": ARCHETYPE_DISTRIBUTION,
        "fursys_consignment_dealer.txt": ARCHETYPE_DISTRIBUTION,
        "construction_works_contract.txt": "construction_works",
        "supply_purchase.txt": "goods_supply",
        "services_consulting.txt": "service_engagement",
        "skai_cove_content_production.txt": "service_engagement",
        "_lm_lease_1.txt": "lease_rental",
    }

    def test_every_fixture_resolves_to_the_right_archetype(self) -> None:
        bad: list[str] = []
        for fixture, expected in self.EXPECTED.items():
            text = (FIXTURES / fixture).read_text(encoding="utf-8")
            profile = build_effect_profile(
                text=text, clauses=extract_clauses(text)[0] or [],
            )
            if profile.archetype != expected:
                bad.append(f"{fixture}: {profile.archetype} != {expected}")
        self.assertEqual(bad, [], "거래 원형 판정 오류")

    def test_license_agreement_is_not_mistaken_for_goods_supply(self) -> None:
        """실측 사고: 34,000자 LICENSE AGREEMENT 가 purchase_supply 로 분류돼
        물품매매 체크리스트가 통째로 돌았다."""
        text = (FIXTURES / "_lm_license_1.txt").read_text(encoding="utf-8")
        profile = build_effect_profile(text=text, clauses=extract_clauses(text)[0] or [])
        self.assertEqual(profile.archetype, ARCHETYPE_LICENSE)
        self.assertTrue(profile.self_declared, "표제·정의에서 스스로 라이선스라고 밝힌다")


class ContractTypeReconciliationTest(unittest.TestCase):
    """항목 1 — 원형이 enum 분류를 이긴다."""

    def _profile(self, fixture: str):
        text = (FIXTURES / fixture).read_text(encoding="utf-8")
        return build_effect_profile(text=text, clauses=extract_clauses(text)[0] or [])

    def test_conflicting_enum_code_is_corrected_to_the_archetype(self) -> None:
        code, family, reconciled, reason = reconcile_contract_type(
            detailed_code="purchase_supply",
            detailed_family="supply_installation",
            profile=self._profile("_lm_license_1.txt"),
        )
        self.assertTrue(reconciled)
        self.assertEqual(code, "license_ip")
        self.assertIn("거래 실질", reason)

    def test_matching_enum_code_is_left_alone(self) -> None:
        _code, _family, reconciled, _reason = reconcile_contract_type(
            detailed_code="nda_confidentiality",
            detailed_family="nda_confidentiality",
            profile=self._profile("webzen_nda.txt"),
        )
        self.assertFalse(reconciled)

    def test_unknown_archetype_never_overwrites(self) -> None:
        """모르는 것을 덮어쓰지 않는다."""
        from runtime.review.clause_effect import ContractEffectProfile

        code, _family, reconciled, _reason = reconcile_contract_type(
            detailed_code="advisory_service",
            detailed_family="development_service",
            profile=ContractEffectProfile(archetype=ARCHETYPE_UNKNOWN),
        )
        self.assertFalse(reconciled)
        self.assertEqual(code, "advisory_service")


class CanonicalLegalStateTest(unittest.TestCase):
    """항목 1 — 11개 축을 한 객체에 담고, 재계산 없이 되살릴 수 있는가."""

    def _state(self, fixture: str = "barter_content_furniture.txt") -> CanonicalLegalState:
        text = (FIXTURES / fixture).read_text(encoding="utf-8")
        return build_legal_state(
            text=text,
            clauses=extract_clauses(text)[0] or [],
            detailed_code="advertising_content_production",
            detailed_family="development_service",
            detailed_label="콘텐츠 제작 계약",
            our_role="client",
            our_role_direction="recipient",
            our_label="갑",
            counterparty_role="service_provider",
            counterparty_label="을",
        )

    def test_state_carries_all_eleven_axes(self) -> None:
        state = self._state()
        for axis in (
            "transaction_type", "contract_type", "our_role", "counterparty_role",
            "each_party_performance", "consideration_structure", "ownership_risk_transfer",
            "deliverables", "governing_contract_documents", "applicable_law_candidates",
            "user_review_scope",
        ):
            with self.subTest(axis=axis):
                self.assertIn(axis, state.to_dict())

    def test_round_trip_needs_no_reclassification(self) -> None:
        """다운로드 경로가 분류기를 다시 돌리지 않게 하는 것이 이 왕복의 목적이다."""
        state = self._state()
        restored = CanonicalLegalState.from_dict(state.to_dict())
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.transaction_type, state.transaction_type)
        self.assertEqual(restored.contract_type, state.contract_type)
        self.assertEqual(restored.our_role_direction, state.our_role_direction)

    def test_barter_is_recognised_as_non_monetary(self) -> None:
        state = self._state()
        self.assertEqual(state.transaction_type, ARCHETYPE_BARTER)
        self.assertTrue(state.is_non_monetary)

    def test_role_is_never_left_blank_for_mutual_contracts(self) -> None:
        """NDA·라이선스처럼 지위를 밝히지 않는 유형에서 빈 값을 남기면
        후속 게이트가 계속 '지위 미확정'으로 걸린다."""
        text = (FIXTURES / "nda_basic.txt").read_text(encoding="utf-8")
        state = build_legal_state(
            text=text, clauses=extract_clauses(text)[0] or [],
            detailed_code="general", detailed_family="nda_confidentiality",
            detailed_label="", our_role="neutral", our_role_direction="",
            our_label="", counterparty_role="unknown", counterparty_label="",
        )
        self.assertTrue(state.our_role_direction, "지위가 비어 있다")

    def test_output_consistency_check_detects_downstream_reclassification(self) -> None:
        state = self._state()
        ok = check_state_consistency(state, {"contract_type": state.contract_type})
        self.assertTrue(ok["ok"])
        bad = check_state_consistency(state, {"contract_type": "purchase_supply"})
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["status"], "REVIEW_FAILED_LEGAL_STATE_MISMATCH")


class EffectBaselineReviewTest(unittest.TestCase):
    """항목 2 — 유형 룰팩이 없어도 실질 리스크를 잡는가."""

    def test_supply_contract_material_risks_are_found(self) -> None:
        """실측: 무과실 전부배상·무통지 즉시해지가 있는데 finding 0건이었다."""
        text = (FIXTURES / "supply_purchase.txt").read_text(encoding="utf-8")
        findings = run_effect_baseline_review(
            extract_clauses(text)[0] or [], full_text=text, existing_results=[],
        )
        checks = {str(f.get("effect_check_id") or "") for f in findings}
        self.assertIn("eb_liability_no_fault", checks)
        self.assertIn("eb_termination_immediate_no_cure", checks)

    def test_baseline_takes_no_contract_type_argument(self) -> None:
        """유형과 무관하게 성립해야 하므로 유형을 인자로 받지 않는다."""
        import inspect

        params = set(inspect.signature(run_effect_baseline_review).parameters)
        self.assertNotIn("contract_type_code", params)
        self.assertNotIn("contract_type", params)

    def test_absence_checks_look_at_the_whole_contract(self) -> None:
        """항목 5 — 다른 조항에 이미 있으면 '없다'고 하지 않는다."""
        with_cap = (
            "제1조(손해배상) 귀책 당사자는 모든 손해를 배상한다.\n"
            "제2조(책임 한도) 배상 총액은 계약금액을 초과하지 아니한다.\n"
        )
        findings = run_effect_baseline_review(
            extract_clauses(with_cap)[0] or [], full_text=with_cap, existing_results=[],
        )
        self.assertNotIn(
            "eb_liability_uncapped",
            {str(f.get("effect_check_id") or "") for f in findings},
            "다른 조항에 한도가 있는데도 '한도 없음'을 지적했다",
        )

    def test_every_baseline_finding_carries_a_complete_edit(self) -> None:
        text = (FIXTURES / "supply_purchase.txt").read_text(encoding="utf-8")
        for f in run_effect_baseline_review(
            extract_clauses(text)[0] or [], full_text=text, existing_results=[],
        ):
            with self.subTest(check=f.get("effect_check_id")):
                self.assertTrue(str(f.get("suggested_rewrite") or "").strip())
                self.assertTrue(str(f.get("negotiation_position") or "").strip())


class MinimalEditTest(unittest.TestCase):
    """항목 7 — 자리표시자 금지, 최소수정안 직접 작성."""

    def test_minimal_edit_preserves_the_original_and_adds_a_safeguard(self) -> None:
        original = "귀책 당사자는 상대방이 입은 모든 손해를 배상하여야 한다."
        final, addition, position = minimal_edit_for(
            original_text=original, clause_title="손해배상",
        )
        self.assertTrue(final.startswith(original), "원문이 보존되지 않았다")
        self.assertIn("총액", addition)
        self.assertTrue(position)

    def test_no_banned_placeholder_wording_is_produced(self) -> None:
        cr = {
            "clause_id": "x",
            "original_text": "갑은 사전 통지 없이 즉시 해지할 수 있다.",
            "clause_title": "계약해지",
            "risk_tier": "HIGH",
        }
        self.assertTrue(apply_minimal_edit(cr, reason="테스트"))
        blob = " ".join(
            str(cr.get(k) or "")
            for k in ("suggested_rewrite", "recommendation_text", "rewrite_reason")
        )
        for banned in ("[수정문안 보류]", "담당 변호사가 직접 확정", "추후 협의", "TBD"):
            self.assertNotIn(banned, blob)

    def test_fact_confirmation_requires_a_specific_fact(self) -> None:
        cr = {"clause_id": "x", "original_text": "", "risk_tier": "MEDIUM"}
        self.assertFalse(apply_minimal_edit(cr, reason="테스트", fact_needed="실제 지급 통화"))
        self.assertEqual(cr["fact_confirmation_required"], FACT_CONFIRMATION_REQUIRED)
        self.assertEqual(cr["fact_confirmation_items"], ["실제 지급 통화"])


class QuestionScopeTest(unittest.TestCase):
    """항목 4 — 유형별 canned question 금지."""

    def test_operations_questions_never_reach_a_barter_contract(self) -> None:
        """실측: 대물교환 계약에 '운영 인력 배치/KPI' 질문이 나갔다."""
        self.assertFalse(is_question_in_scope("Q-OPS-003-staffing", ARCHETYPE_BARTER))
        self.assertFalse(is_question_in_scope("Q-OPS-002-scope-kpi", "construction_works"))

    def test_dealer_questions_never_reach_a_license_contract(self) -> None:
        """실측: 라이선스 계약에 '판촉비/반품비 부담' 질문이 나갔다."""
        self.assertFalse(is_question_in_scope("Q-DL-002-cost-shift", ARCHETYPE_LICENSE))
        self.assertFalse(is_question_in_scope("Q-CA-001-dealer-cost", ARCHETYPE_LICENSE))

    def test_dealer_questions_do_reach_a_distribution_contract(self) -> None:
        self.assertTrue(is_question_in_scope("Q-DL-002-cost-shift", ARCHETYPE_DISTRIBUTION))

    def test_universal_questions_always_pass(self) -> None:
        for qid in ("Q-TYPE-001-contract-nature", "Q-ROLE-001-our-position", "Q-AI-001-x"):
            for archetype in (ARCHETYPE_NDA, ARCHETYPE_LICENSE, ARCHETYPE_BARTER):
                with self.subTest(qid=qid, archetype=archetype):
                    self.assertTrue(is_question_in_scope(qid, archetype))

    def test_unknown_archetype_filters_nothing(self) -> None:
        """모르는 상태에서 질문을 지우면 물어야 할 것을 못 묻는다."""
        self.assertTrue(is_question_in_scope("Q-OPS-003-staffing", ARCHETYPE_UNKNOWN))
        self.assertTrue(is_question_in_scope("Q-OPS-003-staffing", ""))

    def test_filter_helper_removes_only_out_of_scope(self) -> None:
        from runtime.questions.model import Question

        def q(qid: str) -> Question:
            return Question(
                question_id=qid, title="t", description="", answer_type="text",
                required=False, options=[], tags=[], related_rule_ids=[],
            )

        kept = filter_questions_by_transaction_type(
            [q("Q-TYPE-001-x"), q("Q-OPS-003-staffing"), q("Q-DL-001-form")],
            ARCHETYPE_LICENSE,
        )
        self.assertEqual([x.question_id for x in kept], ["Q-TYPE-001-x"])


class EffectQuestionTest(unittest.TestCase):
    """항목 4 — 효과에서 직접 나오고, 계약서에 답이 있으면 묻지 않는다."""

    def _profile(self, fixture: str):
        text = (FIXTURES / fixture).read_text(encoding="utf-8")
        return text, build_effect_profile(text=text, clauses=extract_clauses(text)[0] or [])

    def test_barter_contract_is_asked_about_valuation(self) -> None:
        text, profile = self._profile("barter_content_furniture.txt")
        ids = {
            q.question_id
            for q in build_effect_questions(profile=profile, contract_text=text, max_questions=8)
        }
        self.assertIn("Q-EFF-barter-valuation", ids)

    def test_question_is_skipped_when_the_contract_already_answers_it(self) -> None:
        text = (
            "제1조(손해배상) 귀책 당사자는 모든 손해를 배상한다.\n"
            "제2조(책임 한도) 배상 총액은 계약금액을 초과하지 아니한다.\n"
        )
        profile = build_effect_profile(text=text, clauses=extract_clauses(text)[0] or [])
        ids = {
            q.question_id
            for q in build_effect_questions(profile=profile, contract_text=text, max_questions=8)
        }
        self.assertNotIn(
            "Q-EFF-liability-exposure", ids,
            "계약서에 이미 한도가 있는데도 노출 규모를 물었다",
        )

    def test_effect_absent_from_the_contract_is_never_asked(self) -> None:
        text = "제1조(목적) 본 계약은 상호 협력을 목적으로 한다."
        profile = build_effect_profile(text=text, clauses=extract_clauses(text)[0] or [])
        ids = {
            q.question_id
            for q in build_effect_questions(profile=profile, contract_text=text, max_questions=8)
        }
        self.assertNotIn("Q-EFF-privacy-consent", ids)


class FinalCounselGateTest(unittest.TestCase):
    """항목 12 — 10개 항목 자가점검."""

    def _run(self, **overrides):
        base = dict(
            legal_state={
                "contract_type": "nda_confidentiality",
                "transaction_type": ARCHETYPE_NDA,
                "our_role_direction": "mutual",
            },
            clause_results=[{
                "clause_id": "KR-1", "finding_id": "f1", "risk_tier": "MEDIUM",
                "original_text": "수령자는 비밀정보를 제3자에게 공개할 수 없다.",
                "problem": "예외 규정이 없다",
                "redline_instruction": {
                    "edit_location": "제1조 교체", "edit_type": "replace",
                    "final_clause_text": "수령자는 … 다만 공지의 정보는 제외한다.",
                },
            }],
            final_findings={"medium_issues": [{"finding_id": "f1"}], "high_issues": []},
            statute_decisions=[{"statute": "하도급법", "conclusion": "비적용"}],
            user_review_coverage=[],
            user_review_focus=None,
            answers=None,
            contract_text="수령자는 비밀정보를 제3자에게 공개할 수 없다.",
        )
        base.update(overrides)
        return run_final_counsel_gate(**base)

    def test_gate_has_exactly_the_ten_required_checks(self) -> None:
        report = self._run()
        self.assertEqual(len(report.checks), 10)
        self.assertEqual(
            [c.key for c in report.checks],
            [
                "type_and_role", "no_fabricated_user_request", "answers_applied",
                "statute_gate_first", "no_cross_type_template", "no_false_absence",
                "our_side_not_weakened", "high_justified", "complete_rewrite",
                "ui_docx_identical",
            ],
        )

    def test_clean_review_passes(self) -> None:
        self.assertTrue(self._run().passed)

    def test_fabricated_user_request_fails(self) -> None:
        report = self._run(
            user_review_coverage=[{
                "source": "explicit_user_request",
                "original_user_text": "사용자가 하지 않은 말",
                "issue_id": "x",
            }],
            user_review_focus="",
        )
        self.assertFalse(report.passed)
        self.assertIn("no_fabricated_user_request", [c.key for c in report.failed])

    def test_placeholder_wording_fails(self) -> None:
        report = self._run(clause_results=[{
            "clause_id": "KR-1", "finding_id": "f1", "risk_tier": "HIGH",
            "original_text": "원문", "problem": "문제",
            "high_severity_basis": "근거",
            "recommendation_text": "[수정문안 보류] 담당 변호사가 직접 확정",
        }])
        self.assertIn("complete_rewrite", [c.key for c in report.failed])

    def test_baseless_high_fails(self) -> None:
        report = self._run(clause_results=[{
            "clause_id": "KR-1", "finding_id": "f1", "risk_tier": "HIGH",
            "original_text": "원문", "problem": "문제",
            "redline_instruction": {
                "edit_location": "제1조 교체", "edit_type": "replace",
                "final_clause_text": "수정",
            },
        }])
        self.assertIn("high_justified", [c.key for c in report.failed])

    def test_dangling_ui_finding_fails(self) -> None:
        report = self._run(
            final_findings={"high_issues": [{"finding_id": "ghost"}], "medium_issues": []},
        )
        self.assertIn("ui_docx_identical", [c.key for c in report.failed])

    def test_missing_role_fails(self) -> None:
        report = self._run(legal_state={
            "contract_type": "nda_confidentiality",
            "transaction_type": ARCHETYPE_NDA,
            "our_role_direction": "",
        })
        self.assertIn("type_and_role", [c.key for c in report.failed])


if __name__ == "__main__":
    unittest.main()
