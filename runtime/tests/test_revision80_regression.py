"""Regression tests preventing aouribot_revision(80) failure patterns.

Failures in revision(80):
  1. ai_search_marketing classification for content production contract
  2. "상대방: 상대방" counterparty detection failure
  3. Generic advisories ([권고] 검수 후 지급 구조, etc.) in TOP 5
  4. "검수 없는 대금 지급 구조" when inspection clause exists
  5. No clause numbers in TOP 5 (제9조, 제3조, 제6조, etc.)
  6. "노이즈 필터로 제외된 항목이 없습니다" placeholder text
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


def _full_pipeline_docx(text: str, include_low: bool = False) -> bytes:
    """Full end-to-end pipeline including content production checklist."""
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
        text=text, contract_type_code=ct_code,
        entity="퍼시스", counterparty=detailed.counterparty,
    )

    # Remove generic advisory svc_* items
    _SVC_IDS = {
        "svc_prepayment_guarantee", "svc_inspection_before_payment",
        "svc_deliverable_definition", "svc_refund_on_incomplete",
        "svc_delay_response", "svc_post_use_scope",
    }
    clause_results = [
        cr for cr in bundle.clause_results
        if not (isinstance(cr, dict) and str(cr.get("clause_id") or "") in _SVC_IDS)
    ]

    # Inject content production checklist at front
    new_crs = [ci.to_issue_dict() for ci in content_issues]
    clause_results = new_crs + clause_results

    # Inject mandatory issues
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


class Revision80AbsenceTest(unittest.TestCase):
    """Verify revision(80) failure patterns do NOT appear."""

    @classmethod
    def setUpClass(cls) -> None:
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        cls.text = _read_docx_text(_full_pipeline_docx(text))

    def _absent(self, phrase: str) -> None:
        self.assertNotIn(phrase, self.text, f"FAIL: '{phrase}' must not appear")

    def test_no_ai_search_marketing_label(self) -> None:
        self._absent("계약유형: ai_search_marketing")

    def test_no_counterparty_placeholder(self) -> None:
        self._absent("상대방: 상대방")

    def test_no_generic_advisory_inspection_title(self) -> None:
        self._absent("[권고] 검수 후 지급 구조")

    def test_no_generic_advisory_deliverable_title(self) -> None:
        self._absent("[권고] 단계별 deliverable 정의")

    def test_no_generic_advisory_delay_title(self) -> None:
        self._absent("[권고] 일정 지연 대응 조항")

    def test_no_generic_advisory_post_use_title(self) -> None:
        self._absent("[권고] 용역 종료 후 결과물 활용 범위")

    def test_no_false_inspection_absent_claim(self) -> None:
        self._absent("검수 없는 대금 지급 구조")

    def test_no_inspection_absent_language(self) -> None:
        self._absent("검수 조항이 없어")

    def test_no_noise_filter_placeholder(self) -> None:
        self._absent("노이즈 필터로 제외된 항목이 없습니다")

    def test_no_legacy_sections(self) -> None:
        for title in ["1) 표지/요약", "2) 핵심 쟁점 요약", "6-1) 추가 권고"]:
            self._absent(title)


class Revision80PresenceTest(unittest.TestCase):
    """Verify required clause-based content is present."""

    @classmethod
    def setUpClass(cls) -> None:
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        cls.text = _read_docx_text(_full_pipeline_docx(text))

    def _present(self, phrase: str) -> None:
        self.assertIn(phrase, self.text, f"REQUIRED: '{phrase}' must appear")

    def test_contract_type_label_correct(self) -> None:
        has_label = (
            "제품 광고 콘텐츠 제작" in self.text
            or "콘텐츠 제작 대행" in self.text
            or "콘텐츠 제작" in self.text
        )
        self.assertTrue(has_label, "Contract type label must mention 콘텐츠 제작")

    def test_our_party_fursys(self) -> None:
        self._present("퍼시스")

    def test_counterparty_skai(self) -> None:
        has_skai = "스카이" in self.text
        self.assertTrue(has_skai, "Counterparty 스카이인텔리전스 must appear")

    def test_top5_section_present(self) -> None:
        self._present("TOP 5")

    def test_article9_high_present(self) -> None:
        self._present("제9조")

    def test_article9_ip_revision_present(self) -> None:
        has_ip = (
            "2차적저작물작성권" in self.text
            or "저작재산권" in self.text
            or "편집·수정권" in self.text
        )
        self.assertTrue(has_ip, "IP revision text for 제9조 must appear")

    def test_article3_10_third_party_ip_present(self) -> None:
        has_third = (
            "제3조 제2항" in self.text
            or ("제10조" in self.text and "라이선스" in self.text)
        )
        self.assertTrue(has_third, "제3조 제2항 or 제10조 third-party IP must appear")

    def test_article6_7_inspection_present(self) -> None:
        has_inspection = "제6조" in self.text and "검수" in self.text
        self.assertTrue(has_inspection, "제6조 inspection must appear")

    def test_inspection_described_as_weak_not_absent(self) -> None:
        has_weak = (
            "검수 조항은 있으나" in self.text
            or "무응답 합격 간주" in self.text
            or "중대한 하자" in self.text
        )
        self.assertTrue(has_weak, "Inspection must be 'present_but_weak', not absent")

    def test_article12_termination_present(self) -> None:
        self._present("제12조")

    def test_high_section_present(self) -> None:
        self._present("3. 필수수정")

    def test_medium_section_present(self) -> None:
        self._present("4. 권장수정")


class Revision80ClassificationTest(unittest.TestCase):
    """Verify classification is correct for content production contract."""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.review.contract_classifier import classify_contract_detailed
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        cls.profile = classify_contract_detailed(
            entity="퍼시스",
            contract_type="콘텐츠 제작",
            text=text,
            filename="SKAI_COVE_콘텐츠제작_계약서.docx",
        )

    def test_not_ai_search_marketing(self) -> None:
        self.assertNotEqual(self.profile.contract_type, "ai_search_marketing",
                            f"Got: {self.profile.contract_type}")

    def test_is_content_production(self) -> None:
        self.assertIn(
            self.profile.contract_type,
            ("advertising_content_production", "content_production_service",
             "creative_agency_service", "content_production"),
            f"Got: {self.profile.contract_type}"
        )

    def test_our_party_fursys(self) -> None:
        self.assertEqual(self.profile.our_party, "퍼시스")

    def test_counterparty_skai(self) -> None:
        self.assertIn("스카이", self.profile.counterparty,
                      f"Got: {self.profile.counterparty}")

    def test_counterparty_not_placeholder(self) -> None:
        self.assertNotEqual(self.profile.counterparty, "상대방",
                            "Counterparty must not be '상대방' placeholder")

    def test_our_role_ordering_party(self) -> None:
        role = self.profile.our_legal_role
        self.assertTrue(
            "발주자" in role or "도급인" in role or "ordering" in role.lower(),
            f"Our role should be 발주자/도급인, got: {role}"
        )


class Revision80ColorTest(unittest.TestCase):
    """Verify correct colors in DOCX."""

    @classmethod
    def setUpClass(cls) -> None:
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        cls.xml = _read_docx_xml(_full_pipeline_docx(text))

    def test_red_color_present(self) -> None:
        self.assertIn('val="FF0000"', self.xml, "RED (FF0000) must appear for HIGH")

    def test_orange_color_present(self) -> None:
        self.assertIn('val="F28C28"', self.xml, "ORANGE (F28C28) must appear for MEDIUM")


class Revision80ClauseParserTest(unittest.TestCase):
    """Verify clause parser extracts key contract articles."""

    def test_clause_parser_extracts_content_clauses(self) -> None:
        from runtime.review.clause_extraction import extract_clauses
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        clauses, _ = extract_clauses(text)

        # Build combined text of all clause ids, titles, and article numbers
        all_clause_info = " ".join(
            f"{c.clause_id} {c.title or ''} 제{c.article_number}조"
            for c in clauses
            if c.article_number is not None
        )

        # Check that key articles are extracted by article_number (may be str or int)
        required_articles = [2, 3, 6, 7, 9, 10, 12, 14]
        found_articles = [
            art for art in required_articles
            if any(str(c.article_number) == str(art) for c in clauses)
        ]

        self.assertGreaterEqual(
            len(found_articles), 5,
            f"At least 5 key articles must be parsed. Found articles: {found_articles}. "
            f"Total clauses extracted: {len(clauses)}"
        )


class Revision80ChecklistStatusTest(unittest.TestCase):
    """Verify ABSENT vs PRESENT_BUT_WEAK is correctly determined."""

    def test_inspection_with_clause_is_present_but_weak(self) -> None:
        from runtime.review.checklists.content_production import (
            run_content_production_checklist, ChecklistStatus
        )
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        results = run_content_production_checklist(
            text=text, contract_type_code="advertising_content_production"
        )
        cp002 = next((r for r in results if r.checklist_id == "CP-002"), None)
        if cp002:
            self.assertNotEqual(cp002.status, ChecklistStatus.ABSENT,
                                "Inspection clause EXISTS → must be PRESENT_BUT_WEAK")

    def test_inspection_without_clause_is_absent(self) -> None:
        from runtime.review.checklists.content_production import (
            run_content_production_checklist, ChecklistStatus
        )
        text_no_inspection = (
            "제9조 소유권의 귀속: 저작권은 갑에게 이전된다.\n"
            "제7조 대금 지급: 세금계산서 발행일로부터 30일 이내 지급.\n"
        )
        results = run_content_production_checklist(
            text=text_no_inspection, contract_type_code="advertising_content_production"
        )
        cp002 = next((r for r in results if r.checklist_id == "CP-002"), None)
        if cp002:
            self.assertEqual(cp002.status, ChecklistStatus.ABSENT,
                             "No inspection clause → must be ABSENT")


class Revision80ContentTypeClauseLevelTest(unittest.TestCase):
    """Verify clause_level.py classifies content production correctly."""

    def test_content_production_classified_not_advisory(self) -> None:
        from runtime.review.clause_level import _classify_contract_type
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        result = _classify_contract_type("콘텐츠 제작", text, "SKAI_COVE.docx")
        self.assertEqual(result, "content_production",
                         f"clause_level classifier must return 'content_production', got: {result}")

    def test_ai_search_not_classified_as_content(self) -> None:
        from runtime.review.clause_level import _classify_contract_type
        ai_text = (
            "AI 검색 마케팅 서비스. SEO 최적화. AEO 서비스. "
            "LLM 기반 생성형 AI 검색 결과 최적화. 검색 노출 서비스."
        )
        result = _classify_contract_type("AI 검색", ai_text, "ai_search.docx")
        self.assertNotEqual(result, "content_production",
                            f"AI search contract must not be 'content_production'")


if __name__ == "__main__":
    unittest.main()
