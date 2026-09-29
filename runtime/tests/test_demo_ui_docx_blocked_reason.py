"""'최종 수정본 다운로드' 버튼이 꺼질 때 이유를 알려 주는가 (2026-09-29).

실사례: 계약서 파일 없이 "계약 내용 입력" 칸에 95자 설명문만 넣고 검토했다.
서버는 원문 조항이 없어 `docx_allowed=false` 를 정확히 돌려줬지만, 화면은
1분 넘게 검토한 뒤 버튼만 조용히 껐다 — 사용자는 고장으로 봤다.

게이트는 옳다(원문 없이 수정본을 만들 수 없다). 고친 것은 안내다.
  1. 검토 시작 전에 요약·설명문으로 보이면 먼저 알린다(한 번 더 누르면 진행).
  2. 버튼이 꺼지면 이유(본문 글자 수·조항 수·해결 방법)를 버튼 아래에 적는다.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from runtime.admin.internal_demo_chat_ui import INTERNAL_DEMO_CHAT_HTML as HTML

SUMMARY_95 = (
    "시디즈(알로소)가 한글날 100주년 기념 프로젝트에 참여하기 위하여 상품을 개발하기 위한 "
    "제품개발 협업계약서. 3자간 계약서이므로 여러가지 법률적 쟁점이 발생할 수 있음."
)


class DocxBlockedReasonWiringTest(unittest.TestCase):
    def test_start_review_warns_before_running(self) -> None:
        body = HTML[HTML.index("async function startReview"):]
        body = body[: body.index("// 2. 상태 초기화")]
        self.assertIn("_looksLikeSummaryNotContract(text)", body)

    def test_disabled_button_shows_the_reason_next_to_it(self) -> None:
        self.assertIn("_cn.innerText = _docxBlockedReason(meta)", HTML)
        self.assertNotIn("'수정본: 생성 불가 (계약서 본문/조항 부족)'", HTML)


@unittest.skipUnless(shutil.which("node"), "node 가 없으면 JS 동작 확인을 건너뛴다")
class DocxBlockedReasonBehaviorTest(unittest.TestCase):
    def _run(self, tail: str) -> list[str]:
        start = HTML.index("function _docxBlockedReason")
        end = HTML.index("let _summaryWarnedText")
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
            fh.write(HTML[start:end] + tail)
            path = Path(fh.name)
        try:
            out = subprocess.run(["node", str(path)], capture_output=True, check=True)
            return out.stdout.decode("utf-8").splitlines()
        finally:
            path.unlink(missing_ok=True)

    def test_summary_vs_contract(self) -> None:
        lines = self._run(
            "const c=[%r, '제1조 (목적) '+'x'.repeat(200), 'Article 1. '+'y'.repeat(200), '가'.repeat(700)];"
            "for (const t of c) console.log(String(_looksLikeSummaryNotContract(t)));" % SUMMARY_95
        )
        self.assertEqual(lines, ["true", "false", "false", "false"])

    def test_reason_names_the_numbers_and_the_fix(self) -> None:
        (line,) = self._run(
            "console.log(_docxBlockedReason({text_length:95, clause_count:1, warnings:[]}));"
        )
        self.assertIn("95자", line)
        self.assertIn("조항 1개", line)
        self.assertIn("계약서 파일을 첨부", line)


if __name__ == "__main__":
    unittest.main()
