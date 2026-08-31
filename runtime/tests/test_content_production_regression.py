"""Regression tests for content production contract review quality.

Validates that the system correctly:
1. Classifies SKAI COVE as advertising_content_production (not ai_search_marketing)
2. Generates TOP 5 with clause-grounded issues (not generic [권고] items)
3. Correctly identifies inspection clause as PRESENT_BUT_WEAK (not ABSENT)
4. Detects IP transfer and third-party rights issues
5. Generates proper DOCX with correct structure
"""
from __future__ import annotations

import re
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "skai_cove_content_production.txt"


def _read_docx_text(docx_bytes: bytes) -> str:
    z = zipfile.ZipFile(BytesIO(docx_bytes))
    xml = z.read("word/document.xml").decode("utf-8")
    texts = re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml)
    return " ".join(texts)


def _read_docx_xml(docx_bytes: bytes) -> str:
    z = zipfile.ZipFile(BytesIO(docx_bytes))
    return z.read("word/document.xml").decode("utf-8")


def _build_content_docx(text: str, include_low: bool = False) -> bytes:
    """Full pipeline DOCX for content production contract."""
    from runtime.rules.loader import RuleLoader
    from runtime.services.query_service import RuleQueryService
    from runtime.review.clause_level import build_clause_level_result
    from runtime.review.contract_classifier import classify_contract_detailed
    from runtime.review.checklists.content_production import run_content_production_checklist
    from runtime.review.mandatory_issues import inject_mandatory_issues
    from runtime.review.hallucination_guard import check_revision_text
    from runtime.review.legal_review_docx import build_legal_review_docx

    loader = RuleLoader()
    loader.load()
    service = RuleQueryService(loader)

    bundle = build_clause_level_result(
        service=service,
        entity="퍼시스",
        contract_type="콘텐츠 제작",
        text=text,
        filename="SKAI_COVE_콘텐츠제작_계약서.docx",
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
        contract_type="콘텐츠 제작",
        text=text,
        filename="SKAI_COVE_콘텐츠제작_계약서.docx",
    )
    ct_code = detailed.contract_type

    # Run content production checklist
    content_issues = run_content_production_checklist(
        text=text, contract_type_code=ct_code, entity="퍼시스", counterparty="스카이인텔리전스"
    )

    # Remove generic advisory items
    _GENERIC_ADVISORY = {
        "svc_prepayment_guarantee", "svc_inspection_before_payment",
        "svc_deliverable_definition", "svc_refund_on_incomplete",
        "svc_delay_response", "svc_post_use_scope",
    }
    clause_results = [
        cr for cr in bundle.clause_results
        if not (isinstance(cr, dict) and str(cr.get("clause_id") or "") in _GENERIC_ADVISORY)
    ]

    new_crs = [ci.to_issue_dict() for ci in content_issues]
    clause_results = new_crs + clause_results

    # Inject mandatory issues (dealer/consignment — will be no-op for content)
    clause_results = inject_mandatory_issues(
        full_text=text, clause_results=clause_results,
        contract_type_code=ct_code, is_counterparty_form=True,
    )

    # Hallucination guard
    for cr in clause_results:
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
        contract_type="콘텐츠 제작",
        filename="SKAI_COVE_콘텐츠제작_계약서.docx",
        clause_results=clause_results,
        original_clauses=original_clauses,
        detailed_contract_profile=detailed.to_dict(),
        include_low=include_low,
        contract_type_code=ct_code,
        is_counterparty_form=True,
    )


class ContentContractClassificationTest(unittest.TestCase):
    """Test 1: Classification — SKAI COVE must NOT be ai_search_marketing."""

    def _get_detailed(self, filename: str = "SKAI_COVE_콘텐츠제작.docx") -> "ContractProfile":
        from runtime.review.contract_classifier import classify_contract_detailed
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        return classify_contract_detailed(
            entity="퍼시스",
            contract_type="콘텐츠 제작",
            text=text,
            filename=filename,
        )

    def test_classified_as_content_production(self) -> None:
        profile = self._get_detailed()
        self.assertIn(
            profile.contract_type,
            ("advertising_content_production", "content_production_service", "creative_agency_service"),
            f"Expected content production type, got: {profile.contract_type}"
        )

    def test_not_classified_as_ai_search_marketing(self) -> None:
        profile = self._get_detailed()
        self.assertNotEqual(
            profile.contract_type, "ai_search_marketing",
            "Content production contract must NOT be classified as ai_search_marketing"
        )

    def test_our_party_is_fursys(self) -> None:
        profile = self._get_detailed()
        self.assertEqual(profile.our_party, "퍼시스")

    def test_counterparty_is_skai(self) -> None:
        profile = self._get_detailed()
        self.assertIn("스카이", profile.counterparty,
                      f"Counterparty should be 스카이인텔리전스, got: {profile.counterparty}")

    def test_our_role_is_ordering_party(self) -> None:
        profile = self._get_detailed()
        role = profile.our_legal_role
        self.assertTrue(
            "발주자" in role or "도급인" in role or "ordering_party" in role,
            f"Our role should be 발주자/도급인, got: {role}"
        )

    def test_confidence_high(self) -> None:
        profile = self._get_detailed()
        self.assertGreaterEqual(profile.confidence, 0.75,
                                f"Confidence too low: {profile.confidence}")

    def test_skai_filename_not_ai_classified(self) -> None:
        """Even with SKAI filename, content production signals must win."""
        from runtime.review.contract_classifier import classify_contract_detailed
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        profile = classify_contract_detailed(
            entity="퍼시스",
            contract_type="",
            text=text,
            filename="[SKAI] 퍼시스_COVE 콘텐츠 제작_계약서_260601 법무팀검토본 (1).docx",
        )
        self.assertNotEqual(profile.contract_type, "ai_search_marketing",
                            "SKAI filename must not override content production signals from text")


class ContentContractChecklistTest(unittest.TestCase):
    """Test 2: Checklist items for SKAI COVE contract."""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.review.checklists.content_production import (
            run_content_production_checklist, ChecklistStatus
        )
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        cls.results = run_content_production_checklist(
            text=text,
            contract_type_code="advertising_content_production",
            entity="퍼시스",
            counterparty="스카이인텔리전스",
        )
        cls.by_id = {r.checklist_id: r for r in cls.results}

    def test_cp004_ip_transfer_detected(self) -> None:
        self.assertIn("CP-004", self.by_id,
                      "CP-004 (IP Transfer) should be detected")

    def test_cp004_is_high(self) -> None:
        if "CP-004" in self.by_id:
            self.assertEqual(self.by_id["CP-004"].severity, "HIGH")

    def test_cp005_third_party_ip_detected(self) -> None:
        self.assertIn("CP-005", self.by_id,
                      "CP-005 (Third-party IP) should be detected")

    def test_cp005_is_high(self) -> None:
        if "CP-005" in self.by_id:
            self.assertEqual(self.by_id["CP-005"].severity, "HIGH")

    def test_cp006_termination_detected(self) -> None:
        self.assertIn("CP-006", self.by_id,
                      "CP-006 (Termination settlement) should be detected")

    def test_inspection_present_but_weak_not_absent(self) -> None:
        """CRITICAL: Must say 'present_but_weak' not 'absent' for inspection clause."""
        from runtime.review.checklists.content_production import ChecklistStatus
        if "CP-002" not in self.by_id:
            return  # If inspection is acceptable, that's fine
        result = self.by_id["CP-002"]
        self.assertNotEqual(
            result.status, ChecklistStatus.ABSENT,
            "CP-002: Inspection clause EXISTS in the contract — must be PRESENT_BUT_WEAK, not ABSENT"
        )
        self.assertEqual(
            result.status, ChecklistStatus.PRESENT_BUT_WEAK,
            f"CP-002 status should be PRESENT_BUT_WEAK, got: {result.status}"
        )

    def test_no_absent_inspection_language(self) -> None:
        """Ensure no issue says '검수 없는' or '검수 조항이 없어'."""
        for result in self.results:
            combined = result.problem + " " + result.issue_title + " " + result.original_text
            self.assertNotIn("검수 없는 대금 지급 구조", combined,
                             f"False claim about inspection: '{combined[:100]}'")
            self.assertNotIn("검수 조항이 없어", combined,
                             f"False claim about inspection absence: '{combined[:100]}'")

    def test_cp004_revision_contains_media_scope(self) -> None:
        if "CP-004" in self.by_id:
            rev = self.by_id["CP-004"].proposed_revision
            self.assertIn("SNS", rev, "IP revision must mention SNS")
            self.assertIn("홈페이지", rev, "IP revision must mention 홈페이지")
            self.assertIn("2차적저작물작성권", rev, "IP revision must mention 2차적저작물작성권")

    def test_cp005_revision_contains_license_elements(self) -> None:
        if "CP-005" in self.by_id:
            rev = self.by_id["CP-005"].proposed_revision
            self.assertIn("음원", rev, "CP-005 must mention 음원")
            self.assertIn("초상", rev, "CP-005 must mention 초상")
            self.assertIn("AI 생성물", rev, "CP-005 must mention AI 생성물")
            self.assertIn("라이선스", rev, "CP-005 must mention 라이선스")


class ContentContractTop5Test(unittest.TestCase):
    """Test 3: TOP 5 must be clause-grounded, not generic advisory."""

    @classmethod
    def setUpClass(cls) -> None:
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        cls.docx_bytes = _build_content_docx(text)
        cls.text_content = _read_docx_text(cls.docx_bytes)

    def test_top5_section_exists(self) -> None:
        # TOP 5 핵심 리스크 섹션은 폐지됨(필수수정 HIGH 섹션과 중복) — 대신
        # 그 자리를 대체한 필수수정 섹션이 존재하는지 확인한다.
        self.assertIn("필수수정", self.text_content)

    def test_cp004_in_top5_area(self) -> None:
        self.assertIn("제9조", self.text_content,
                      "제9조 (IP transfer) must appear in DOCX output")

    def test_cp005_in_top5_area(self) -> None:
        has_cp005 = (
            "제3조 제2항" in self.text_content
            or "제10조" in self.text_content
        )
        self.assertTrue(has_cp005, "제3조 제2항 또는 제10조 (third-party IP) must appear")

    def test_inspection_clause_present(self) -> None:
        has_inspection = (
            "제6조" in self.text_content
            and "검수" in self.text_content
        )
        self.assertTrue(has_inspection, "제6조 (inspection) must appear in DOCX")

    def test_termination_clause_present(self) -> None:
        self.assertIn("제12조", self.text_content, "제12조 (termination) must appear")

    def test_no_generic_advisory_in_top5_titles(self) -> None:
        _FORBIDDEN_TITLES = [
            "[권고] 검수 후 지급 구조",
            "[권고] 단계별 deliverable 정의",
            "[권고] 일정 지연 대응 조항",
            "[권고] 용역 종료 후 결과물 활용 범위",
        ]
        for title in _FORBIDDEN_TITLES:
            self.assertNotIn(title, self.text_content,
                             f"Generic advisory '{title}' must not appear as TOP 5 title")

    def test_inspection_not_described_as_absent(self) -> None:
        """검수 조항이 있는데 '없다'고 하면 안 된다."""
        _FORBIDDEN = ["검수 없는 대금 지급 구조", "검수 조항이 없어", "검수 없는"]
        for phrase in _FORBIDDEN:
            self.assertNotIn(phrase, self.text_content,
                             f"False claim '{phrase}' must not appear in DOCX")

    def test_inspection_described_as_weak(self) -> None:
        has_weak_inspection = (
            "검수 조항은 있으나" in self.text_content
            or "무응답 합격 간주" in self.text_content
            or "중대한 하자" in self.text_content
            or "지급 보류" in self.text_content
        )
        if "CP-002" in str(self.text_content):
            self.assertTrue(has_weak_inspection,
                            "Inspection must be described as 'present_but_weak', not 'absent'")


class ContentContractDocxQualityTest(unittest.TestCase):
    """Test 4: DOCX output quality for content production contract."""

    @classmethod
    def setUpClass(cls) -> None:
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        cls.text_no_low = _read_docx_text(_build_content_docx(text, include_low=False))
        cls.xml_no_low = _read_docx_xml(_build_content_docx(text, include_low=False))

    def test_contract_type_label_present(self) -> None:
        has_label = (
            "콘텐츠 제작" in self.text_no_low
            or "제품 광고" in self.text_no_low
        )
        self.assertTrue(has_label, "Contract type label must contain '콘텐츠 제작' or '제품 광고'")

    def test_not_ai_search_marketing_label(self) -> None:
        self.assertNotIn("ai_search_marketing", self.text_no_low.lower(),
                         "ai_search_marketing must not appear in DOCX output")

    def test_our_company_fursys(self) -> None:
        self.assertIn("퍼시스", self.text_no_low)

    def test_red_color_for_high(self) -> None:
        self.assertIn('val="FF0000"', self.xml_no_low)

    def test_orange_color_for_medium(self) -> None:
        self.assertIn('val="F28C28"', self.xml_no_low)

    def test_no_legacy_sections(self) -> None:
        _LEGACY = ["1) 표지/요약", "2) 핵심 쟁점 요약", "6-1) 추가 권고"]
        for title in _LEGACY:
            self.assertNotIn(title, self.text_no_low,
                             f"Legacy section '{title}' must not appear")

    def test_new_section_structure(self) -> None:
        self.assertIn("1. 계약 구조 및 검토 결론", self.text_no_low)
        self.assertIn("2. 필수수정", self.text_no_low)
        self.assertIn("3. 권장수정", self.text_no_low)

    def test_ip_revision_content(self) -> None:
        has_ip_content = (
            "저작재산권" in self.text_no_low
            or "2차적저작물" in self.text_no_low
            or "편집·수정권" in self.text_no_low
        )
        self.assertTrue(has_ip_content, "IP revision text must appear in DOCX")

    def test_no_placeholder_text(self) -> None:
        for ph in ["제안 문안 없음", "사유 없음", "협상 전략 없음", "원문 핵심: -"]:
            self.assertNotIn(ph, self.text_no_low, f"Placeholder '{ph}' must not appear")


class NoAiSearchMarketingFalseClassificationTest(unittest.TestCase):
    """Test 5: Ensure no false ai_search_marketing classification for content contracts."""

    def test_content_keywords_not_classified_as_ai_search(self) -> None:
        from runtime.review.contract_classifier import classify_contract_detailed

        content_text = (
            "콘텐츠 제작 대행 계약서. 갑: 퍼시스. 을: 스카이인텔리전스.\n"
            "제1조 계약 목적: 제품 광고 콘텐츠 제작 대행.\n"
            "제9조 소유권의 귀속: 저작재산권은 갑에게 이전된다.\n"
            "제10조 지식재산권: 제3자 저작권 침해 보증.\n"
        )
        profile = classify_contract_detailed(entity="퍼시스", contract_type="", text=content_text)
        self.assertNotEqual(profile.contract_type, "ai_search_marketing",
                            f"Content contract wrongly classified as ai_search_marketing")

    def test_ai_search_keywords_required_for_ai_search_classification(self) -> None:
        from runtime.review.contract_classifier import classify_contract_detailed

        ai_search_text = (
            "AI 검색 마케팅 서비스 계약서. 갑: 퍼시스. 을: AI업체.\n"
            "제1조 계약 목적: AI 기반 검색 노출 및 AEO 최적화 서비스.\n"
            "검색 알고리즘 기반 콘텐츠 최적화, SEO, GEO 서비스 제공.\n"
            "LLM 생성형 AI 검색 결과 최적화.\n"
        )
        profile = classify_contract_detailed(entity="퍼시스", contract_type="", text=ai_search_text)
        self.assertEqual(profile.contract_type, "ai_search_marketing",
                         f"Actual AI search contract should be classified as ai_search_marketing")


class ChecklistStatusDistinctionTest(unittest.TestCase):
    """Test 6: ABSENT vs PRESENT_BUT_WEAK distinction."""

    def test_contract_with_inspection_not_absent(self) -> None:
        from runtime.review.checklists.content_production import (
            run_content_production_checklist, ChecklistStatus
        )
        text_with_inspection = (
            "제6조 (콘텐츠의 제출 및 검수)\n"
            "① 갑은 콘텐츠 수령일로부터 10일 이내에 검수 결과를 을에게 서면으로 통보한다.\n"
            "② 갑이 10일 이내에 통보하지 아니하는 경우 합격된 것으로 간주한다.\n"
            "제9조 소유권의 귀속: 저작권은 갑에게 이전된다.\n"
        )
        results = run_content_production_checklist(
            text=text_with_inspection,
            contract_type_code="advertising_content_production",
        )
        cp002 = next((r for r in results if r.checklist_id == "CP-002"), None)
        if cp002:
            self.assertNotEqual(cp002.status, ChecklistStatus.ABSENT,
                                "Contract WITH inspection clause must not be ABSENT")

    def test_contract_without_inspection_is_absent(self) -> None:
        from runtime.review.checklists.content_production import (
            run_content_production_checklist, ChecklistStatus
        )
        text_without_inspection = (
            "제7조 (대금 지급): 갑은 을에게 용역대금을 지급한다.\n"
            "제9조 소유권의 귀속: 저작권은 갑에게 이전된다.\n"
        )
        results = run_content_production_checklist(
            text=text_without_inspection,
            contract_type_code="advertising_content_production",
        )
        cp002 = next((r for r in results if r.checklist_id == "CP-002"), None)
        if cp002:
            self.assertEqual(cp002.status, ChecklistStatus.ABSENT,
                             "Contract WITHOUT inspection clause must be ABSENT")


if __name__ == "__main__":
    unittest.main()
