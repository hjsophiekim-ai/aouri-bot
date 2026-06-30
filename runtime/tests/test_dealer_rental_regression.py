"""Regression tests for Fursys rental dealer contract review quality.

Validates the failure modes identified in the real-world case:
  퍼시스 렌탈 위탁 대리점 계약서 + 바로스 A/S provider misidentification

Tests (A-G from specification):
  A. Company=퍼시스, contract_type=dealer_rental_service_contract
  B. Customer contracting party = 공급업자/퍼시스 (not 대리점)
  C. 세금계산서/대금청구 주체 = 공급업자
  D. TOP risks include: 수수료 상계, 고객 미수금, 계약 해지/갱신거절, 비용분담
  E. No 소유권/채권추심 text in termination clause revisions
  F. No 인력관리 text in confidentiality clause revisions
  G. UI display_bucket matches Word report severity bucket (unified ReviewIssue)

Additional tests:
  H. 바로스 appearing in body text does NOT override 퍼시스 hint_entity
  I. MR-001 through MR-010 trigger patterns match fixture text
  J. Standard rental contract (no dealer) NOT classified as dealer_rental_service_contract
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path


DEALER_FIXTURE = Path(__file__).parent / "fixtures" / "fursys_rental_dealer_contract.txt"
STANDARD_FIXTURE = Path(__file__).parent / "fixtures" / "fursys_rental_standard_contract.txt"


class TestA_ContractClassification(unittest.TestCase):
    """A: Company=퍼시스, contract type = dealer_rental_service_contract."""

    def _text(self) -> str:
        return DEALER_FIXTURE.read_text(encoding="utf-8")

    def test_a1_entity_is_fursys(self) -> None:
        from runtime.review.contract_classifier import classify_contract_detailed

        profile = classify_contract_detailed(
            entity="퍼시스",
            contract_type="렌탈/대리점",
            text=self._text(),
        )
        self.assertEqual(
            profile.our_party, "퍼시스",
            f"Expected our_party=퍼시스, got: {profile.our_party}",
        )

    def test_a2_contract_type_is_dealer_rental(self) -> None:
        from runtime.review.contract_classifier import classify_contract_detailed

        profile = classify_contract_detailed(
            entity="퍼시스",
            contract_type="렌탈/대리점",
            text=self._text(),
        )
        self.assertEqual(
            profile.contract_type, "dealer_rental_service_contract",
            f"Expected dealer_rental_service_contract, got: {profile.contract_type}. "
            f"Reasons: {profile.reasons}",
        )

    def test_a3_our_legal_role_is_supplier(self) -> None:
        from runtime.review.contract_classifier import classify_contract_detailed

        profile = classify_contract_detailed(
            entity="퍼시스",
            contract_type="렌탈/대리점",
            text=self._text(),
        )
        self.assertEqual(profile.our_legal_role, "supplier")


class TestB_CustomerContractingParty(unittest.TestCase):
    """B: Customer contracting party = 공급업자/퍼시스 (not 대리점)."""

    def _text(self) -> str:
        return DEALER_FIXTURE.read_text(encoding="utf-8")

    def test_b_customer_contracting_party_is_supplier(self) -> None:
        from runtime.review.contract_classifier import classify_contract_detailed

        profile = classify_contract_detailed(
            entity="퍼시스",
            contract_type="렌탈/대리점",
            text=self._text(),
        )
        # In a rental dealer contract, the supplier (퍼시스) contracts directly with end customers.
        self.assertIn(
            profile.customer_contracting_party,
            ("공급업자", "퍼시스", "공급자"),
            f"Expected customer contracting party = 공급업자/퍼시스, got: {profile.customer_contracting_party}",
        )

    def test_b_customer_contracting_party_is_not_dealer(self) -> None:
        from runtime.review.contract_classifier import classify_contract_detailed

        profile = classify_contract_detailed(
            entity="퍼시스",
            contract_type="렌탈/대리점",
            text=self._text(),
        )
        self.assertNotEqual(
            profile.customer_contracting_party, "대리점",
            "Customer contracting party must NOT be 대리점 in rental dealer structure",
        )


class TestC_TaxInvoiceIssuer(unittest.TestCase):
    """C: 세금계산서·대금청구 주체 = 공급업자."""

    def _text(self) -> str:
        return DEALER_FIXTURE.read_text(encoding="utf-8")

    def test_c_tax_invoice_issuer_is_supplier(self) -> None:
        from runtime.review.contract_classifier import classify_contract_detailed

        profile = classify_contract_detailed(
            entity="퍼시스",
            contract_type="렌탈/대리점",
            text=self._text(),
        )
        # tax_invoice_issuer should be 공급업자 or 퍼시스 — never 대리점
        if profile.tax_invoice_issuer:
            self.assertIn(
                profile.tax_invoice_issuer,
                ("공급업자", "퍼시스", "공급자"),
                f"Tax invoice issuer must be 공급업자, got: {profile.tax_invoice_issuer}",
            )
            self.assertNotEqual(
                profile.tax_invoice_issuer, "대리점",
                "Tax invoice issuer must NOT be 대리점",
            )


class TestD_TopRisks(unittest.TestCase):
    """D: Mandatory issues MR-001 through MR-010 inject the right risk topics."""

    def _text(self) -> str:
        return DEALER_FIXTURE.read_text(encoding="utf-8")

    def test_d1_mandatory_issues_injected_for_dealer_rental(self) -> None:
        from runtime.review.mandatory_issues import get_triggered_mandatory_issues

        text = self._text()
        result = get_triggered_mandatory_issues(
            contract_type_code="dealer_rental_service_contract",
            text=text,
        )
        self.assertGreater(
            len(result), 0,
            "Expected mandatory issues to be injected for dealer_rental_service_contract",
        )

    def test_d2_fee_setoff_risk_present(self) -> None:
        from runtime.review.mandatory_issues import get_triggered_mandatory_issues

        text = "수수료 차감 및 상계 조항이 포함된 계약서"
        result = get_triggered_mandatory_issues(
            contract_type_code="dealer_rental_service_contract",
            text=text,
        )
        codes = [i.issue_code for i in result]
        self.assertIn("MR-006", codes, f"MR-006 (수수료 차감/상계) should be injected. Got codes: {codes}")

    def test_d3_receivable_risk_present(self) -> None:
        from runtime.review.mandatory_issues import get_triggered_mandatory_issues

        text = "렌탈료 미납이 발생하는 경우 대리점이 이를 부담한다."
        result = get_triggered_mandatory_issues(
            contract_type_code="dealer_rental_service_contract",
            text=text,
        )
        codes = [i.issue_code for i in result]
        self.assertIn("MR-004", codes, f"MR-004 (고객 미수금) should be injected. Got codes: {codes}")

    def test_d4_termination_risk_present(self) -> None:
        from runtime.review.mandatory_issues import get_triggered_mandatory_issues

        text = "공급업자는 대리점에 대한 갱신을 거절할 수 있다."
        result = get_triggered_mandatory_issues(
            contract_type_code="dealer_rental_service_contract",
            text=text,
        )
        codes = [i.issue_code for i in result]
        self.assertIn("MR-007", codes, f"MR-007 (갱신거절) should be injected. Got codes: {codes}")

    def test_d5_promotion_cost_risk_present(self) -> None:
        from runtime.review.mandatory_issues import get_triggered_mandatory_issues

        text = "판촉 활동 비용은 대리점 부담으로 처리될 수 있다."
        result = get_triggered_mandatory_issues(
            contract_type_code="dealer_rental_service_contract",
            text=text,
        )
        codes = [i.issue_code for i in result]
        self.assertIn("MR-008", codes, f"MR-008 (판촉비 비용분담) should be injected. Got codes: {codes}")

    def test_d6_mandatory_issues_have_high_severity_codes(self) -> None:
        from runtime.review.mandatory_issues import get_triggered_mandatory_issues

        text = (
            "퍼시스의 대리점에 본 계약과 관련된 업무를 위탁할 수 있다. "
            "세금계산서 발행일은 익월 10일로 한다. "
            "렌탈 대리점을 통해 체결한 계약."
        )
        result = get_triggered_mandatory_issues(
            contract_type_code="dealer_rental_service_contract",
            text=text,
        )
        high_issues = [i for i in result if i.severity == "HIGH"]
        self.assertGreater(
            len(high_issues), 0,
            f"Expected at least one HIGH mandatory issue. Got: {[(i.issue_code, i.severity) for i in result]}",
        )


class TestE_TerminationClauseNoOwnership(unittest.TestCase):
    """E: No 소유권/채권추심 text in termination clause revisions."""

    def test_e1_termination_clause_identity_excludes_ownership(self) -> None:
        from runtime.review.dealer_direct_findings import classify_clause_identity

        termination_text = (
            "공급업자 또는 대리점은 상대방의 중대한 계약 위반 시 "
            "서면 통보 후 계약을 해지할 수 있다. "
            "갱신을 거절할 수 있다."
        )
        identity = classify_clause_identity(
            title="계약 해지",
            text=termination_text,
        )
        self.assertEqual(
            identity, "termination",
            f"Termination clause should be classified as 'termination', got: {identity}",
        )

    def test_e2_ownership_text_not_classified_as_termination(self) -> None:
        from runtime.review.dealer_direct_findings import classify_clause_identity

        ownership_text = (
            "렌탈 물품의 소유권은 공급업자에게 있으며, "
            "소유권 행사를 제한하는 표식을 훼손할 수 없다."
        )
        identity = classify_clause_identity(
            title="소유권",
            text=ownership_text,
        )
        # Ownership text with rental context should NOT be classified as termination
        self.assertNotEqual(
            identity, "termination",
            f"Ownership clause must NOT be classified as termination. Got: {identity}",
        )

    def test_e3_hallucination_guard_blocks_ownership_in_termination_revision(self) -> None:
        from runtime.review.hallucination_guard import check_revision_text

        # A revision for a termination clause that mentions 소유권 is wrong-context
        bad_revision = (
            "계약 해지 시 소유권 표식이 부착된 렌탈 물품에 대하여 "
            "채권추심 절차를 통하여 반환을 요구할 수 있다."
        )
        result = check_revision_text(
            bad_revision,
            contract_type_code="dealer_rental_service_contract",
            clause_identity="termination",
        )
        self.assertFalse(
            result.is_clean,
            "Termination clause revision with 소유권/채권추심 text must be blocked by guard",
        )
        # Verify the specific violation type
        violation_types = [v.split(":")[0] for v in result.violations]
        self.assertIn(
            "wrong_clause_context[termination]", violation_types,
            f"Expected wrong_clause_context[termination] violation. Got: {result.violations}",
        )

    def test_e4_clean_termination_revision_passes(self) -> None:
        from runtime.review.hallucination_guard import check_revision_text

        clean_revision = (
            "공급업자는 계약 만료 30일 전에 서면으로 갱신 거절 의사를 통보하여야 하며, "
            "갱신 거절 시 그 사유를 구체적으로 명시하여야 한다."
        )
        result = check_revision_text(
            clean_revision,
            contract_type_code="dealer_rental_service_contract",
            clause_identity="termination",
        )
        self.assertTrue(
            result.is_clean,
            f"Clean termination revision should pass. Violations: {result.violations}",
        )


class TestF_ConfidentialityClauseNoHR(unittest.TestCase):
    """F: No 인력관리 text in confidentiality clause revisions."""

    def test_f1_confidentiality_clause_identity_correct(self) -> None:
        from runtime.review.dealer_direct_findings import classify_clause_identity

        confidentiality_text = (
            "대리점은 본 계약에서 취득한 공급업자의 기밀 정보를 "
            "제3자에게 누설하거나 목적 외 사용하여서는 아니 된다."
        )
        identity = classify_clause_identity(
            title="비밀유지",
            text=confidentiality_text,
        )
        self.assertEqual(
            identity, "confidentiality",
            f"Confidentiality clause should be 'confidentiality', got: {identity}",
        )

    def test_f2_hr_text_not_classified_as_confidentiality(self) -> None:
        from runtime.review.dealer_direct_findings import classify_clause_identity

        hr_text = (
            "계약 기간 동안 상대방의 직원을 채용하거나 스카우트하여서는 아니 된다. "
            "인력 유출을 방지하기 위한 고용 금지 조항."
        )
        identity = classify_clause_identity(
            title="인력관리 제한",
            text=hr_text,
        )
        # HR/staffing text should NOT be classified as confidentiality
        self.assertNotEqual(
            identity, "confidentiality",
            f"HR clause must NOT be classified as confidentiality. Got: {identity}",
        )

    def test_f3_hallucination_guard_blocks_hr_in_confidentiality_revision(self) -> None:
        from runtime.review.hallucination_guard import check_revision_text

        bad_revision = (
            "대리점은 공급업자 임직원을 채용하거나 스카우트하여서는 아니 되며, "
            "인력관리 측면에서 이탈을 방지할 의무가 있다."
        )
        result = check_revision_text(
            bad_revision,
            contract_type_code="dealer_rental_service_contract",
            clause_identity="confidentiality",
        )
        self.assertFalse(
            result.is_clean,
            "Confidentiality clause revision with 인력관리 text must be blocked by guard",
        )
        violation_types = [v.split(":")[0] for v in result.violations]
        self.assertIn(
            "wrong_clause_context[confidentiality]", violation_types,
            f"Expected wrong_clause_context[confidentiality] violation. Got: {result.violations}",
        )

    def test_f4_clean_confidentiality_revision_passes(self) -> None:
        from runtime.review.hallucination_guard import check_revision_text

        clean_revision = (
            "대리점은 본 계약 이행 과정에서 취득한 공급업자의 기밀 정보 "
            "(가격 정책, 고객 정보, 영업 전략 등)를 제3자에게 공개하거나 목적 외로 이용하여서는 아니 된다. "
            "본 의무는 계약 종료 후 3년간 존속한다."
        )
        result = check_revision_text(
            clean_revision,
            contract_type_code="dealer_rental_service_contract",
            clause_identity="confidentiality",
        )
        self.assertTrue(
            result.is_clean,
            f"Clean confidentiality revision should pass. Violations: {result.violations}",
        )


class TestG_UIAndWordCountMatch(unittest.TestCase):
    """G: UI display_bucket and Word report severity buckets must be consistent (unified ReviewIssue)."""

    def test_g1_display_bucket_high_is_mandatory(self) -> None:
        from runtime.review.output_filter import ReviewIssue

        issue = ReviewIssue(
            clause_id="C001",
            clause_title="제7조",
            severity="HIGH",
            approval_required=True,
            issue_title="테스트 HIGH 이슈",
            original_text="원문",
            problem="문제점",
            legal_business_reason="법적 이유",
            proposed_revision="수정문안",
            negotiation_position="협상",
            confidence=0.9,
        )
        self.assertEqual(issue.display_bucket, "필수수정")
        # to_dict must include display_bucket
        d = issue.to_dict()
        self.assertEqual(d["display_bucket"], "필수수정")

    def test_g2_display_bucket_medium_is_recommended(self) -> None:
        from runtime.review.output_filter import ReviewIssue

        issue = ReviewIssue(
            clause_id="C002",
            clause_title="제8조",
            severity="MEDIUM",
            approval_required=False,
            issue_title="테스트 MEDIUM 이슈",
            original_text="원문",
            problem="문제점",
            legal_business_reason="법적 이유",
            proposed_revision="수정문안",
            negotiation_position="협상",
            confidence=0.8,
        )
        self.assertEqual(issue.display_bucket, "권장수정")
        d = issue.to_dict()
        self.assertEqual(d["display_bucket"], "권장수정")

    def test_g3_display_bucket_low_is_reference(self) -> None:
        from runtime.review.output_filter import ReviewIssue

        issue = ReviewIssue(
            clause_id="C003",
            clause_title="제9조",
            severity="LOW",
            approval_required=False,
            issue_title="테스트 LOW 이슈",
            original_text="원문",
            problem="문제점",
            legal_business_reason="법적 이유",
            proposed_revision="수정문안",
            negotiation_position="협상",
            confidence=0.6,
        )
        self.assertEqual(issue.display_bucket, "참고")
        d = issue.to_dict()
        self.assertEqual(d["display_bucket"], "참고")

    def test_g4_docx_review_issue_same_display_bucket_mapping(self) -> None:
        """DOCX ReviewIssue must use the same display_bucket mapping as output_filter."""
        from runtime.review.output_filter import ReviewIssue as FilterIssue
        from runtime.review.legal_review_docx import ReviewIssue as DocxIssue

        for severity, expected_bucket in [("HIGH", "필수수정"), ("MEDIUM", "권장수정"), ("LOW", "참고")]:
            with self.subTest(severity=severity):
                filter_issue = FilterIssue(
                    clause_id="C001", clause_title="조항",
                    severity=severity,  # type: ignore[arg-type]
                    approval_required=False, issue_title="이슈",
                    original_text="원문", problem="문제", legal_business_reason="이유",
                    proposed_revision="수정", negotiation_position="협상", confidence=0.9,
                )
                docx_issue = DocxIssue(
                    clause_id="C001", clause_title="조항",
                    severity=severity,  # type: ignore[arg-type]
                    approval_required=False, issue_title="이슈",
                    original_text="원문", problem="문제", legal_business_reason="이유",
                    proposed_revision="수정", negotiation_position="협상", confidence=0.9,
                )
                self.assertEqual(
                    filter_issue.display_bucket, expected_bucket,
                    f"output_filter.ReviewIssue display_bucket mismatch for {severity}",
                )
                self.assertEqual(
                    docx_issue.display_bucket, expected_bucket,
                    f"legal_review_docx.ReviewIssue display_bucket mismatch for {severity}",
                )
                # Both must agree
                self.assertEqual(
                    filter_issue.display_bucket, docx_issue.display_bucket,
                    f"Filter and DOCX ReviewIssue display_bucket differ for {severity}",
                )


class TestH_EntityDetection(unittest.TestCase):
    """H: 바로스 in body text does NOT override 퍼시스 hint_entity."""

    def test_h1_hint_entity_fursys_wins_over_baros_in_text(self) -> None:
        from runtime.review.contract_classifier import detect_our_party_from_text

        # Text mentions 바로스 as A/S logistics provider
        text_with_baros = (
            "공급업자는 물류 및 설치 과정에서 바로스 물류서비스를 이용할 수 있다. "
            "고객에 대한 개인정보 제3자 제공은 바로스에게도 적용된다."
        )
        result = detect_our_party_from_text(text_with_baros, hint_entity="퍼시스")
        self.assertEqual(
            result, "퍼시스",
            f"hint_entity='퍼시스' must take priority over '바로스' in body text. Got: {result}",
        )

    def test_h2_no_hint_entity_falls_back_to_text_scan(self) -> None:
        from runtime.review.contract_classifier import detect_our_party_from_text

        text = "주식회사 시디즈 대리점 계약서 관련"
        result = detect_our_party_from_text(text, hint_entity="")
        self.assertEqual(result, "시디즈")

    def test_h3_baros_hint_detected_correctly(self) -> None:
        from runtime.review.contract_classifier import detect_our_party_from_text

        # When uploader explicitly hints 바로스, it should be detected
        result = detect_our_party_from_text("임의 계약서 내용", hint_entity="바로스")
        self.assertEqual(result, "바로스")

    def test_h4_fursys_fixture_classified_as_fursys_not_baros(self) -> None:
        from runtime.review.contract_classifier import classify_contract_detailed

        text = DEALER_FIXTURE.read_text(encoding="utf-8")
        profile = classify_contract_detailed(
            entity="퍼시스",
            contract_type="렌탈/대리점",
            text=text,
        )
        self.assertEqual(
            profile.our_party, "퍼시스",
            f"Fixture with 바로스 in body should still detect 퍼시스 as our party. Got: {profile.our_party}",
        )


class TestI_MandatoryIssueTriggers(unittest.TestCase):
    """I: MR-001 through MR-010 trigger patterns match fixture text."""

    def _get_mandatory_issues_by_code(self) -> dict:
        from runtime.review.mandatory_issues import _DEALER_RENTAL_MANDATORY_ISSUES
        return {mi.issue_code: mi for mi in _DEALER_RENTAL_MANDATORY_ISSUES}

    def test_i_mandatory_issues_registry_has_all_mr_codes(self) -> None:
        issues = self._get_mandatory_issues_by_code()
        expected = {f"MR-{i:03d}" for i in range(1, 11)}
        missing = expected - set(issues.keys())
        self.assertEqual(
            missing, set(),
            f"Missing mandatory issue codes: {missing}",
        )

    def test_i_mr001_trigger_matches_fixture(self) -> None:
        issues = self._get_mandatory_issues_by_code()
        mr001 = issues.get("MR-001")
        self.assertIsNotNone(mr001, "MR-001 not found in registry")
        text = DEALER_FIXTURE.read_text(encoding="utf-8")
        match = re.search(mr001.trigger_pattern, text, re.IGNORECASE)
        self.assertIsNotNone(
            match,
            f"MR-001 trigger '{mr001.trigger_pattern}' should match fixture text",
        )

    def test_i_mr003_trigger_matches_fixture(self) -> None:
        issues = self._get_mandatory_issues_by_code()
        mr003 = issues.get("MR-003")
        self.assertIsNotNone(mr003, "MR-003 not found in registry")
        text = DEALER_FIXTURE.read_text(encoding="utf-8")
        match = re.search(mr003.trigger_pattern, text, re.IGNORECASE)
        self.assertIsNotNone(
            match,
            f"MR-003 trigger '{mr003.trigger_pattern}' should match fixture text",
        )

    def test_i_mr007_trigger_matches_fixture(self) -> None:
        issues = self._get_mandatory_issues_by_code()
        mr007 = issues.get("MR-007")
        self.assertIsNotNone(mr007, "MR-007 not found in registry")
        text = DEALER_FIXTURE.read_text(encoding="utf-8")
        match = re.search(mr007.trigger_pattern, text, re.IGNORECASE)
        self.assertIsNotNone(
            match,
            f"MR-007 trigger '{mr007.trigger_pattern}' should match fixture text",
        )

    def test_i_all_mandatory_issues_have_non_empty_content(self) -> None:
        from runtime.review.mandatory_issues import _DEALER_RENTAL_MANDATORY_ISSUES
        for mi in _DEALER_RENTAL_MANDATORY_ISSUES:
            with self.subTest(code=mi.issue_code):
                self.assertTrue(mi.issue_title.strip(), f"{mi.issue_code}: empty issue_title")
                self.assertTrue(mi.problem.strip(), f"{mi.issue_code}: empty problem")
                self.assertTrue(mi.proposed_revision.strip(), f"{mi.issue_code}: empty proposed_revision")
                self.assertIn(mi.severity, ("HIGH", "MEDIUM"), f"{mi.issue_code}: unexpected severity")


class TestJ_StandardRentalNotDealer(unittest.TestCase):
    """J: Standard B2B rental contract (no dealer) is NOT classified as dealer_rental_service_contract."""

    def test_j_standard_rental_not_dealer_type(self) -> None:
        from runtime.review.contract_classifier import classify_contract_detailed

        text = STANDARD_FIXTURE.read_text(encoding="utf-8")
        profile = classify_contract_detailed(
            entity="퍼시스",
            contract_type="렌탈",
            text=text,
        )
        self.assertNotEqual(
            profile.contract_type, "dealer_rental_service_contract",
            f"Standard rental contract should NOT be dealer_rental_service_contract. "
            f"Got: {profile.contract_type}. Reasons: {profile.reasons}",
        )


class TestClauseIdentityEdgeCases(unittest.TestCase):
    """Additional clause identity edge cases to prevent regressions."""

    def test_assignment_clause_not_promotion(self) -> None:
        from runtime.review.dealer_direct_findings import classify_clause_identity

        text = "대리점의 지위 또는 권리를 제3자에게 양도할 수 없다."
        identity = classify_clause_identity(title="계약 양도 제한", text=text)
        self.assertNotEqual(
            identity, "promotion",
            f"Assignment clause must NOT be classified as promotion. Got: {identity}",
        )

    def test_confidentiality_with_hr_text_not_confidentiality(self) -> None:
        from runtime.review.dealer_direct_findings import classify_clause_identity

        # When the title says 비밀 but the body is about HR, it should not be confidentiality
        text = (
            "계약 기간 중 및 종료 후 2년간 상대방의 임직원을 채용하거나 "
            "인력관리 목적으로 스카우트하는 행위를 금지한다."
        )
        identity = classify_clause_identity(title="인력 관련 제한", text=text)
        self.assertNotEqual(
            identity, "confidentiality",
            f"HR clause should not be classified as confidentiality. Got: {identity}",
        )

    def test_hallucination_guard_clause_identity_parameter(self) -> None:
        """check_revision_text must accept clause_identity parameter without error."""
        from runtime.review.hallucination_guard import check_revision_text

        result = check_revision_text(
            "정상적인 수정 문안",
            contract_type_code="dealer_rental_service_contract",
            clause_identity="termination",
        )
        # A clean text should pass regardless
        self.assertIsInstance(result.is_clean, bool)

    def test_display_bucket_in_to_dict(self) -> None:
        """display_bucket must appear in to_dict() for both output_filter and docx ReviewIssue."""
        from runtime.review.output_filter import ReviewIssue as FilterIssue
        from runtime.review.legal_review_docx import ReviewIssue as DocxIssue

        for cls in (FilterIssue, DocxIssue):
            with self.subTest(cls=cls.__module__):
                issue = cls(
                    clause_id="X", clause_title="조",
                    severity="HIGH", approval_required=True,
                    issue_title="이슈", original_text="원문",
                    problem="문제", legal_business_reason="이유",
                    proposed_revision="수정", negotiation_position="협상",
                    confidence=0.9,
                )
                d = issue.to_dict()
                self.assertIn("display_bucket", d, f"{cls.__module__}.ReviewIssue.to_dict() missing display_bucket")
                self.assertEqual(d["display_bucket"], "필수수정")


if __name__ == "__main__":
    unittest.main()
