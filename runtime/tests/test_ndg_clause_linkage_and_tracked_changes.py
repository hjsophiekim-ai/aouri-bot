"""2026-11-02 Norden(NDG) 디자인 라이선스 계약 실측에서 찾은 원인들 — AI 없이 결정론적으로 고정한다.

1. PDF 머리글·줄 끝 하이픈이 조항 원문에 섞여 실재 인용이 "가짜 인용" 이 됐다.
2. "2.1." / "6. 1" 항 번호를 못 읽어 제2.1·2.2·6.1·6.3조가 색인에서 사라졌다.
3. 사용자 인용 "제6.5조" 와 영문 경로 "Article 6.5" 를 문자열로 비교해 5개 요청이 "해당 조항 없음" 이 됐다.
4. 국문 계약용 분석기·점검이 영문 계약에 국내 관할 결론·국문 무제한 권리 문구를 붙였다.
5. 변경추적본이 단락 전체를 지우고 다시 써서, 바뀐 부분만 보이지 않았고 PDF 원본은 변경추적본을 받을 수 없었다.
"""
from __future__ import annotations

import io
import json
import re
import unittest
import zipfile

from runtime.review.clause_extraction import extract_clauses
from runtime.review.clause_label import clause_path_key, clause_path_relation
from runtime.review.text_diff import after_text, before_text, diff_segments
from runtime.review.text_extract import join_line_hyphenation, strip_running_headers

HEADER = "Norden Design Gesellschaft m.b.H / Sidiz Inc.\nDesign Development Agreement including Reference to Cooperation\n"


def _filler(a: int, b: int) -> str:
    # 영문 조 제목은 1부터 차례로 올라가야 조로 읽힌다 — 사이 조를 채운다.
    return "".join(f"{n}. Article Heading {n}\n{n}.1 Customer shall comply with this article {n}.\n" for n in range(a, b))


def _pages() -> list[str]:
    body = [
        "1. Subject Matter of the Agreement\n1.1 The subject matter is the development of a design.\n" + _filler(2, 6),
        "6. Reference to the cooperation with NDG\n6. 1 References can only be made under the following conditions.\n"
        "6.2 The Customer is entitled to use the reference.\n6. 3 The use of the trademark is not permitted.\n",
        "6.5 For any single case of culpable violation Customer shall pay a contractual penalty not exceeding EUR 50.000.\n"
        + _filler(7, 13) + "13. Term\n13.1 This Agreement shall end after five years with the option to extend for "
        "further five years, subject to the consent of both Parties.\n",
        "13.3 As from the termination of this Agreement Customer shall refrain from the sale of the Design Product.\n"
        + _filler(14, 16) + "16. General Provisions\n16.8 German law shall apply to the Agreement and its construc-\n",
        "tion. The CISG shall not apply.\n",
    ]
    return [HEADER + b + f"Seite {i + 1} von {len(body)}\n" for i, b in enumerate(body)]


class SourceTextTest(unittest.TestCase):
    def test_running_headers_and_page_numbers_removed(self) -> None:
        pages, removed = strip_running_headers(_pages())
        joined = "\n".join(pages)
        self.assertNotIn("Seite", joined)
        self.assertNotIn("Norden Design Gesellschaft m.b.H / Sidiz Inc.", joined)
        self.assertIn("6.5 For any single case", joined)
        self.assertTrue(removed)

    def test_line_end_hyphen_joined_across_page_marker(self) -> None:
        t = "its construc-\n\n[페이지 15]\ntion. The CISG shall not apply."
        out = join_line_hyphenation(t)
        self.assertIn("its construction.", out)
        self.assertIn("[페이지 15]", out)

    def test_dotted_and_spaced_paragraph_numbers_are_clauses(self) -> None:
        pages, _ = strip_running_headers(_pages())
        cs, _rep = extract_clauses("\n".join(pages))
        paths = [c.display_path for c in cs]
        for p in ("Article 6.1", "Article 6.2", "Article 6.3", "Article 6.5", "Article 13.1", "Article 13.3", "Article 16.8"):
            self.assertIn(p, paths)
        self.assertFalse(any("Seite" in c.text for c in cs))


class CitationLinkTest(unittest.TestCase):
    def test_korean_citation_matches_english_path_by_number(self) -> None:
        self.assertEqual(clause_path_key("제6.5조"), ("6", "5"))
        self.assertEqual(clause_path_key("Article 6.5"), ("6", "5"))
        self.assertEqual(clause_path_relation("제6.5조", "Article 6.5"), "exact")
        self.assertEqual(clause_path_relation("제13조", "Article 13.3"), "inside")
        # 숫자 접두어로 잇지 않는다 — 제1.3조는 제13.1조가 아니다.
        self.assertEqual(clause_path_relation("제1.3조", "Article 13.1"), "")
        self.assertEqual(clause_path_relation("제4.1조", "Article 4.10"), "")

    def test_cited_clause_wins_over_keyword_neighbour(self) -> None:
        from runtime.review.user_review_request import UserReviewIssue, link_clauses_to_issues

        pages, _ = strip_running_headers(_pages())
        cs, _rep = extract_clauses("\n".join(pages))
        issue = UserReviewIssue(issue_id="x", source="explicit_user_request",
                                original_user_text="제13.3조(계약 종료 후 후속 조치): 잔여 재고 판매",
                                normalized_issue="종료 후 재고", cited_clause_paths=["제13.3조"],
                                search_keywords=["재고", "종료"])
        link_clauses_to_issues([issue], cs)
        self.assertEqual([c for c in issue.relevant_clause_ids], ["EN-13.3"])

    def test_request_blocks_keep_detail_lines_and_cited_clause(self) -> None:
        from runtime.review.requested_clause_review import resolve_cited, split_request_blocks

        rf = ("검토 요청드립니다.\n\n1. 제6.5조(위약금 조항): 적정성 검토\n\n2. 제13.3조(종료 후 조치): wind-down 추가\n"
              "■잔여 재고 판매\n○일정 기간 판매 허용\n\n3. 제16.8조(준거법): 리스크 검토\n")
        blocks = split_request_blocks(rf)
        self.assertEqual([b.index for b in blocks], [1, 2, 3])
        self.assertIn("잔여 재고 판매", blocks[1].text)
        pages, _ = strip_running_headers(_pages())
        cs, _rep = extract_clauses("\n".join(pages))
        self.assertEqual([c.display_path for c in resolve_cited(blocks[1].cited, cs)], ["Article 13.3"])


class ForeignContractGuardTest(unittest.TestCase):
    def test_commercial_jurisdiction_answer_not_given_for_english_clause(self) -> None:
        from runtime.review.commercial_request_review import review_commercial_requests

        clauses = [{"display_path": "Article 16.8", "title": "General Provisions",
                    "text": "For all disputes the exclusive jurisdiction of the court in Stuttgart, Germany is agreed."}]
        out = review_commercial_requests(review_focus="1. 제16.8조(준거법 및 관할): 관할 리스크 검토\n2. a\n3. b",
                                         clauses=clauses)
        self.assertFalse(any("국내 법인" in r.conclusion for r in out))

    def test_korean_baseline_checks_skip_english_clause(self) -> None:
        from runtime.review.effect_baseline_review import run_effect_baseline_review

        clauses = [{"clause_id": "EN-7.1", "display_path": "Article 7.1", "title": "Industrial Property Rights",
                    "text": "Customer acknowledges that any copyright to the Design Result is the property of NDG."}]
        out = run_effect_baseline_review(clauses, full_text=clauses[0]["text"])
        self.assertEqual([o["clause_id"] for o in out], [])

    def test_english_party_aliases_are_read(self) -> None:
        from runtime.review.entity_resolution import resolve_entities

        text = ('By and between\nNorden Design Gesellschaft m.b.H., Musterstraße 1, 5020 Salzburg, Austria, ["NDG"]\n'
                'and\nSidiz Inc., 67-20, Segyosandan-ro, Pyeongtaek-si, South Korea ["Customer"].\n'
                "1. Subject Matter of the Agreement\n1.1 The subject matter is a design.\n")
        res = resolve_entities(text, entity="시디즈")
        labels = {p.label: p.is_our_company for p in res.parties}
        self.assertEqual(labels, {"NDG": False, "Customer": True})

    def test_contamination_gate_does_not_delete_english_drafting_words(self) -> None:
        from runtime.review.review_isolation import detect_contamination

        crs = [{"clause_id": "EN-13.3", "issue_title": "종료 후 처리 미흡",
                "suggested_rewrite": "Notwithstanding clause 13.3, Customer may sell off Wind-down inventory in Seoul."}]
        self.assertEqual(detect_contamination(crs, contract_text="13.3 As from the termination of this Agreement ..."), [])


class EditVerificationTest(unittest.TestCase):
    CLAUSE = ("For the usage of the reference Customer shall pay to NDG a reimbursement of 7 % of the dealer supply price. "
              "Customer shall pay a contractual penalty not exceeding EUR 50.000 [in words: fifty thousand EURO].")

    def _v(self, raw: dict, request: str = ""):
        from runtime.review.requested_clause_review import verify_edit

        return verify_edit(raw, clause_text=self.CLAUSE, contract_text=self.CLAUSE, request_text=request,
                           answers_text="", latin=True)

    def test_replacement_that_drops_royalty_rate_is_held(self) -> None:
        e = self._v({"mode": "replace", "target_text": "Customer shall pay to NDG a reimbursement of 7 % of the dealer supply price.",
                     "new_text": "'Dealer supply price' means the ex-factory price."})
        self.assertTrue(e.held)
        self.assertIn("7%", e.hold_reason.replace(" ", ""))

    def test_definition_added_after_sentence_keeps_terms(self) -> None:
        from runtime.review.requested_clause_review import apply_edit

        e = self._v({"mode": "insert_after", "target_text": "of 7 % of the dealer supply price.",
                     "new_text": "'dealer supply price' means the ex-factory price."})
        self.assertFalse(e.held)
        self.assertIn("7 % of the dealer supply price. 'dealer supply price' means", apply_edit(self.CLAUSE, e))

    def test_amount_format_difference_is_not_a_lost_term(self) -> None:
        e = self._v({"mode": "replace",
                     "target_text": "Customer shall pay a contractual penalty not exceeding EUR 50.000 [in words: fifty thousand EURO].",
                     "new_text": "Customer shall pay a contractual penalty not exceeding EUR 50,000 [in words: fifty thousand EURO] "
                                 "in aggregate."}, request="건당 최대 EUR 50,000 위약금")
        self.assertFalse(e.held, e.hold_reason)

    def test_korean_text_ellipsis_and_invented_numbers(self) -> None:
        self.assertTrue(self._v({"mode": "insert_after", "target_text": "of 7 % of the dealer supply price.",
                                 "new_text": "국문 문장."}).held)
        self.assertTrue(self._v({"mode": "insert_after", "target_text": "of 7 % of the dealer supply price.",
                                 "new_text": "The definition applies ..."}).held)
        e = self._v({"mode": "insert_after", "target_text": "of 7 % of the dealer supply price.",
                     "new_text": "Payment is due within 45 days."})
        self.assertTrue(any("45 days" in u for u in e.undecided))

    def test_text_not_in_clause_is_held(self) -> None:
        self.assertTrue(self._v({"mode": "replace", "target_text": "1. Definitions", "new_text": "x"}).held)


class DiffAndTrackedChangesTest(unittest.TestCase):
    def test_diff_invariants(self) -> None:
        a = "This Agreement shall end after five years with the option to extend, subject to the consent of both Parties."
        b = "This Agreement shall end after five years and shall be automatically extended unless Customer is in breach."
        segs = diff_segments(a, b)
        self.assertEqual(before_text(segs), a)
        self.assertEqual(after_text(segs), b)
        self.assertTrue(any(o == "=" and "shall end after five years" in t for o, t in segs))

    def _docs(self, crs: list[dict]):
        from runtime.review.docx_redline import build_redline_docx
        from runtime.review.source_docx import build_docx_from_text

        src = build_docx_from_text("13. Term\n13.1 This Agreement shall end after five years with the option to extend.\n"
                                   "13.2 Either party may terminate for cause.\n")
        rep: list[dict] = []
        red, clean = build_redline_docx(docx_bytes=src, original_clauses=[], clause_results=crs, author="퍼시스 법무",
                                        date="2026-11-02T00:00:00Z", report=rep, normalize_whitespace=True)
        return src, red, clean, rep

    def test_only_changed_words_are_tracked_and_accept_reject_round_trip(self) -> None:
        from runtime.review.docx_redline import docx_paragraph_texts

        cr = {"clause_id": "rq5_1_EN-13.1", "display_path": "Article 13.1", "risk_tier": "HIGH", "article_number": "13",
              "paragraph_number": "1", "has_rewrite_change": True,
              "original_text": "This Agreement shall end after five years with the option to extend.",
              "suggested_rewrite": "This Agreement shall end after five years and shall be automatically extended.",
              "redline_instruction": {"edit_type": "replace",
                                      "target_text": "with the option to extend.",
                                      "replacement_text": "and shall be automatically extended."}}
        src, red, clean, rep = self._docs([cr])
        self.assertEqual(rep[0]["status"], "applied")
        with zipfile.ZipFile(io.BytesIO(red)) as z:
            xml = z.read("word/document.xml").decode("utf-8")
            settings = z.read("word/settings.xml").decode("utf-8")
        self.assertIn("trackRevisions", settings)
        deleted = "".join(re.findall(r"<w:delText[^>]*>([^<]*)</w:delText>", xml))
        self.assertNotIn("shall end after five years", deleted)   # 유지 부분은 지우지 않는다
        self.assertEqual(docx_paragraph_texts(red, mode="reject"), docx_paragraph_texts(src))
        self.assertEqual(docx_paragraph_texts(red, mode="accept"), docx_paragraph_texts(clean))
        self.assertIn("13.1 This Agreement shall end after five years and shall be automatically extended.",
                      docx_paragraph_texts(clean))

    def test_unlocatable_edit_is_held_not_overwritten(self) -> None:
        from runtime.review.docx_redline import docx_paragraph_texts

        cr = {"clause_id": "x", "display_path": "Article 13.2", "risk_tier": "HIGH", "article_number": "13",
              "paragraph_number": "2", "has_rewrite_change": True,
              "original_text": "Completely different text that is nowhere in the document at all.",
              "suggested_rewrite": "New wording.",
              "redline_instruction": {"edit_type": "replace", "target_text": "nowhere", "replacement_text": "New"}}
        src, red, clean, rep = self._docs([cr])
        self.assertEqual(rep[0]["status"], "not_found")
        self.assertEqual(docx_paragraph_texts(clean), docx_paragraph_texts(src))


class BriefCardsTest(unittest.TestCase):
    def test_open_request_blocks_unconditional_proceed_and_cards_show_before_after(self) -> None:
        from runtime.review.business_brief import brief_sections, build_business_brief

        cr = {"clause_id": "rq2_1_EN-6.5", "display_path": "Article 6.5", "risk_tier": "MEDIUM", "severity": "MEDIUM",
              "is_requested_clause_review": True, "issue_title": "위약금 재량 과도", "review_category": "권장수정",
              "brief_current": "NDG가 위약금을 재량으로 정한다.", "brief_risk": "부담이 커질 수 있다.",
              "brief_action": "상한을 둔다.", "original_text": "Customer shall pay a penalty fixed by NDG.",
              "suggested_rewrite": "Customer shall pay a penalty fixed by NDG, capped at EUR [●] in aggregate.",
              "redline_instruction": {"edit_type": "replace", "target_text": "Customer shall pay a penalty fixed by NDG.",
                                      "replacement_text": "Customer shall pay a penalty fixed by NDG, capped at EUR [●] in aggregate."}}
        cov = [{"request_index": 1, "normalized_issue": "제16.8조(준거법)", "review_status": "사실관계 추가확인",
                "direct_answer": "확인 필요", "matched_finding_ids": []}]
        b = build_business_brief(clause_results=[cr], high_issues=[], medium_issues=[cr], user_review_coverage=cov,
                                 apply_report=[{"clause_id": "rq2_1_EN-6.5", "status": "applied"}])
        self.assertEqual(b.verdict, "조건부 진행 가능")
        rows = [r for _h, rs in brief_sections(b) for r in rs]
        styles = [s for s, _t in rows]
        # 2026-11-27 지시: 수정 전/후 블록("b"/"a") 대신 변경 표시("d") 한 블록만
        self.assertNotIn("b", styles)
        self.assertNotIn("a", styles)
        self.assertIn("d", styles)
        d = json.loads(next(t for s, t in rows if s == "d"))
        self.assertIn(["+", ", capped at EUR [●] in aggregate"], [list(x) for x in d])
        self.assertTrue(any(t.startswith("쟁점 1 [MEDIUM · 권장수정] 위약금 재량 과도") for s, t in rows if s == "h"))


if __name__ == "__main__":
    unittest.main()
