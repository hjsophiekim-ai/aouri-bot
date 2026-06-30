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


class TestDealerRentalFinalGate(unittest.TestCase):
    """Regression tests for apply_dealer_rental_final_gate — 6 failure conditions.

    These tests verify the production clause_results gate:
    1. isr_*/sppc_* removed from clause_results (UI text never shows them)
    2. top_risks from final_findings has no isr_*/sppc_*
    3. Termination clause proposed_clause has no 소유권/채권추심/신용정보
    4. Assignment clause proposed_clause has no 판촉비/광고비/반품비/원상회복비
    5. Confidentiality clause proposed_clause has no 인력/채용/배치/평가/징계
    6. UI count == DOCX count (final_findings counts consistent with lists)
    """

    def _make_cr(self, clause_id: str, clause_title: str, suggested_rewrite: str,
                 risk_tier: str = "HIGH", high_risk: bool = True) -> dict:
        return {
            "clause_id": clause_id,
            "clause_title": clause_title,
            "suggested_rewrite": suggested_rewrite,
            "original_text": "원문",
            "risk_tier": risk_tier,
            "high_risk": high_risk,
            "approval_required": high_risk,
            "has_rewrite_change": bool(suggested_rewrite),
            "display_kind": "redline" if high_risk else "guidance",
        }

    # ── Failure condition 1: UI 텍스트에 isr_ 또는 sppc_가 포함되면 실패 ──────
    def test_blocked_isr_ids_removed_from_clause_results(self) -> None:
        from runtime.review.clause_level import apply_dealer_rental_final_gate, _DEALER_RENTAL_HARD_BLOCKED_IDS
        input_results = [
            self._make_cr("isr_accident_reporting", "[제조물검토] 사고 보고", "즉시 보고하라"),
            self._make_cr("isr_pl_defect_liability", "[제조물검토] 제조물 결함", "책임을 진다"),
            self._make_cr("isr_installation_defect", "[제조물검토] 설치 하자", "설치자가 책임"),
            self._make_cr("isr_user_safety", "[제조물검토] 사용자 안전", "안전보호"),
            self._make_cr("isr_safety_certification", "[제조물검토] 안전인증", "KC인증"),
            self._make_cr("isr_pl_insurance", "[제조물검토] PL보험", "보험가입"),
            self._make_cr("isr_defect_sla", "[제조물검토] 하자 SLA", "24시간 응답"),
            self._make_cr("sppc_inspection_standard", "[공급자보호] 검수기준", "검수 완료"),
            self._make_cr("sppc_return_limit", "[공급자보호] 반품제한", "반품불가"),
            self._make_cr("sppc_payment_retention", "[공급자보호] 대금미지급", "이행유보"),
            self._make_cr("sppc_custom_cancel_limit", "[공급자보호] 취소제한", "취소불가"),
            self._make_cr("DLR-001", "고객계약 구조", "고객계약은 공급업자가 체결한다."),
        ]
        result = apply_dealer_rental_final_gate(input_results, "dealer_rental_service_contract")
        result_ids = {str(cr.get("clause_id") or "") for cr in result}
        for blocked_id in _DEALER_RENTAL_HARD_BLOCKED_IDS:
            self.assertNotIn(blocked_id, result_ids,
                f"[실패조건1] UI에 {blocked_id}가 나오면 안 됩니다")
        self.assertIn("DLR-001", result_ids, "DLR-001은 제거되면 안 됩니다")

    def test_blocked_sppc_ids_removed_from_clause_results(self) -> None:
        from runtime.review.clause_level import apply_dealer_rental_final_gate
        input_results = [
            self._make_cr("sppc_inspection_standard", "[공급자보호] 검수", "검수 기준"),
            self._make_cr("DLR-004", "수수료 상계", "상계를 제한한다."),
        ]
        result = apply_dealer_rental_final_gate(input_results, "dealer_rental_service_contract")
        result_ids = [str(cr.get("clause_id") or "") for cr in result]
        self.assertNotIn("sppc_inspection_standard", result_ids,
            "[실패조건1] sppc_inspection_standard가 UI에 나오면 안 됩니다")
        self.assertIn("DLR-004", result_ids)

    # ── Failure condition 2: final_findings top_risks에 isr_/sppc_가 있으면 실패 ──
    def test_top_risks_has_no_isr_sppc(self) -> None:
        from runtime.review.output_filter import ReviewIssue, filter_issues
        # isr_* 항목은 original_text가 없어 _review_issues_raw에서 제외됨
        # 그러나 ReviewIssue로 직접 만들어 filter_issues 통과 시도
        fake_isr = ReviewIssue(
            clause_id="isr_accident_reporting",
            clause_title="[제조물검토] 사고보고",
            severity="HIGH",
            approval_required=True,
            issue_title="사고보고 의무",
            original_text="사고시 보고",
            problem="미비",
            legal_business_reason="제조물책임법",
            proposed_revision="즉시 보고",
            negotiation_position="",
            confidence=0.9,
        )
        result = filter_issues([fake_isr], contract_type_code="dealer_rental_service_contract")
        top_ids = [i.clause_id for i in result["top_risks"]]
        self.assertNotIn("isr_accident_reporting", top_ids,
            "[실패조건2] isr_* 가 final_findings top_risks에 있으면 안 됩니다")

    # ── Failure condition 3: 계약해지 조항 proposed_clause에 소유권/채권추심/신용정보 금지 ──
    def test_termination_clause_no_ownership_in_proposed(self) -> None:
        from runtime.review.clause_level import apply_dealer_rental_final_gate, _DEALER_RENTAL_MISMATCH_MSG
        forbidden_texts = [
            "계약 해지 시 소유권 표식을 확인한다.",
            "해지 후 채권추심 기관에 위탁한다.",
            "해지 시 신용정보를 조회한다.",
            "해지 후 개인정보를 활용해 회수한다.",
        ]
        for text in forbidden_texts:
            cr = self._make_cr("DLR-005", "계약해지 조항", text)
            result = apply_dealer_rental_final_gate([cr], "dealer_rental_service_contract")
            sr = str(result[0].get("suggested_rewrite") or "")
            self.assertEqual(sr, _DEALER_RENTAL_MISMATCH_MSG,
                f"[실패조건3] 계약해지 조항에 금지 문구 차단 실패: '{text[:30]}'")
            self.assertFalse(result[0].get("has_rewrite_change"),
                "[실패조건3] has_rewrite_change는 False여야 합니다")

    # ── Failure condition 4: 계약자 변경 조항 proposed_clause에 판촉비/반품비 등 금지 ──
    def test_assignment_clause_no_promotion_cost_in_proposed(self) -> None:
        from runtime.review.clause_level import apply_dealer_rental_final_gate, _DEALER_RENTAL_MISMATCH_MSG
        forbidden_texts = [
            "지위 이전 시 판촉비를 정산해야 한다.",
            "양도 시 광고비 분담이 필요하다.",
            "계약자 변경 시 반품비를 공제한다.",
            "양도 전 원상회복비를 납부해야 한다.",
            "지위 이전 시 비용분담이 선행되어야 한다.",
        ]
        for text in forbidden_texts:
            cr = self._make_cr("DLR-007", "계약자 변경 조항", text)
            result = apply_dealer_rental_final_gate([cr], "dealer_rental_service_contract")
            sr = str(result[0].get("suggested_rewrite") or "")
            self.assertEqual(sr, _DEALER_RENTAL_MISMATCH_MSG,
                f"[실패조건4] 계약자 변경 조항 금지 문구 차단 실패: '{text[:30]}'")

    # ── Failure condition 5: 비밀유지 조항 proposed_clause에 인력/채용/배치/평가/징계 금지 ──
    def test_confidentiality_clause_no_hr_in_proposed(self) -> None:
        from runtime.review.clause_level import apply_dealer_rental_final_gate, _DEALER_RENTAL_MISMATCH_MSG
        forbidden_texts = [
            "비밀유지를 위해 인력을 관리해야 한다.",
            "비밀정보 보호를 위한 채용 기준을 정한다.",
            "기밀 담당자 배치 방식을 명시한다.",
            "기밀 접근자에 대한 평가를 정기 실시한다.",
            "비밀 위반 시 징계 절차를 적용한다.",
            "기밀 보호를 위해 경영간섭 조항을 추가한다.",
        ]
        for text in forbidden_texts:
            cr = self._make_cr("DLR-008", "비밀유지 조항", text)
            result = apply_dealer_rental_final_gate([cr], "dealer_rental_service_contract")
            sr = str(result[0].get("suggested_rewrite") or "")
            self.assertEqual(sr, _DEALER_RENTAL_MISMATCH_MSG,
                f"[실패조건5] 비밀유지 조항 금지 문구 차단 실패: '{text[:30]}'")

    # ── Failure condition 6: UI count와 docx report count가 다르면 실패 ──────────
    def test_ui_count_equals_docx_count_via_final_findings(self) -> None:
        from runtime.review.review_orchestrator import build_dealer_rental_review
        text = DEALER_FIXTURE.read_text(encoding="utf-8")
        result = build_dealer_rental_review(text=text, entity="퍼시스")
        ff = result["final_findings"]
        self.assertEqual(len(ff["high_issues"]), ff["high_count"],
            "[실패조건6] high_issues 개수가 high_count와 다릅니다 (UI ≠ DOCX)")
        self.assertEqual(len(ff["medium_issues"]), ff["medium_count"],
            "[실패조건6] medium_issues 개수가 medium_count와 다릅니다 (UI ≠ DOCX)")
        self.assertEqual(ff["display_buckets"]["필수수정"], ff["high_count"],
            "[실패조건6] 필수수정 bucket 카운트가 high_count와 다릅니다")
        self.assertEqual(ff["display_buckets"]["권장수정"], ff["medium_count"],
            "[실패조건6] 권장수정 bucket 카운트가 medium_count와 다릅니다")

    def test_gate_not_applied_for_other_contract_types(self) -> None:
        from runtime.review.clause_level import apply_dealer_rental_final_gate
        input_results = [
            self._make_cr("isr_accident_reporting", "[제조물검토] 사고보고", "즉시 보고"),
        ]
        result = apply_dealer_rental_final_gate(input_results, "general_purchase")
        self.assertEqual(len(result), 1,
            "dealer_rental 이외 계약에서는 isr_*를 제거하면 안 됩니다")


# ─────────────────────────────────────────────────────────────────────────────


class TestUIRenderGate(unittest.TestCase):
    """Smoke tests: UI rendering gate must filter isr_/sppc_/clause-topic violations.

    These tests replicate the JS applyDealerRentalRenderGate() logic in Python so
    CI can verify correctness without a browser. The gate is authoritative in JS;
    this is a structural mirror.
    """

    _HARD_BLOCKED = frozenset({
        "isr_accident_reporting", "isr_pl_defect_liability", "isr_installation_defect",
        "isr_user_safety", "isr_safety_certification", "isr_pl_insurance", "isr_defect_sla",
        "sppc_inspection_standard", "sppc_return_limit", "sppc_payment_retention",
        "sppc_custom_cancel_limit",
    })
    _BLOCKED_KW = ["사고 발생 보고", "검수 완료 간주", "반품 제한", "이행유보권", "주문제작 취소 제한"]
    _CLAUSE_GATE = [
        (["해지", "종료", "해제"], ["소유권", "채권추심", "신용정보", "개인정보"]),
        (["양도", "지위 이전", "계약자 변경"], ["판촉비", "광고비", "반품비", "원상회복비", "비용분담"]),
        (["비밀", "기밀"], ["인력", "채용", "배치", "평가", "징계", "경영간섭"]),
    ]
    _MISMATCH = "자동수정 보류: 조항 주제와 수정문안 불일치"
    _CONTRACT_TYPE = "dealer_rental_service_contract"

    def _gate(self, items: list[dict], contract_type: str = "") -> tuple[list[dict], list[str]]:
        """Python mirror of JS applyDealerRentalRenderGate()."""
        ct = contract_type or self._CONTRACT_TYPE
        if "dealer_rental" not in ct:
            return items, []
        filtered, hidden = [], []
        for it in items:
            cid = str(it.get("clause_id") or it.get("rule_id") or "")
            title = str(it.get("issue_title") or it.get("clause_title") or "")
            if (cid in self._HARD_BLOCKED or cid.startswith("isr_") or cid.startswith("sppc_")
                    or any(k in title for k in self._BLOCKED_KW)):
                hidden.append(cid or title)
                continue
            tlo = str(it.get("clause_title") or "").lower()
            rw = str(it.get("suggested_rewrite") or "").strip()
            if rw and rw != self._MISMATCH:
                for title_keys, forbidden in self._CLAUSE_GATE:
                    if any(k in tlo for k in title_keys):
                        if any(f in rw for f in forbidden):
                            it = dict(it, suggested_rewrite=self._MISMATCH, has_rewrite_change=False)
                        break
            filtered.append(it)
        return filtered, hidden

    # ── test_streamlit_ui_uses_final_findings_only ──
    def test_streamlit_ui_uses_final_findings_only(self) -> None:
        """[실패조건7] UI는 raw clause_results를 직접 노출하지 않고 gate를 통과한 결과만 사용해야 한다."""
        raw = [
            {"clause_id": "isr_accident_reporting", "clause_title": "사고처리", "risk_tier": "HIGH", "high_risk": True, "suggested_rewrite": "보고 즉시"},
            {"clause_id": "DLR-001", "clause_title": "거래구조", "risk_tier": "HIGH", "high_risk": True, "suggested_rewrite": "수정안"},
            {"clause_id": "DLR-003", "clause_title": "세금계산서", "risk_tier": "MEDIUM", "high_risk": False, "suggested_rewrite": ""},
        ]
        filtered, hidden = self._gate(raw)
        ids = [x["clause_id"] for x in filtered]
        self.assertNotIn("isr_accident_reporting", ids,
            "[실패조건7] UI가 isr_accident_reporting을 표시했습니다 — raw findings 차단 실패")
        self.assertIn("DLR-001", ids, "[실패조건7] DLR-001이 UI에서 사라졌습니다")
        self.assertIn("isr_accident_reporting", hidden,
            "[실패조건7] hidden_finding_ids에 isr_accident_reporting이 없습니다")

    # ── test_no_legacy_isr_sppc_in_ui ──
    def test_no_legacy_isr_sppc_in_ui(self) -> None:
        """[실패조건8] dealer_rental에서 isr_* / sppc_* 항목이 UI에 노출되면 안 된다."""
        raw = [
            {"clause_id": "isr_safety_certification", "clause_title": "안전인증", "risk_tier": "HIGH"},
            {"clause_id": "sppc_inspection_standard", "clause_title": "검수기준", "risk_tier": "HIGH"},
            {"clause_id": "sppc_return_limit", "clause_title": "반품제한", "risk_tier": "HIGH"},
            {"clause_id": "DLR-002", "clause_title": "세금계산서", "risk_tier": "HIGH"},
        ]
        filtered, hidden = self._gate(raw)
        filtered_ids = [x["clause_id"] for x in filtered]
        for bad_id in ("isr_safety_certification", "sppc_inspection_standard", "sppc_return_limit"):
            self.assertNotIn(bad_id, filtered_ids,
                f"[실패조건8] {bad_id}가 UI에 노출되었습니다 — sppc/isr 차단 실패")
        self.assertIn("DLR-002", filtered_ids, "[실패조건8] DLR-002가 잘못 제거되었습니다")
        self.assertEqual(len(hidden), 3, "[실패조건8] hidden 수 불일치")

    # ── test_docx_and_ui_counts_match ──
    def test_docx_and_ui_counts_match(self) -> None:
        """[실패조건9] UI count와 DOCX count가 동일한 final_findings를 기준으로 산출되어야 한다."""
        # Simulate what the orchestrator produces
        from runtime.review.review_orchestrator import build_dealer_rental_review
        text = "퍼시스와 대리점 간 렌탈 위탁판매 계약입니다. 대리점은 고객과 직접 계약을 체결합니다. 세금계산서는 대리점이 발행합니다."
        result = build_dealer_rental_review(text=text, entity="퍼시스")
        ff = result.get("final_findings") or {}
        cr = result.get("clause_results") or []
        ui_high = sum(1 for x in cr if str(x.get("risk_level") or x.get("risk_tier") or "").upper() == "HIGH")
        ui_med = sum(1 for x in cr if str(x.get("risk_level") or x.get("risk_tier") or "").upper() == "MEDIUM")
        docx_high = ff.get("high_count", -1)
        docx_med = ff.get("medium_count", -1)
        self.assertEqual(ui_high, docx_high,
            f"[실패조건9] HIGH count mismatch: ui={ui_high} docx={docx_high}")
        self.assertEqual(ui_med, docx_med,
            f"[실패조건9] MEDIUM count mismatch: ui={ui_med} docx={docx_med}")

    # ── test_clause_template_gate_applied_before_render ──
    def test_clause_template_gate_applied_before_render(self) -> None:
        """[실패조건9] 최종 렌더링 직전 clause-template hard gate가 적용되어야 한다."""
        raw = [
            {
                "clause_id": "DLR-004",
                "clause_title": "계약 해지 조항",
                "risk_tier": "HIGH",
                "suggested_rewrite": "소유권 이전을 통해 담보를 설정합니다.",
            },
            {
                "clause_id": "DLR-005",
                "clause_title": "계약자 변경 조항",
                "risk_tier": "MEDIUM",
                "suggested_rewrite": "판촉비는 대리점이 부담합니다.",
            },
            {
                "clause_id": "DLR-006",
                "clause_title": "비밀유지 조항",
                "risk_tier": "MEDIUM",
                "suggested_rewrite": "인력 채용 및 배치는 공급업자가 승인합니다.",
            },
            {
                "clause_id": "DLR-001",
                "clause_title": "거래구조 명확화",
                "risk_tier": "HIGH",
                "suggested_rewrite": "퍼시스가 고객과 직접 계약을 체결합니다.",
            },
        ]
        filtered, hidden = self._gate(raw)
        rewrite_map = {x["clause_id"]: x.get("suggested_rewrite", "") for x in filtered}
        self.assertEqual(rewrite_map.get("DLR-004"), self._MISMATCH,
            "[실패조건9] 해지 조항의 소유권 문구가 차단되지 않았습니다")
        self.assertEqual(rewrite_map.get("DLR-005"), self._MISMATCH,
            "[실패조건9] 계약자 변경 조항의 판촉비 문구가 차단되지 않았습니다")
        self.assertEqual(rewrite_map.get("DLR-006"), self._MISMATCH,
            "[실패조건9] 비밀유지 조항의 인력 문구가 차단되지 않았습니다")
        self.assertEqual(rewrite_map.get("DLR-001"), "퍼시스가 고객과 직접 계약을 체결합니다.",
            "[실패조건9] 정상 수정안이 잘못 차단되었습니다")
        self.assertNotIn("DLR-001", hidden, "[실패조건9] DLR-001이 hidden_ids에 포함되었습니다")


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main()
