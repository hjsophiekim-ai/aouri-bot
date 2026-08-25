"""Complete regression tests for aouribot_revision(76) failure patterns.

Verifies the new legal-team pipeline in server.py correctly:
1. Uses new legal_review_docx writer (not legacy docx_writer)
2. Injects mandatory issues (MI-001..006) for consignment dealer contracts
3. Applies severity reclassification
4. Blocks hallucination (dev phrases in dealer contract)
5. Blocks service/dev contract advisory items
6. Outputs proper colors (RED/ORANGE/BLUE)
7. No legacy section titles
8. No placeholder text
"""
from __future__ import annotations

import re
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fursys_consignment_dealer.txt"


def _read_docx_text(docx_bytes: bytes) -> str:
    z = zipfile.ZipFile(BytesIO(docx_bytes))
    xml = z.read("word/document.xml").decode("utf-8")
    texts = re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml)
    return " ".join(texts)


def _read_docx_xml(docx_bytes: bytes) -> str:
    z = zipfile.ZipFile(BytesIO(docx_bytes))
    return z.read("word/document.xml").decode("utf-8")


def _full_pipeline_docx(text: str, include_low: bool = False) -> bytes:
    """Run the complete new pipeline and return DOCX bytes."""
    from runtime.rules.loader import RuleLoader
    from runtime.services.query_service import RuleQueryService
    from runtime.review.clause_level import build_clause_level_result
    from runtime.review.contract_classifier import classify_contract_detailed
    from runtime.review.mandatory_issues import inject_mandatory_issues
    from runtime.review.severity_reclassifier import reclassify_for_consignment_dealer
    from runtime.review.hallucination_guard import check_revision_text
    from runtime.review.legal_review_docx import build_legal_review_docx

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

    results = list(bundle.clause_results)

    # inject mandatory
    results = inject_mandatory_issues(
        full_text=text, clause_results=results,
        contract_type_code=ct_code, is_counterparty_form=True,
    )

    # severity reclassification
    _DEALER = {"consignment_sales_agency", "direct_customer_sales_support", "dealer_agency"}
    if ct_code in _DEALER:
        for cr in results:
            if not isinstance(cr, dict) or cr.get("is_mandatory"):
                continue
            cur = str(cr.get("risk_tier") or "LOW").upper()
            new, _ = reclassify_for_consignment_dealer(severity=cur, clause_text=str(cr.get("original_text") or ""))
            if new != cur:
                cr["risk_tier"] = new
                cr["severity"] = new

    # hallucination guard
    for cr in results:
        if not isinstance(cr, dict) or cr.get("is_mandatory"):
            continue
        sr = str(cr.get("suggested_rewrite") or "").strip()
        if sr:
            g = check_revision_text(sr, contract_type_code=ct_code)
            if not g.is_clean:
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
        clause_results=results,
        original_clauses=original_clauses,
        detailed_contract_profile=detailed.to_dict(),
        include_low=include_low,
        contract_type_code=ct_code,
        is_counterparty_form=True,
    )


class Revision76AbsenceTest(unittest.TestCase):
    """Test: All revision76 failure patterns must NOT appear."""

    @classmethod
    def setUpClass(cls) -> None:
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        cls.text_content = _read_docx_text(_full_pipeline_docx(text, include_low=False))
        cls.xml_content = _read_docx_xml(_full_pipeline_docx(text, include_low=False))

    def _assert_absent(self, phrase: str) -> None:
        self.assertNotIn(phrase, self.text_content, f"FAIL: '{phrase}' must not appear in DOCX")

    def test_no_low_spam(self) -> None:
        self._assert_absent("참고제안(LOW): 7")
        self._assert_absent("참고제안(LOW): 5")

    def test_no_undetermined_party(self) -> None:
        self._assert_absent("미확정 (갑)")
        self._assert_absent("미확정(갑)")

    def test_no_redline_missing_message(self) -> None:
        self._assert_absent("필수수정(redline) 조항이 없습니다")

    def test_no_negotiation_placeholder(self) -> None:
        self._assert_absent("협상 전략 없음")
        self._assert_absent("(협상 전략 없음)")

    def test_no_proposal_placeholder(self) -> None:
        for m in ["(제안 문안 없음)", "(사유 없음)", "원문 핵심: -", "통합 관리 필요"]:
            self._assert_absent(m)

    def test_no_consolidation_message(self) -> None:
        self._assert_absent("대표 항의 수정안을 기준으로 통합 관리하십시오")

    def test_no_dev_phrases(self) -> None:
        for p in ["수탁자", "위탁자", "결과물", "산출물", "오픈소스",
                  "무료 이미지", "라이선스 조건", "소스코드", "제3자 권리 침해 보증"]:
            self._assert_absent(p)

    def test_no_svc_dev_advisories(self) -> None:
        for p in ["선급금 보증", "미완성 시 환수", "일정 지연 대응", "용역 종료 후 결과물"]:
            self._assert_absent(p)

    def test_no_legacy_section_titles(self) -> None:
        for title in ["1) 표지/요약", "2) 핵심 쟁점 요약", "3) 검토된 주요 조항",
                      "4) 수정 권고 조항", "5) 본문 redline 버전", "6) 조항별 검토 의견",
                      "6-1) 추가 권고", "7) 조항별 구체적 수정안 부록"]:
            self._assert_absent(title)

    def test_no_low_in_body(self) -> None:
        # [LOW] should not appear (only in legend "파란색, 기본 숨김")
        low_markers = re.findall(r"\[LOW\]", self.text_content)
        self.assertLess(len(low_markers), 3,
                        f"Too many [LOW] markers ({len(low_markers)}) in default output")


class Revision76PresenceTest(unittest.TestCase):
    """Test: Required content must appear in output."""

    @classmethod
    def setUpClass(cls) -> None:
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        cls.text_content = _read_docx_text(_full_pipeline_docx(text, include_low=False))

    def _assert_present(self, phrase: str) -> None:
        self.assertIn(phrase, self.text_content, f"REQUIRED: '{phrase}' must appear in DOCX")

    def test_contract_type_label(self) -> None:
        self._assert_present("위탁판매 대리점 계약")

    def test_our_company(self) -> None:
        self._assert_present("우리 회사")
        self._assert_present("퍼시스")

    def test_our_role_supplier(self) -> None:
        self._assert_present("공급업자")

    def test_top5_section(self) -> None:
        self._assert_present("TOP 5")

    def test_mi001_present(self) -> None:
        self._assert_present("제5조 제1항")
        self._assert_present("거래구조 불일치")

    def test_mi001_revision_text(self) -> None:
        self._assert_present("공급업자는 고객과 직접 상품공급계약을 체결하고")

    def test_mi002_present(self) -> None:
        self._assert_present("세금계산서")

    def test_mi003_present(self) -> None:
        self._assert_present("고객계약서 작성")

    def test_mi003_revision_text(self) -> None:
        self._assert_present("대리점은 고객으로부터 상품대금을 직접 수령하여서는 아니 되며")

    def test_mi004_present(self) -> None:
        self._assert_present("제6조 제13항")

    def test_mi004_revision_text(self) -> None:
        self._assert_present("자신의 귀책 범위 내에서")

    def test_mi005_present(self) -> None:
        self._assert_present("상계")

    def test_mi005_revision_text(self) -> None:
        self.assertTrue(
            "증빙자료" in self.text_content or "이의를 제기한" in self.text_content,
            "MI-005 revision text (증빙자료 or 이의를 제기한) must appear"
        )

    def test_medium_section_present(self) -> None:
        self._assert_present("MEDIUM")

    def test_high_section_present(self) -> None:
        self._assert_present("HIGH")


class Revision76ColorTest(unittest.TestCase):
    """Test: Colors must be applied correctly."""

    @classmethod
    def setUpClass(cls) -> None:
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        cls.xml_no_low = _read_docx_xml(_full_pipeline_docx(text, include_low=False))
        cls.xml_with_low = _read_docx_xml(_full_pipeline_docx(text, include_low=True))

    def test_red_for_high(self) -> None:
        self.assertIn('val="FF0000"', self.xml_no_low, "RED (FF0000) must appear for HIGH")

    def test_orange_for_medium(self) -> None:
        self.assertIn('val="F28C28"', self.xml_no_low, "ORANGE (F28C28) must appear for MEDIUM")

    def test_blue_for_low_when_included(self) -> None:
        self.assertIn('val="0070C0"', self.xml_with_low, "BLUE (0070C0) must appear when include_low=True")

    def test_no_legacy_medium_blue(self) -> None:
        # Legacy writer used "1F7AE0" for MEDIUM — new writer must use F28C28
        self.assertNotIn('val="1F7AE0"', self.xml_no_low,
                         "Legacy blue (1F7AE0) for MEDIUM must not appear")


class Revision76LowExclusionTest(unittest.TestCase):
    """Test: LOW excluded by default, included when requested."""

    @classmethod
    def setUpClass(cls) -> None:
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        cls.text_no_low = _read_docx_text(_full_pipeline_docx(text, include_low=False))
        cls.text_with_low = _read_docx_text(_full_pipeline_docx(text, include_low=True))

    def test_low_section_not_in_default(self) -> None:
        # Count [LOW] items — only legend should mention LOW
        low_items = re.findall(r"\[LOW\]\s+\S", self.text_no_low)
        self.assertLess(len(low_items), 3, f"Too many [LOW] issue markers: {low_items}")

    def test_low_section_in_appendix(self) -> None:
        # include_low=True should have LOW section header
        self.assertIn("참고 조항", self.text_with_low, "LOW appendix section should appear")

    def test_no_placeholder_even_with_low(self) -> None:
        for m in ["(제안 문안 없음)", "(사유 없음)", "원문 핵심: -"]:
            self.assertNotIn(m, self.text_with_low, f"Placeholder '{m}' must not appear even with low")


class MandatoryIssueInjectionTest(unittest.TestCase):
    """Test: Mandatory issues are injected and survive the full pipeline."""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService
        from runtime.review.clause_level import build_clause_level_result
        from runtime.review.contract_classifier import classify_contract_detailed
        from runtime.review.mandatory_issues import inject_mandatory_issues
        from runtime.review.severity_reclassifier import reclassify_for_consignment_dealer
        from runtime.review.hallucination_guard import check_revision_text

        text = FIXTURE_PATH.read_text(encoding="utf-8")
        loader = RuleLoader()
        loader.load()
        service = RuleQueryService(loader)

        bundle = build_clause_level_result(
            service=service, entity="퍼시스", contract_type="대리점/위탁/유통",
            text=text, filename="test.docx", answers=None, law_service=None,
            ai_provider=None, ai_model=None, ai_timeout_sec=None, ai_max_tokens=None, ai_temperature=None,
        )

        detailed = classify_contract_detailed(entity="퍼시스", contract_type="대리점/위탁/유통", text=text)
        results = list(bundle.clause_results)
        results = inject_mandatory_issues(
            full_text=text, clause_results=results,
            contract_type_code=detailed.contract_type, is_counterparty_form=True,
        )

        for cr in results:
            if not isinstance(cr, dict) or cr.get("is_mandatory"):
                continue
            cur = str(cr.get("risk_tier") or "LOW").upper()
            new, _ = reclassify_for_consignment_dealer(severity=cur, clause_text=str(cr.get("original_text") or ""))
            if new != cur:
                cr["risk_tier"] = new

        for cr in results:
            if not isinstance(cr, dict) or cr.get("is_mandatory"):
                continue
            sr = str(cr.get("suggested_rewrite") or "").strip()
            if sr:
                g = check_revision_text(sr, contract_type_code=detailed.contract_type)
                if not g.is_clean:
                    cr["suggested_rewrite"] = None

        cls.results = results

    def test_mi001_injected(self) -> None:
        mi1 = [cr for cr in self.results if cr.get("mandatory_issue_id") == "MI-001"]
        self.assertGreater(len(mi1), 0, "MI-001 (거래구조 불일치) must be injected")
        self.assertEqual(mi1[0]["severity"], "HIGH")
        self.assertIn("공급업자는 고객과 직접", mi1[0]["suggested_rewrite"])

    def test_mi002_injected(self) -> None:
        mi2 = [cr for cr in self.results if cr.get("mandatory_issue_id") == "MI-002"]
        self.assertGreater(len(mi2), 0, "MI-002 (세금계산서) must be injected")
        self.assertEqual(mi2[0]["severity"], "HIGH")

    def test_mi003_injected(self) -> None:
        mi3 = [cr for cr in self.results if cr.get("mandatory_issue_id") == "MI-003"]
        self.assertGreater(len(mi3), 0, "MI-003 (수금 주체) must be injected")
        self.assertEqual(mi3[0]["severity"], "HIGH")
        self.assertIn("대리점은 고객으로부터 상품대금을 직접 수령하여서는 아니 되며",
                      mi3[0]["suggested_rewrite"])

    def test_mi004_injected(self) -> None:
        mi4 = [cr for cr in self.results if cr.get("mandatory_issue_id") == "MI-004"]
        self.assertGreater(len(mi4), 0, "MI-004 (모든 책임) must be injected")
        self.assertEqual(mi4[0]["severity"], "HIGH")
        self.assertIn("자신의 귀책 범위 내에서", mi4[0]["suggested_rewrite"])

    def test_mi005_injected(self) -> None:
        mi5 = [cr for cr in self.results if cr.get("mandatory_issue_id") == "MI-005"]
        self.assertGreater(len(mi5), 0, "MI-005 (상계) must be injected")
        sev = mi5[0]["severity"]
        self.assertIn(sev, ("MEDIUM", "HIGH"))
        self.assertIn("사전에 대리점에게", mi5[0]["suggested_rewrite"])

    def test_mandatory_issues_not_contain_dev_phrases(self) -> None:
        from runtime.review.hallucination_guard import check_revision_text
        for cr in self.results:
            if not isinstance(cr, dict) or not cr.get("is_mandatory"):
                continue
            sr = str(cr.get("suggested_rewrite") or "")
            if not sr:
                continue
            g = check_revision_text(sr, contract_type_code="consignment_sales_agency")
            self.assertTrue(g.is_clean,
                f"Mandatory issue {cr.get('mandatory_issue_id')} has forbidden phrases: {g.violations}")

    def test_no_svc_dev_items_in_mandatory(self) -> None:
        _SVC_TITLES = {"선급금 보증 구조", "미완성 시 환수 조항", "일정 지연 대응 조항",
                       "용역 종료 후 결과물 활용 범위"}
        for cr in self.results:
            if not isinstance(cr, dict) or not cr.get("is_mandatory"):
                continue
            title = str(cr.get("clause_title") or "")
            self.assertNotIn(title, _SVC_TITLES,
                f"Service/dev advisory '{title}' must not appear as mandatory issue")


class LegacyWriterBlockedTest(unittest.TestCase):
    """Test: Legacy writer section titles must NOT appear in legal-team output."""

    @classmethod
    def setUpClass(cls) -> None:
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        cls.text = _read_docx_text(_full_pipeline_docx(text, include_low=False))

    def test_no_legacy_section_1_summary(self) -> None:
        self.assertNotIn("1) 표지/요약", self.text)

    def test_no_legacy_section_2_issues(self) -> None:
        self.assertNotIn("2) 핵심 쟁점 요약", self.text)

    def test_no_legacy_section_3_clauses(self) -> None:
        self.assertNotIn("3) 검토된 주요 조항", self.text)

    def test_no_legacy_section_4_recommend(self) -> None:
        self.assertNotIn("4) 수정 권고 조항", self.text)

    def test_no_legacy_section_5_redline(self) -> None:
        self.assertNotIn("5) 본문 redline 버전", self.text)

    def test_no_legacy_section_6_guidance(self) -> None:
        self.assertNotIn("6) 조항별 검토 의견", self.text)

    def test_no_legacy_section_6_1_advisory(self) -> None:
        self.assertNotIn("6-1) 추가 권고", self.text)

    def test_no_legacy_section_7_appendix(self) -> None:
        self.assertNotIn("7) 조항별 구체적 수정안 부록", self.text)

    def test_new_section_1_present(self) -> None:
        self.assertIn("1. 계약 구조 및 우리 측 포지션", self.text)

    def test_new_section_2_present(self) -> None:
        self.assertIn("2. TOP 5 핵심 리스크", self.text)

    def test_new_section_3_present(self) -> None:
        self.assertIn("3. 필수수정 조항", self.text)

    def test_new_section_4_present(self) -> None:
        self.assertIn("4. 권장수정 조항", self.text)


if __name__ == "__main__":
    unittest.main()
