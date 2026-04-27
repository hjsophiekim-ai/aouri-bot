from __future__ import annotations

import unittest
from pathlib import Path

from runtime.review.clause_level import build_clause_level_result
from runtime.review.docx_writer import build_revision_docx
from runtime.rules.loader import RuleLoader
from runtime.services.query_service import RuleQueryService


class BuyerFavorableRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        loader = RuleLoader()
        loader.load()
        cls.service = RuleQueryService(loader)

    def test_lg_equipment_purchase_installation_posture(self) -> None:
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
        self.assertEqual(bundle.meta.get("review_posture"), "buyer_favorable")
        pr = bundle.meta.get("party_role") if isinstance(bundle.meta, dict) else None
        self.assertTrue(isinstance(pr, dict))
        self.assertTrue(pr.get("our_role") in ("buyer", "ordering_party", "neutral", "unknown"))

    def test_favorable_safety_clause_not_unnecessarily_rewritten(self) -> None:
        text = Path("runtime/tests/fixtures/lg_purchase_installation.txt").read_text(encoding="utf-8")
        bundle = build_clause_level_result(
            service=self.service,
            entity="퍼시스",
            contract_type="장비공급/설치/시운전",
            text=text,
            filename=None,
            answers=None,
            law_service=None,
            ai_provider=None,
            ai_model=None,
            ai_timeout_sec=None,
            ai_max_tokens=None,
            ai_temperature=None,
        )
        safety_crs = [cr for cr in bundle.clause_results if "안전관리" in str(cr.get("clause_title") or "")]
        self.assertTrue(safety_crs)
        for cr in safety_crs:
            sr = cr.get("suggested_rewrite")
            self.assertFalse(isinstance(sr, str) and sr.strip())

    def test_one_sided_liability_or_disclaimer_is_rewritten_in_buyer_favorable_direction(self) -> None:
        text = Path("runtime/tests/fixtures/lg_purchase_installation.txt").read_text(encoding="utf-8")
        bundle = build_clause_level_result(
            service=self.service,
            entity="퍼시스",
            contract_type="장비공급/설치/시운전",
            text=text,
            filename=None,
            answers=None,
            law_service=None,
            ai_provider=None,
            ai_model=None,
            ai_timeout_sec=None,
            ai_max_tokens=None,
            ai_temperature=None,
        )
        crs = [cr for cr in bundle.clause_results if "손해배상" in str(cr.get("clause_title") or "") or "면책" in str(cr.get("clause_title") or "")]
        self.assertTrue(crs)
        any_strengthened = False
        for cr in crs:
            sr = cr.get("suggested_rewrite")
            if isinstance(sr, str) and sr.strip():
                if "책임" in sr and ("상한" in sr or "제한" in sr or "통지" in sr):
                    any_strengthened = True
        self.assertTrue(any_strengthened)

    def test_dealer_act_not_inferred_for_lg_purchase_installation(self) -> None:
        from runtime.law.search_service import _derive_queries

        text = Path("runtime/tests/fixtures/lg_purchase_installation.txt").read_text(encoding="utf-8")
        qobjs = _derive_queries(entity="퍼시스", contract_type="장비공급/설치/시운전", text=text, matched_rules=[], scope="contract")
        qs = [q.get("query") for q in qobjs if isinstance(q.get("query"), str)]
        self.assertFalse(any("대리점법" == t for t in qs))
        self.assertTrue(any("민법" in t for t in qs))

    def test_redline_docx_has_mixed_color_runs(self) -> None:
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
        original_clauses = [{"clause_id": c.clause_id, "article_number": c.article_number, "clause_title": c.title, "text": c.text} for c in bundle.clauses]
        b = build_revision_docx(
            entity="퍼시스",
            contract_type="장비공급/설치/시운전",
            filename="LG_장비공급설치_계약서.docx",
            original_clauses=original_clauses,
            clause_results=bundle.clause_results,
        )
        import zipfile
        from io import BytesIO
        from xml.etree import ElementTree as ET

        with zipfile.ZipFile(BytesIO(b), "r") as z:
            xml_bytes = z.read("word/document.xml")
        root = ET.fromstring(xml_bytes)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        red = 0
        non_red = 0
        for r in root.findall(".//w:r", ns):
            pr = r.find("w:rPr", ns)
            is_red = pr is not None and pr.find("w:color", ns) is not None
            t = r.find("w:t", ns)
            if t is None or not (t.text or "").strip():
                continue
            if is_red:
                red += 1
            else:
                non_red += 1
        self.assertGreater(red, 0)
        self.assertGreater(non_red, 0)

    def test_clause_title_mismatch_fails(self) -> None:
        original_clauses = [{"clause_id": "KR-1", "clause_title": "목적", "text": "제1조 목적"}]
        clause_results = [{"clause_id": "KR-1", "clause_title": "불일치", "suggested_rewrite": "x"}]
        with self.assertRaises(ValueError):
            _ = build_revision_docx(
                entity="퍼시스",
                contract_type="장비공급/설치/시운전",
                filename="x.docx",
                original_clauses=original_clauses,
                clause_results=clause_results,
            )


if __name__ == "__main__":
    unittest.main()

