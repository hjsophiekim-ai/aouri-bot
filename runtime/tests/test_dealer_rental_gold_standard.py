"""Gold standard regression tests for dealer_rental professional review.

Verifies that fursys_rental_dealer_contract.txt produces 김현주 수정본 수준 검토:
  - DLR-RS-001/002/009: 반영됨 (not shown as 필수수정)
  - DLR-RS-004/006: 필수 수정
  - DLR-RS-003/007/008: 보완 권장
  - DLR-RS-005: 해당없음 (excluded)
  - No isr_/sppc_/pi_ findings
  - No false "고객 계약 당사자 명시 필요" or "세금계산서 발행 주체 미확인"
"""
import os
import unittest

_FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "fursys_rental_dealer_contract.txt")


def _load_fixture() -> str:
    with open(_FIXTURE_PATH, encoding="utf-8") as f:
        return f.read()


class TestDLRSRulesAssessment(unittest.TestCase):
    """Unit tests for DLRSRule.assess_contract() on the fixture contract."""

    @classmethod
    def setUpClass(cls):
        cls.text = _load_fixture()
        from runtime.review.dealer_rental_service_rules import DLRS_RULES
        cls.rule_map = {r.rule_id: r for r in DLRS_RULES}

    def _assess(self, rule_id: str) -> str:
        return self.rule_map[rule_id].assess_contract(self.text)

    # ── 반영됨 assertions ──────────────────────────────────────────────────

    def test_dlr_rs_001_is_reflected(self):
        """제2조에서 역할 분리가 명확히 반영됨."""
        self.assertEqual(self._assess("DLR-RS-001"), "반영됨")

    def test_dlr_rs_002_is_reflected(self):
        """제3조에서 세금계산서·청구 주체가 명확히 반영됨."""
        self.assertEqual(self._assess("DLR-RS-002"), "반영됨")

    def test_dlr_rs_009_is_reflected(self):
        """제11조에서 공정거래법 준수·보복금지·관할이 반영됨."""
        self.assertEqual(self._assess("DLR-RS-009"), "반영됨")

    # ── 필수수정 assertions ────────────────────────────────────────────────

    def test_dlr_rs_004_is_must_fix(self):
        """제4조③ 수수료 차감 사전통지·이의절차 없음 → 필수 수정."""
        self.assertEqual(self._assess("DLR-RS-004"), "필수 수정")

    def test_dlr_rs_006_is_must_fix(self):
        """제7조② '정당한 사유 없이 갱신 거절 가능' → 필수 수정."""
        self.assertEqual(self._assess("DLR-RS-006"), "필수 수정")

    # ── 보완권장 assertions ────────────────────────────────────────────────

    def test_dlr_rs_003_is_partial(self):
        """제5조② 귀책 한정 있으나 '일정 범위' 불명확 → 보완 권장."""
        self.assertEqual(self._assess("DLR-RS-003"), "보완 권장")

    def test_dlr_rs_007_is_partial(self):
        """제6조② 설치 하자 귀책 범위 불명확 → 보완 권장."""
        self.assertEqual(self._assess("DLR-RS-007"), "보완 권장")

    def test_dlr_rs_008_is_partial(self):
        """제6조③ 개인정보 파기·이관 절차 없음 → 보완 권장."""
        self.assertEqual(self._assess("DLR-RS-008"), "보완 권장")

    # ── 해당없음 assertions ────────────────────────────────────────────────

    def test_dlr_rs_005_is_na(self):
        """거래보증금 조항 없음 → 해당없음."""
        self.assertEqual(self._assess("DLR-RS-005"), "해당없음")


class TestProfessionalAssessmentOutput(unittest.TestCase):
    """Integration tests for run_professional_assessment() on the fixture contract."""

    @classmethod
    def setUpClass(cls):
        text = _load_fixture()
        from runtime.review.professional_assessment import run_professional_assessment
        cls.result = run_professional_assessment(text=text, entity="퍼시스")
        cls.clause_results = cls.result["clause_results"]
        cls.must_fix = cls.result["must_fix"]
        cls.partial = cls.result["partial"]
        cls.already_reflected = cls.result["already_reflected"]
        cls.excluded = cls.result["excluded"]
        cls.role_matrix = cls.result["role_matrix"]

    def _find_by_id(self, rule_id: str) -> dict | None:
        for f in self.clause_results:
            if f.get("rule_id") == rule_id or f.get("clause_id") == rule_id:
                return f
        return None

    # ── Role matrix ────────────────────────────────────────────────────────

    def test_role_matrix_confirmed(self):
        """역할매트릭스: 공급업자-고객 직접 계약 구조 확인됨."""
        self.assertTrue(self.role_matrix.get("role_matrix_confirmed"), "role_matrix_confirmed should be True")

    def test_role_matrix_dealer_not_party(self):
        """역할매트릭스: 대리점이 계약 당사자 아님 확인됨."""
        self.assertTrue(self.role_matrix.get("dealer_is_not_contract_party"))

    # ── 필수수정 must appear ───────────────────────────────────────────────

    def test_must_fix_contains_dlr_rs_004(self):
        """DLR-RS-004 수수료 차감이 필수수정에 포함."""
        ids = [f["rule_id"] for f in self.must_fix]
        self.assertIn("DLR-RS-004", ids)

    def test_must_fix_contains_dlr_rs_006(self):
        """DLR-RS-006 갱신거절이 필수수정에 포함."""
        ids = [f["rule_id"] for f in self.must_fix]
        self.assertIn("DLR-RS-006", ids)

    # ── 반영됨 must NOT appear as 필수수정 ─────────────────────────────────

    def test_dlr_rs_001_not_in_must_fix(self):
        """DLR-RS-001(역할구조)이 필수수정에 나오면 안 됨 — 이미 반영됨."""
        must_fix_ids = [f["rule_id"] for f in self.must_fix]
        self.assertNotIn("DLR-RS-001", must_fix_ids,
                         "DLR-RS-001 is ALREADY REFLECTED — must NOT appear as 필수수정")

    def test_dlr_rs_002_not_in_must_fix(self):
        """DLR-RS-002(세금계산서)이 필수수정에 나오면 안 됨 — 이미 반영됨."""
        must_fix_ids = [f["rule_id"] for f in self.must_fix]
        self.assertNotIn("DLR-RS-002", must_fix_ids,
                         "DLR-RS-002 is ALREADY REFLECTED — must NOT appear as 필수수정")

    def test_dlr_rs_009_not_in_must_fix(self):
        """DLR-RS-009(공정거래)이 필수수정에 나오면 안 됨 — 이미 반영됨."""
        must_fix_ids = [f["rule_id"] for f in self.must_fix]
        self.assertNotIn("DLR-RS-009", must_fix_ids)

    # ── 이미반영 items ────────────────────────────────────────────────────

    def test_already_reflected_contains_dlr_rs_001(self):
        """DLR-RS-001이 이미반영 목록에 있어야 함."""
        ids = [f["rule_id"] for f in self.already_reflected]
        self.assertIn("DLR-RS-001", ids)

    def test_already_reflected_contains_dlr_rs_002(self):
        """DLR-RS-002가 이미반영 목록에 있어야 함."""
        ids = [f["rule_id"] for f in self.already_reflected]
        self.assertIn("DLR-RS-002", ids)

    # ── 블로킹 (failure conditions) ────────────────────────────────────────

    def test_no_isr_findings(self):
        """isr_로 시작하는 finding이 없어야 함."""
        blocked = [f for f in self.clause_results
                   if str(f.get("rule_id", "")).startswith("isr_")
                   or str(f.get("clause_id", "")).startswith("isr_")]
        self.assertEqual(len(blocked), 0, f"isr_ findings must not appear: {[f['rule_id'] for f in blocked]}")

    def test_no_pi_findings(self):
        """pi_로 시작하는 finding이 없어야 함."""
        blocked = [f for f in self.clause_results
                   if str(f.get("rule_id", "")).startswith("pi_")
                   or str(f.get("clause_id", "")).startswith("pi_")]
        self.assertEqual(len(blocked), 0)

    def test_no_false_customer_party_issue(self):
        """'고객 계약 당사자 명시 필요' 제목의 finding이 없어야 함 — 이미 반영됨."""
        bad = [f for f in self.clause_results
               if "고객 계약 당사자 명시 필요" in str(f.get("issue_title", ""))
               or "고객 계약 당사자 명시 필요" in str(f.get("clause_title", ""))]
        self.assertEqual(len(bad), 0, "'고객 계약 당사자 명시 필요' must not appear — role matrix confirmed")

    def test_no_false_tax_invoice_issue(self):
        """'세금계산서 발행 주체 미확인' finding이 없어야 함 — 이미 반영됨."""
        bad = [f for f in self.clause_results
               if "세금계산서 발행 주체 미확인" in str(f.get("issue_title", ""))]
        self.assertEqual(len(bad), 0)

    def test_dlr_rs_006_has_professional_opinion(self):
        """DLR-RS-006 finding에 '자동수정 보류'가 아닌 전문 검토의견이 있어야 함."""
        f006 = self._find_by_id("DLR-RS-006")
        self.assertIsNotNone(f006, "DLR-RS-006 must be in clause_results")
        rewrite = str(f006.get("suggested_rewrite", "") or "")
        assessment = str(f006.get("current_assessment_text", "") or "")
        self.assertNotEqual(rewrite, "자동수정 보류", "DLR-RS-006 must have professional opinion, not 자동수정 보류")
        self.assertGreater(len(assessment), 30, "DLR-RS-006 must have non-empty professional assessment text")


if __name__ == "__main__":
    unittest.main()
