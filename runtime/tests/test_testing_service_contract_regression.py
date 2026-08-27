"""Regression tests for the FITI 시험분석약정서 misclassification incident.

Background (2026-08-27): a 시디즈-FITI시험연구원 시험분석 약정서 (a testing/
inspection service agreement — 시디즈 is the party requesting testing, FITI is
the testing lab) was misclassified as an "AI 검색·마케팅 서비스 계약" because
the word "광고" appeared once, inside an incidental usage-restriction clause
("시험성적서를 광고에 사용하지 말 것"). That single misclassification cascaded
through several contract-type-agnostic injector functions and produced a
review full of boilerplate that has nothing to do with the actual contract:
  - "[공급자 보호]" 검수/반품/A/S/위험이전/설치환경/주문취소/이행유보권 항목
    (물품공급 계약 전용 체크리스트, _apply_supplier_product_checklist)
  - "[시디즈 위탁자 보호]" CI/SI 위반 즉시해지 + 위약벌 조항
    (_apply_sidiz_position_strategy, 계약유형 게이트가 아예 없었음)
  - "[수정 제안 — 제3자 권리 침해 보증]" IP/저작권 보증 조항
    (_apply_advisory_ip_review, "용역" 키워드만으로 발동)
  - "원문" 인용이 제8조/제10조/제12조 문장을 뒤섞어 존재하지 않는 문장을 인용
  - "문제점" 필드에 "사용자 중점 이슈: 구상권/소송비용 전가" 같은 내부 카테고리
    라벨이 설명 없이 그대로 노출

These tests pin the fix: contract_classifier now recognises
"testing_inspection_service" as its own type, the three injector functions
are hard-blocked for non-matching contract classes, and a final self-check
backstop strips anything that slips through regardless of which upstream
function caused it.
"""
from __future__ import annotations

import unittest
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fiti_testing_service_agreement.txt"

_FORBIDDEN_MARKERS = [
    # 반품
    "반품이 불가", "반품 요청서",
    # A/S
    "무상 A/S 대상", "A/S 제외",
    # 설치환경
    "설치 환경 요건",
    # 주문제작 취소
    "주문제작 공정", "주문제작 또는 설치가 완료된",
    # 물품 위험이전
    "위험은 공급자가", "위험이전 시점",
    # 오픈소스
    "오픈소스", "오픈소스 라이선스",
    # CI/SI 위약벌
    "CI/SI 가이드라인", "브랜드를 훼손", "위약벌을",
    # 콘텐츠/IP 결과물 보증
    "제3자의 저작권", "결과물 소유권", "저작재산권",
    "검수 완료 간주", "이행유보권",
    "sppc_", "MI-001", "MI-002", "MI-003", "MI-004", "MR-001", "MR-005",
]


class ContractClassifierTest(unittest.TestCase):
    """The classifier must recognise the testing-service type directly,
    not fall through to a marketing/dealer/product-supply guess."""

    def setUp(self) -> None:
        self.text = FIXTURE_PATH.read_text(encoding="utf-8")

    def test_classified_as_testing_inspection_service(self) -> None:
        from runtime.review.contract_classifier import classify_contract_detailed

        profile = classify_contract_detailed(entity="시디즈", contract_type="", text=self.text)
        self.assertEqual(profile.contract_type, "testing_inspection_service")
        self.assertNotEqual(profile.contract_type, "ai_search_marketing")
        self.assertGreaterEqual(profile.confidence, 0.75)

    def test_our_role_is_service_recipient_not_supplier(self) -> None:
        from runtime.review.contract_classifier import classify_contract_detailed

        profile = classify_contract_detailed(entity="시디즈", contract_type="", text=self.text)
        self.assertEqual(profile.our_role_bucket, "service_recipient")
        self.assertNotIn(profile.our_role_bucket, ("supplier", "contractor"))

    def test_single_incidental_ad_keyword_does_not_trigger_marketing(self) -> None:
        # The exact incidental phrase that caused the original misclassification.
        from runtime.review.contract_classifier import classify_contract_detailed

        text = "위탁자는 수탁자의 사전 서면동의 없이 시험성적서를 광고 ㆍ판촉 활동에 사용하여서는 아니 된다."
        profile = classify_contract_detailed(entity="시디즈", contract_type="", text=text)
        self.assertNotEqual(profile.contract_type, "ai_search_marketing")

    def test_answers_override_low_confidence_classification(self) -> None:
        from runtime.review.contract_classifier import classify_contract_detailed

        ambiguous_text = "본 계약은 당사자 간 협력을 위해 체결한다. 갑과 을은 성실히 이행한다."
        baseline = classify_contract_detailed(entity="시디즈", contract_type="", text=ambiguous_text)
        self.assertLess(baseline.confidence, 0.75)

        confirmed = classify_contract_detailed(
            entity="시디즈", contract_type="", text=ambiguous_text,
            answers={
                "Q-TYPE-001-contract-nature": "testing_inspection",
                "Q-ROLE-001-our-position": "we_are_service_recipient",
            },
        )
        self.assertEqual(confirmed.contract_type, "testing_inspection_service")
        self.assertEqual(confirmed.our_role_bucket, "service_recipient")
        self.assertGreaterEqual(confirmed.confidence, 0.9)


class PipelineNoOutOfScopeInjectionTest(unittest.TestCase):
    """End-to-end: build_clause_level_result on the FITI fixture must not
    inject product-supply / CI-SI / dealer-mandatory boilerplate."""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService
        from runtime.review.clause_level import build_clause_level_result

        text = FIXTURE_PATH.read_text(encoding="utf-8")
        loader = RuleLoader()
        loader.load()
        service = RuleQueryService(loader)
        cls.bundle = build_clause_level_result(
            service=service,
            entity="시디즈",
            contract_type="",
            text=text,
            filename="시디즈_FITI_시험분석약정서.pdf",
            answers=None,
            law_service=None,
            ai_provider=None,
            ai_model=None,
            ai_timeout_sec=None,
            ai_max_tokens=None,
            ai_temperature=None,
        )

    def test_contract_class_is_testing_service(self) -> None:
        self.assertEqual(self.bundle.meta.get("contract_class"), "testing_service")

    def test_no_forbidden_markers_anywhere_in_output(self) -> None:
        blob = str(self.bundle.clause_results) + str(self.bundle.meta)
        for marker in _FORBIDDEN_MARKERS:
            self.assertNotIn(marker, blob, f"forbidden out-of-scope marker leaked into output: {marker!r}")

    def test_no_out_of_scope_clause_ids(self) -> None:
        for cr in self.bundle.clause_results:
            if not isinstance(cr, dict):
                continue
            cid = str(cr.get("clause_id") or "")
            self.assertFalse(cid.startswith("sppc_"), f"sppc_ (product-supply) rule fired: {cid}")
            self.assertFalse(cid.startswith("MI-"), f"dealer mandatory issue fired: {cid}")
            self.assertFalse(cid.startswith("MR-"), f"dealer rental mandatory issue fired: {cid}")

    def test_self_check_report_present_and_clean(self) -> None:
        report = self.bundle.meta.get("self_check")
        self.assertIsInstance(report, dict)
        self.assertEqual(report.get("contract_type_code"), "testing_inspection_service")
        self.assertEqual(report.get("scope_violations_stripped"), [])
        self.assertTrue(report.get("passed"))

    def test_no_false_negative_zero_findings(self) -> None:
        # This was the actual regression: HARD BLOCK removed the noise but
        # also (via an unrelated pre-existing bug in the priority engine)
        # suppressed every real finding down to HIGH=0/MEDIUM=0. Common
        # legal-risk rules (Layer 1) must now produce real findings.
        tier_counts = self.bundle.meta.get("tier_counts") or {}
        self.assertGreater(tier_counts.get("must", 0), 0, "expected at least one HIGH finding")
        self.assertGreater(tier_counts.get("medium", 0), 0, "expected at least one MEDIUM finding")
        report = self.bundle.meta.get("self_check")
        self.assertFalse(report.get("zero_findings_but_risk_language_present"))
        self.assertEqual(report.get("review_status"), "OK")

    def _clause_ids(self) -> set[str]:
        return {str(cr.get("clause_id") or "") for cr in self.bundle.clause_results if isinstance(cr, dict)}

    def _cr_by_id(self, clause_id: str) -> dict:
        for cr in self.bundle.clause_results:
            if isinstance(cr, dict) and cr.get("clause_id") == clause_id:
                return cr
        raise AssertionError(f"clause_id {clause_id!r} not found among findings: {sorted(self._clause_ids())}")

    def test_article6_4_and_11_1_fault_blind_exemption_is_high(self) -> None:
        # 제6조④ / 제11조① — 수탁자 귀책 여부와 무관한 전면 면책 -> HIGH
        cr = self._cr_by_id("clr_fault_blind_exemption")
        self.assertEqual(cr.get("risk_tier"), "HIGH")

    def test_article6_5_and_11_2_unlimited_recourse_is_high_or_medium(self) -> None:
        # 제6조⑤ / 제11조② — 배상액·소송비용/변호사보수 구상 -> HIGH 또는 MEDIUM
        cr = self._cr_by_id("clr_unlimited_recourse_with_legal_costs")
        self.assertIn(cr.get("risk_tier"), ("HIGH", "MEDIUM"))

    def test_article5_other_lab_notice_is_medium(self) -> None:
        # 제5조 — 타 시험기관과 유사 약정 체결 시 사전통보 -> MEDIUM
        cr = self._cr_by_id("clr_competitor_restriction_notice")
        self.assertEqual(cr.get("risk_tier"), "MEDIUM")

    def test_article6_2_advertising_consent_is_medium(self) -> None:
        # 제6조② — 성적서 광고·판촉 사전서면동의 -> MEDIUM
        cr = self._cr_by_id("tsr_certificate_usage_restriction")
        self.assertEqual(cr.get("risk_tier"), "MEDIUM")

    def test_article12_termination_right_vs_2yr_term_is_medium(self) -> None:
        # 제12조 — 2년 계약인데 편의해지권 없음 -> MEDIUM
        cr = self._cr_by_id("clr_termination_right_restricted")
        self.assertEqual(cr.get("risk_tier"), "MEDIUM")

    def test_article14_1_standard_terms_incorporation_is_high_or_medium(self) -> None:
        # 제14조① — FITI 표준시험약관·규정 포괄 적용 -> HIGH 또는 MEDIUM
        cr = self._cr_by_id("clr_external_terms_incorporation")
        self.assertIn(cr.get("risk_tier"), ("HIGH", "MEDIUM"))

    def test_article4_4_payment_guarantee_misreading_flagged(self) -> None:
        # 제4조④ — 협력사 미수금 관련 "적극 협조" -> 지급보증 오인 가능성 검토
        cr = self._cr_by_id("clr_payment_guarantee_ambiguous")
        self.assertIn(cr.get("risk_tier"), ("HIGH", "MEDIUM"))

    def test_article8_5_data_reuse_flagged(self) -> None:
        # 제8조⑤ — FITI의 자료 연구·분석 활용 -> 데이터 활용 리스크 검토
        cr = self._cr_by_id("tsr_data_reuse_by_lab")
        self.assertIn(cr.get("risk_tier"), ("HIGH", "MEDIUM"))

    def test_self_check_flags_real_exculpatory_clause_as_uncovered_by_catalog(self) -> None:
        # The user_focus priority-risk catalog's "exculpatory_clause" category
        # keyword-matches this contract's text but the actual finding lives
        # under a differently-named clause_id (clr_fault_blind_exemption) —
        # self-check's coverage scan should still list it so a reviewer can
        # cross-check the catalog against the concrete findings.
        report = self.bundle.meta.get("self_check")
        self.assertIn("exculpatory_clause", report.get("priority_risk_present_but_unflagged", []))


class ReviewFocusSurfacesEvenWithoutRuleDbMatchTest(unittest.TestCase):
    """Regression: a clause matching the user's stated review_focus keywords
    must appear in the output even when no JSON rule in the rule DB happens
    to trigger on it — a clause used to be silently dropped from
    revision.py's per-clause loop entirely (`if not clause_issues: continue`)
    whenever no rule matched, regardless of review_focus."""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService
        from runtime.review.clause_level import build_clause_level_result

        text = FIXTURE_PATH.read_text(encoding="utf-8")
        loader = RuleLoader()
        loader.load()
        service = RuleQueryService(loader)
        cls.bundle = build_clause_level_result(
            service=service,
            entity="시디즈",
            contract_type="",
            text=text,
            filename="시디즈_FITI_시험분석약정서.pdf",
            answers=None,
            review_focus="면책 조항과 구상권 범위를 중점적으로 봐주세요",
            law_service=None,
            ai_provider=None,
            ai_model=None,
            ai_timeout_sec=None,
            ai_max_tokens=None,
            ai_temperature=None,
        )

    def test_focus_matched_clauses_are_surfaced(self) -> None:
        hit_ids = {
            str(cr.get("clause_id") or "")
            for cr in self.bundle.clause_results
            if isinstance(cr, dict) and cr.get("user_focus_hit")
        }
        self.assertTrue(hit_ids, "no clause was tagged user_focus_hit for a review_focus that clearly matches 제6조/제11조")

    def test_focus_matched_clause_is_not_silently_low(self) -> None:
        # At least one of the focus-matched clauses must be visible at
        # MEDIUM+ — LOW-only findings are excluded from default output, which
        # would mean the user's stated focus area is effectively invisible.
        promoted = [
            cr for cr in self.bundle.clause_results
            if isinstance(cr, dict) and cr.get("user_focus_hit")
            and str(cr.get("risk_tier") or "").upper() in ("HIGH", "MEDIUM")
        ]
        self.assertTrue(promoted, "review_focus-matched clause(s) were left at LOW and effectively hidden")


class HallucinationGuardBackstopTest(unittest.TestCase):
    """Direct unit tests on the new phrase lists — belt-and-suspenders even
    if a future injector function reintroduces the bug."""

    def test_product_supply_phrase_blocked_for_testing_service(self) -> None:
        from runtime.review.hallucination_guard import check_revision_text

        text = "구매자는 물품 수령 후 [ ]영업일 이내에 검수를 완료하여야 하며, 검수 완료 간주 규정을 둔다."
        result = check_revision_text(text, contract_type_code="testing_inspection_service")
        self.assertFalse(result.is_clean)
        self.assertTrue(any("product_supply_phrase" in v for v in result.violations))

    def test_ci_brand_phrase_blocked_for_testing_service(self) -> None:
        from runtime.review.hallucination_guard import check_revision_text

        text = "수탁자가 CI/SI 가이드라인을 위반한 경우 위약벌을 갑에게 지급한다."
        result = check_revision_text(text, contract_type_code="testing_inspection_service")
        self.assertFalse(result.is_clean)
        self.assertTrue(any("ci_brand_phrase" in v for v in result.violations))

    def test_product_supply_phrase_allowed_for_purchase_supply(self) -> None:
        from runtime.review.hallucination_guard import check_revision_text

        text = "구매자는 물품 수령 후 검수 완료 간주 규정에 동의한다."
        result = check_revision_text(text, contract_type_code="purchase_supply")
        self.assertTrue(result.is_clean)


if __name__ == "__main__":
    unittest.main()
