"""TOP 5 핵심 리스크 섹션 폐지 — DOCX/PDF 동일 (2026-09-08 지시).

PDF 리포트의 "TOP 5 핵심 리스크" 섹션이 `_issue_block()` 을 그대로 호출해
원문·문제점·수정문안까지 찍었고, 바로 뒤 "필수수정 조항 — HIGH" 섹션이
같은 내용을 다시 출력해 같은 조항이 두 번 나왔다. DOCX 는 같은 이유로
2026-08-31 에 이미 이 섹션을 폐지한 상태여서 두 포맷이 서로 달랐다.

이제 두 포맷 모두 TOP 5 섹션이 없고 섹션 번호도 일치한다:

    1. 계약 구조
    (2. 관련 법률 적용성 검토 — 사용자가 특정 법률을 물은 경우에만)
    다음 번호. 필수수정 조항 — HIGH
    다음 번호. 권장수정 조항 — MEDIUM

`top_risks_filtered` 파라미터는 호출자 호환을 위해 남아 있지만 어느 포맷도
별도 섹션으로 렌더링하지 않는다.
"""
from __future__ import annotations

import io
import re
import unittest
import zipfile

from runtime.review.legal_review_docx import ReviewIssue, build_legal_review_docx
from runtime.review.legal_review_pdf import build_legal_review_pdf


def _markers(tag: str) -> tuple[str, ...]:
    """이슈마다 고유한 본문 마커 — 같은 문자열이면 정상 출력이 중복으로 오인된다."""
    return tuple(f"{kind}본문{tag}" for kind in ("원문", "문제점", "수정문안", "협상포지션"))


def _issue(clause_title: str, *, severity="HIGH", clause_id="c1", tag="T") -> ReviewIssue:
    m_orig, m_prob, m_rev, m_neg = _markers(tag)
    return ReviewIssue(
        clause_id=clause_id,
        clause_title=clause_title,
        severity=severity,
        approval_required=False,
        issue_title="이슈제목",
        original_text=m_orig,
        problem=m_prob,
        legal_business_reason=f"법적이유본문{tag}",
        proposed_revision=m_rev,
        negotiation_position=m_neg,
    )


HIGH = [
    _issue("제8조 제3항 [Background IP 침해]", clause_id="h1", tag="H1"),
    _issue("제4조 제1항 [범용 AI 모델 학습 제한 부재]", clause_id="h2", tag="H2"),
]
MEDIUM = [
    _issue("제11조 [손해배상 범위]", severity="MEDIUM", clause_id="m1", tag="M1"),
]
ALL_MARKERS = [m for tag in ("H1", "H2", "M1") for m in _markers(tag)]

PROFILE = {
    "our_party": "일룸",
    "counterparty": "에이슬립",
    "our_legal_role": "principal",
    "contract_type": "nda_confidentiality",
    "confidence": 0.82,
    "confidentiality_term": "3년",
    "unresolved_questions": ["실제 음성정보 처리 주체 확인 필요", "서버 소재지 확인 필요"],
}

_KWARGS = dict(
    entity="일룸",
    contract_type="nda_confidentiality",
    filename="NDA.docx",
    clause_results=[],
    detailed_contract_profile=PROFILE,
    top_risks_filtered=[i.to_dict() for i in (HIGH + MEDIUM)],
    high_issues_filtered=[i.to_dict() for i in HIGH],
    medium_issues_filtered=[i.to_dict() for i in MEDIUM],
    include_low=False,
    contract_type_code="nda_confidentiality",
)


def _pdf_text(**extra) -> str:
    import fitz

    doc = fitz.open(stream=build_legal_review_pdf(**dict(_KWARGS, **extra)), filetype="pdf")
    out = "\n".join(page.get_text() for page in doc)
    doc.close()
    return out


def _docx_text(**extra) -> str:
    blob = build_legal_review_docx(**dict(_KWARGS, **extra))
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    return "\n".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml, re.S))


def _section_number(case: unittest.TestCase, text: str, title: str, label: str) -> str:
    m = re.search(rf"(\d+)\.\s*{re.escape(title)}", text)
    case.assertIsNotNone(m, f"{label}: '{title}' 섹션을 찾지 못했다")
    return m.group(1)


class Top5SectionAbolishedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            import fitz  # noqa: F401
        except Exception:  # pragma: no cover
            raise unittest.SkipTest("pymupdf(fitz) 없음 — PDF 검증 생략")
        cls.pdf = _pdf_text()
        cls.docx = _docx_text()

    # ── 두 포맷 모두 TOP 5 섹션이 없어야 한다 ────────────────────────────
    def test_pdf_has_no_top5_section(self) -> None:
        self.assertNotIn("TOP 5", self.pdf)
        self.assertNotIn("핵심 리스크", self.pdf)

    def test_docx_has_no_top5_section(self) -> None:
        self.assertNotIn("TOP 5", self.docx)

    # ── 상세 내용은 정확히 한 번만 ───────────────────────────────────────
    def test_pdf_detail_appears_exactly_once(self) -> None:
        flat = "".join(self.pdf.split())
        for marker in ALL_MARKERS:
            self.assertEqual(
                flat.count(marker), 1,
                f"{marker!r} 가 {flat.count(marker)}회 — 2회면 TOP 5 중복 부활, 0회면 상세 누락",
            )

    def test_docx_detail_appears_exactly_once(self) -> None:
        flat = "".join(self.docx.split())
        for marker in ALL_MARKERS:
            self.assertEqual(flat.count(marker), 1, f"{marker!r} 가 {flat.count(marker)}회")

    # ── 섹션 번호가 두 포맷에서 같아야 한다 ──────────────────────────────
    def test_high_section_number_matches_across_formats(self) -> None:
        pdf_no = _section_number(self, self.pdf, "필수수정 조항", "PDF")
        docx_no = _section_number(self, self.docx, "필수수정 조항", "DOCX")
        self.assertEqual(pdf_no, docx_no, "필수수정 섹션 번호가 DOCX/PDF 간 다르다")
        # 관련 법률 적용성 섹션이 없는 이 케이스에서는 2번이어야 한다.
        self.assertEqual(pdf_no, "2")

    def test_medium_section_number_matches_across_formats(self) -> None:
        self.assertEqual(
            _section_number(self, self.pdf, "권장수정 조항", "PDF"),
            _section_number(self, self.docx, "권장수정 조항", "DOCX"),
        )

    def test_structure_section_is_first_in_both(self) -> None:
        self.assertIn("1. 계약 구조", self.pdf)
        self.assertIn("1. 계약 구조", self.docx)

    # ── 제거가 과했는지 확인 — 상세 섹션은 살아 있어야 한다 ─────────────
    def test_both_formats_still_render_the_clauses(self) -> None:
        for name, text in (("PDF", self.pdf), ("DOCX", self.docx)):
            flat = "".join(text.split())
            for citation in ("제8조제3항", "제4조제1항", "제11조"):
                self.assertIn(citation, flat, f"{name}: {citation} 누락")


def _section1_body(text: str) -> list[str]:
    """섹션 1 제목 다음부터 다음 번호 섹션 전까지의 본문 행."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    start = next(i for i, l in enumerate(lines) if l.startswith("1. 계약 구조"))
    end = next(i for i, l in enumerate(lines)
               if re.match(r"^\d+\.\s*(관련 법률|필수수정)", l))
    return lines[start + 1:end]


class Section1IdenticalAcrossFormatsTest(unittest.TestCase):
    """섹션 1 은 report_header 가 유일한 소스이므로 두 포맷이 글자까지 같다.

    이전에는 DOCX 에만 핵심 결론·미결 사항·구조 요약 필드·계약유형 한글
    라벨이 있고 제목도 달랐다(2026-09-08 지시: DOCX 기준 통일).
    """

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import fitz  # noqa: F401
        except Exception:  # pragma: no cover
            raise unittest.SkipTest("pymupdf(fitz) 없음")
        cls.pdf_rows = _section1_body(_pdf_text())
        cls.docx_rows = _section1_body(_docx_text())

    def test_title_is_identical(self) -> None:
        self.assertIn("1. 계약 구조 및 검토 결론", _pdf_text())
        self.assertIn("1. 계약 구조 및 검토 결론", _docx_text())

    def test_every_row_is_identical(self) -> None:
        self.assertEqual(self.pdf_rows, self.docx_rows)

    def test_docx_only_fields_now_present_in_pdf(self) -> None:
        flat = "".join(self.pdf_rows)
        for expected in ("핵심 결론:", "미결 사항:", "분석 신뢰도",
                         "고객사(상대방) 양식 여부", "비밀유지기간"):
            self.assertIn(expected.replace(" ", ""), flat.replace(" ", ""),
                          f"PDF 섹션 1 에 {expected} 가 없다")

    def test_contract_type_label_is_human_readable(self) -> None:
        for rows in (self.pdf_rows, self.docx_rows):
            self.assertTrue(
                any("비밀유지계약(NDA)" in r for r in rows),
                "계약유형이 코드로 노출된다",
            )

    def test_role_code_is_not_leaked(self) -> None:
        for rows in (self.pdf_rows, self.docx_rows):
            joined = "".join(rows)
            self.assertNotIn("principal", joined)
            self.assertIn("위탁자", joined)


class LegalApplicabilityShiftsNumberingTest(unittest.TestCase):
    """관련 법률 적용성 섹션이 있으면 두 포맷 모두 HIGH=3 이어야 한다."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import fitz  # noqa: F401
        except Exception:  # pragma: no cover
            raise unittest.SkipTest("pymupdf(fitz) 없음")
        law = [{
            "statute": "부정경쟁방지 및 영업비밀보호에 관한 법률",
            "applicability": "적용 가능",
            "reasoning": "영업비밀 보호 조항이 포함되어 있다",
            "related_clauses": ["제6조"],
        }]
        cls.pdf = _pdf_text(legal_applicability_review=law)
        cls.docx = _docx_text(legal_applicability_review=law)

    def test_high_is_section_3_in_both(self) -> None:
        for name, text in (("PDF", self.pdf), ("DOCX", self.docx)):
            self.assertEqual(
                _section_number(self, text, "필수수정 조항", name), "3",
                f"{name}: 필수수정 섹션 번호가 3이 아니다",
            )

    def test_law_section_is_2_in_both(self) -> None:
        for name, text in (("PDF", self.pdf), ("DOCX", self.docx)):
            self.assertEqual(
                _section_number(self, text, "관련 법률 적용성 검토", name), "2", f"{name}",
            )

    def test_still_no_top5_when_law_section_present(self) -> None:
        self.assertNotIn("TOP 5", self.pdf)
        self.assertNotIn("TOP 5", self.docx)


if __name__ == "__main__":
    unittest.main()
