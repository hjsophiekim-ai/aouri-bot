"""변경 묶음(change set)·런 단위 변경추적·메모·근거 주제 대조 — 2026-11-02 지시(Norden 회귀).

실제 AI 없이 결정적으로 본다:
  · 여러 run 에 걸친 문장을 고쳐도 대상 밖 run 서식·글자가 그대로다(모두 거절 = 원본, 모두 수락 = 수정 후)
  · 한 조항이 두 단락이면(제9.9조) 고칠 문장이 든 단락만 고치고 조항 전체를 첫 단락에 다시 쓰지 않는다(중복 금지)
  · 모든 w:ins/w:del 이 메모 범위 안, 작성자 아우리봇, comments.xml 이 올바른 XML
  · 화면 데이터(change_set)의 수정 전·후 = 파일
  · 세금 조항(4.11)을 종료 후 A/S 보호 근거로 들면 빠진다
  · 설명이 상한을 요구하는데 문구에 없으면 걸린다 / 연장 선택권과 '부당 거절 금지' 를 섞으면 걸린다
  · HIGH 는 필수 수정에만, HIGH 가 없으면 0건으로 정상 표시
"""
from __future__ import annotations

import io
import unittest
import zipfile
from xml.etree import ElementTree as ET

from runtime.review.change_set import build_change_set
from runtime.review.docx_redline import W, build_redline_docx, docx_paragraph_texts
from runtime.review.requested_clause_review import (
    RequestBlock, RequestedReview, VerifiedEdit, guard_protection, measure_problems, to_findings,
)

_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _docx(paras_xml: list[str]) -> bytes:
    doc = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {_NS}><w:body>'
           + "".join(paras_xml) + "<w:sectPr/></w:body></w:document>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                   '</Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/_rels/document.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>')
        z.writestr("word/document.xml", doc)
    return buf.getvalue()


def _p(*runs: tuple[str, bool]) -> str:
    out = "<w:p>"
    for text, bold in runs:
        out += "<w:r>" + ("<w:rPr><w:b/></w:rPr>" if bold else "") + f'<w:t xml:space="preserve">{text}</w:t></w:r>'
    return out + "</w:p>"


def _cr(cid: str, path: str, original: str, target: str, replacement: str, *, risk: str = "HIGH",
        cat: str = "필수수정", undecided: list[str] | None = None) -> dict:
    return {"clause_id": cid, "display_path": path, "original_text": original, "risk_tier": risk,
            "review_category": cat, "is_requested_clause_review": True, "has_rewrite_change": True,
            "brief_action": "상한을 둔다", "brief_risk": "무제한 배상 위험", "undecided_terms": undecided or [],
            "issue_title": "테스트 쟁점",
            "redline_instruction": {"edit_type": "replace", "target_text": target, "replacement_text": replacement,
                                    "final_clause_text": original.replace(target, replacement), "edit_mode": "replace"}}


class SpliceTrackedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.src = _docx([
            _p(("9. Claims", True)),
            _p(("9.9 Customer shall indemnify NDG against all claims ", False), ("by third parties", True),
               (" arising out of or relating to any demand:", False)),
            _p(("(a) a breach by Customer; The conditions and the amount of insurance cover do not limit the "
                "customer's obligation to fully indemnify NDG.", False)),
            _p(("10. Proprietary Rights", True)),
        ])
        self.orig99 = ("Customer shall indemnify NDG against all claims by third parties arising out of or relating to any "
                       "demand: (a) a breach by Customer; The conditions and the amount of insurance cover do not limit the "
                       "customer's obligation to fully indemnify NDG.")

    def _build(self, crs: list[dict]) -> tuple[bytes, bytes, list[dict]]:
        rep: list[dict] = []
        red, clean = build_redline_docx(docx_bytes=self.src, original_clauses=[], clause_results=crs, report=rep,
                                        date="2026-11-02T00:00:00Z")
        return red, clean, rep

    def test_two_paragraph_clause_edits_only_the_right_paragraph(self) -> None:
        cr = _cr("rq4_1", "Article 9.9", self.orig99, "do not limit the customer's obligation to fully indemnify NDG",
                 "shall constitute the maximum limit of the Customer's obligation to indemnify NDG")
        red, clean, rep = self._build([cr])
        self.assertEqual(rep[0]["status"], "applied", rep)
        src_t = [t for t in docx_paragraph_texts(self.src) if t]
        self.assertEqual([t for t in docx_paragraph_texts(red, mode="reject") if t], src_t)
        cln = [t for t in docx_paragraph_texts(clean) if t]
        self.assertEqual(len(cln), len(src_t), "단락 수가 같아야 한다(조항 전체를 다시 쓰지 않음)")
        self.assertEqual(sum("arising out of or relating" in t for t in cln), 1, "문장 중복 금지")
        self.assertIn("maximum limit", cln[2])
        self.assertTrue(cln[1].startswith("9.9 Customer shall indemnify"))
        # 조항 범위 = 두 단락(같은 조항 원문)
        self.assertEqual(rep[0]["para_range"], [1, 2])

    def test_sentence_spanning_two_paragraphs_is_tracked_per_paragraph(self) -> None:
        """2026-11-03 Norden 제9.9조: 고칠 문장이 "…demand:" / "(a) …" 두 단락에 걸치면 보류되던 문제."""
        target = ("Customer shall indemnify NDG against all claims by third parties arising out of or relating to any "
                  "demand: (a) a breach by Customer;")
        repl = ("Customer shall indemnify NDG only against claims by third parties to the extent arising out of any "
                "demand: (a) a material breach by Customer;")
        cr = _cr("rq4_2", "Article 9.9", self.orig99, target, repl)
        red, clean, rep = self._build([cr])
        self.assertEqual(rep[0]["status"], "applied", rep)
        src_t = [t for t in docx_paragraph_texts(self.src) if t]
        self.assertEqual([t for t in docx_paragraph_texts(red, mode="reject") if t], src_t, "모두 거절 = 원본")
        cln = [t for t in docx_paragraph_texts(clean) if t]
        self.assertEqual(len(cln), len(src_t), "단락 구조 유지")
        self.assertIn("only against claims", cln[1])
        self.assertTrue(cln[2].startswith("(a) a material breach by Customer;"), cln[2])
        self.assertIn("do not limit", cln[2], "대상 밖 문장 유지")
        self.assertEqual(rep[0]["para_range"], [1, 2])
        root = ET.fromstring(zipfile.ZipFile(io.BytesIO(red)).read("word/document.xml"))
        open_ids: set[str] = set()
        for el in root.iter():
            if el.tag == f"{W}commentRangeStart":
                open_ids.add(el.get(f"{W}id"))
            elif el.tag == f"{W}commentRangeEnd":
                open_ids.discard(el.get(f"{W}id"))
            elif el.tag in (f"{W}ins", f"{W}del") and el.find(f"{W}r") is not None:
                self.assertTrue(open_ids, "메모 범위 밖 변경")

    def test_untouched_runs_keep_formatting(self) -> None:
        cr = _cr("rq1_1", "Article 9.9", self.orig99, "claims by third parties arising",
                 "claims by third parties to the extent arising")
        red, _clean, rep = self._build([cr])
        root = ET.fromstring(zipfile.ZipFile(io.BytesIO(red)).read("word/document.xml"))
        p = list(root.iter(f"{W}p"))[1]
        bold_runs = ["".join(t.text or "" for t in r.iter(f"{W}t")) for r in p.iter(f"{W}r")
                     if r.find(f"{W}rPr/{W}b") is not None]
        self.assertIn("by third parties", "".join(bold_runs), "굵은 run 이 그대로 남아야 한다")
        self.assertEqual(rep[0]["status"], "applied")

    def test_comments_anchor_every_change_author_and_valid_xml(self) -> None:
        cr = _cr("rq4_1", "Article 9.9", self.orig99, "do not limit", "shall limit", undecided=["[●] EUR — 협의 필요"])
        red, clean, _ = self._build([cr])
        z = zipfile.ZipFile(io.BytesIO(red))
        comments = ET.fromstring(z.read("word/comments.xml"))   # 속성 중복이면 여기서 ParseError
        texts = ["\n".join("".join(t.text or "" for t in p.iter(f"{W}t")) for p in c.iter(f"{W}p"))
                 for c in comments.iter(f"{W}comment")]
        self.assertTrue(any("수정 이유" in t and "우리 회사 위험" in t and "미확정 조건: [●] EUR" in t for t in texts), texts)
        self.assertEqual({c.get(f"{W}author") for c in comments.iter(f"{W}comment")}, {"법무팀"})
        root = ET.fromstring(z.read("word/document.xml"))
        open_ids: set[str] = set()
        for el in root.iter():
            if el.tag == f"{W}commentRangeStart":
                open_ids.add(el.get(f"{W}id"))
            elif el.tag == f"{W}commentRangeEnd":
                open_ids.discard(el.get(f"{W}id"))
            elif el.tag in (f"{W}ins", f"{W}del") and el.find(f"{W}r") is not None:
                self.assertTrue(open_ids, "메모 범위 밖 변경")
                self.assertEqual(el.get(f"{W}author"), "법무팀")
        self.assertNotIn("word/comments.xml", zipfile.ZipFile(io.BytesIO(clean)).namelist(), "클린본에는 메모가 없다")

    def test_change_set_matches_file_and_marks_draft(self) -> None:
        cr = _cr("rq4_1", "Article 9.9", self.orig99, "do not limit", "shall not exceed EUR [●] in aggregate and do not limit",
                 undecided=["EUR [●] — 협의 필요"])
        red, clean, rep = self._build([cr])
        cs = build_change_set(clause_results=[cr], report=rep)
        card = cs["cards"][0]
        self.assertEqual(card["paths"], ["Article 9.9"])
        before = "".join(t for o, t in card["segments"] if o in "=-")
        after = "".join(t for o, t in card["segments"] if o in "=+")
        cln = [t for t in docx_paragraph_texts(clean)]
        self.assertEqual(after, "\n".join(cln[1:3]))
        self.assertEqual(before, "\n".join(docx_paragraph_texts(self.src)[1:3]))
        self.assertTrue(cs["draft"])
        self.assertTrue(any(w.startswith("협상 초안") for w in cs["warnings"]))

    def test_held_target_is_reported_not_silently_dropped(self) -> None:
        cr = _cr("rq9_1", "Article 9.2", "NDG shall be liable", "this sentence does not exist", "x")
        _red, _clean, rep = self._build([cr])
        cs = build_change_set(clause_results=[cr], report=rep)
        self.assertEqual(rep[0]["status"], "not_found")
        self.assertEqual(len(cs["held"]), 1)
        self.assertTrue(any("자동 적용 보류" in w for w in cs["warnings"]))

    def test_no_high_shows_zero_not_inflated(self) -> None:
        cr = _cr("rq5_1", "Article 9.9", self.orig99, "do not limit", "shall limit", risk="MEDIUM", cat="권장수정")
        _red, _clean, rep = self._build([cr])
        cs = build_change_set(clause_results=[cr], report=rep)
        self.assertEqual(cs["counts"], {"HIGH": 0, "MEDIUM": 1, "LOW": 0})
        self.assertEqual(cs["cards"][0]["action"], "협상 권고")


class ReviewQualityGuardsTest(unittest.TestCase):
    CLAUSES = [
        {"clause_id": "c411", "display_path": "Article 4.11", "article_number": "4", "title": "Tax",
         "text": "All amounts are inclusive any withholding tax. The Customer shall deduct withholding tax and bear "
                 "other taxes; NDG shall bear the withholding income tax and refund excess withholding taxes on royalties."},
        {"clause_id": "c133", "display_path": "Article 13.3", "article_number": "13", "title": "Term",
         "text": "As from the termination of this Agreement Customer shall refrain from the manufacture, sale and "
                 "distribution of the Design Product."},
    ]

    def test_tax_clause_is_not_protection_for_wind_down(self) -> None:
        data = {"existing_protection": "Article 4.11 에 따라 종료 후 A/S 부품 공급이 보호된다.",
                "existing_protection_refs": ["Article 4.11"], "legal_limits": ""}
        dropped = guard_protection(data, issue_text="종료 후 재고 판매·A/S 부품 wind-down termination after-sales",
                                   clauses=self.CLAUSES)
        self.assertTrue(dropped and "4.11" in dropped[0])
        self.assertNotIn("4.11", data["existing_protection"])
        self.assertIn("근거 확인 필요", data["legal_limits"])

    def test_cap_asked_but_missing_in_text(self) -> None:
        data = {"action": "위약금 누적 상한을 둔다", "action_type": "필수수정", "measures": []}
        edits = [VerifiedEdit(mode="replace", target_text="x", new_text="to be fixed by mutual agreement")]
        self.assertTrue(any("상한" in p for p in measure_problems(data, edits)))
        edits_ok = [VerifiedEdit(mode="replace", target_text="x", new_text="shall not exceed EUR [●] in aggregate")]
        self.assertFalse(any("상한" in p for p in measure_problems(data, edits_ok)))
        data_reason = {**data, "measures": [{"measure": "누적 상한", "edit_index": None,
                                             "not_reflected_reason": "상한 금액은 협상 미확정 — 상한 없이 제안"}]}
        self.assertFalse(any("상한" in p for p in measure_problems(data_reason, edits)))

    def test_renewal_option_and_unreasonable_consent_not_mixed(self) -> None:
        data = {"action": "연장", "action_type": "필수수정"}
        mixed = [VerifiedEdit(mode="replace", target_text="x", new_text=(
            "Customer shall have the option to extend for five years, and NDG shall not unreasonably withhold consent."))]
        self.assertTrue(any("섞임" in p for p in measure_problems(data, mixed)))

    def test_drafting_structure_checks(self) -> None:
        from runtime.review.requested_clause_review import drafting_problems, restore_number_notation

        price = [VerifiedEdit(mode="insert_after", target_text="x", new_text=(
            "'dealer supply price' means the ex-factory price, after deduction of any discounts and rebates."))]
        p = drafting_problems({}, price, targets=[], ctx=[], request_text="ex-factory price", answers_text="")
        self.assertTrue(any("공장도가" in x for x in p))
        self.assertTrue(any("할인·리베이트" in x for x in p))
        self.assertTrue(any("직접판매" in x for x in p))
        ok = [VerifiedEdit(mode="insert_after", target_text="x", new_text=(
            "'dealer supply price' means the ex-factory price [net of discounts and rebates / before discounts]; for direct "
            "sales and sales to affiliates, the price in Customer's dealer price list [●] applies."))]
        self.assertEqual(drafting_problems({}, ok, targets=[], ctx=[], request_text="ex-factory", answers_text=""), [])
        # 이메일 정의 그대로(공제 언급 없음) — 공제 전/후 기준이 비어 있으면 확인 사항으로 남겨야 한다(2026-11-03 ③).
        from runtime.review.requested_clause_review import PRICE_DISCOUNT_GAP
        mail = [VerifiedEdit(mode="insert_after", target_text="x", new_text=(
            "'dealer supply price' means the price at which products are supplied to dealers, equivalent to the ex-factory "
            "price in trade. For direct sales and sales to affiliates, the 'dealer supply price' shall be [●]."))]
        self.assertIn(PRICE_DISCOUNT_GAP, drafting_problems({}, mail, targets=[], ctx=[], request_text="", answers_text=""))
        checked = {"checks": [{"what": "할인·리베이트 공제 전/후 기준 확인"}]}
        self.assertNotIn(PRICE_DISCOUNT_GAP, drafting_problems(checked, mail, targets=[], ctx=[], request_text="", answers_text=""))

        t99 = {"display_path": "Article 9.9", "article_number": "9", "text": (
            "Customer shall indemnify NDG. The customer is obliged to defend, indemnify and hold NDG harmless from all "
            "third-party claims arising from or in connection with the design product. The conditions do not limit the indemnity.")}
        t101 = {"display_path": "Article 10.1", "article_number": "10", "text": "Customer shall indemnify NDG against infringement claims."}
        only_ins = [VerifiedEdit(mode="replace", target_text="The conditions do not limit the indemnity.",
                                 new_text="The conditions limit the indemnity.")]
        p = drafting_problems({}, only_ins, targets=[t99], ctx=[t101], request_text="", answers_text="")
        self.assertTrue(any("포괄 면책" in x and "Article 10.1" in x for x in p), p)

        t41 = {"display_path": "Article 4.1", "article_number": "4", "text": "The reimbursement is due until the end of the contract period."}
        wd = [VerifiedEdit(mode="insert_after", target_text="y", new_text="Customer may sell off inventory after termination.")]
        p = drafting_problems({}, wd, targets=[t99], ctx=[t41], request_text="", answers_text="")
        self.assertTrue(any("사용권" in x for x in p))
        self.assertTrue(any("Article 4.1" in x for x in p))

        self.assertEqual(restore_number_notation("up to EUR 50.000 per case", "up to EUR 50,000 per breach"),
                         "up to EUR 50.000 per breach")

    def test_same_target_additions_merge_into_one_edit(self) -> None:
        """2026-11-03 제12조: 같은 문장 뒤에 붙이는 수정 두 개 중 정의 수정만 보류돼 정의 없는 용어가 남던 문제."""
        from runtime.review.requested_clause_review import merge_same_target_additions

        t = "The transfer shall require the prior written consent of NDG."
        a = VerifiedEdit(mode="replace", target_text=t, new_text=t + " NDG shall not unreasonably withhold consent for Affiliates.")
        b = VerifiedEdit(mode="replace", target_text=t, new_text=t + ' "Affiliates" shall mean any entity under common control.')
        other = VerifiedEdit(mode="replace", target_text="Other sentence.", new_text="Changed sentence.")
        out = merge_same_target_additions([a, other, b])
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0].target_text, t)
        self.assertIn("unreasonably withhold", out[0].new_text)
        self.assertIn('"Affiliates" shall mean', out[0].new_text)
        self.assertTrue(out[0].new_text.startswith(t))
        self.assertEqual(out[1].new_text, "Changed sentence.")

    def test_severity_guard_law_cap_and_uncapped_indemnity_floor(self) -> None:
        from runtime.review.requested_clause_review import severity_guard

        def rv(text: str) -> RequestedReview:
            return RequestedReview(block=RequestBlock(index=1, head="x", text="x", cited=[]),
                                   targets=[{"display_path": "Article 1", "text": text}], data={}, edits=[])

        law = rv("This Agreement shall be governed by German law. The courts of Stuttgart shall have exclusive jurisdiction.")
        self.assertEqual(severity_guard("HIGH", "필수수정", law), ("MEDIUM", "권장수정"))  # 2026-11-03: 법무 권고안 + 불수용 시 대안
        ind = rv("The customer is obliged to defend, indemnify and hold NDG harmless from all third-party claims arising "
                 "in connection with the design product. The conditions do not limit the obligation to fully indemnify NDG.")
        self.assertEqual(severity_guard("MEDIUM", "권장수정", ind), ("HIGH", "필수수정"))
        # 위약금 조항에 "court having jurisdiction" 이 나와도 관할 조항이 아니다(2026-11-03 Norden 6.5 강등).
        pen = rv("For any single case of culpable violation Customer shall pay a contractual penalty not exceeding EUR 50.000 "
                 "to be fixed at the reasonably exercised discretion NDG and in the case of dispute to be reviewed by the "
                 "court having jurisdiction.")
        self.assertEqual(severity_guard("HIGH", "필수수정", pen), ("HIGH", "필수수정"))
        from runtime.review.requested_clause_review import norm_request_status
        self.assertEqual(norm_request_status("반영됨", "사업부 결정"), "사업 판단 필요")
        self.assertEqual(norm_request_status("반영됨", "현행 유지"), "반영됨")
        capped = rv("Customer shall indemnify NDG against any and all claims in connection with the product, "
                    "provided that such liability shall not exceed EUR 1.000.000.")
        self.assertEqual(severity_guard("MEDIUM", "권장수정", capped), ("MEDIUM", "권장수정"))

    def test_high_only_for_mandatory_fix(self) -> None:
        r = RequestedReview(block=RequestBlock(index=7, head="16.8", text="16.8", cited=["Article 16.8"]),
                            targets=[{"clause_id": "c168", "display_path": "Article 16.8", "text": "German law applies.",
                                      "article_number": "16", "paragraph_number": "8", "title": "Law"}],
                            data={"risk": "HIGH", "action_type": "체결 전 확인", "verdict": "체결 전 확인",
                                  "request_status": "사업 판단 필요", "edits": []}, edits=[])
        f = to_findings([r])[0]
        self.assertEqual(f["risk_tier"], "MEDIUM")
        self.assertEqual(f["request_status"], "확인 필요")

    def test_business_decision_is_not_written_into_contract(self) -> None:
        """사업부 결정 사항(거래조건 선택)은 변경추적본에 수정안처럼 넣지 않는다 — 요청 상태는 '확인 필요'."""
        tgt = "Customer shall make an annual payment of EUR 200.000,00 for the marketing package."
        e = VerifiedEdit(mode="replace", target_text=tgt, new_text="Customer shall make an annual payment of EUR 200.000,00 for the basic package only.")
        r = RequestedReview(block=RequestBlock(index=7, head="4.2", text="4.2", cited=["Article 4.2"]),
                            targets=[{"clause_id": "c42", "display_path": "Article 4.2", "text": tgt,
                                      "article_number": "4", "paragraph_number": "2", "title": "Fee"}],
                            data={"risk": "MEDIUM", "action_type": "사업부 결정", "verdict": "수정 필요",
                                  "request_status": "미반영", "measures": [{"measure": "패키지 변경 제안", "edit_index": 0}]},
                            edits=[e])
        fs = to_findings([r])
        self.assertEqual(len(fs), 1)
        f = fs[0]
        self.assertFalse(f["has_rewrite_change"])
        self.assertTrue(f["action_only"])
        self.assertEqual(f["request_status"], "확인 필요")
        self.assertTrue(any("basic package" in c["what"] and "반영하지 않음" in c["what"] for c in f["brief_checks"]))
        self.assertTrue(all(m["not_reflected_reason"] for m in f["measures"]))

    def test_forum_request_gets_legal_recommendation_not_business_decision(self) -> None:
        """2026-11-03 지시 4항: 준거법·관할 요청은 법무 권고안과 불수용 시 대안 — 상대방 수용 여부를 사업부 결정으로 넘기지 않는다."""
        tgt = "German law shall apply to the Agreement and its construction."
        e = VerifiedEdit(mode="replace", target_text=tgt,
                         new_text="Any dispute shall be finally settled by arbitration under the ICC Rules seated in Singapore. German law shall apply to the Agreement and its construction.")
        r = RequestedReview(block=RequestBlock(index=7, head="16.8", text="16.8", cited=["Article 16.8"]),
                            targets=[{"clause_id": "c168", "display_path": "Article 16.8", "text": tgt,
                                      "article_number": "16", "paragraph_number": "8", "title": "Law"}],
                            data={"risk": "HIGH", "action_type": "사업부 결정", "verdict": "수정 필요",
                                  "recommendation": "중립 중재(싱가포르 ICC)로 변경 요청", "fallback": "거절 시 현행 독일법·슈투트가르트 유지(대응비용 예산 반영)",
                                  "decisions": ["상대방이 중재 조항을 수용하는지 여부는 사업부가 결정", "거절 시 현행 조건으로 진행할지"],
                                  "measures": [{"measure": "중재 제안", "edit_index": 0}]},
                            edits=[e])
        f = to_findings([r])[0]
        self.assertEqual(f["review_category"], "권장수정")
        self.assertEqual(f["risk_tier"], "MEDIUM")
        self.assertTrue(f["has_rewrite_change"])
        self.assertIn("싱가포르", f["recommendation"])
        self.assertIn("현행", f["fallback"])
        decs = [a for a in f["required_actions"] if a.startswith("사업부 결정")]
        self.assertEqual(decs, ["사업부 결정: 거절 시 현행 조건으로 진행할지"])
        self.assertTrue(any("협상 결과 확인" in c["what"] for c in f["brief_checks"]))


if __name__ == "__main__":
    unittest.main()
