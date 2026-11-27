"""사업팀 전달본 + 원인 단계 수정 회귀 (2026-10-30).

전달본은 같은 최종 데이터에서 결론·실행사항만 뽑는다. 여기서는 규칙을 고정하고, 실제 개선 여부는
reports_evidence/business_brief/ 의 업로드→검토→다운로드 실행 결과(check_brief_acceptance.py)로 판정한다.
"""
from __future__ import annotations

import io
import re
import unittest
import zipfile
from pathlib import Path

from runtime.review.business_brief import (
    STATUS_PENDING,
    brief_text,
    build_business_brief,
    build_business_brief_docx,
    build_business_brief_pdf,
    undecided_terms,
)

_FIX = Path(__file__).resolve().parent / "fixtures"


def _issue(cid: str, sev: str, title: str, path: str, *, rw: str = "", ri: dict | None = None, **kw) -> dict:
    d = {"clause_id": cid, "finding_id": cid, "severity": sev, "risk_tier": sev, "issue_title": title,
         "display_path": path, "problem": kw.pop("problem", f"{title} 문제."),
         "legal_business_reason": kw.pop("lbr", "대금을 돌려받지 못할 수 있다."),
         "proposed_revision": rw, "suggested_rewrite": rw, "redline_instruction": ri}
    d.update(kw)
    return d


class BriefRulesTest(unittest.TestCase):
    def _brief(self, issues, **kw):
        high = [i for i in issues if i["severity"] == "HIGH"]
        med = [i for i in issues if i["severity"] == "MEDIUM"]
        return build_business_brief(clause_results=issues, high_issues=high, medium_issues=med, **kw)

    def test_sections_in_order_and_no_internal_codes(self) -> None:
        b = self._brief([_issue("KR-3-p2", "HIGH", "[협찬 대가] 보장 수량이 예정으로 바뀜", "제3조 제2항",
                                rw="다만, 보장 수량은 변경할 수 없다.",
                                ri={"edit_type": "replace", "target_text": "협의하여 변경한다.",
                                    "replacement_text": "협의하여 변경한다. 다만, 보장 수량은 변경할 수 없다.",
                                    "edit_location": "제3조 제2항 교체"},
                                problem="AI 자체 판단으로 보면 보장 수량이 예정으로 바뀐다. REVIEW_FAILED_X 상태.")])
        t = brief_text(b)
        pos = [t.find(h) for h in ("1. 검토 결론", "2. 체결 전 필수 확정 사항", "3. 쟁점별 요약", "4. 계약 전 확인사항", "5. 파일 안내")]
        self.assertTrue(all(p >= 0 for p in pos) and pos == sorted(pos), pos)
        # 위험도(HIGH/MEDIUM/LOW)는 쟁점 카드 머리에 싣는다(2026-11-02 지시 3·4항) — 내부 코드·처리 과정 표현은 여전히 금지.
        self.assertNotRegex(t, r"REVIEW_|KR-\d|AI 자체")
        self.assertIn("[HIGH · 필수수정]", t)
        # 2026-11-27 지시: 전달본은 국문 수정안을 '변경 표시' 한 블록으로만 — 수정 전/수정 후 블록은 싣지 않는다
        self.assertNotIn("수정 전:", t)
        self.assertNotIn("수정 후:", t)
        self.assertIn("[+ 다만, 보장 수량은 변경할 수 없다.+]", t)
        self.assertEqual(b.verdict, "조건부 진행 가능")

    def test_held_rewrite_is_disclosed_with_impact_not_hidden(self) -> None:
        b = self._brief([_issue("KR-4", "HIGH", "보증 범위", "제4조", rw="새 문안",
                                ri={"held": True, "hold_reason": "교체하면 기존 보호 문구가 사라짐", "edit_type": "replace"})])
        self.assertEqual(b.revisions[0].status, STATUS_PENDING)
        self.assertIn("체결", b.revisions[0].impact)
        self.assertEqual(b.appendix, [])  # 검증되지 않은 문안을 붙여 넣을 수 있게 내보내지 않는다
        # 2026-11-27 지시: 도구 상태(자동 적용 보류)는 결론을 바꾸지 않는다 — 결론은 계약 리스크로만 정하고,
        # 보류된 수정안이 있으면 전달본을 사업팀에 내보내지 않고 법무에게만 사유를 알린다.
        self.assertEqual(b.verdict, "조건부 진행 가능")
        self.assertTrue(b.delivery_blocked)
        self.assertTrue(any("기존 보호 문구" in r for r in b.delivery_block_reasons))
        self.assertNotIn("기존 보호 문구", brief_text(b))

    def test_undecided_amount_is_marked_not_invented(self) -> None:
        self.assertEqual(undecided_terms("최고액은 금 [    ]원으로 한다", contract_text="", answers_text=""),
                         ["최고액은 금 [    ]원"])
        self.assertEqual(undecided_terms("10영업일 이내", contract_text="", answers_text=""), ["10영업일"])
        self.assertEqual(undecided_terms("3개월 이내", contract_text="기간은 3 개월", answers_text=""), [])

    def test_unsupported_law_assertion_dropped_from_brief(self) -> None:
        b = self._brief([_issue("KR-10", "MEDIUM", "", "제10조", clause_title="제10조 (임차인의 준수의무)",
                                problem="연대배상 문구가 모호하다. 상가건물임대차보호법 및 민법상 임차인 책임은 통상 과실범위로 한정됨.",
                                rw="임차인은 중대한 과실에 한하여 배상한다.", ri={"edit_type": "replace"})])
        t = brief_text(b)
        self.assertNotIn("상가건물임대차보호법", t)
        self.assertIn("임차인의 준수의무 문구 보완", t)

    def test_one_issue_once_and_requests_linked(self) -> None:
        issues = [_issue("A", "MEDIUM", "주차장 승계", "제14조", rw="승계 문장", ri={"edit_type": "replace"})]
        cov = [{"request_index": "1", "normalized_issue": "주차장", "judgment": "수정 필요: 승계 누락", "matched_finding_ids": ["A"]},
               {"request_index": "2", "normalized_issue": "전대 동의", "judgment": "현행 유지 — 동의가 이미 있다",
                "matched_finding_ids": []}]
        b = self._brief(issues + issues, user_review_coverage=cov)
        self.assertEqual(len(b.revisions), 1)
        self.assertEqual([r.index for r in b.requests], ["1", "2"])  # 답이 없는 요청도 빠지지 않는다
        self.assertEqual(b.requests[0].items, ["쟁점 1"])

    def test_request_with_proposed_sentence_keeps_the_sentence(self) -> None:
        cov = [{"issue_id": "answer_subcontracting", "normalized_issue": "제3자 수행 통제", "matched_finding_ids": [],
                "direct_answer": "재위탁 문언이 없습니다. 업무 범위 조항에 아래 한 문장을 넣으면 충분합니다.",
                "review_status": "사업부 결정 필요",
                "proposed_clauses": ["상대방이 업무를 제3자에게 수행하게 하는 경우에도 그 책임은 상대방이 부담한다."]}]
        b = self._brief([], user_review_coverage=cov)
        t = brief_text(b)
        self.assertIn("별첨 문장", t)
        self.assertNotIn("아래 한 문장", t)
        self.assertIn("상대방이 업무를 제3자에게 수행하게 하는 경우에도", t)
        self.assertEqual(b.appendix[0].mode, "선택 시 추가")
        self.assertEqual(b.requests[0].items, ["쟁점 1"])

    def test_answer_scoped_decision_is_not_blanket_acceptance(self) -> None:
        deal = {"active": True, "core_risks": [], "protections": [
            {"key": "parking_collateral", "label": "주차장 지분 담보가치", "path": "제14조",
             "assessment": "주차장의 문제는 담보가치가 아니라 사용권이다 — 실익은 작고(사용자 결정: 담보설정을 하지 않을 예정입니다)",
             "limits": ["지분이 약 9.5%라 회수 실익은 제한적이다"]}]}
        b = self._brief([], deal_assessment=deal)
        d = b.decisions[0]
        self.assertEqual(d.level, "결정됨")
        self.assertIn("다른 위험의 수용을 뜻하지 않습니다", d.action)

    def test_docx_and_pdf_render_the_same_lines(self) -> None:
        b = self._brief([_issue("A", "HIGH", "보증 최고액", "제14조", rw="이 보증채무의 최고액은 금 [ ]원으로 한다.",
                                ri={"edit_type": "insert_after", "edit_location": "제14조 제6항 뒤에 신설"})])
        docx = build_business_brief_docx(b)
        xml = zipfile.ZipFile(io.BytesIO(docx)).read("word/document.xml").decode("utf-8")
        text = re.sub(r"<[^>]+>", "", xml)
        self.assertIn("미확정", text)
        self.assertIn("이 보증채무의 최고액은 금 [ ]원으로 한다.", text)
        self.assertTrue(build_business_brief_pdf(b).startswith(b"%PDF"))


class RootCauseTest(unittest.TestCase):
    def test_statute_relations_follow_the_issue(self) -> None:
        from runtime.review.statute_grounding import detect_relations, statutes_for

        def cites(cr, arche=""):
            return [s.citation for s in statutes_for(detect_relations(cr, archetype=arche))]

        self.assertEqual(cites({"issue_title": "주차장 사용권 — 양수인 승계 누락·공유자 동의 미확인",
                                "original_text": "양수인이 제 1호의 승낙을 승계하도록 한다."}), ["민법 제265조"])
        self.assertNotIn("민법 제543조 제1항", cites({"issue_title": "예금질권 — 만기 재예치 때 질권 공백",
                                                   "original_text": "예금은 해지 및 인출하지 않으며"}))
        self.assertIn("민법 제428조의3 제2항", cites({"issue_title": "연대보증 — 최고액 미특정", "original_text": "연대하여 보증한다"}))
        self.assertEqual(cites({"issue_title": "하자 보수", "original_text": "“임대인”은 하자를 보수한다"}, "lease_rental"),
                         ["민법 제623조"])
        # 저작물이 있는 이용권은 그대로 이용허락
        self.assertIn("저작권법 제46조 제2항", cites({"issue_title": "콘텐츠 이용권 범위", "original_text": "콘텐츠의 이용을 허락한다"}))

    def test_two_sentence_edits_in_one_word_paragraph_both_apply(self) -> None:
        from runtime.review.docx_redline import build_redline_docx

        items = ["(6) “토지소유자”는 다음 사항을 확약한다.", "2. 주차장 사용을 승인한다.",
                 "3. 토지를 양도하는 경우 사전 통지한다. 양도 시에는 양수인이 제 1호의 승낙을 승계하도록 한다.",
                 "4. 보증금 반환채무 및 손해배상채무를 연대하여 보증한다."]
        run = "<w:br/>".join(f'<w:t xml:space="preserve">{t}</w:t>' for t in items)
        body = '<w:p><w:r><w:t>제 14 조 (특약)</w:t></w:r></w:p>' + f"<w:p><w:r>{run}</w:r></w:p>"
        xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
               f'wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>')
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("word/document.xml", xml)
            z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
            z.writestr("word/_rels/document.xml.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')

        def edit(cid, original, target, repl):
            return {"clause_id": cid, "article_number": "14", "risk_tier": "MEDIUM", "original_text": original,
                    "suggested_rewrite": repl, "has_rewrite_change": True,
                    "redline_instruction": {"edit_type": "replace", "target_text": target, "replacement_text": repl,
                                            "final_clause_text": original.replace(target, repl)}}

        t1, r1 = "양도 시에는 양수인이 제 1호의 승낙을 승계하도록 한다.", "양도 시에는 양수인이 제 1호의 승낙 및 제2호의 사용 승인을 승계하도록 한다."
        t2 = "보증금 반환채무 및 손해배상채무를 연대하여 보증한다."
        r2 = t2 + " 이 보증채무의 최고액은 금오억원으로 한다."
        crs = [edit("g", items[3], t2, r2), edit("p", items[2], t1, r1)]
        _, clean = build_redline_docx(docx_bytes=buf.getvalue(), original_clauses=[], clause_results=crs)
        text = re.sub(r"<[^>]+>", "", zipfile.ZipFile(io.BytesIO(clean)).read("word/document.xml").decode("utf-8"))
        self.assertIn("제2호의 사용 승인을 승계", text)       # 종전: 두 번째 수정이 건너뛰어졌다
        self.assertIn("최고액은 금오억원", text)
        self.assertIn("주차장 사용을 승인한다", text)
        self.assertEqual(text.count("사전 통지한다"), 1)

    def test_answer_is_matched_by_question_topic_not_quoted_contract_text(self) -> None:
        from runtime.review.deal_assessment import _answer_for

        qa = [("토지소유자의 연대보증 범위가 '임대보증금 반환채무 및 손해배상채무(일룸 투자비 한도)'로 충분합니까?", "임대보증금 한도입니다."),
              # 11-02 실측: 따옴표 없이 언급해도 주제는 연대보증이다
              ("토지소유자의 연대보증 범위가 보증금 반환채무 외에 손해배상(일룸 투자비 한도)까지 포함되는 것에 동의하십니까?", "임대보증금 한도입니다."),
              ("용도변경 인허가가 불가하면 투자비 보전 등 안전장치를 원하십니까?", "즉시 해지하고 계약금을 반환받습니다."),
              ("컬렉티브 매장 내 계열사 전대 시 토지소유자(연대보증인)에게도 동의가 필요한지 확인하셨습니까?", "확인 필요")]
        self.assertEqual(_answer_for(qa, "investment"), "")          # 실측: 투자비 답으로 잘못 읽었다
        self.assertEqual(_answer_for(qa, "guarantee"), "임대보증금 한도입니다.")
        self.assertEqual(_answer_for(qa, "use_change"), "즉시 해지하고 계약금을 반환받습니다.")
        self.assertEqual(_answer_for(qa, "sublease"), "확인 필요")
        self.assertEqual(_answer_for([("임차인 투자비(인테리어 등)에 대한 안전장치로 추가 담보를 요구하십니까?", "특별히 없습니다.")],
                                     "investment"), "특별히 없습니다.")

    def test_inline_duplicate_rewrite_is_not_word_salad(self) -> None:
        src = (Path(__file__).resolve().parents[1] / "review" / "clause_level.py").read_text(encoding="utf-8")
        self.assertNotIn('" 조건 포함)"', src)


if __name__ == "__main__":
    unittest.main()
