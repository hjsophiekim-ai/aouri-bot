"""Regression (2026-08-31 incident): a real FITI 시험분석약정서 PDF upload
is laid out in two columns per page. pdfplumber's plain page.extract_text()
orders text primarily by vertical position, so the left and right columns
— sitting at the same heights — get concatenated onto the same output line
(e.g. "...위탁자에게 시험성적서를 교부한다. 제 5 조(상호협력) 수탁자는...").
An article heading buried mid-line like that is invisible to the
line-anchored "제N조(" heading scanner in clause_extraction.py, so the
whole downstream pipeline mis-segments the contract: articles disappear
entirely (absorbed into whatever article was accumulating at that point),
and MANDATORY_REVIEW_TARGET citations the user named explicitly (e.g.
"제5조 제2항 제1호") resolve as "clause_not_found" even though the clause
genuinely exists in the contract — see mandatory_review_target.py.

This is a text-extraction-layer bug, not a rule/resolver bug: no amount of
downstream keyword matching can recover an article boundary that was never
visible in the extracted text in the first place. The fix lives in
text_extract.py's _extract_page_text_column_aware(), which detects a real
column gutter (a wide, page-height-spanning empty band in the character
x-position histogram) and extracts+concatenates column-by-column instead of
row-by-row, before any downstream processing ever sees the text.
"""
from __future__ import annotations

import unittest
from pathlib import Path

_MALGUN_REGULAR = r"C:\Windows\Fonts\malgun.ttf"


def _has_korean_font() -> bool:
    return Path(_MALGUN_REGULAR).exists()


def _build_two_column_pdf(path: Path) -> None:
    """A minimal two-page-column PDF reproducing the real incident's exact
    shape: 제3조 in the left column, 제5조 starting at the same height in
    the right column — the precise pattern that interleaved into
    "...제 3 조... 제 5 조(상호협력)..." on one line in the real upload."""
    from fpdf import FPDF

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    pdf.add_font("KR", "", _MALGUN_REGULAR)
    pdf.set_font("KR", "", 11)

    margin = 15
    col_w = (pdf.w - 2 * margin - 8) / 2
    left_x = margin
    right_x = margin + col_w + 8

    left_paras = [
        "제 3 조(시험분석 의뢰) 위탁자는 시험분석 신청서와 시료를 수탁자에게 제출한다.",
        "수탁자는 시험을 접수한 날짜를 포함하여 소정의 기일 내에 시험을 완료하고 위탁자에게 시험성적서를 교부한다.",
        "위탁자는 시험분석 신청서의 기재사항이 진실함을 보증한다.",
    ]
    right_paras = [
        "제 5 조(상호협력) 수탁자는 다음 각 호의 사항을 위탁자에게 협조한다.",
        "1. 시험분석업무의 절차, 시험기준 및 방법 등에 관한 사항",
        "2. 각종 기술자료의 우선 배포",
    ]

    y = 20
    for i in range(3):
        pdf.set_xy(left_x, y)
        pdf.multi_cell(col_w, 7, left_paras[i])
        y_after_left = pdf.get_y()
        pdf.set_xy(right_x, y)
        pdf.multi_cell(col_w, 7, right_paras[i] if i < len(right_paras) else "")
        y = max(y_after_left, pdf.get_y()) + 3

    pdf.output(str(path))


@unittest.skipUnless(_has_korean_font(), "requires a Korean-capable TTF font (malgun.ttf) to render the fixture PDF")
class TwoColumnPdfExtractionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import pdfplumber

        cls.tmp_dir = Path(__file__).parent / "_tmp_pdf_column_test"
        cls.tmp_dir.mkdir(exist_ok=True)
        cls.pdf_path = cls.tmp_dir / "two_column.pdf"
        _build_two_column_pdf(cls.pdf_path)
        with pdfplumber.open(str(cls.pdf_path)) as pdf:
            cls.page = pdf.pages[0]
            cls.naive_text = cls.page.extract_text() or ""

            from runtime.review.text_extract import _extract_page_text_column_aware
            cls.fixed_text = _extract_page_text_column_aware(cls.page)

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.pdf_path.unlink(missing_ok=True)
            cls.tmp_dir.rmdir()
        except Exception:
            pass

    def test_naive_extraction_reproduces_the_interleaving_bug(self) -> None:
        # Sanity check on the fixture itself: without the fix, pdfplumber's
        # plain extract_text() really does bury "제 5 조(" mid-line, proving
        # this fixture reproduces the real incident's failure mode.
        for line in self.naive_text.splitlines():
            if "제 3 조" in line and "제 5 조" in line:
                return
        self.fail("fixture PDF did not reproduce the two-column interleaving bug — naive_text:\n" + self.naive_text)

    def test_column_aware_extraction_separates_articles_cleanly(self) -> None:
        # The fix must never produce a line containing both article
        # headings — each column's text must be fully separated.
        for line in self.fixed_text.splitlines():
            self.assertFalse(
                "제 3 조" in line and "제 5 조" in line,
                f"column-aware extraction still interleaved articles on one line: {line!r}",
            )
        # 제5조's heading must appear at the start of its own line so the
        # line-anchored "제N조(" scanner in clause_extraction.py can see it.
        art5_lines = [l for l in self.fixed_text.splitlines() if l.strip().startswith("제 5 조")]
        self.assertTrue(art5_lines, f"제5조 heading never appears at a line start:\n{self.fixed_text}")

    def test_full_pipeline_segments_both_articles_correctly(self) -> None:
        from runtime.review.clause_extraction import extract_clauses

        clauses, _report = extract_clauses(self.fixed_text)
        article_numbers = {c.article_number for c in clauses}
        self.assertIn("3", article_numbers, f"제3조 missing from segmentation: {[c.clause_id for c in clauses]}")
        self.assertIn("5", article_numbers, f"제5조 missing from segmentation: {[c.clause_id for c in clauses]}")
        art5 = [c for c in clauses if c.article_number == "5"]
        combined_art5_text = " ".join(c.text for c in art5)
        self.assertNotIn("제 3 조", combined_art5_text, "제5조's segmented text still contains 제3조's content")
        self.assertIn("상호협력", combined_art5_text)


if __name__ == "__main__":
    unittest.main()
