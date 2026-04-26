from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from runtime.review.text_extract import extract_text_from_file


def _build_minimal_docx_bytes(*, document_xml: str) -> bytes:
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""
    with tempfile.TemporaryFile() as tmp:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", content_types)
            z.writestr("_rels/.rels", rels)
            z.writestr("word/document.xml", document_xml)
        tmp.seek(0)
        return tmp.read()


class DocxExtractionTest(unittest.TestCase):
    def test_extract_docx_final_policy_drops_deleted_text(self) -> None:
        doc_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>제1조 </w:t></w:r><w:r><w:t>목적</w:t></w:r></w:p>
    <w:p>
      <w:ins><w:r><w:t>삽입문</w:t></w:r></w:ins>
      <w:del><w:r><w:delText>삭제문</w:delText></w:r></w:del>
      <w:r><w:t>현재문</w:t></w:r>
    </w:p>
  </w:body>
</w:document>
"""
        b = _build_minimal_docx_bytes(document_xml=doc_xml)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "tracked.docx"
            p.write_bytes(b)
            res = extract_text_from_file(p)
        self.assertTrue(res.success, res.error)
        self.assertIn("삽입문", res.text)
        self.assertIn("현재문", res.text)
        self.assertNotIn("삭제문", res.text)
        self.assertNotIn("<w:", res.text)

    def test_extract_docx_rejects_word_xml_marker_in_visible_text(self) -> None:
        doc_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>&lt;w:rPr&gt;</w:t></w:r></w:p>
  </w:body>
</w:document>
"""
        b = _build_minimal_docx_bytes(document_xml=doc_xml)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad_visible_text.docx"
            p.write_bytes(b)
            res = extract_text_from_file(p)
        self.assertFalse(res.success)
        self.assertIsNotNone(res.error)

    def test_extract_docx_rejects_invalid_xml(self) -> None:
        doc_xml = "<w:document><w:body><w:p><w:t>broken</w:t></w:p></w:body>"
        b = _build_minimal_docx_bytes(document_xml=doc_xml)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "invalid.docx"
            p.write_bytes(b)
            res = extract_text_from_file(p)
        self.assertFalse(res.success)
        self.assertIsNotNone(res.error)


if __name__ == "__main__":
    unittest.main()

