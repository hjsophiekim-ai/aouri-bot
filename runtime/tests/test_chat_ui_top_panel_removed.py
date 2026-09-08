"""The result-card top summary panel is removed from the UI only.

2026-09-08 지시: 앱 상단의 결론/추천 패널 4개 요소는 화면에서 제거하되,
워드(DOCX)·PDF 리포트 표시는 **그대로 유지**한다. 즉 경계가 두 방향으로
깨질 수 있어서 양쪽을 다 고정한다:

  1. UI 에 4개 요소가 되살아나면 실패
  2. DOCX/PDF 의 0-2·0-3 절이 같이 지워지면 실패

`#phaseNote` 가 analyze 오류 메시지의 유일한 표시 위치였기 때문에
(`analyzeState.lastError` 는 저장만 되고 렌더되지 않음) 오류 문구는
기본 hidden 인 `#analyzeErrorNote` 로 옮겼다 — 정상 화면 모양은 그대로다.
"""
from __future__ import annotations

import re
import unittest

from runtime.admin.internal_demo_chat_ui import INTERNAL_DEMO_CHAT_HTML as CHAT_HTML
from runtime.project_paths import CODE_REPO_ROOT

_REMOVED_IDS = ("conclusionTitle", "conclusionBody", "phaseNote", "recommendedAction")
_KEPT_IDS = ("analyzeErrorNote", "docxStatus", "resultTitle")

_REMOVED_TEXT = (
    "이 유형은 템플릿 기반 초안 작성을 추천해요",
    "대부분 정형 계약으로 보여 템플릿 초안이 빠른 시작점이 될 수 있어요.",
    "대표 추천 액션",
    "정밀 결과가 준비되었어요",
    "위험도가 높아 법무 검토가 필요합니다",
    "이 조항은 수정 제안을 권장합니다",
)

#: '먼저 핵심 결과를 보여드리고...' 는 #phaseNote 에서는 지웠지만
#: #analyzeHint / #resultAnalyzeHint(분석 진행 중 안내)에는 그대로 남는다 —
#: 삭제 대상 4개 요소와 다른 엘리먼트이므로 _REMOVED_TEXT 에 넣지 않는다.
_KEPT_PROGRESS_HINT = "먼저 핵심 결과를 보여드리고"


def _js() -> str:
    return "\n".join(re.findall(r"<script[^>]*>(.*?)</script>", CHAT_HTML, re.S))


def _markup() -> str:
    return re.sub(r"<script[^>]*>.*?</script>", "", CHAT_HTML, flags=re.S)


class ChatUiTopPanelRemovedTest(unittest.TestCase):
    def test_removed_ids_are_absent_from_markup(self) -> None:
        for el_id in _REMOVED_IDS:
            self.assertNotIn(
                f'id="{el_id}"',
                CHAT_HTML,
                f"#{el_id} must stay removed from the result card",
            )

    def test_no_javascript_writes_to_the_removed_elements(self) -> None:
        """A leftover getElementById(...).innerText would throw on null."""
        js = _js()
        for el_id in _REMOVED_IDS:
            self.assertNotIn(
                f"getElementById('{el_id}')",
                js,
                f"JS still looks up #{el_id}, which no longer exists",
            )

    def test_removed_copy_is_gone(self) -> None:
        for text in _REMOVED_TEXT:
            self.assertNotIn(text, CHAT_HTML, f"removed UI copy is back: {text!r}")

    def test_progress_hint_is_untouched(self) -> None:
        """The in-progress hint lives on #analyzeHint and must survive."""
        self.assertIn(_KEPT_PROGRESS_HINT, CHAT_HTML)
        self.assertIn("resultAnalyzeHint", _js())

    def test_kept_elements_survive(self) -> None:
        for el_id in _KEPT_IDS:
            self.assertIn(f'id="{el_id}"', CHAT_HTML, f"#{el_id} must remain")

    def test_error_reporting_still_has_a_home(self) -> None:
        """Deleting #phaseNote must not silently drop analyze error feedback."""
        js = _js()
        self.assertIn("function showAnalyzeError(", js)
        self.assertIn("function clearAnalyzeError(", js)
        self.assertIn("1차 결과 생성 중 오류가 발생했어요", js)
        self.assertIn("정밀 결과 로딩 중 오류가 발생했어요", js)
        # Hidden by default so the normal-state top area shows nothing.
        self.assertIn('id="analyzeErrorNote" hidden', _markup())

    def test_button_styling_logic_survived(self) -> None:
        """The draft/revision branch still styled the buttons; only the label went."""
        js = _js()
        self.assertIn("if (action === 'draft')", js)
        self.assertIn("btnDraft.dataset.templateId", js)
        self.assertIn("btnDraft.disabled", js)

    def test_review_failed_badge_logic_survived(self) -> None:
        js = _js()
        self.assertIn("_reviewFailed", js)
        self.assertIn("badgeDanger", js)


class ReportSectionsUnchangedTest(unittest.TestCase):
    """DOCX/PDF must KEEP what the UI dropped (2026-09-08 정정 지시)."""

    def test_docx_keeps_user_answer_sections(self) -> None:
        src = (CODE_REPO_ROOT / "runtime" / "review" / "legal_review_docx.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("0-2. 사용자 검토항목 답변", src)
        self.assertIn("0-3. 사용자 요청사항 검토 결과", src)

    def test_pdf_keeps_user_answer_sections(self) -> None:
        src = (CODE_REPO_ROOT / "runtime" / "review" / "legal_review_pdf.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("0-2. 사용자 검토항목 답변", src)
        self.assertIn("0-3. 사용자 요청사항 검토 결과", src)


if __name__ == "__main__":
    unittest.main()
