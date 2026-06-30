"""Professional legal review quality tests for dealer_rental_service_contract.

Required results for 퍼시스 렌탈대리점계약서:
  - Role matrix: our_company=퍼시스, customer_contract_party≠대리점, dealer_agency_authority=False
  - TOP risks use DLR-001 as first item (if fixture triggers it)
  - isr_*/sppc_* never in TOP risks or 필수수정
  - Clause-template hard gate blocks wrong-context revisions
  - UI and DOCX display_bucket counts are identical
  - ProfessionalFinding has all required attorney-level fields
"""
from __future__ import annotations

import unittest
from pathlib import Path


DEALER_FIXTURE = Path(__file__).parent / "fixtures" / "fursys_rental_dealer_contract.txt"

_BLOCKED_PREFIXES = ("isr_", "sppc_", "pi_", "svc_")


def _is_blocked(rule_id: str) -> bool:
    return any(rule_id.startswith(p) for p in _BLOCKED_PREFIXES)


# ─────────────────────────────────────────────────────────────────────────────


class TestRoleMatrix(unittest.TestCase):
    """test_role_matrix_for_fursys_rental_dealer"""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.review.review_orchestrator import build_dealer_rental_review
        text = DEALER_FIXTURE.read_text(encoding="utf-8")
        cls.result = build_dealer_rental_review(text=text, entity="퍼시스")

    def test_role_matrix_for_fursys_rental_dealer(self) -> None:
        rm = self.result["role_matrix"]
        self.assertEqual(rm["our_company"], "퍼시스",
            f"our_company는 퍼시스여야 합니다. 실제: {rm['our_company']}")
        self.assertIn("퍼시스", rm["customer_contract_party"],
            f"customer_contract_party에 퍼시스가 포함되어야 합니다. 실제: {rm['customer_contract_party']}")
        self.assertIn("퍼시스", rm["invoice_issuer"],
            f"invoice_issuer에 퍼시스가 포함되어야 합니다. 실제: {rm['invoice_issuer']}")
        self.assertFalse(rm["dealer_agency_authority"],
            "dealer_agency_authority는 False여야 합니다")
        self.assertIn("수금지원", rm["collection_role"],
            "collection_role에 '수금지원' 포함되어야 합니다")

    def test_our_company_not_baros(self) -> None:
        rm = self.result["role_matrix"]
        self.assertNotEqual(rm["our_company"], "바로스",
            "우리 회사가 바로스로 오인되면 안 됩니다")

    def test_customer_contract_party_not_dealer(self) -> None:
        rm = self.result["role_matrix"]
        ccp = rm["customer_contract_party"]
        self.assertNotIn("대리점", ccp,
            f"고객 계약 당사자가 대리점이면 안 됩니다. 실제: {ccp}")

    def test_billing_party_not_dealer(self) -> None:
        rm = self.result["role_matrix"]
        bp = rm["billing_party"]
        self.assertNotIn("대리점", bp,
            f"billing_party가 대리점이면 안 됩니다. 실제: {bp}")

    def test_role_matrix_has_all_fields(self) -> None:
        rm = self.result["role_matrix"]
        required = [
            "our_company", "supplier", "dealer", "customer_contract_party",
            "invoice_issuer", "billing_party", "collection_role",
            "dealer_agency_authority", "ownership_party",
        ]
        for f in required:
            self.assertIn(f, rm, f"role_matrix 필드 누락: {f}")


# ─────────────────────────────────────────────────────────────────────────────


class TestNoIsrSppcInTopRisks(unittest.TestCase):
    """test_no_isr_sppc_in_top_risks"""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.review.review_orchestrator import build_dealer_rental_review
        text = DEALER_FIXTURE.read_text(encoding="utf-8")
        cls.result = build_dealer_rental_review(text=text, entity="퍼시스")

    def test_no_isr_sppc_in_top_risks(self) -> None:
        ff = self.result["final_findings"]
        top_ids = {
            f.get("rule_id") or f.get("clause_id") or ""
            for f in ff["top_risks"]
        }
        blocked_found = {rid for rid in top_ids if _is_blocked(rid)}
        self.assertEqual(len(blocked_found), 0,
            f"isr_*/sppc_*/pi_*/svc_* found in top_risks: {blocked_found}")

    def test_no_isr_sppc_in_high_issues(self) -> None:
        ff = self.result["final_findings"]
        high_ids = {
            f.get("rule_id") or f.get("clause_id") or ""
            for f in ff["high_issues"]
        }
        blocked_found = {rid for rid in high_ids if _is_blocked(rid)}
        self.assertEqual(len(blocked_found), 0,
            f"isr_*/sppc_* found in high_issues (필수수정): {blocked_found}")

    def test_is_blocked_utility(self) -> None:
        from runtime.review.dealer_rental_rules import is_blocked_for_dealer_rental
        self.assertTrue(is_blocked_for_dealer_rental("isr_accident_reporting"))
        self.assertTrue(is_blocked_for_dealer_rental("sppc_inspection_standard"))
        self.assertTrue(is_blocked_for_dealer_rental("pi_safety_manager"))
        self.assertTrue(is_blocked_for_dealer_rental("svc_latency_check"))
        self.assertFalse(is_blocked_for_dealer_rental("DLR-001"))
        self.assertFalse(is_blocked_for_dealer_rental("MI-001"))
        self.assertFalse(is_blocked_for_dealer_rental("MR-001"))

    def test_filter_issues_blocks_isr_for_dealer(self) -> None:
        from runtime.review.output_filter import ReviewIssue, filter_issues
        fake_isr = ReviewIssue(
            clause_id="isr_accident_reporting",
            clause_title="사고 발생 즉시 보고 의무",
            severity="HIGH",
            approval_required=True,
            issue_title="제조물 사고보고 의무",
            original_text="사고 발생 즉시 보고",
            problem="보고 의무 미비",
            legal_business_reason="제조물책임법",
            proposed_revision="사고 시 즉시 보고한다.",
            negotiation_position="필요",
            confidence=0.9,
        )
        result = filter_issues(
            [fake_isr],
            contract_type_code="dealer_rental_service_contract",
        )
        high_ids = [i.clause_id for i in result["high"]]
        self.assertNotIn("isr_accident_reporting", high_ids,
            "isr_* 는 dealer_rental 에서 high에 나오면 안 됩니다")
        top_ids = [i.clause_id for i in result["top_risks"]]
        self.assertNotIn("isr_accident_reporting", top_ids,
            "isr_* 는 dealer_rental 에서 top_risks에 나오면 안 됩니다")


# ─────────────────────────────────────────────────────────────────────────────


class TestClauseTemplateHardGate(unittest.TestCase):
    """test_clause_template_hard_gate"""

    def test_termination_no_ownership(self) -> None:
        from runtime.review.hallucination_guard import check_revision_text
        bad = "계약 해지 시 소유권 표식 확인 및 채권추심 기관을 통해 렌탈료를 회수한다."
        result = check_revision_text(
            bad,
            contract_type_code="dealer_rental_service_contract",
            clause_identity="termination",
        )
        self.assertFalse(result.is_clean,
            "해지 조항에 소유권/채권추심 문구는 차단해야 합니다")

    def test_confidentiality_no_hr(self) -> None:
        from runtime.review.hallucination_guard import check_revision_text
        bad = "비밀정보 보호를 위해 직원 채용 시 보안 서약서를 징구하고 스카우트를 금지한다."
        result = check_revision_text(
            bad,
            contract_type_code="dealer_rental_service_contract",
            clause_identity="confidentiality",
        )
        self.assertFalse(result.is_clean,
            "비밀유지 조항에 직원 채용/스카우트 문구는 차단해야 합니다")

    def test_assignment_no_promotion_cost(self) -> None:
        from runtime.review.hallucination_guard import check_revision_text
        bad = "계약상 지위 양도 시 판촉비, 광고비, 반품비, 원상회복비 정산이 선행되어야 한다."
        result = check_revision_text(
            bad,
            contract_type_code="dealer_rental_service_contract",
            clause_identity="assignment",
        )
        self.assertFalse(result.is_clean,
            "양도 조항에 판촉비/광고비/반품비 문구는 차단해야 합니다")

    def test_assignment_party_change_alias_works(self) -> None:
        from runtime.review.hallucination_guard import check_revision_text
        bad = "계약 지위 이전 시 원상회복비 정산을 선행한다."
        result = check_revision_text(
            bad,
            contract_type_code="dealer_rental_service_contract",
            clause_identity="assignment_party_change",
        )
        self.assertFalse(result.is_clean,
            "assignment_party_change alias도 반품비/원상회복비를 차단해야 합니다")

    def test_clean_termination_passes(self) -> None:
        from runtime.review.hallucination_guard import check_revision_text
        good = "공급업자는 대리점이 중대한 의무를 위반하고 30일 내 시정하지 않는 경우 계약을 해지할 수 있다."
        result = check_revision_text(
            good,
            contract_type_code="dealer_rental_service_contract",
            clause_identity="termination",
        )
        self.assertTrue(result.is_clean,
            f"정상 해지 문구가 차단되면 안 됩니다. violations: {result.violations}")

    def test_clean_confidentiality_passes(self) -> None:
        from runtime.review.hallucination_guard import check_revision_text
        good = "대리점은 비밀정보를 제3자에게 공개하지 않으며, 계약 종료 후 30일 내 파기한다."
        result = check_revision_text(
            good,
            contract_type_code="dealer_rental_service_contract",
            clause_identity="confidentiality",
        )
        self.assertTrue(result.is_clean,
            f"정상 비밀유지 문구가 차단되면 안 됩니다. violations: {result.violations}")

    def test_orchestrator_hard_gate_no_mismatch_in_results(self) -> None:
        """Orchestrator step E must not produce MISMATCH_TEXT for DLR rules."""
        from runtime.review.review_orchestrator import build_dealer_rental_review, _MISMATCH_TEXT
        text = DEALER_FIXTURE.read_text(encoding="utf-8")
        result = build_dealer_rental_review(text=text, entity="퍼시스")

        ff = result["final_findings"]
        all_findings = ff["high_issues"] + ff["medium_issues"]
        for finding in all_findings:
            proposed = (
                finding.get("proposed_clause") or
                finding.get("proposed_revision") or
                finding.get("suggested_rewrite") or ""
            )
            # DLR rules have well-crafted proposed clauses that should not trigger the gate
            self.assertNotEqual(proposed, _MISMATCH_TEXT,
                f"{finding.get('rule_id')}: 수정문안이 MISMATCH로 차단되면 안 됩니다")


# ─────────────────────────────────────────────────────────────────────────────


class TestProfessionalTopRiskOrder(unittest.TestCase):
    """test_professional_top_risk_order"""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.review.review_orchestrator import build_dealer_rental_review
        text = DEALER_FIXTURE.read_text(encoding="utf-8")
        cls.result = build_dealer_rental_review(text=text, entity="퍼시스")

    def test_professional_top_risk_order(self) -> None:
        ff = self.result["final_findings"]
        top = ff["top_risks"]
        self.assertGreater(len(top), 0, "TOP 리스크가 비어 있습니다")
        first_id = top[0].get("rule_id") or top[0].get("clause_id")
        self.assertEqual(first_id, "DLR-001",
            f"첫 번째 TOP 리스크는 DLR-001이어야 합니다. 실제: {first_id}")

    def test_top_risks_max_5(self) -> None:
        ff = self.result["final_findings"]
        self.assertLessEqual(len(ff["top_risks"]), 5,
            "TOP 리스크는 최대 5개")

    def test_expected_top_risk_themes(self) -> None:
        ff = self.result["final_findings"]
        top_text = " ".join(
            (f.get("issue_title") or "") + " " + (f.get("relevant_clause") or "")
            for f in ff["top_risks"]
        )
        expected_themes = ["고객계약", "수수료", "해지", "미수금", "개인정보", "판촉"]
        found = [th for th in expected_themes if th in top_text]
        self.assertGreater(len(found), 1,
            f"TOP 리스크에 핵심 주제가 부족합니다. 발견: {found}, 전체 텍스트: {top_text[:300]}")

    def test_dlr_rules_all_8_defined(self) -> None:
        from runtime.review.dealer_rental_rules import DLR_RULES
        ids = [r.rule_id for r in DLR_RULES]
        for expected_id in [f"DLR-{i:03d}" for i in range(1, 9)]:
            self.assertIn(expected_id, ids, f"{expected_id} not in DLR_RULES")

    def test_dlr_001_004_005_trigger_on_fixture(self) -> None:
        from runtime.review.dealer_rental_rules import get_triggered_dlr_rules
        text = DEALER_FIXTURE.read_text(encoding="utf-8")
        triggered = get_triggered_dlr_rules(text)
        ids = [r.rule_id for r in triggered]
        self.assertIn("DLR-001", ids, "DLR-001 should trigger on fixture")
        self.assertIn("DLR-004", ids, "DLR-004 (수수료 차감) should trigger on fixture")
        self.assertIn("DLR-005", ids, "DLR-005 (해지/갱신거절) should trigger on fixture")


# ─────────────────────────────────────────────────────────────────────────────


class TestUIDocxCountsIdentical(unittest.TestCase):
    """test_ui_docx_counts_are_identical"""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.review.review_orchestrator import build_dealer_rental_review
        text = DEALER_FIXTURE.read_text(encoding="utf-8")
        cls.result = build_dealer_rental_review(text=text, entity="퍼시스")

    def test_ui_docx_counts_are_identical(self) -> None:
        ff = self.result["final_findings"]
        buckets = ff["display_buckets"]
        self.assertEqual(buckets["필수수정"], ff["high_count"],
            f"필수수정 count 불일치: buckets={buckets['필수수정']}, high_count={ff['high_count']}")
        self.assertEqual(buckets["권장수정"], ff["medium_count"],
            f"권장수정 count 불일치: buckets={buckets['권장수정']}, medium_count={ff['medium_count']}")

    def test_display_bucket_property(self) -> None:
        from runtime.review.review_orchestrator import ProfessionalFinding
        high_f = ProfessionalFinding(
            rule_id="DLR-001", issue_title="테스트", relevant_clause="제1조",
            original_excerpt="", legal_risk="법적리스크", business_risk="사업리스크",
            why_this_matters="이유", risk_level="HIGH", approval_required=True,
            required_action="조치", proposed_clause="제안문안", negotiation_position="협상",
            evidence_from_contract="", confidence=0.9,
        )
        self.assertEqual(high_f.display_bucket, "필수수정")

        med_f = ProfessionalFinding(
            rule_id="DLR-006", issue_title="테스트", relevant_clause="제2조",
            original_excerpt="", legal_risk="법적리스크", business_risk="사업리스크",
            why_this_matters="이유", risk_level="MEDIUM", approval_required=False,
            required_action="조치", proposed_clause="제안문안", negotiation_position="협상",
            evidence_from_contract="", confidence=0.8,
        )
        self.assertEqual(med_f.display_bucket, "권장수정")

    def test_final_findings_counts_consistent_with_lists(self) -> None:
        ff = self.result["final_findings"]
        self.assertEqual(len(ff["high_issues"]), ff["high_count"],
            "high_issues 개수가 high_count와 다릅니다")
        self.assertEqual(len(ff["medium_issues"]), ff["medium_count"],
            "medium_issues 개수가 medium_count와 다릅니다")


# ─────────────────────────────────────────────────────────────────────────────


class TestFinalFindingsHasLawyerFields(unittest.TestCase):
    """test_final_findings_has_lawyer_fields"""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.review.review_orchestrator import build_dealer_rental_review
        text = DEALER_FIXTURE.read_text(encoding="utf-8")
        cls.result = build_dealer_rental_review(text=text, entity="퍼시스")

    def test_final_findings_has_lawyer_fields(self) -> None:
        ff = self.result["final_findings"]
        required_keys = ["top_risks", "high_issues", "medium_issues", "display_buckets",
                         "high_count", "medium_count", "must_fix_count"]
        for k in required_keys:
            self.assertIn(k, ff, f"final_findings 키 누락: {k}")

        for finding in ff["top_risks"]:
            for field_name in [
                "issue_title", "legal_risk", "business_risk", "why_this_matters",
                "required_action", "proposed_clause", "negotiation_position",
                "evidence_from_contract", "display_bucket",
            ]:
                self.assertIn(field_name, finding,
                    f"finding 필드 누락: {field_name} in {finding.get('rule_id')}")

    def test_no_abstract_placeholder_in_findings(self) -> None:
        ff = self.result["final_findings"]
        for finding in ff["high_issues"] + ff["medium_issues"]:
            lr = finding.get("legal_risk") or finding.get("problem") or ""
            br = finding.get("business_risk") or ""
            self.assertNotIn("자산 소유권을 명확히 함", lr + br,
                f"추상적 플레이스홀더 감지: {finding.get('rule_id')}")
            self.assertNotIn("일반적으로", lr + br,
                f"generic 법률 설명 감지: {finding.get('rule_id')}")

    def test_dlr_rule_has_all_professional_fields(self) -> None:
        from runtime.review.dealer_rental_rules import DLR_RULES
        for rule in DLR_RULES:
            self.assertGreater(len(rule.legal_risk), 20,
                f"{rule.rule_id}: legal_risk 너무 짧음")
            self.assertGreater(len(rule.business_risk), 20,
                f"{rule.rule_id}: business_risk 너무 짧음")
            self.assertGreater(len(rule.why_this_matters), 20,
                f"{rule.rule_id}: why_this_matters 너무 짧음")
            self.assertGreater(len(rule.proposed_clause), 30,
                f"{rule.rule_id}: proposed_clause 너무 짧음")
            self.assertGreater(len(rule.trigger_keywords), 0,
                f"{rule.rule_id}: trigger_keywords 없음")

    def test_dlr_rule_to_clause_result_structure(self) -> None:
        from runtime.review.dealer_rental_rules import DLR_001
        cr = DLR_001.to_clause_result("테스트 발췌")
        required_cr_keys = [
            "clause_id", "clause_title", "risk_tier", "severity",
            "approval_required", "issue_title", "original_text",
            "problem", "suggested_rewrite", "negotiation_position",
        ]
        for k in required_cr_keys:
            self.assertIn(k, cr, f"to_clause_result 키 누락: {k}")
        self.assertEqual(cr["clause_id"], "DLR-001")
        self.assertEqual(cr["severity"], "HIGH")
        self.assertTrue(cr["approval_required"])


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main()
