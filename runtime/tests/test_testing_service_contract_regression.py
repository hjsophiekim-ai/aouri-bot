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
    "검수 완료 간주", "반품이 불가", "이행유보권", "주문제작 공정",
    "무상 A/S 대상", "위험은 공급자가", "설치 환경 요건",
    "CI/SI 가이드라인", "브랜드를 훼손", "위약벌을", "제3자의 저작권",
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

    def test_self_check_flags_real_exculpatory_clause_as_uncovered(self) -> None:
        # 제6조/제11조의 포괄적 면책조항(귀책사유 불문 면책)은 이 계약서에 실제로
        # 존재하는 진짜 리스크다. self-check의 우선순위 리스크 커버리지 스캔이
        # 이를 "본문에 있으나 아직 findings로 안 잡힘" 목록에 표시해야 한다 —
        # 최소한 완전히 조용히 누락되지는 않는다.
        report = self.bundle.meta.get("self_check")
        self.assertIn("exculpatory_clause", report.get("priority_risk_present_but_unflagged", []))


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
