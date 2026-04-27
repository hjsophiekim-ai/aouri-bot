from __future__ import annotations

import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

from runtime.law.search_service import _derive_queries
from runtime.review.clause_extraction import extract_clauses
from runtime.review.clause_level import build_clause_level_result
from runtime.review.docx_writer import build_revision_docx
from runtime.rules.loader import RuleLoader
from runtime.services.query_service import RuleQueryService


class BuyerFavorableRegressionV2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        loader = RuleLoader()
        loader.load()
        cls.service = RuleQueryService(loader)

    def test_clause_id_duplicates_are_disambiguated(self) -> None:
        text = "제1조(목적)\nA\n\n제1조(정의)\nB\n"
        clauses, rep = extract_clauses(text)
        self.assertTrue(clauses)
        ids = [c.clause_id for c in clauses]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(any(".D" in x for x in ids))

    def test_purchase_installation_queries_prioritize_civil_and_safety_laws(self) -> None:
        text = Path("runtime/tests/fixtures/lg_purchase_installation.txt").read_text(encoding="utf-8")
        qobjs = _derive_queries(entity="퍼시스", contract_type="장비공급/설치/시운전", text=text, matched_rules=[], scope="contract")
        qs = [q.get("query") for q in qobjs if isinstance(q.get("query"), str)]
        self.assertTrue(any("민법" in q for q in qs))
        self.assertTrue(any("산업안전보건법" in q or "중대재해" in q for q in qs))
        self.assertFalse(any("대리점법" in q for q in qs))

    def test_redline_docx_marks_only_changed_tokens(self) -> None:
        text = Path("runtime/tests/fixtures/lg_purchase_installation.txt").read_text(encoding="utf-8")
        bundle = build_clause_level_result(
            service=self.service,
            entity="퍼시스",
            contract_type="장비공급/설치/시운전",
            text=text,
            filename="LG_장비공급설치_계약서.docx",
            answers=None,
            law_service=None,
            ai_provider=None,
            ai_model=None,
            ai_timeout_sec=None,
            ai_max_tokens=None,
            ai_temperature=None,
        )
        original_clauses = [
            {"clause_id": c.clause_id, "article_number": c.article_number, "clause_title": c.title, "text": c.text} for c in bundle.clauses
        ]
        b = build_revision_docx(
            entity="퍼시스",
            contract_type="장비공급/설치/시운전",
            filename="LG_장비공급설치_계약서.docx",
            original_clauses=original_clauses,
            clause_results=bundle.clause_results,
        )
        with zipfile.ZipFile(BytesIO(b), "r") as z:
            xml_bytes = z.read("word/document.xml")
        root = ET.fromstring(xml_bytes)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        red_runs = 0
        plain_runs = 0
        for r in root.findall(".//w:r", ns):
            pr = r.find("w:rPr", ns)
            has_color = pr is not None and pr.find("w:color", ns) is not None
            if has_color:
                red_runs += 1
            else:
                plain_runs += 1
        self.assertGreater(red_runs, 0)
        self.assertGreater(plain_runs, 0)


if __name__ == "__main__":
    unittest.main()

