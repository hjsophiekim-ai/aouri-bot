from __future__ import annotations

import unittest
import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET

from runtime.review.docx_writer import W_NS, build_revision_docx


class DocxOutputPipelineTest(unittest.TestCase):
    def test_generated_docx_has_no_word_xml_string_in_text_nodes(self) -> None:
        original_clauses = [
            {"clause_id": "KR-1", "clause_title": "목적", "text": "제1조 목적은 테스트이다."},
        ]
        clause_results = [
            {
                "clause_id": "KR-1",
                "suggested_rewrite": "제1조 목적은 테스트이다. (단, 책임 상한을 명시한다.)",
                "rewrite_reason": "무제한 책임으로 해석될 소지가 있어 책임 상한을 명시.",
            }
        ]
        b = build_revision_docx(
            entity="테스트",
            contract_type="테스트",
            filename="sample.docx",
            original_clauses=original_clauses,
            clause_results=clause_results,
        )
        with zipfile.ZipFile(BytesIO(b), "r") as z:
            xml_bytes = z.read("word/document.xml")
        root = ET.fromstring(xml_bytes)
        ns = {"w": W_NS}
        for t in root.findall(".//w:t", ns):
            s = t.text or ""
            self.assertNotIn("<w:", s)
            self.assertNotIn("w:rPr", s)
            self.assertNotIn("w:delText", s)

    def test_docx_writer_rejects_word_xml_markers_in_input_text(self) -> None:
        original_clauses = [
            {"clause_id": "KR-1", "clause_title": "목적", "text": "<w:rPr>bad</w:rPr>"},
        ]
        with self.assertRaises(ValueError):
            _ = build_revision_docx(
                entity="테스트",
                contract_type="테스트",
                filename="bad.docx",
                original_clauses=original_clauses,
                clause_results=[],
            )


if __name__ == "__main__":
    unittest.main()

