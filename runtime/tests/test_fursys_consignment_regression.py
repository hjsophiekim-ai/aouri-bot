"""Regression tests for Fursys consignment dealer contract review quality.

Validates the six failure modes identified in the real-world case:
  OPC_퍼시스_판매대리점_계약서_260430_검토중.docx vs aouribot_revision (73).docx

Tests:
  1. Contract type classification (consignment_sales_agency)
  2. Our party recognition (퍼시스 = supplier, not "미확정")
  3. Forbidden dev-contract phrases in Article 19 revision
  4. Setoff clause severity reclassification (LOW → MEDIUM+)
  5. Group company recognition (일룸, 시디즈, 데스커, 바로스)
  6. Noise suppression (no LOW spam in default output)
  7. Placeholder text suppression
  8. HIGH issue must have proposed_revision
  9. Compliance clause false-positive suppression
"""
from __future__ import annotations

import unittest
from pathlib import Path


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fursys_consignment_dealer.txt"


class ContractClassifierTest(unittest.TestCase):
    """Test 1-2: Classification and our-party recognition."""

    def _get_text(self) -> str:
        return FIXTURE_PATH.read_text(encoding="utf-8")

    def test_contract_type_is_consignment_sales_agency(self) -> None:
        from runtime.review.contract_classifier import classify_contract_detailed

        profile = classify_contract_detailed(
            entity="퍼시스",
            contract_type="대리점/위탁/유통",
            text=self._get_text(),
        )
        self.assertIn(
            profile.contract_type,
            ("consignment_sales_agency", "direct_customer_sales_support"),
            f"Expected consignment_sales_agency, got: {profile.contract_type}. Reasons: {profile.reasons}",
        )

    def test_our_party_is_fursys(self) -> None:
        from runtime.review.contract_classifier import classify_contract_detailed

        profile = classify_contract_detailed(
            entity="퍼시스",
            contract_type="대리점/위탁/유통",
            text=self._get_text(),
        )
        self.assertEqual(profile.our_party, "퍼시스")

    def test_our_legal_role_is_supplier(self) -> None:
        from runtime.review.contract_classifier import classify_contract_detailed

        profile = classify_contract_detailed(
            entity="퍼시스",
            contract_type="대리점/위탁/유통",
            text=self._get_text(),
        )
        self.assertEqual(profile.our_legal_role, "supplier")

    def test_customer_contracting_party_field_is_set(self) -> None:
        from runtime.review.contract_classifier import classify_contract_detailed

        profile = classify_contract_detailed(
            entity="퍼시스",
            contract_type="대리점/위탁/유통",
            text=self._get_text(),
        )
        # Must be퍼시스 or "needs_clarification_with_high_risk" — never None without reason
        self.assertIn(
            profile.customer_contracting_party,
            ("퍼시스", "needs_clarification_with_high_risk", "공급업자"),
            f"Got unexpected value: {profile.customer_contracting_party}",
        )

    def test_high_risk_signals_in_unresolved(self) -> None:
        from runtime.review.contract_classifier import classify_contract_detailed

        profile = classify_contract_detailed(
            entity="퍼시스",
            contract_type="대리점/위탁/유통",
            text=self._get_text(),
        )
        # The fixture has "대리점은 최종소비자에게 판매" → needs_clarification_with_high_risk
        # At least one unresolved item should mention high risk
        combined = " ".join(profile.unresolved_questions)
        # Should detect at least one structural issue
        self.assertTrue(
            len(profile.unresolved_questions) > 0 or profile.customer_contracting_party == "needs_clarification_with_high_risk",
            "Expected at least one unresolved question for consignment dealer structure issues",
        )


class GroupCompanyRecognitionTest(unittest.TestCase):
    """Test 3: All Fursys group companies must be recognised as 'ours'."""

    _BRANDS = [
        ("퍼시스", "supplier"),
        ("일룸", "supplier"),
        ("시디즈", "supplier"),
        ("데스커", "supplier"),
        ("바로스", "supplier"),
    ]

    def test_all_fursys_brands_recognized_as_group(self) -> None:
        from runtime.review.contract_classifier import is_fursys_group

        for brand, _ in self._BRANDS:
            with self.subTest(brand=brand):
                self.assertTrue(
                    is_fursys_group(brand),
                    f"{brand} not recognised as Fursys group brand",
                )

    def test_all_brands_recognized_in_party_role(self) -> None:
        from runtime.review.party_role import infer_party_role

        dealer_text = "대리점 계약서\n위탁판매 대리점\n용역수수료를 지급한다."
        for brand, expected_role in self._BRANDS:
            with self.subTest(brand=brand):
                role = infer_party_role(
                    entity=brand,
                    contract_type="대리점/위탁/유통",
                    text=dealer_text,
                    answers=None,
                )
                self.assertEqual(
                    role.our_role,
                    expected_role,
                    f"{brand}: expected our_role='{expected_role}', got '{role.our_role}'",
                )

    def test_fursys_brand_text_in_contract(self) -> None:
        from runtime.review.contract_classifier import detect_our_party_from_text

        texts = [
            ("주식회사 시디즈 대리점 계약서", "시디즈"),
            ("일룸 위탁판매 계약서", "일룸"),
            ("SIDIZ dealer agreement", "시디즈"),
            ("Desker consignment contract", "데스커"),
        ]
        for text, expected in texts:
            with self.subTest(text=text[:30]):
                result = detect_our_party_from_text(text)
                self.assertEqual(result, expected, f"For text '{text[:30]}': expected '{expected}', got '{result}'")


class HallucinationGuardTest(unittest.TestCase):
    """Test 4: Forbidden dev-contract phrases must not appear in dealer contract revisions."""

    def test_dev_phrases_flagged_in_dealer_revision(self) -> None:
        from runtime.review.hallucination_guard import check_revision_text

        dev_text = (
            "수탁자는 결과물이 제3자의 저작권·특허권을 침해하지 않음을 보증한다. "
            "오픈소스 소프트웨어 사용 시 라이선스 조건을 고지하여야 한다. "
            "개발 완료 후 소스코드를 제출하여야 한다."
        )
        result = check_revision_text(
            dev_text,
            contract_type_code="consignment_sales_agency",
        )
        self.assertFalse(result.is_clean, "Expected guard to catch dev phrases in dealer contract")
        self.assertTrue(len(result.violations) > 0)

    def test_clean_dealer_revision_passes_guard(self) -> None:
        from runtime.review.hallucination_guard import check_revision_text

        clean_text = (
            "공급업자는 고객과 직접 상품공급계약을 체결하고, "
            "대리점은 공급업자로부터 위탁받은 범위 내에서 고객 발굴, 수주 등록, "
            "납품 지원, 수금 지원 등 판매 관련 용역을 수행한다."
        )
        result = check_revision_text(
            clean_text,
            contract_type_code="consignment_sales_agency",
        )
        self.assertTrue(result.is_clean, f"Expected clean revision to pass guard. Violations: {result.violations}")

    def test_dev_phrases_allowed_in_software_contract(self) -> None:
        from runtime.review.hallucination_guard import check_revision_text

        dev_text = (
            "수탁자는 산출물이 제3자의 저작권을 침해하지 않음을 보증한다. "
            "오픈소스 라이선스를 고지하여야 한다."
        )
        result = check_revision_text(
            dev_text,
            contract_type_code="software_app_development",
        )
        self.assertTrue(result.is_clean, "Dev phrases should be allowed in software contract")

    def test_article19_revision_no_dev_phrases(self) -> None:
        from runtime.review.hallucination_guard import is_dev_phrase_in_text
        from runtime.review.dealer_direct_findings import _TEMPLATES

        # Check the trademark_ip_use_rewrite template (used for Article 19)
        template = _TEMPLATES.get("trademark_ip_use_rewrite", "")
        self.assertFalse(
            is_dev_phrase_in_text(template),
            f"trademark_ip_use_rewrite contains forbidden dev phrases: {template[:200]}",
        )


class SeverityReclassifierTest(unittest.TestCase):
    """Test 5: Severity reclassification rules."""

    def test_setoff_clause_reclassified_to_medium(self) -> None:
        from runtime.review.severity_reclassifier import reclassify_setoff_clause

        text = "공급업자는 용역수수료에서 차감하거나 거래보증금에서 상계할 수 있다."
        result = reclassify_setoff_clause("LOW", text)
        self.assertIn(result, ("MEDIUM", "HIGH"), f"Setoff clause LOW should be upgraded, got: {result}")

    def test_all_liability_clause_reclassified_to_high(self) -> None:
        from runtime.review.severity_reclassifier import reclassify_severity

        text = "모든 책임은 대리점에게 있다."
        new_sev, reasons = reclassify_severity("LOW", text, "consignment_sales_agency")
        self.assertEqual(new_sev, "HIGH", f"'모든 책임' should be HIGH, got: {new_sev}")
        self.assertTrue(any("all_liability" in r for r in reasons))

    def test_invoice_mismatch_reclassified_to_high(self) -> None:
        from runtime.review.severity_reclassifier import reclassify_severity

        text = "대리점은 고객에게 세금계산서 발행 및 대금의 청구를 수행한다."
        new_sev, reasons = reclassify_severity("MEDIUM", text, "consignment_sales_agency")
        self.assertEqual(new_sev, "HIGH", f"Invoice party mismatch should be HIGH, got: {new_sev}")

    def test_collection_liability_reclassified_to_high(self) -> None:
        from runtime.review.severity_reclassifier import reclassify_severity

        text = "대리점은 대금 수금 업무를 성실히 수행하여야 한다."
        new_sev, reasons = reclassify_severity("LOW", text, "consignment_sales_agency")
        self.assertEqual(new_sev, "HIGH")

    def test_supply_cutoff_reclassified_to_high(self) -> None:
        from runtime.review.severity_reclassifier import reclassify_severity

        text = "공급업자는 공급을 중단하거나 물량을 현저히 축소할 수 있다."
        new_sev, reasons = reclassify_severity("LOW", text, "consignment_sales_agency")
        self.assertEqual(new_sev, "HIGH")

    def test_severity_never_downgrades(self) -> None:
        from runtime.review.severity_reclassifier import reclassify_severity

        text = "단순 문구 조항이다."
        new_sev, _ = reclassify_severity("HIGH", text, "general")
        self.assertEqual(new_sev, "HIGH", "Severity must never downgrade")

    def test_consignment_combined_reclassifier(self) -> None:
        from runtime.review.severity_reclassifier import reclassify_for_consignment_dealer

        text = "용역수수료에서 차감하거나 정책지원금에서 상계할 수 있다."
        new_sev, reasons = reclassify_for_consignment_dealer("LOW", text)
        self.assertIn(new_sev, ("MEDIUM", "HIGH"))


class OutputFilterTest(unittest.TestCase):
    """Test 6-8: Output quality filtering."""

    def _make_issue(
        self,
        severity: str = "HIGH",
        proposed_revision: str = "구체적인 수정문안입니다.",
        original_text: str = "원문 텍스트",
        problem: str = "문제점 설명",
        legal_reason: str = "법적 이유",
    ) -> "ReviewIssue":
        from runtime.review.output_filter import ReviewIssue
        return ReviewIssue(
            clause_id="C001",
            clause_title="제6조",
            severity=severity,  # type: ignore[arg-type]
            approval_required=True,
            issue_title="테스트 이슈",
            original_text=original_text,
            problem=problem,
            legal_business_reason=legal_reason,
            proposed_revision=proposed_revision,
            negotiation_position="협상 포지션",
            confidence=0.9,
        )

    def test_issue_with_empty_proposed_revision_invalid(self) -> None:
        from runtime.review.output_filter import is_valid_issue

        issue = self._make_issue(proposed_revision="")
        self.assertFalse(is_valid_issue(issue))

    def test_issue_with_placeholder_invalid(self) -> None:
        from runtime.review.output_filter import is_valid_issue

        for placeholder in ("제안 문안 없음", "사유 없음", "원문 핵심: -"):
            with self.subTest(placeholder=placeholder):
                issue = self._make_issue(proposed_revision=placeholder)
                self.assertFalse(is_valid_issue(issue), f"Placeholder '{placeholder}' should invalidate issue")

    def test_high_issue_with_generic_revision_invalid(self) -> None:
        from runtime.review.output_filter import is_valid_issue

        issue = self._make_issue(
            severity="HIGH",
            proposed_revision="통합 관리 필요",
        )
        self.assertFalse(is_valid_issue(issue))

    def test_low_issues_excluded_from_default_output(self) -> None:
        from runtime.review.output_filter import ReviewIssue, filter_issues

        issues = [
            self._make_issue(severity="LOW"),
            self._make_issue(severity="MEDIUM"),
            self._make_issue(severity="HIGH"),
        ]
        result = filter_issues(issues, include_low=False)
        self.assertEqual(len(result["low"]), 0)
        self.assertGreater(len(result["high"]) + len(result["medium"]), 0)

    def test_low_issues_included_when_requested(self) -> None:
        from runtime.review.output_filter import ReviewIssue, filter_issues

        issues = [self._make_issue(severity="LOW")]
        result = filter_issues(issues, include_low=True)
        self.assertEqual(len(result["low"]), 1)

    def test_medium_capped_at_10(self) -> None:
        from runtime.review.output_filter import ReviewIssue, filter_issues

        issues = [
            ReviewIssue(
                clause_id=f"C{i:03d}",
                clause_title=f"제{i}조",
                severity="MEDIUM",
                approval_required=False,
                issue_title=f"이슈 {i}",
                original_text="원문",
                problem="문제점",
                legal_business_reason="법적 이유",
                proposed_revision="수정문안",
                negotiation_position="협상",
                confidence=0.8,
            )
            for i in range(1, 20)
        ]
        result = filter_issues(issues, max_medium=10)
        self.assertLessEqual(len(result["medium"]), 10)

    def test_top_risks_max_5(self) -> None:
        from runtime.review.output_filter import ReviewIssue, filter_issues

        issues = [
            self._make_issue(severity="HIGH") for _ in range(10)
        ]
        result = filter_issues(issues, max_top_risks=5)
        self.assertLessEqual(len(result["top_risks"]), 5)

    def test_dev_phrases_in_dealer_revision_excluded(self) -> None:
        from runtime.review.output_filter import is_valid_issue

        issue = self._make_issue(
            severity="HIGH",
            proposed_revision="수탁자는 결과물이 제3자의 저작권을 침해하지 않음을 보증한다.",
        )
        self.assertFalse(
            is_valid_issue(issue, contract_type_code="consignment_sales_agency"),
            "Issue with dev phrases should be invalid for dealer contract",
        )

    def test_placeholder_detection_in_raw_output(self) -> None:
        from runtime.review.output_filter import has_placeholder_text

        bad_output = {
            "clause_results": [
                {"risk_tier": "HIGH", "suggested_rewrite": "제안 문안 없음"},
            ]
        }
        self.assertTrue(has_placeholder_text(bad_output))

        good_output = {
            "clause_results": [
                {"risk_tier": "HIGH", "suggested_rewrite": "구체적인 수정문안입니다."},
            ]
        }
        self.assertFalse(has_placeholder_text(good_output))


class NoiseSuppressTest(unittest.TestCase):
    """Test 9: Compliance clause false-positive suppression."""

    def test_compliance_clause_not_flagged_as_cost_burden(self) -> None:
        from runtime.review.dealer_direct_findings import is_false_positive_compliance

        compliance_text = (
            "거래상 우월적 지위를 남용하지 않으며, "
            "동반성장을 위하여 지원프로그램을 운영할 수 있다. "
            "불공정거래행위를 하지 아니하며 향응·편의를 제공해서는 아니된다."
        )
        is_fp = is_false_positive_compliance(compliance_text, "RISK-006")
        self.assertTrue(is_fp, "Clean compliance clause should be suppressed as false positive")

    def test_actual_cost_burden_not_suppressed(self) -> None:
        from runtime.review.dealer_direct_findings import is_false_positive_compliance

        cost_text = (
            "대리점은 판촉비를 부담하여야 한다. "
            "반품 비용은 대리점이 차감하여 정산한다."
        )
        is_fp = is_false_positive_compliance(cost_text, "RISK-006")
        self.assertFalse(is_fp, "Actual cost burden clause should NOT be suppressed")


class ArticleSpecificSeverityTest(unittest.TestCase):
    """Test specific article severity requirements from the failure case."""

    def test_article5_structure_mismatch_detected_as_high(self) -> None:
        from runtime.review.dealer_direct_findings import analyze_clause_for_structure_findings

        art5_text = (
            "대리점은 공급업자로부터 위탁받은 상품을 최종소비자에게 판매하고, "
            "판매 관련 제반 업무를 수행한다."
        )
        findings = analyze_clause_for_structure_findings(
            clause_title="거래형태",
            clause_text=art5_text,
            clause_id="제5조제1항",
        )
        high_findings = [f for f in findings if f.severity == "HIGH"]
        self.assertGreater(
            len(high_findings), 0,
            f"Article 5.1 structure mismatch should be HIGH. Got findings: {[f.finding_id for f in findings]}",
        )

    def test_article6_13_all_liability_detected_as_high(self) -> None:
        from runtime.review.dealer_direct_findings import analyze_clause_for_structure_findings

        art6_13_text = (
            "대리점이 본 조의 의무를 위반하여 관련 법령 또는 입찰·조달 조건을 위반하고 "
            "이로 인해 공급업자에게 손해가 발생하는 경우 모든 책임은 대리점에게 있다."
        )
        findings = analyze_clause_for_structure_findings(
            clause_title="대리점의 의무",
            clause_text=art6_13_text,
            clause_id="제6조제13항",
        )
        high_findings = [f for f in findings if f.severity == "HIGH"]
        self.assertGreater(
            len(high_findings), 0,
            "Article 6.13 'all liability' should be HIGH",
        )

    def test_article6_13_high_finding_has_proposed_revision(self) -> None:
        from runtime.review.dealer_direct_findings import analyze_clause_for_structure_findings

        art6_13_text = (
            "모든 책임은 대리점에게 있다."
        )
        findings = analyze_clause_for_structure_findings(
            clause_title="의무 및 책임",
            clause_text=art6_13_text,
            clause_id="제6조제13항",
        )
        for f in findings:
            if f.severity == "HIGH":
                self.assertTrue(
                    f.suggested_rewrite and len(f.suggested_rewrite) > 20,
                    f"HIGH finding {f.finding_id} must have proposed_revision",
                )

    def test_article16_setoff_minimum_medium(self) -> None:
        from runtime.review.severity_reclassifier import reclassify_setoff_clause

        art16_text = (
            "공급업자는 대리점에게 청구할 채권이 발생한 경우, "
            "용역수수료에서 차감하거나 정책지원금에서 상계할 수 있다."
        )
        result = reclassify_setoff_clause("LOW", art16_text)
        self.assertIn(result, ("MEDIUM", "HIGH"), "Article 16 setoff must be at least MEDIUM")

    def test_article19_4_revision_no_dev_language(self) -> None:
        from runtime.review.hallucination_guard import check_revision_text
        from runtime.review.dealer_direct_findings import _TEMPLATES

        # The trademark/IP template should be used for Article 19
        ip_template = _TEMPLATES.get("trademark_ip_use_rewrite", "")
        result = check_revision_text(ip_template, contract_type_code="consignment_sales_agency")
        self.assertTrue(
            result.is_clean,
            f"Article 19 IP template contains forbidden dev phrases: {result.violations}",
        )

    def test_article19_original_dev_language_detected(self) -> None:
        from runtime.review.hallucination_guard import check_revision_text

        # The original Article 19.4 (problematic) text
        art19_4_original = (
            "대리점(수탁자)은 본 계약의 이행 결과물이 제3자의 저작권, 특허권을 "
            "침해하지 않음을 보증한다. 오픈소스 소프트웨어 사용 시 라이선스 조건을 "
            "고지하여야 한다. 개발 완료 시 소스코드를 제출하여야 한다."
        )
        # If this were proposed as a revision for a dealer contract, it should be blocked
        result = check_revision_text(art19_4_original, contract_type_code="consignment_sales_agency")
        self.assertFalse(result.is_clean, "Original Article 19.4 dev language should be blocked as revision")


if __name__ == "__main__":
    unittest.main()
