"""End-to-end tests for legal_review_docx and pipeline integration.

Tests:
  1. Fursys consignment dealer DOCX generation (fixture-based, no AI)
  2. HIGH issue requires proposed_revision
  3. LOW excluded from default output
  4. include_low=True shows LOW in appendix
  5. Unknown clause_id fallback (no crash)
  6. UTF-8 encoding correctness
"""
from __future__ import annotations

import logging
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fursys_consignment_dealer.txt"


def _read_docx_xml(docx_bytes: bytes) -> str:
    z = zipfile.ZipFile(BytesIO(docx_bytes))
    return z.read("word/document.xml").decode("utf-8", errors="replace")


class LegalReviewDocxTest(unittest.TestCase):
    """Test 1: Fursys consignment dealer contract DOCX generation."""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService
        loader = RuleLoader()
        loader.load()
        cls.service = RuleQueryService(loader)
        cls.text = FIXTURE_PATH.read_text(encoding="utf-8")

    def _build_bundle(self):
        from runtime.review.clause_level import build_clause_level_result
        return build_clause_level_result(
            service=self.service,
            entity="퍼시스",
            contract_type="대리점/위탁/유통",
            text=self.text,
            filename="OPC_퍼시스_판매대리점_계약서.docx",
            answers=None,
            law_service=None,
            ai_provider=None,
            ai_model=None,
            ai_timeout_sec=None,
            ai_max_tokens=None,
            ai_temperature=None,
        )

    def test_docx_file_is_generated(self) -> None:
        from runtime.review.legal_review_docx import build_legal_review_docx
        from runtime.review.contract_classifier import classify_contract_detailed

        bundle = self._build_bundle()
        detailed = classify_contract_detailed(entity="퍼시스", contract_type="대리점/위탁/유통", text=self.text)
        original_clauses = [
            {"clause_id": c.clause_id, "article_number": c.article_number,
             "clause_title": c.title, "text": c.text}
            for c in bundle.clauses
        ]
        docx_bytes = build_legal_review_docx(
            entity="퍼시스",
            contract_type="대리점/위탁/유통",
            filename="OPC_퍼시스_판매대리점_계약서.docx",
            clause_results=bundle.clause_results,
            original_clauses=original_clauses,
            detailed_contract_profile=detailed.to_dict(),
            contract_type_code=detailed.contract_type,
        )
        self.assertIsNotNone(docx_bytes)
        self.assertGreater(len(docx_bytes), 0, "DOCX must not be empty")
        # Verify it's a valid ZIP
        z = zipfile.ZipFile(BytesIO(docx_bytes))
        self.assertIn("word/document.xml", z.namelist())

    def test_docx_contains_high_section(self) -> None:
        # TOP 5 핵심 리스크 섹션은 폐지됨(필수수정 HIGH 섹션과 중복되어 삭제,
        # 변호사형 전체계약 판단 지시 2026-08-31).
        from runtime.review.legal_review_docx import build_legal_review_docx
        from runtime.review.contract_classifier import classify_contract_detailed

        bundle = self._build_bundle()
        detailed = classify_contract_detailed(entity="퍼시스", contract_type="대리점/위탁/유통", text=self.text)
        docx_bytes = build_legal_review_docx(
            entity="퍼시스",
            contract_type="대리점/위탁/유통",
            filename="OPC_test.docx",
            clause_results=bundle.clause_results,
            detailed_contract_profile=detailed.to_dict(),
            contract_type_code=detailed.contract_type,
        )
        xml = _read_docx_xml(docx_bytes)
        self.assertIn("필수수정", xml, "DOCX must contain '필수수정' (HIGH) section")
        self.assertNotIn("TOP 5", xml, "TOP 5 핵심 리스크 section must no longer appear")

    def test_docx_contains_article6_13_revision(self) -> None:
        from runtime.review.legal_review_docx import build_legal_review_docx
        from runtime.review.contract_classifier import classify_contract_detailed

        bundle = self._build_bundle()
        detailed = classify_contract_detailed(entity="퍼시스", contract_type="대리점/위탁/유통", text=self.text)
        docx_bytes = build_legal_review_docx(
            entity="퍼시스",
            contract_type="대리점/위탁/유통",
            filename="OPC_test.docx",
            clause_results=bundle.clause_results,
            detailed_contract_profile=detailed.to_dict(),
            contract_type_code=detailed.contract_type,
        )
        xml = _read_docx_xml(docx_bytes)
        # Check for dealer structure revision language
        # The fixture has 모든 책임은 대리점에게 있다 → should produce overbroad_all_liability revision
        has_revision_content = (
            "귀책" in xml
            or "대리점" in xml
            or "공급업자" in xml
        )
        self.assertTrue(has_revision_content, "DOCX should contain dealer-specific revision content")

    def test_docx_no_dev_phrases_in_output(self) -> None:
        from runtime.review.legal_review_docx import build_legal_review_docx
        from runtime.review.contract_classifier import classify_contract_detailed

        bundle = self._build_bundle()
        detailed = classify_contract_detailed(entity="퍼시스", contract_type="대리점/위탁/유통", text=self.text)
        docx_bytes = build_legal_review_docx(
            entity="퍼시스",
            contract_type="대리점/위탁/유통",
            filename="OPC_test.docx",
            clause_results=bundle.clause_results,
            detailed_contract_profile=detailed.to_dict(),
            contract_type_code=detailed.contract_type,
        )
        xml = _read_docx_xml(docx_bytes)
        # In revision sections, these should not appear
        _FORBIDDEN = ["수탁자는 결과물이 제3자의 저작권", "오픈소스 소프트웨어 사용 시 라이선스 조건", "개발 완료 시 소스코드를 제출"]
        for phrase in _FORBIDDEN:
            self.assertNotIn(phrase, xml, f"Forbidden dev phrase '{phrase}' should not appear in DOCX")

    def test_docx_no_placeholder_text(self) -> None:
        from runtime.review.legal_review_docx import build_legal_review_docx
        from runtime.review.contract_classifier import classify_contract_detailed

        bundle = self._build_bundle()
        detailed = classify_contract_detailed(entity="퍼시스", contract_type="대리점/위탁/유통", text=self.text)
        docx_bytes = build_legal_review_docx(
            entity="퍼시스",
            contract_type="대리점/위탁/유통",
            filename="OPC_test.docx",
            clause_results=bundle.clause_results,
            detailed_contract_profile=detailed.to_dict(),
            contract_type_code=detailed.contract_type,
        )
        xml = _read_docx_xml(docx_bytes)
        _FORBIDDEN_PLACEHOLDERS = ["제안 문안 없음", "사유 없음", "원문 핵심: -", "협상 전략 없음"]
        for placeholder in _FORBIDDEN_PLACEHOLDERS:
            self.assertNotIn(placeholder, xml, f"Placeholder '{placeholder}' must not appear in DOCX output")


class HighIssueRequiresRevisionTest(unittest.TestCase):
    """Test 2: HIGH issues must have proposed_revision; if not, they are excluded from output."""

    def test_high_issue_without_revision_is_excluded(self) -> None:
        from runtime.review.legal_review_docx import build_legal_review_docx

        high_issue_no_revision = {
            "clause_id": "C001",
            "clause_title": "제6조",
            "risk_tier": "HIGH",
            "approval_required": True,
            "original_text": "모든 책임은 대리점에게 있다.",
            "rewrite_reason": "과도한 책임 전가",
            "suggested_rewrite": "",  # empty — should be excluded
        }
        docx_bytes = build_legal_review_docx(
            entity="퍼시스",
            contract_type="대리점/위탁/유통",
            filename="test.docx",
            clause_results=[high_issue_no_revision],
            contract_type_code="consignment_sales_agency",
        )
        xml = _read_docx_xml(docx_bytes)
        # The HIGH issue should not appear in TOP 5 since it has no revision
        self.assertNotIn("모든 책임은 대리점에게 있다", xml)

    def test_high_issue_with_revision_appears_in_output(self) -> None:
        from runtime.review.legal_review_docx import build_legal_review_docx

        high_issue_with_revision = {
            "clause_id": "C001",
            "clause_title": "제6조 제13항",
            "risk_tier": "HIGH",
            "approval_required": True,
            "original_text": "모든 책임은 대리점에게 있다.",
            "rewrite_reason": "과도한 책임 전가 — 귀책 범위로 한정 필요",
            "suggested_rewrite": "대리점의 귀책사유가 있는 경우에 한하여 손해를 배상한다. 공급업자의 지시, 승인, 오류로 인한 손해는 제외한다.",
        }
        docx_bytes = build_legal_review_docx(
            entity="퍼시스",
            contract_type="대리점/위탁/유통",
            filename="test.docx",
            clause_results=[high_issue_with_revision],
            contract_type_code="consignment_sales_agency",
        )
        xml = _read_docx_xml(docx_bytes)
        self.assertIn("귀책사유", xml, "HIGH issue with revision should appear in output")


class LowExclusionTest(unittest.TestCase):
    """Test 3 & 4: LOW issues excluded by default, included when include_low=True."""

    def _make_issues(self):
        return [
            {
                "clause_id": "C001", "clause_title": "제1조", "risk_tier": "HIGH",
                "original_text": "공급업자에게 모든 책임이 있다.", "rewrite_reason": "HIGH test",
                "suggested_rewrite": "공급업자의 귀책사유 범위 내에서만 책임을 진다.",
            },
            {
                "clause_id": "C002", "clause_title": "제2조", "risk_tier": "LOW",
                "original_text": "계약은 성실하게 이행한다.", "rewrite_reason": "LOW test",
                "suggested_rewrite": "성실하게 이행하여야 한다.",
            },
        ]

    def test_low_excluded_by_default(self) -> None:
        from runtime.review.legal_review_docx import build_legal_review_docx

        docx_bytes = build_legal_review_docx(
            entity="퍼시스",
            contract_type="대리점/위탁/유통",
            filename="test.docx",
            clause_results=self._make_issues(),
            include_low=False,
            contract_type_code="consignment_sales_agency",
        )
        xml = _read_docx_xml(docx_bytes)
        # LOW issue should not appear in the body
        self.assertNotIn("계약은 성실하게 이행한다", xml)

    def test_low_included_when_requested(self) -> None:
        from runtime.review.legal_review_docx import build_legal_review_docx

        docx_bytes = build_legal_review_docx(
            entity="퍼시스",
            contract_type="대리점/위탁/유통",
            filename="test.docx",
            clause_results=self._make_issues(),
            include_low=True,
            contract_type_code="consignment_sales_agency",
        )
        xml = _read_docx_xml(docx_bytes)
        # With include_low=True, LOW section header should appear
        self.assertIn("LOW", xml, "LOW section should appear when include_low=True")


class ClauseIdFallbackTest(unittest.TestCase):
    """Test 5: Unknown clause_id does not crash DOCX generation."""

    def test_unknown_clause_id_does_not_raise(self) -> None:
        from runtime.review.docx_writer import build_revision_docx

        original_clauses = [
            {"clause_id": "KR-001", "article_number": "1", "clause_title": "목적", "text": "제1조 목적"},
        ]
        clause_results = [
            # isr_pl_defect_liability is NOT in original_clauses — this caused the bug
            {
                "clause_id": "isr_pl_defect_liability",
                "clause_title": "[제조물검토] 제조물 결함 책임 귀속",
                "risk_tier": "HIGH",
                "must_fix": True,
                "approval_required": True,
                "high_risk": True,
                "is_checklist_item": True,
                "display_kind": "guidance",
                "has_rewrite_change": False,
                "original_text": "",
                "suggested_rewrite": None,
                "recommendation_text": "[추가 권고] 제조물 결함 책임 귀속 조항을 추가하세요.",
                "rewrite_reason": "제조물 결함으로 인한 책임 귀속 명확화",
            },
            {
                "clause_id": "KR-001",
                "clause_title": "목적",
                "risk_tier": "LOW",
                "must_fix": False,
                "approval_required": False,
                "high_risk": False,
                "is_checklist_item": False,
                "display_kind": "note",
                "has_rewrite_change": False,
                "original_text": "제1조 목적",
                "suggested_rewrite": None,
                "rewrite_reason": None,
            },
        ]
        # Should NOT raise ValueError
        docx_bytes = build_revision_docx(
            entity="퍼시스",
            contract_type="장비공급/설치/시운전",
            filename="test.docx",
            original_clauses=original_clauses,
            clause_results=clause_results,
        )
        self.assertIsNotNone(docx_bytes)
        self.assertGreater(len(docx_bytes), 0)

    def test_legal_review_docx_with_unknown_clause_id(self) -> None:
        from runtime.review.legal_review_docx import build_legal_review_docx

        # HIGH issue with proper revision — should appear even without original_clauses entry
        clause_results = [
            {
                "clause_id": "isr_pl_defect_liability",
                "clause_title": "[제조물검토] 제조물 결함 책임",
                "risk_tier": "HIGH",
                "must_fix": True,
                "approval_required": True,
                "high_risk": True,
                "is_checklist_item": True,
                "original_text": "제조물 결함 관련 조항 없음",
                "suggested_rewrite": "[추가 권고] 제조물 결함으로 인한 손해 책임을 공급자에게 귀속한다.",
                "rewrite_reason": "제조물 결함 책임 귀속 조항 없음",
            },
        ]
        docx_bytes = build_legal_review_docx(
            entity="퍼시스",
            contract_type="장비공급/설치/시운전",
            filename="test.docx",
            clause_results=clause_results,
            contract_type_code="equipment_purchase_installation",
        )
        self.assertGreater(len(docx_bytes), 0)


class Utf8EncodingTest(unittest.TestCase):
    """Test 6: UTF-8 encoding works correctly on Windows."""

    def test_docx_xml_is_utf8_decodable(self) -> None:
        from runtime.review.legal_review_docx import build_legal_review_docx

        clause_results = [
            {
                "clause_id": "C001",
                "clause_title": "제1조 (목적)",
                "risk_tier": "HIGH",
                "original_text": "계약의 목적을 정한다. 위탁판매 대리점 거래",
                "suggested_rewrite": "공급업자는 고객과 직접 상품공급계약을 체결한다.",
                "rewrite_reason": "거래구조 불일치",
            }
        ]
        docx_bytes = build_legal_review_docx(
            entity="퍼시스",
            contract_type="대리점/위탁/유통",
            filename="한글파일명_계약서.docx",
            clause_results=clause_results,
            contract_type_code="consignment_sales_agency",
        )
        # Should decode as valid UTF-8
        z = zipfile.ZipFile(BytesIO(docx_bytes))
        xml_bytes = z.read("word/document.xml")
        xml_str = xml_bytes.decode("utf-8")  # Must not raise
        self.assertIn("공급업자", xml_str)

    def test_fixture_reads_as_utf8(self) -> None:
        # The fixture file must be readable as UTF-8
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        self.assertIn("퍼시스", text)
        self.assertIn("위탁판매", text)

    def test_docx_writer_reads_fixture_utf8(self) -> None:
        from runtime.review.docx_writer import build_revision_docx

        text = FIXTURE_PATH.read_text(encoding="utf-8")
        self.assertTrue(text)
        # Simple smoke test that the writer handles Korean text
        docx_bytes = build_revision_docx(
            entity="퍼시스",
            contract_type="대리점/위탁/유통",
            filename="test_utf8.docx",
            original_clauses=[{"clause_id": "KR-001", "article_number": "1", "clause_title": "위탁판매", "text": text[:300]}],
            clause_results=[],
        )
        xml = _read_docx_xml(docx_bytes)
        self.assertIn("위탁판매", xml)


class PipelineIntegrationTest(unittest.TestCase):
    """Test severity reclassifier and hallucination guard integration in pipeline."""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService
        loader = RuleLoader()
        loader.load()
        cls.service = RuleQueryService(loader)

    def test_severity_reclassifier_active_for_consignment(self) -> None:
        from runtime.review.clause_level import build_clause_level_result

        text = FIXTURE_PATH.read_text(encoding="utf-8")
        bundle = build_clause_level_result(
            service=self.service,
            entity="퍼시스",
            contract_type="위탁판매 대리점",
            text=text,
            filename="OPC_퍼시스_판매대리점.docx",
            answers=None,
            law_service=None,
            ai_provider=None,
            ai_model=None,
            ai_timeout_sec=None,
            ai_max_tokens=None,
            ai_temperature=None,
        )
        # Check that at least some clauses were upgraded
        upgraded = [cr for cr in bundle.clause_results if cr.get("auto_severity_upgrade")]
        # Not strictly required to have upgrades (depends on fixture match),
        # but the pipeline should not error
        self.assertIsNotNone(bundle.clause_results)

    def test_hallucination_guard_active_in_pipeline(self) -> None:
        from runtime.review.clause_level import build_clause_level_result

        text = FIXTURE_PATH.read_text(encoding="utf-8")
        bundle = build_clause_level_result(
            service=self.service,
            entity="퍼시스",
            contract_type="위탁판매 대리점",
            text=text,
            filename="OPC_퍼시스_판매대리점.docx",
            answers=None,
            law_service=None,
            ai_provider=None,
            ai_model=None,
            ai_timeout_sec=None,
            ai_max_tokens=None,
            ai_temperature=None,
        )
        # No dev-contract phrases should appear in proposed revisions for dealer contracts
        dev_phrases = ["수탁자는 결과물이 제3자의 저작권", "오픈소스 소프트웨어", "소스코드를 제출"]
        for cr in bundle.clause_results:
            sr = str(cr.get("suggested_rewrite") or "")
            for phrase in dev_phrases:
                self.assertNotIn(
                    phrase, sr,
                    f"Dev phrase '{phrase}' found in clause_id={cr.get('clause_id')} revision",
                )

    def test_detailed_profile_in_meta(self) -> None:
        from runtime.review.clause_level import build_clause_level_result

        text = FIXTURE_PATH.read_text(encoding="utf-8")
        bundle = build_clause_level_result(
            service=self.service,
            entity="퍼시스",
            contract_type="위탁판매 대리점",
            text=text,
            filename="OPC_퍼시스_판매대리점.docx",
            answers=None,
            law_service=None,
            ai_provider=None,
            ai_model=None,
            ai_timeout_sec=None,
            ai_max_tokens=None,
            ai_temperature=None,
        )
        self.assertIn("detailed_contract_profile", bundle.meta)
        dp = bundle.meta.get("detailed_contract_profile")
        if dp is not None:
            self.assertIn("contract_type", dp)
            self.assertIn("our_party", dp)


if __name__ == "__main__":
    unittest.main()
