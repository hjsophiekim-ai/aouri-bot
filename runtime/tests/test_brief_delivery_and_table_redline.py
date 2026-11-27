"""사업팀 전달본 정리 · 표 셀 레드라인 회귀 (2026-11-27 지시).

실측(원단 수입 계약, 국·영 좌우 병기 표): 변경추적본 삽입 8건·삭제 0건 — 표 셀 안의 문구 치환이 전부 실패했고, 새 항은
셀 밖에 들어갔으며, 전달본에는 "⚠ 미해결"·예외 메시지·"제안만 있음·파일 미반영" 같은 도구 상태가 그대로 나갔다.

1. 레드라인 엔진: 표 셀 안 단락 치환, 여러 run 에 걸친 문장 치환(같은 단락의 두 번째 수정), 기준 단락 바로 뒤(같은 셀) 삽입,
   본문 속 조 인용("제3조의 선적")을 조 머리로 세지 않음.
2. 전달본: 도구 상태 문구 없음, 도구 실패는 결론을 바꾸지 않고 전달 보류(법무 전용), 국문 변경 표시 한 블록만, 미확정 조건은
   항목 이름으로, 필수수정 + LOW 조합 없음, 같은 답 요청은 한 줄로.
3. 기타: 관점 판단은 사용자가 쓴 말만, cross_border finding 의 loss_path 는 표준 구조(dict).
"""
from __future__ import annotations

import io
import re
import unittest
import zipfile

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

_BODY = (
    '<w:p><w:r><w:t>원단 매매 계약서</w:t></w:r></w:p>'
    '<w:tbl>'
    '<w:tr><w:tc><w:p><w:r><w:t>제2조 (대금) / Article 2 (Payment)</w:t></w:r></w:p></w:tc></w:tr>'
    '<w:tr><w:tc><w:p><w:r><w:t>1. 잔금은 제3조의 선적 후 30일 이내에 지급한다.</w:t></w:r></w:p></w:tc>'
    '<w:tc><w:p><w:r><w:t>1. The balance is due 30 days after shipment under Article 3.</w:t></w:r></w:p></w:tc></w:tr>'
    '<w:tr><w:tc><w:p><w:r><w:t>제3조 (준거법) / Article 3 (Governing Law)</w:t></w:r></w:p></w:tc></w:tr>'
    '<w:tr><w:tc><w:p><w:r><w:t xml:space="preserve">1. 준거법은 대한민국 법(또는 중립국 법)으로 한다. 분쟁은 </w:t></w:r>'
    '<w:r><w:rPr><w:b/></w:rPr><w:t>SIAC 또는 KCAB</w:t></w:r>'
    '<w:r><w:t xml:space="preserve"> 중재로 해결한다.</w:t></w:r></w:p></w:tc>'
    '<w:tc><w:p><w:r><w:t>1. This Agreement is governed by Korean law.</w:t></w:r></w:p></w:tc></w:tr>'
    '</w:tbl>'
)
KO_PARA = "1. 준거법은 대한민국 법(또는 중립국 법)으로 한다. 분쟁은 SIAC 또는 KCAB 중재로 해결한다."


def _table_docx() -> bytes:
    from runtime.review.source_docx import build_docx_from_text

    base = build_docx_from_text("x\n")
    zin = zipfile.ZipFile(io.BytesIO(base))
    xml = zin.read("word/document.xml").decode("utf-8")
    xml = re.sub(r"(<w:body[^>]*>).*?(<w:sectPr|</w:body>)", lambda m: m.group(1) + _BODY + m.group(2), xml, count=1, flags=re.S)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n in zin.namelist():
            z.writestr(n, xml if n == "word/document.xml" else zin.read(n))
    return out.getvalue()


def _cr(cid: str, ri: dict, **kw) -> dict:
    base = {"clause_id": cid, "finding_id": cid, "display_path": "제3조 제1항", "article_number": "3", "risk_tier": "MEDIUM",
            "original_text": KO_PARA, "has_rewrite_change": ri.get("edit_type") == "replace",
            "has_addition": ri.get("edit_type") != "replace", "redline_instruction": ri}
    if ri.get("edit_type") == "replace":
        base["suggested_rewrite"] = KO_PARA.replace(ri["target_text"], ri["replacement_text"])
    else:
        base["addition_text"] = ri["replacement_text"]
        base["suggested_rewrite"] = ri["replacement_text"]
    base.update(kw)
    return base


class TableCellRedlineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from runtime.review.docx_redline import build_redline_docx

        cls.src = _table_docx()
        crs = [
            _cr("gov", {"edit_type": "replace", "target_text": "대한민국 법(또는 중립국 법)으로 한다.",
                        "replacement_text": "대한민국 법으로 한다."}),
            _cr("arb", {"edit_type": "replace", "target_text": "SIAC 또는 KCAB 중재로 해결한다.",
                        "replacement_text": "대한상사중재원(KCAB) 중재(중재지 서울)로 해결한다."}),
            _cr("new", {"edit_type": "insert_after", "edit_location": "제3조 제1항 뒤에 추가", "target_text": "",
                        "replacement_text": "2. 신설 항 문장이다.", "anchor_text": "1. 준거법은 대한민국 법(또는 중립국 법)으로"}),
        ]
        cls.rep: list[dict] = []
        cls.red, cls.clean = build_redline_docx(docx_bytes=cls.src, original_clauses=[], clause_results=crs, author="법무",
                                                date="2026-11-27T00:00:00Z", report=cls.rep, normalize_whitespace=False)
        cls.xml = zipfile.ZipFile(io.BytesIO(cls.red)).read("word/document.xml").decode("utf-8")

    def test_all_edits_applied_inside_table(self) -> None:
        self.assertEqual({r["clause_id"]: r["status"] for r in self.rep}, {"gov": "applied", "arb": "applied", "new": "applied"},
                         self.rep)
        self.assertGreaterEqual(len(re.findall(r"<w:del\b", self.xml)), 2)
        self.assertGreaterEqual(len(re.findall(r"<w:ins\b", self.xml)), 3)

    def test_accept_and_reject_round_trip(self) -> None:
        from runtime.review.docx_redline import docx_paragraph_texts

        acc = docx_paragraph_texts(self.red, mode="accept")
        self.assertIn("1. 준거법은 대한민국 법으로 한다. 분쟁은 대한상사중재원(KCAB) 중재(중재지 서울)로 해결한다.", acc)
        self.assertEqual(docx_paragraph_texts(self.red, mode="reject"), docx_paragraph_texts(self.src))

    def test_new_paragraph_goes_into_the_same_cell(self) -> None:
        import xml.etree.ElementTree as ET

        root = ET.fromstring(self.xml)
        for tc in root.iter(f"{W}tc"):
            texts = ["".join(t.text or "" for t in p.iter(f"{W}t")) for p in tc.findall(f"{W}p")]
            if any("준거법은" in t for t in texts):
                self.assertTrue(any("신설 항 문장" in t for t in texts), texts)
                return
        self.fail("국문 셀을 찾지 못함")

    def test_inline_article_reference_is_not_a_heading(self) -> None:
        import xml.etree.ElementTree as ET

        from runtime.review.docx_redline import _build_article_index, _doc_paras

        body = ET.fromstring(zipfile.ZipFile(io.BytesIO(self.src)).read("word/document.xml")).find(f".//{W}body")
        idx = _build_article_index(_doc_paras(body))
        paras = _doc_paras(body)
        first3 = "".join(t.text or "" for t in paras[idx["3"][0]].iter(f"{W}t"))
        self.assertTrue(first3.startswith("제3조"), first3)   # "잔금은 제3조의 선적 후…" 가 아니다


class BriefDeliveryTest(unittest.TestCase):
    def _brief(self, crs, apply_report=None, verification=None):
        from runtime.review.business_brief import build_business_brief

        return build_business_brief(clause_results=crs, high_issues=[c for c in crs if c["risk_tier"] == "HIGH"],
                                    medium_issues=[c for c in crs if c["risk_tier"] != "HIGH"], apply_report=apply_report,
                                    verification=verification)

    def _xb(self, cid, risk, action, title, **kw) -> dict:
        d = {"clause_id": cid, "finding_id": cid, "display_path": "제3조 제2항", "risk_tier": risk, "review_category": action,
             "action_type": action, "clause_title": title, "is_cross_border_check": True,
             "brief_current": "현재 조건 문장이다. 두 번째 문장이다. 세 번째 문장이다.",
             "brief_risk": "위험 문장이다.", "brief_action": "조치 문장이다.", "problem": "현재 조건 문장이다.",
             "rewrite_reason": "현재 조건 문장이다.", "legal_business_reason": "위험 문장이다.",
             "original_text": "본 거래의 인도 조건은 [ FCA / FOB 중 선택 ] 조건으로 한다.",
             "suggested_rewrite": "본 거래의 인도 조건은 FOB [지정 선적항], Incoterms 2020 조건으로 한다.",
             "has_rewrite_change": True,
             "redline_instruction": {"edit_type": "replace", "target_text": "[ FCA / FOB 중 선택 ]",
                                     "replacement_text": "FOB [지정 선적항], Incoterms 2020", "edit_location": "제3조 제2항 교체"},
             "undecided_labels": ["지정 선적항"], "translation_ids": [cid + "__en"]}
        d.update(kw)
        return d

    def _en(self, cid) -> dict:
        return {"clause_id": cid + "__en", "finding_id": cid + "__en", "display_path": "제3조 제2항", "risk_tier": "HIGH",
                "brief_merge_into": cid, "translation_of": cid, "is_cross_border_check": True, "clause_title": "x (영문)",
                "original_text": "The delivery term shall be [ FCA / FOB ].", "has_rewrite_change": True,
                "suggested_rewrite": "The delivery term shall be FOB [named port of shipment], Incoterms 2020.",
                "redline_instruction": {"edit_type": "replace", "target_text": "[ FCA / FOB ]",
                                        "replacement_text": "FOB [named port of shipment], Incoterms 2020"}}

    def test_tool_failure_blocks_delivery_without_changing_verdict(self) -> None:
        from runtime.review.business_brief import brief_text
        from runtime.review.delivery_docs import RX_TOOL_STATUS

        crs = [self._xb("xb_a", "HIGH", "필수수정", "인도 조건 미선택"), self._en("xb_a")]
        ok = self._brief(crs, apply_report=[{"clause_id": "xb_a", "status": "applied"}, {"clause_id": "xb_a__en", "status": "applied"}])
        bad = self._brief(crs, apply_report=[{"clause_id": "xb_a", "status": "not_found", "reason": "고칠 단락을 찾지 못함"}])
        self.assertEqual(ok.verdict, bad.verdict)
        self.assertFalse(ok.delivery_blocked)
        self.assertTrue(bad.delivery_blocked and bad.delivery_block_reasons)
        for b in (ok, bad):
            t = brief_text(b)
            self.assertFalse(RX_TOOL_STATUS.search(t), RX_TOOL_STATUS.findall(t))

    def test_korean_change_block_only_and_item_names(self) -> None:
        from runtime.review.business_brief import brief_sections

        b = self._brief([self._xb("xb_a", "HIGH", "필수수정", "인도 조건 미선택"), self._en("xb_a")])
        rows = [r for _h, rs in brief_sections(b) for r in rs]
        self.assertEqual([s for s, _t in rows].count("d"), 1)
        flat = " ".join(t for _s, t in rows)
        self.assertNotIn("named port of shipment", flat)   # 영문 수정은 변경추적본에만
        self.assertIn("미확정 조건(합의 전): 지정 선적항", flat)
        self.assertNotIn("수정 전", flat)

    def test_must_fix_is_never_low(self) -> None:
        b = self._brief([self._xb("xb_b", "LOW", "필수수정", "선택형 조항")])
        self.assertTrue(all(not (c.action_type == "필수수정" and c.risk == "LOW") for c in b.cards))

    def test_five_sections_in_order(self) -> None:
        from runtime.review.business_brief import brief_sections

        heads = [h for h, _r in brief_sections(self._brief([self._xb("xb_a", "HIGH", "필수수정", "인도 조건 미선택")]))]
        self.assertEqual([h.split(".")[0] for h in heads], ["1", "2", "3", "4", "5"])
        self.assertTrue(heads[1].startswith("2. 체결 전 필수 확정"))


class MiscTest(unittest.TestCase):
    def test_perspective_reads_user_words_only(self) -> None:
        from runtime.review.cross_border.perspective import user_words

        req = ("가나다가 이탈리아 업체로부터 원단을 수입하는 계약서 검토\n\n[사용자 확인 답변]\n"
               "- 공급자가 판매하는 원단의 최종 공급 조건은 무엇입니까?: FOB")
        w = user_words(req)
        self.assertIn("수입하는", w)
        self.assertIn("FOB", w)
        self.assertNotIn("판매하는", w)

    def test_cross_border_loss_path_is_structured(self) -> None:
        from runtime.review.cross_border.findings import _loss_path_dict

        d = _loss_path_dict("공급자 지연 → 기한 공란 → 손실")
        self.assertEqual(d, {"event": "공급자 지연", "failed_protection": "기한 공란", "loss": "손실"})


if __name__ == "__main__":
    unittest.main()
