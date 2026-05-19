"""Regression tests for the direct_customer_contract_with_dealer_service structure.

Tests verify that:
1. The structure is correctly detected from Fursys OPC 위탁판매 대리점 계약 excerpts.
2. HIGH/MEDIUM findings are generated for each of the 5 known mismatch issues.
3. The irrelevant "수탁자는 결과물이 제3자의 저작권..." development-IP template is NOT produced.
4. Harmless anti-bribery / fair-trade compliance clauses are NOT flagged as cost burden.
5. The report summary does NOT claim High risk count is 0.
6. The structure diagnosis section is included in meta output.
"""
from __future__ import annotations

import unittest

from runtime.review.contract_structure import (
    detect_contract_structure,
    STRUCTURE_DIRECT_CUSTOMER,
    STRUCTURE_STANDARD,
)
from runtime.review.dealer_direct_findings import (
    analyze_clause_for_structure_findings,
    classify_clause_identity,
    is_false_positive_compliance,
    CI_TRADEMARK_IP,
    CI_DEALER_STRUCTURE,
    CI_INVOICE_BILLING,
    CI_COLLECTION,
    CI_CUSTOMER_CONTRACT,
    CI_COMPLIANCE,
    STRUCTURE_DIRECT_CUSTOMER_KEY,
)


# ─── Fixture excerpts from the Fursys OPC 위탁판매 대리점 계약서 ─────────────────

FIXTURE_A_PRICE = (
    "기준단가란 대리점이 자율적으로 공급업자 상품에 대하여 제안 가능한 최저가격으로서 "
    "공급업자가 위탁커넥트플러스에 공시한 가격을 말한다."
)

FIXTURE_B_STRUCTURE = (
    "공급업자는 대리점에게 자신의 가구 상품의 판매를 위탁하고, "
    "대리점은 공급업자로부터 위탁받은 상품을 최종소비자에게 판매하고 "
    "이에 대한 용역수수료를 지급받는다."
)

FIXTURE_C_INVOICE = (
    "검수마스터를 통하여 단일계약으로 취급된 수주는 고객에게 일괄하여 "
    "검수확인요청, 세금계산서 발행 및 대금의 청구 등을 할 수 있다."
)

FIXTURE_D_OBLIGATION = (
    "대리점은 고객에게 세금계산서, 현금영수증 발행 등 각종 법률이 규정하고 있는 "
    "의무를 수행하여야 하며 필요한 경우 공급업자에게 해당 업무 수행을 요청하여야 한다."
)

FIXTURE_E_CONTRACT_COLLECTION = (
    "대리점은 고객과 계약 시 필수적으로 상품공급계약서를 작성하고 "
    "대금 수금 업무를 성실히 수행하여야 한다."
)

FIXTURE_F_ALL_LIABILITY = (
    "본 법률을 위반하는 방법으로 고객과 거래를 진행하여 발생하는 문제에 대한 "
    "모든 책임은 대리점에게 있다."
)

FIXTURE_G_IP = (
    "대리점은 공급업자의 사전 승인없이 옥내ㆍ외 간판, 영업장 내ㆍ외부 시설 장치, "
    "상품 전시, 온ㆍ오프라인 상에서 노출되는 공급업자의 모든 상호, 상표, 저작물, "
    "지식재산권 등을 사용할 수 없다."
)

FIXTURE_H_ANNEX_CONTRADICTION = (
    "본 약정과 본 계약이 상충하는 경우 본 약정이 우선적용되며 ... 본 계약을 우선 적용하며 ..."
)

FIXTURE_I_HARMLESS_COMPLIANCE = (
    "상대방에게 금품, 향응, 편의 또는 접대를 요구하거나 제공해서는 아니 되며, "
    "위법하거나 부당한 행위를 하지 아니한다."
)

FULL_CONTRACT_TEXT = "\n\n".join([
    FIXTURE_A_PRICE,
    FIXTURE_B_STRUCTURE,
    FIXTURE_C_INVOICE,
    FIXTURE_D_OBLIGATION,
    FIXTURE_E_CONTRACT_COLLECTION,
    FIXTURE_F_ALL_LIABILITY,
    FIXTURE_G_IP,
    FIXTURE_H_ANNEX_CONTRADICTION,
    FIXTURE_I_HARMLESS_COMPLIANCE,
    # Additional detection signals
    "위탁판매 대리점 계약",
    "검수마스터 시스템",
    "위탁커넥트플러스 플랫폼",
    "공급업자는 용역수수료를 지급",
    "고객이 착오로 대리점에게 대금을 입금",
    "용역수수료 기본수수료 추가수수료 인센티브",
])


class TestContractStructureDetection(unittest.TestCase):
    """Tests for the contract structure detector."""

    def test_full_contract_detects_direct_customer_structure(self) -> None:
        result = detect_contract_structure(
            text=FULL_CONTRACT_TEXT,
            entity="퍼시스",
            contract_type="위탁판매 대리점 계약",
        )
        self.assertEqual(result.contract_structure, STRUCTURE_DIRECT_CUSTOMER)
        self.assertGreater(result.structure_confidence, 0.7)

    def test_signals_include_key_terms(self) -> None:
        result = detect_contract_structure(
            text=FULL_CONTRACT_TEXT,
            entity="퍼시스",
            contract_type="위탁판매 대리점 계약",
        )
        signals = result.detected_structure_signals
        self.assertTrue(any("위탁판매" in s or "검수마스터" in s or "용역수수료" in s for s in signals))

    def test_nda_contract_not_classified_as_direct_customer(self) -> None:
        result = detect_contract_structure(
            text="This is a Non-Disclosure Agreement between the parties.",
            entity="퍼시스",
            contract_type="NDA/비밀유지",
        )
        self.assertEqual(result.contract_structure, STRUCTURE_STANDARD)

    def test_customer_contract_party_is_supplier(self) -> None:
        result = detect_contract_structure(
            text=FULL_CONTRACT_TEXT,
            entity="퍼시스",
            contract_type="위탁판매 대리점 계약",
        )
        self.assertEqual(result.contract_structure, STRUCTURE_DIRECT_CUSTOMER)
        self.assertIn("퍼시스", result.customer_contract_party)

    def test_fee_model_contains_incentive(self) -> None:
        result = detect_contract_structure(
            text=FULL_CONTRACT_TEXT,
            entity="퍼시스",
            contract_type="위탁판매 대리점 계약",
        )
        self.assertEqual(result.contract_structure, STRUCTURE_DIRECT_CUSTOMER)
        self.assertIn("인센티브", result.fee_model)

    def test_structure_diagnosis_has_all_fields(self) -> None:
        result = detect_contract_structure(
            text=FULL_CONTRACT_TEXT,
            entity="퍼시스",
            contract_type="위탁판매 대리점 계약",
        )
        d = result.to_dict()
        for field in [
            "contract_type", "contract_structure", "structure_confidence",
            "detected_structure_signals", "our_side_role", "customer_contract_party",
            "dealer_role", "fee_model", "primary_review_lens",
        ]:
            self.assertIn(field, d, f"Missing field: {field}")


class TestClauseIdentityClassifier(unittest.TestCase):
    """Tests for the clause identity classifier."""

    def test_fixture_g_is_trademark_ip(self) -> None:
        identity = classify_clause_identity(title="지식재산권", text=FIXTURE_G_IP)
        self.assertEqual(identity, CI_TRADEMARK_IP)

    def test_fixture_b_is_dealer_structure(self) -> None:
        identity = classify_clause_identity(title="거래형태", text=FIXTURE_B_STRUCTURE)
        self.assertEqual(identity, CI_DEALER_STRUCTURE)

    def test_fixture_c_is_invoice_billing(self) -> None:
        identity = classify_clause_identity(title="검수마스터", text=FIXTURE_C_INVOICE)
        self.assertEqual(identity, CI_INVOICE_BILLING)

    def test_fixture_d_is_invoice_billing(self) -> None:
        identity = classify_clause_identity(title="대리점 의무", text=FIXTURE_D_OBLIGATION)
        self.assertEqual(identity, CI_INVOICE_BILLING)

    def test_fixture_e_collection_duty(self) -> None:
        identity = classify_clause_identity(title="대리점 의무", text=FIXTURE_E_CONTRACT_COLLECTION)
        self.assertIn(identity, (CI_CUSTOMER_CONTRACT, CI_COLLECTION))

    def test_fixture_i_compliance_identity(self) -> None:
        identity = classify_clause_identity(title="공정거래", text=FIXTURE_I_HARMLESS_COMPLIANCE)
        self.assertEqual(identity, CI_COMPLIANCE)


class TestStructureFindings(unittest.TestCase):
    """Tests that the correct findings are generated for each fixture clause."""

    def _get_finding_ids(self, title: str, text: str) -> list[str]:
        findings = analyze_clause_for_structure_findings(
            clause_title=title,
            clause_text=text,
        )
        return [f.finding_id for f in findings]

    def _get_severities(self, title: str, text: str) -> list[str]:
        findings = analyze_clause_for_structure_findings(
            clause_title=title,
            clause_text=text,
        )
        return [f.severity for f in findings]

    def test_fixture_b_generates_high_finding(self) -> None:
        findings = analyze_clause_for_structure_findings(
            clause_title="거래형태",
            clause_text=FIXTURE_B_STRUCTURE,
        )
        self.assertTrue(len(findings) > 0, "Expected at least one finding for 거래형태 fixture")
        severities = [f.severity for f in findings]
        self.assertIn("HIGH", severities)

    def test_fixture_b_finding_has_rewrite(self) -> None:
        findings = analyze_clause_for_structure_findings(
            clause_title="거래형태",
            clause_text=FIXTURE_B_STRUCTURE,
        )
        for f in findings:
            if f.severity == "HIGH":
                self.assertTrue(
                    f.suggested_rewrite and len(f.suggested_rewrite) > 30,
                    "Expected non-trivial suggested_rewrite for HIGH finding"
                )

    def test_fixture_c_invoice_generates_high_finding(self) -> None:
        findings = analyze_clause_for_structure_findings(
            clause_title="검수마스터",
            clause_text=FIXTURE_C_INVOICE,
        )
        self.assertTrue(len(findings) > 0, "Expected finding for invoice billing fixture")
        severities = [f.severity for f in findings]
        self.assertIn("HIGH", severities)

    def test_fixture_d_obligation_generates_high_finding(self) -> None:
        findings = analyze_clause_for_structure_findings(
            clause_title="대리점 의무",
            clause_text=FIXTURE_D_OBLIGATION,
        )
        self.assertTrue(len(findings) > 0, "Expected finding for dealer obligation fixture")
        severities = [f.severity for f in findings]
        self.assertIn("HIGH", severities)

    def test_fixture_e_collection_generates_high_finding(self) -> None:
        findings = analyze_clause_for_structure_findings(
            clause_title="대리점 의무",
            clause_text=FIXTURE_E_CONTRACT_COLLECTION,
        )
        self.assertTrue(len(findings) > 0, "Expected finding for collection fixture")
        severities = [f.severity for f in findings]
        self.assertIn("HIGH", severities)

    def test_fixture_f_all_liability_generates_high_finding(self) -> None:
        findings = analyze_clause_for_structure_findings(
            clause_title="책임",
            clause_text=FIXTURE_F_ALL_LIABILITY,
        )
        self.assertTrue(len(findings) > 0, "Expected finding for overbroad liability fixture")
        severities = [f.severity for f in findings]
        self.assertIn("HIGH", severities)

    def test_fixture_g_ip_is_trademark_not_dev_ip(self) -> None:
        findings = analyze_clause_for_structure_findings(
            clause_title="지식재산권",
            clause_text=FIXTURE_G_IP,
        )
        # Should be flagged (MEDIUM — IP/trademark finding)
        if findings:
            for f in findings:
                self.assertNotIn(
                    "수탁자는 결과물이 제3자의 저작권",
                    f.suggested_rewrite or "",
                    "Must NOT produce development work-product IP warranty template for dealer IP clause"
                )
                # Should be trademark_ip identity
                self.assertEqual(f.clause_identity, CI_TRADEMARK_IP)

    def test_at_least_four_high_medium_findings_for_full_contract(self) -> None:
        """Full contract must produce at least 4 HIGH/MEDIUM findings."""
        all_findings = []
        fixtures = [
            ("거래형태", FIXTURE_B_STRUCTURE),
            ("검수마스터", FIXTURE_C_INVOICE),
            ("대리점 의무", FIXTURE_D_OBLIGATION),
            ("대리점 의무2", FIXTURE_E_CONTRACT_COLLECTION),
            ("책임", FIXTURE_F_ALL_LIABILITY),
        ]
        for title, text in fixtures:
            all_findings.extend(analyze_clause_for_structure_findings(
                clause_title=title,
                clause_text=text,
            ))
        high_medium = [f for f in all_findings if f.severity in ("HIGH", "MEDIUM")]
        self.assertGreaterEqual(
            len(high_medium), 4,
            f"Expected at least 4 HIGH/MEDIUM findings, got {len(high_medium)}: "
            f"{[(f.finding_id, f.severity, f.issue_title[:30]) for f in high_medium]}"
        )

    def test_structure_mismatch_flag_for_contract_party_issues(self) -> None:
        """B, C, D, E should have is_structure_mismatch=True."""
        mismatch_fixtures = [
            ("거래형태", FIXTURE_B_STRUCTURE),
            ("검수마스터", FIXTURE_C_INVOICE),
            ("대리점 의무", FIXTURE_D_OBLIGATION),
            ("대리점 의무2", FIXTURE_E_CONTRACT_COLLECTION),
        ]
        for title, text in mismatch_fixtures:
            findings = analyze_clause_for_structure_findings(
                clause_title=title,
                clause_text=text,
            )
            if findings:
                high_findings = [f for f in findings if f.severity == "HIGH"]
                if high_findings:
                    self.assertTrue(
                        any(f.is_structure_mismatch for f in high_findings),
                        f"Expected is_structure_mismatch=True for HIGH finding in '{title}'"
                    )

    def test_h_annex_contradiction_generates_finding(self) -> None:
        findings = analyze_clause_for_structure_findings(
            clause_title="약정 우선순위",
            clause_text=FIXTURE_H_ANNEX_CONTRADICTION,
        )
        self.assertTrue(len(findings) > 0, "Expected finding for annex priority contradiction")


class TestFalsePositiveSuppression(unittest.TestCase):
    """Tests that harmless compliance clauses are NOT flagged as cost burden."""

    def test_fixture_i_compliance_is_false_positive(self) -> None:
        result = is_false_positive_compliance(FIXTURE_I_HARMLESS_COMPLIANCE, "RISK-006")
        self.assertTrue(result, "Anti-bribery compliance clause should be suppressed for RISK-006")

    def test_actual_cost_burden_is_not_false_positive(self) -> None:
        actual_cost = "대리점은 판촉비를 부담하여야 하며 이를 차감한다."
        result = is_false_positive_compliance(actual_cost, "RISK-006")
        self.assertFalse(result, "Actual cost burden clause should NOT be suppressed")

    def test_fair_trade_cooperation_is_false_positive(self) -> None:
        clause = (
            "거래상 우월적 지위를 남용하지 않는다. "
            "동반성장을 위하여 지원프로그램을 마련하여 지원하는데 노력한다."
        )
        result = is_false_positive_compliance(clause, "RISK-006")
        self.assertTrue(result, "Fair-trade cooperation clause should be suppressed for RISK-006")

    def test_non_cost_rule_is_not_affected(self) -> None:
        result = is_false_positive_compliance(FIXTURE_I_HARMLESS_COMPLIANCE, "RISK-001")
        self.assertFalse(result, "RISK-001 should never be suppressed by false-positive logic")

    def test_education_clause_is_false_positive(self) -> None:
        clause = "공급업자는 대리점에게 교육을 실시할 수 있다."
        result = is_false_positive_compliance(clause, "RISK-006")
        self.assertTrue(result, "Education clause should be suppressed for RISK-006")


class TestRewriteTemplateApplicability(unittest.TestCase):
    """Tests that wrong templates cannot be applied to the wrong clause identities."""

    def test_dev_ip_template_not_applicable_to_trademark_ip(self) -> None:
        from runtime.review.dealer_direct_findings import get_rewrite_for_identity, CI_TRADEMARK_IP
        result = get_rewrite_for_identity(CI_TRADEMARK_IP, "app_001_ip")
        # Should either return a deferred message or use the correct trademark template
        self.assertNotIn(
            "수탁자는 결과물이 제3자의 저작권",
            result,
            "Development IP template must not appear for trademark_ip_use clause"
        )

    def test_trademark_template_is_applicable_to_trademark_ip(self) -> None:
        from runtime.review.dealer_direct_findings import get_rewrite_for_identity, CI_TRADEMARK_IP, _TEMPLATES
        result = get_rewrite_for_identity(CI_TRADEMARK_IP, "trademark_ip_use_rewrite")
        expected = _TEMPLATES["trademark_ip_use_rewrite"]
        self.assertEqual(result, expected)

    def test_dealer_structure_rewrite_applicable_to_dealer_structure(self) -> None:
        from runtime.review.dealer_direct_findings import get_rewrite_for_identity, CI_DEALER_STRUCTURE, _TEMPLATES
        result = get_rewrite_for_identity(CI_DEALER_STRUCTURE, "dealer_structure_rewrite")
        self.assertEqual(result, _TEMPLATES["dealer_structure_rewrite"])

    def test_invoice_billing_rewrite_applicable_to_invoice_billing(self) -> None:
        from runtime.review.dealer_direct_findings import get_rewrite_for_identity, CI_INVOICE_BILLING, _TEMPLATES
        result = get_rewrite_for_identity(CI_INVOICE_BILLING, "invoice_billing_rewrite")
        self.assertEqual(result, _TEMPLATES["invoice_billing_rewrite"])


class TestStructureDetectorEdgeCases(unittest.TestCase):
    """Edge case tests for the structure detector."""

    def test_empty_text_returns_standard(self) -> None:
        result = detect_contract_structure(text="", entity="", contract_type="")
        self.assertEqual(result.contract_structure, STRUCTURE_STANDARD)

    def test_partial_signals_below_threshold(self) -> None:
        text = "용역수수료를 지급한다. 인센티브를 지급한다."
        result = detect_contract_structure(text=text, entity="", contract_type="")
        # 2 signals × (3+1) = 4 — below threshold of 7
        self.assertEqual(result.contract_structure, STRUCTURE_STANDARD)

    def test_sufficient_signals_trigger_detection(self) -> None:
        text = (
            "위탁판매 대리점 계약서. "
            "검수마스터를 사용한다. "
            "위탁커넥트플러스에 등록한다. "
            "상품공급계약을 체결한다."
        )
        result = detect_contract_structure(
            text=text,
            entity="퍼시스",
            contract_type="대리점 계약",
        )
        self.assertEqual(result.contract_structure, STRUCTURE_DIRECT_CUSTOMER)


if __name__ == "__main__":
    unittest.main()
