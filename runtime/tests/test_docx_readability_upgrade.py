from __future__ import annotations

import unittest
import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET

from runtime.review.docx_writer import W_NS, build_revision_docx


class DocxReadabilityUpgradeTest(unittest.TestCase):
    def test_redline_only_changed_clause_is_rendered_and_not_all_text_is_red(self) -> None:
        original_clauses = [
            {"clause_id": "KR-1", "clause_title": "목적", "text": "제1조 목적은 테스트이다."},
            {"clause_id": "KR-2", "clause_title": "책임", "text": "을은 갑에게 무제한 책임을 부담한다."},
        ]
        clause_results = [
            {"clause_id": "KR-1", "clause_title": "목적", "suggested_rewrite": "", "rewrite_reason": None, "high_risk": False, "approval_required": False},
            {
                "clause_id": "KR-2",
                "clause_title": "책임",
                "suggested_rewrite": "을은 갑에게 책임(상한 적용)을 부담한다.",
                "rewrite_reason": "무제한 책임 문구를 책임 상한으로 조정.",
                "high_risk": True,
                "approval_required": True,
                "related_laws": {"results": {"laws": [{"title": "민법"}]}},
            },
        ]
        b = build_revision_docx(
            entity="테스트",
            contract_type="장비공급/설치/시운전",
            filename="LG_장비공급설치_계약서.docx",
            original_clauses=original_clauses,
            clause_results=clause_results,
        )
        with zipfile.ZipFile(BytesIO(b), "r") as z:
            xml_bytes = z.read("word/document.xml")
        root = ET.fromstring(xml_bytes)
        ns = {"w": W_NS}

        red_run_count = 0
        for r in root.findall(".//w:r", ns):
            pr = r.find("w:rPr", ns)
            if pr is None:
                continue
            c = pr.find("w:color", ns)
            if c is not None:
                red_run_count += 1
        self.assertGreaterEqual(red_run_count, 1)

        any_non_red_text = False
        for t in root.findall(".//w:t", ns):
            s = (t.text or "").strip()
            if s and "<w:" not in s and "w:rPr" not in s:
                any_non_red_text = True
                break
        self.assertTrue(any_non_red_text)

    def test_clause_title_mismatch_fails(self) -> None:
        original_clauses = [{"clause_id": "KR-1", "clause_title": "목적", "text": "제1조 목적은 테스트이다."}]
        clause_results = [{"clause_id": "KR-1", "clause_title": "다른제목", "suggested_rewrite": "x"}]
        with self.assertRaises(ValueError):
            _ = build_revision_docx(
                entity="테스트",
                contract_type="장비공급/설치/시운전",
                filename="x.docx",
                original_clauses=original_clauses,
                clause_results=clause_results,
            )


if __name__ == "__main__":
    unittest.main()

