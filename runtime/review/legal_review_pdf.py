"""법무팀 검토용 PDF 생성.

legal_review_docx.py와 동일한 이슈 선정 로직(_build_review_issues,
_filter_and_sort_issues)을 그대로 재사용한다. 별도로 필터링 규칙을
다시 구현하면 UI/DOCX/PDF 세 출력이 서로 다른 내용을 보이는 문제가
재발하므로, 반드시 legal_review_docx의 함수를 공유해야 한다.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from runtime.review.legal_review_docx import (
    ReviewIssue,
    _build_review_issues,
    _filter_and_sort_issues,
    _format_val,
)

logger = logging.getLogger(__name__)

COLOR_HIGH = (204, 0, 0)
COLOR_MEDIUM = (194, 108, 14)
COLOR_LOW = (0, 90, 158)
COLOR_DARK = (31, 41, 55)
COLOR_LABEL = (55, 65, 81)
COLOR_MUTED = (120, 120, 120)

_FONT_FAMILY = "AouriKR"

# (regular, bold) TTF candidates, in priority order. malgun.ttf ships with every
# Korean-locale Windows install; NotoSansKR is a fallback for non-Windows hosts
# that happen to have it installed.
_FONT_CANDIDATES: list[tuple[str, str]] = [
    (r"C:\Windows\Fonts\malgun.ttf", r"C:\Windows\Fonts\malgunbd.ttf"),
    (r"C:\Windows\Fonts\NotoSansKR-VF.ttf", r"C:\Windows\Fonts\NotoSansKR-VF.ttf"),
    ("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc", "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc"),
]


def _mc(pdf: FPDF, w: float, h: float, text: str) -> None:
    """multi_cell wrapper that always resets x to the left margin afterward.

    fpdf2's multi_cell defaults to new_x=XPos.RIGHT, which leaves the cursor at
    the right edge of the cell (the page's right margin, for w=0). A following
    multi_cell(0, ...) then computes an ~empty available width and raises
    FPDFException("Not enough horizontal space"). Every call must reset back
    to the left margin.
    """
    pdf.multi_cell(w, h, text or "", new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _ensure_font(pdf: FPDF) -> None:
    for regular, bold in _FONT_CANDIDATES:
        if Path(regular).exists():
            pdf.add_font(_FONT_FAMILY, "", regular)
            pdf.add_font(_FONT_FAMILY, "B", bold if Path(bold).exists() else regular)
            return
    raise RuntimeError(
        "한글을 지원하는 TTF 폰트를 찾을 수 없습니다 (malgun.ttf 등). "
        "PDF 생성을 위해 서버에 한글 폰트 설치가 필요합니다."
    )


def _heading(pdf: FPDF, text: str, *, size: int = 13) -> None:
    pdf.set_font(_FONT_FAMILY, "B", size)
    pdf.set_text_color(*COLOR_DARK)
    pdf.ln(2)
    _mc(pdf, 0, 8, text)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(1)


def _label(pdf: FPDF, text: str) -> None:
    pdf.set_font(_FONT_FAMILY, "B", 10)
    pdf.set_text_color(*COLOR_LABEL)
    _mc(pdf, 0, 6, text)


def _body(pdf: FPDF, text: str, *, size: int = 10) -> None:
    pdf.set_font(_FONT_FAMILY, "", size)
    pdf.set_text_color(0, 0, 0)
    _mc(pdf, 0, 6, text or "")


def _severity_color(sev: str) -> tuple[int, int, int]:
    s = (sev or "").upper()
    if s == "HIGH":
        return COLOR_HIGH
    if s == "MEDIUM":
        return COLOR_MEDIUM
    return COLOR_LOW


def _rule(pdf: FPDF) -> None:
    pdf.ln(2)
    pdf.set_draw_color(210, 210, 210)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)


def _issue_block(pdf: FPDF, issue: ReviewIssue, *, index: int | None = None) -> None:
    color = _severity_color(issue.severity)
    pdf.set_font(_FONT_FAMILY, "B", 11)
    pdf.set_text_color(*color)
    prefix = f"[{issue.severity}] "
    if index is not None:
        prefix += f"{index}. "
    title = f"{prefix}{issue.clause_title or issue.issue_title}"
    if issue.issue_title and issue.issue_title != issue.clause_title:
        title += f" — {issue.issue_title}"
    _mc(pdf, 0, 7, title)

    if issue.approval_required:
        pdf.set_font(_FONT_FAMILY, "B", 9)
        pdf.set_text_color(*COLOR_HIGH)
        _mc(pdf, 0, 5, "내부 법무 승인 필요")

    pdf.set_text_color(0, 0, 0)

    if issue.original_text:
        _label(pdf, "원문")
        _body(pdf, issue.original_text)
    _label(pdf, "문제점")
    _body(pdf, issue.problem)
    if issue.legal_business_reason and issue.legal_business_reason != issue.problem:
        _label(pdf, "법적/실무상 이유")
        _body(pdf, issue.legal_business_reason)
    _label(pdf, "수정문안")
    _body(pdf, issue.proposed_revision)
    if issue.negotiation_position:
        _label(pdf, "협상 포지션")
        _body(pdf, issue.negotiation_position)
    if issue.related_clauses:
        _label(pdf, "함께 수정할 조항")
        _body(pdf, ", ".join(issue.related_clauses))

    _rule(pdf)


def build_legal_review_pdf(
    *,
    entity: str,
    contract_type: str,
    filename: str | None,
    clause_results: list[dict[str, Any]],
    original_clauses: list[dict[str, Any]] | None = None,
    detailed_contract_profile: dict[str, Any] | None = None,
    include_low: bool = False,
    contract_type_code: str = "general",
    is_counterparty_form: bool = True,
) -> bytes:
    """Generate a lawyer-grade contract review PDF.

    Mirrors build_legal_review_docx's section structure and issue selection
    exactly (same _build_review_issues / _filter_and_sort_issues call), so the
    PDF and DOCX downloads always show identical findings.

    Colors: HIGH = RED, MEDIUM = ORANGE, LOW = BLUE (appendix only, when
    include_low=True).
    """
    dp = detailed_contract_profile or {}

    issues_raw = _build_review_issues(
        clause_results,
        contract_type_code=contract_type_code,
        is_counterparty_form=is_counterparty_form,
    )
    filtered = _filter_and_sort_issues(issues_raw, max_medium=10, max_top_risks=5, contract_type_code=contract_type_code)
    top_issues = filtered["top_risks"]
    high_issues = filtered["high"]
    medium_issues = filtered["medium"]
    low_issues = filtered["low"] if include_low else []
    excluded_count = max(0, len(issues_raw) - len(high_issues) - len(medium_issues))

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(18, 18, 18)
    _ensure_font(pdf)
    pdf.add_page()
    pdf.set_font(_FONT_FAMILY, "", 10)

    _heading(pdf, "아우리봇 계약 검토·수정본 (법무팀 검토용)", size=15)
    _body(pdf, "표시 기준: HIGH/필수수정=빨간색 · MEDIUM/권장수정=주황색 · LOW/참고=파란색(기본 숨김)", size=9)

    _heading(pdf, "1. 계약 구조 및 우리 측 포지션")
    party = dp.get("party_role") if isinstance(dp.get("party_role"), dict) else {}
    must_fix_count = sum(1 for i in high_issues if i.approval_required)
    lines = [
        f"계약명: {_format_val(filename)}",
        f"우리 회사: {_format_val(entity)}",
        f"우리 측 지위: {_format_val((party or {}).get('our_role'))}",
        f"상대방: {_format_val((party or {}).get('counterparty_role'))}",
        f"계약유형: {_format_val(contract_type)}",
        f"검토 결과: HIGH {len(high_issues)}건 | MEDIUM {len(medium_issues)}건 | 내부 승인 필요 {must_fix_count}건",
    ]
    _body(pdf, "\n".join(lines))

    _heading(pdf, "2. TOP 5 핵심 리스크")
    if not top_issues:
        _body(pdf, "분석된 핵심 리스크가 없습니다.")
    else:
        for idx, issue in enumerate(top_issues, start=1):
            _issue_block(pdf, issue, index=idx)

    _heading(pdf, "3. 필수수정 조항 — HIGH")
    if not high_issues:
        _body(pdf, "HIGH 조항이 없습니다.")
    else:
        for issue in high_issues:
            _issue_block(pdf, issue)

    _heading(pdf, "4. 권장수정 조항 — MEDIUM")
    if not medium_issues:
        _body(pdf, "권장 수정 조항이 없습니다.")
    else:
        for issue in medium_issues:
            _issue_block(pdf, issue)

    section_num = 5
    if include_low:
        _heading(pdf, f"{section_num}. 참고 조항 — LOW 부록")
        if not low_issues:
            _body(pdf, "참고 조항이 없습니다.")
        else:
            for issue in low_issues:
                _issue_block(pdf, issue)
        section_num += 1

    _heading(pdf, f"{section_num}. 제외된 항목 요약")
    if excluded_count > 0:
        _body(
            pdf,
            f"계약유형과 무관하거나 수정문안이 없는 일반론적 의견 {excluded_count}건은 본문에서 제외하였습니다. "
            "(include_low=True 옵션 사용 시 LOW 항목을 부록으로 확인할 수 있습니다.)",
        )
    else:
        _body(pdf, "제외된 항목: 없음")

    return bytes(pdf.output())
