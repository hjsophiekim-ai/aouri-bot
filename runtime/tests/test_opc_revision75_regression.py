"""Regression tests preventing aouribot_revision(75).docx failure patterns.

Failure patterns from revision75:
  1. "참고제안(LOW): 73" — LOW spam
  2. "우리 측 지위: 미확정 (갑)" — wrong party identification
  3. "필수수정(redline) 조항이 없습니다" — HIGH with no redline
  4. "(협상 전략 없음)" — placeholder negotiation
  5. "제안 문안 없음", "사유 없음", "원문 핵심: -" — placeholder text
  6. 제6조 제2항/6항/12항 → LOW (wrong severity)
  7. 제16조 → LOW (wrong severity)
  8. 제19조 → dev contract phrases
  9. Excessive repeated issues

Tests ensure these never appear in the output DOCX again.
"""
from __future__ import annotations

import unittest
import zipfile
from io import BytesIO
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fursys_consignment_dealer.txt"


def _read_docx_xml(docx_bytes: bytes) -> str:
    z = zipfile.ZipFile(BytesIO(docx_bytes))
    return z.read("word/document.xml").decode("utf-8", errors="replace")


def _build_docx(text: str, include_low: bool = False) -> bytes:
    from runtime.review.mandatory_issues import inject_mandatory_issues
    from runtime.review.legal_review_docx import build_legal_review_docx
    from runtime.review.contract_classifier import classify_contract_detailed
    from runtime.review.severity_reclassifier import reclassify_for_consignment_dealer
    from runtime.review.hallucination_guard import check_revision_text
    from runtime.rules.loader import RuleLoader
    from runtime.services.query_service import RuleQueryService
    from runtime.review.clause_level import build_clause_level_result

    loader = RuleLoader()
    loader.load()
    service = RuleQueryService(loader)

    bundle = build_clause_level_result(
        service=service,
        entity="퍼시스",
        contract_type="대리점/위탁/유통",
        text=text,
        filename="OPC_퍼시스_판매대리점_계약서.docx",
        answers=None,
        law_service=None,
        ai_provider=None,
        ai_model=None,
        ai_timeout_sec=None,
        ai_max_tokens=None,
        ai_temperature=None,
    )

    detailed = classify_contract_detailed(
        entity="퍼시스",
        contract_type="대리점/위탁/유통",
        text=text,
    )
    ct_code = detailed.contract_type

    clause_results = list(bundle.clause_results)

    # Inject mandatory issues
    clause_results = inject_mandatory_issues(
        full_text=text,
        clause_results=clause_results,
        contract_type_code=ct_code,
        is_counterparty_form=True,
    )

    # Severity reclassification
    for cr in clause_results:
        if not isinstance(cr, dict) or cr.get("is_mandatory"):
            continue
        if bool(cr.get("dedup_suppressed")) or bool(cr.get("keep_as_is")):
            continue
        cur_sev = str(cr.get("risk_tier") or "LOW").upper()
        new_sev, _ = reclassify_for_consignment_dealer(
            severity=cur_sev,
            clause_text=str(cr.get("original_text") or ""),
        )
        if new_sev != cur_sev:
            cr["risk_tier"] = new_sev
            cr["severity"] = new_sev

    # Hallucination guard
    for cr in clause_results:
        if not isinstance(cr, dict) or cr.get("is_mandatory"):
            continue
        sr = str(cr.get("suggested_rewrite") or "").strip()
        if sr:
            guard = check_revision_text(sr, contract_type_code=ct_code)
            if not guard.is_clean:
                cr["suggested_rewrite"] = None

    original_clauses = [
        {"clause_id": c.clause_id, "article_number": c.article_number,
         "clause_title": c.title, "text": c.text}
        for c in bundle.clauses
    ]

    return build_legal_review_docx(
        entity="퍼시스",
        contract_type="대리점/위탁/유통",
        filename="OPC_퍼시스_판매대리점_계약서.docx",
        clause_results=clause_results,
        original_clauses=original_clauses,
        detailed_contract_profile=detailed.to_dict(),
        include_low=include_low,
        contract_type_code=ct_code,
        is_counterparty_form=True,
    )


class Revision75AbsenceTest(unittest.TestCase):
    """Test 1: All revision75 failure patterns must NOT appear in output."""

    @classmethod
    def setUpClass(cls) -> None:
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        cls.xml = _read_docx_xml(_build_docx(text, include_low=False))

    def test_no_low_spam(self) -> None:
        # "참고제안(LOW): 73" or similar mass LOW output must not appear
        self.assertNotIn("참고제안(LOW): 7", self.xml,
                         "LOW spam (참고제안(LOW): 7X) must not appear")
        self.assertNotIn("LOW): 73", self.xml)
        self.assertNotIn("LOW): 50", self.xml)

    def test_no_undetermined_party(self) -> None:
        self.assertNotIn("미확정 (갑)", self.xml,
                         "'우리 측 지위: 미확정 (갑)' must not appear")
        self.assertNotIn("미확정(갑)", self.xml)

    def test_no_missing_redline_message(self) -> None:
        self.assertNotIn("필수수정(redline) 조항이 없습니다", self.xml,
                         "DOCX must not say HIGH조항 없음 when HIGH issues exist")

    def test_no_negotiation_placeholder(self) -> None:
        self.assertNotIn("협상 전략 없음", self.xml, "'협상 전략 없음' must not appear")
        self.assertNotIn("(협상 전략 없음)", self.xml)

    def test_no_proposal_placeholder(self) -> None:
        for marker in ["제안 문안 없음", "사유 없음", "원문 핵심: -", "통합 관리 필요"]:
            self.assertNotIn(marker, self.xml, f"Placeholder '{marker}' must not appear")

    def test_no_consolidation_message(self) -> None:
        self.assertNotIn("대표 항의 수정안을 기준으로 통합 관리하십시오", self.xml)

    def test_no_dev_contract_phrases(self) -> None:
        """Dev contract phrases must never appear in dealer contract output."""
        _FORBIDDEN = [
            "수탁자", "위탁자", "결과물", "산출물", "오픈소스",
            "무료 이미지", "라이선스 조건", "소스코드",
            "개발 완료", "제3자 저작권·특허권 침해 보증",
        ]
        for phrase in _FORBIDDEN:
            self.assertNotIn(phrase, self.xml,
                             f"Dev phrase '{phrase}' must not appear in dealer contract DOCX")


class Revision75PresenceTest(unittest.TestCase):
    """Test 2: Required content must appear in output."""

    @classmethod
    def setUpClass(cls) -> None:
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        cls.xml = _read_docx_xml(_build_docx(text, include_low=False))

    def test_contract_type_label_present(self) -> None:
        # Must contain the proper contract type description
        has_type = (
            "위탁판매 대리점 계약" in self.xml
            or "consignment_sales_agency" in self.xml
        )
        self.assertTrue(has_type, "Contract type label must appear")

    def test_our_party_fursys_present(self) -> None:
        self.assertIn("퍼시스", self.xml, "우리 회사: 퍼시스 must appear")

    def test_our_role_supplier_present(self) -> None:
        has_role = "공급업자" in self.xml
        self.assertTrue(has_role, "우리 측 지위: 공급업자 must appear")

    def test_top5_section_present(self) -> None:
        self.assertIn("TOP 5", self.xml, "TOP 5 핵심 리스크 section must appear")

    def test_article5_1_high_present(self) -> None:
        has_art5 = "제5조" in self.xml and "HIGH" in self.xml
        self.assertTrue(has_art5, "[HIGH] 제5조 must appear")

    def test_article5_1_revision_text_present(self) -> None:
        self.assertIn("공급업자는 고객과 직접 상품공급계약을 체결하고", self.xml,
                      "제5조 revision text must appear")

    def test_article6_13_high_present(self) -> None:
        # "모든 책임" clause must be flagged as HIGH
        has_613 = ("제6조" in self.xml or "모든 책임" in self.xml or "귀책 범위" in self.xml)
        self.assertTrue(has_613, "제6조 제13항 HIGH must appear")

    def test_article6_13_revision_text_present(self) -> None:
        self.assertIn("자신의 귀책 범위 내에서", self.xml,
                      "제6조 제13항 revision text must appear")

    def test_article16_setoff_present(self) -> None:
        has_art16 = ("제16조" in self.xml or "증빙자료" in self.xml or "이의를 제기한" in self.xml)
        self.assertTrue(has_art16, "제16조 상계 조항 must appear")

    def test_setoff_revision_text_present(self) -> None:
        has_setoff_revision = (
            "증빙자료" in self.xml or "이의를 제기한 금액" in self.xml
            or "사전에 대리점에게" in self.xml
        )
        self.assertTrue(has_setoff_revision, "제16조 setoff revision text must appear")

    def test_medium_section_present(self) -> None:
        self.assertIn("MEDIUM", self.xml, "MEDIUM section must appear")


class SeverityClassificationTest(unittest.TestCase):
    """Test 3: Specific clauses must NOT be classified as LOW."""

    @classmethod
    def setUpClass(cls) -> None:
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        from runtime.review.mandatory_issues import inject_mandatory_issues
        from runtime.review.severity_reclassifier import reclassify_for_consignment_dealer
        from runtime.review.hallucination_guard import check_revision_text
        from runtime.review.contract_classifier import classify_contract_detailed
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService
        from runtime.review.clause_level import build_clause_level_result

        loader = RuleLoader()
        loader.load()
        service = RuleQueryService(loader)

        bundle = build_clause_level_result(
            service=service,
            entity="퍼시스",
            contract_type="대리점/위탁/유통",
            text=text,
            filename="test.docx",
            answers=None,
            law_service=None,
            ai_provider=None,
            ai_model=None,
            ai_timeout_sec=None,
            ai_max_tokens=None,
            ai_temperature=None,
        )

        detailed = classify_contract_detailed(entity="퍼시스", contract_type="대리점/위탁/유통", text=text)
        ct_code = detailed.contract_type
        clause_results = list(bundle.clause_results)

        clause_results = inject_mandatory_issues(
            full_text=text, clause_results=clause_results,
            contract_type_code=ct_code, is_counterparty_form=True,
        )
        for cr in clause_results:
            if not isinstance(cr, dict) or cr.get("is_mandatory"):
                continue
            cur_sev = str(cr.get("risk_tier") or "LOW").upper()
            new_sev, _ = reclassify_for_consignment_dealer(
                severity=cur_sev, clause_text=str(cr.get("original_text") or ""),
            )
            if new_sev != cur_sev:
                cr["risk_tier"] = new_sev

        cls.clause_results = clause_results

    def _find_cr_by_hint(self, *hints: str) -> list[dict]:
        results = []
        for cr in self.clause_results:
            if not isinstance(cr, dict):
                continue
            combined = (str(cr.get("clause_title") or "") + " " + str(cr.get("original_text") or "")).lower()
            if any(h.lower() in combined for h in hints):
                results.append(cr)
        return results

    def test_article5_1_not_low(self) -> None:
        # 제5조 제1항 (거래구조) should be HIGH
        crs = self._find_cr_by_hint("최종소비자에게 판매", "위탁받은 상품을 최종소비자")
        if crs:
            for cr in crs:
                sev = str(cr.get("risk_tier") or "").upper()
                self.assertNotEqual(sev, "LOW",
                    f"제5조 제1항 (거래구조 불일치) must be HIGH or MEDIUM, got {sev}")

    def test_invoice_clause_not_low(self) -> None:
        # 세금계산서 조항 should be HIGH
        crs = self._find_cr_by_hint("세금계산서", "각종 법률이 규정")
        for cr in crs:
            sev = str(cr.get("risk_tier") or "").upper()
            self.assertNotEqual(sev, "LOW",
                f"세금계산서 조항 must be HIGH or MEDIUM, got {sev}")

    def test_setoff_clause_not_low(self) -> None:
        # 제16조 상계 should be MEDIUM or HIGH
        crs = self._find_cr_by_hint("용역수수료에서 차감", "거래보증금에서 상계", "정책지원금에서 상계")
        for cr in crs:
            sev = str(cr.get("risk_tier") or "").upper()
            self.assertNotEqual(sev, "LOW",
                f"제16조 상계 조항 must be MEDIUM or HIGH, got {sev}")

    def test_all_liability_clause_not_low(self) -> None:
        # "모든 책임" should be HIGH
        crs = self._find_cr_by_hint("모든 책임은 대리점")
        for cr in crs:
            sev = str(cr.get("risk_tier") or "").upper()
            self.assertEqual(sev, "HIGH",
                f"'모든 책임' clause must be HIGH, got {sev}")

    def test_mandatory_issues_injected(self) -> None:
        mandatory = [cr for cr in self.clause_results
                     if isinstance(cr, dict) and cr.get("is_mandatory")]
        self.assertGreater(len(mandatory), 0, "At least one mandatory issue must be injected")

    def test_article16_mandatory_injected(self) -> None:
        # MI-005 (상계) must be injected
        mi5 = [cr for cr in self.clause_results
               if isinstance(cr, dict) and cr.get("mandatory_issue_id") == "MI-005"]
        self.assertGreater(len(mi5), 0, "MI-005 (제16조 상계) mandatory issue must be injected")
        for cr in mi5:
            sev = str(cr.get("risk_tier") or cr.get("severity") or "LOW").upper()
            self.assertNotEqual(sev, "LOW",
                "MI-005 severity must be MEDIUM or HIGH")


class ColorAppliedTest(unittest.TestCase):
    """Test 4: Colors must be applied in DOCX XML."""

    @classmethod
    def setUpClass(cls) -> None:
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        cls.xml_no_low = _read_docx_xml(_build_docx(text, include_low=False))
        cls.xml_with_low = _read_docx_xml(_build_docx(text, include_low=True))

    def test_red_color_for_high(self) -> None:
        self.assertIn('val="FF0000"', self.xml_no_low,
                      "RED color (FF0000) must appear for HIGH issues")

    def test_orange_color_for_medium(self) -> None:
        self.assertIn('val="F28C28"', self.xml_no_low,
                      "ORANGE color (F28C28) must appear for MEDIUM issues")

    def test_blue_color_for_low(self) -> None:
        self.assertIn('val="0070C0"', self.xml_with_low,
                      "BLUE color (0070C0) must appear when include_low=True")

    def test_low_not_in_default_output(self) -> None:
        # When include_low=False, LOW section header should not appear prominently
        # The word "LOW" may appear in legend, but not as body issue items
        # Check that the fixture low count (10 clauses) doesn't produce 10 LOW entries
        low_count = self.xml_no_low.count("[LOW]")
        self.assertLess(low_count, 5, f"Too many [LOW] markers ({low_count}) in default output")


class MandatoryIssueTest(unittest.TestCase):
    """Test 5: Mandatory issues must be injected with correct content."""

    def test_mi001_structure_mismatch(self) -> None:
        from runtime.review.mandatory_issues import inject_mandatory_issues

        text = "대리점은 공급업자로부터 위탁받은 상품을 최종소비자에게 판매하고 판매 관련 업무를 수행한다."
        results = inject_mandatory_issues(
            full_text=text, clause_results=[], contract_type_code="consignment_sales_agency"
        )
        mi1 = [cr for cr in results if cr.get("mandatory_issue_id") == "MI-001"]
        self.assertGreater(len(mi1), 0, "MI-001 should be injected")
        self.assertEqual(mi1[0]["severity"], "HIGH")
        self.assertIn("공급업자는 고객과 직접", mi1[0]["suggested_rewrite"])

    def test_mi002_invoice_mismatch(self) -> None:
        from runtime.review.mandatory_issues import inject_mandatory_issues

        text = "대리점은 각종 법률이 규정하고 있는 의무를 수행하여야 하며, 세금계산서 발행 및 대금의 청구를 수행한다."
        results = inject_mandatory_issues(
            full_text=text, clause_results=[], contract_type_code="consignment_sales_agency"
        )
        mi2 = [cr for cr in results if cr.get("mandatory_issue_id") == "MI-002"]
        self.assertGreater(len(mi2), 0, "MI-002 should be injected")
        self.assertEqual(mi2[0]["severity"], "HIGH")
        self.assertIn("세금계산서", mi2[0]["suggested_rewrite"])

    def test_mi005_setoff(self) -> None:
        from runtime.review.mandatory_issues import inject_mandatory_issues

        text = "공급업자는 용역수수료에서 차감하거나 거래보증금에서 상계할 수 있다."
        results = inject_mandatory_issues(
            full_text=text, clause_results=[], contract_type_code="consignment_sales_agency"
        )
        mi5 = [cr for cr in results if cr.get("mandatory_issue_id") == "MI-005"]
        self.assertGreater(len(mi5), 0, "MI-005 should be injected")
        sev = mi5[0]["severity"]
        self.assertIn(sev, ("MEDIUM", "HIGH"), f"MI-005 must be MEDIUM or HIGH, got {sev}")
        self.assertIn("사전에 대리점에게", mi5[0]["suggested_rewrite"])

    def test_mi004_all_liability(self) -> None:
        from runtime.review.mandatory_issues import inject_mandatory_issues

        text = "모든 책임은 대리점에게 있다."
        results = inject_mandatory_issues(
            full_text=text, clause_results=[], contract_type_code="consignment_sales_agency"
        )
        mi4 = [cr for cr in results if cr.get("mandatory_issue_id") == "MI-004"]
        self.assertGreater(len(mi4), 0, "MI-004 should be injected")
        self.assertEqual(mi4[0]["severity"], "HIGH")
        self.assertIn("자신의 귀책 범위 내에서", mi4[0]["suggested_rewrite"])

    def test_mi006_no_dev_phrases_in_ip_revision(self) -> None:
        from runtime.review.mandatory_issues import MANDATORY_CONSIGNMENT_ISSUES
        from runtime.review.hallucination_guard import check_revision_text

        mi6 = next((m for m in MANDATORY_CONSIGNMENT_ISSUES if m.issue_id == "MI-006"), None)
        if mi6 is None:
            return
        result = check_revision_text(mi6.proposed_revision, contract_type_code="consignment_sales_agency")
        self.assertTrue(result.is_clean,
            f"MI-006 revision contains forbidden phrases: {result.violations}")

    def test_mi001_no_dev_phrases(self) -> None:
        from runtime.review.mandatory_issues import MANDATORY_CONSIGNMENT_ISSUES
        from runtime.review.hallucination_guard import check_revision_text

        mi1 = next((m for m in MANDATORY_CONSIGNMENT_ISSUES if m.issue_id == "MI-001"), None)
        if mi1 is None:
            return
        result = check_revision_text(mi1.proposed_revision, contract_type_code="consignment_sales_agency")
        self.assertTrue(result.is_clean,
            f"MI-001 revision contains forbidden phrases: {result.violations}")

    def test_no_negotiation_placeholder_in_mandatory(self) -> None:
        from runtime.review.mandatory_issues import inject_mandatory_issues

        text = "대리점은 공급업자로부터 위탁받은 상품을 최종소비자에게 판매한다."
        results = inject_mandatory_issues(
            full_text=text, clause_results=[], contract_type_code="consignment_sales_agency"
        )
        for cr in results:
            if not isinstance(cr, dict):
                continue
            neg = str(cr.get("negotiation_position") or "")
            self.assertNotIn("협상 전략 없음", neg,
                f"Mandatory issue {cr.get('mandatory_issue_id')} has placeholder negotiation")
            self.assertNotIn("(협상 전략 없음)", neg)


if __name__ == "__main__":
    unittest.main()
