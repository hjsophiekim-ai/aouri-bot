"""데모 화면의 인라인 스크립트가 실제로 파싱되는지 확인한다.

2026-09-14 실측 사고
──────────────────
`internal_demo_chat_ui.py` 의 HTML 은 **일반**(raw 가 아닌) 삼중따옴표
문자열이다. 그래서 소스에 적은 백슬래시-n 을 Python 이 **진짜 줄바꿈**으로
바꿔 HTML 에 내보낸다. 그 줄바꿈이 JS 작은따옴표 문자열 안으로 들어가면
스크립트 **전체**가 SyntaxError 로 죽는다.

그러면 화면은 멀쩡히 뜨는데 버튼이 하나도 동작하지 않는다. 실제 증상은
"계약서 첨부하고 검토 시작을 눌렀는데 페이지가 넘어가질 않는다" 였고, 서버
로그에는 아무것도 남지 않았다(서버는 요청조차 받지 못한다). 파이썬 단위
테스트도 전부 통과한다 — 파이썬 문법으로는 멀쩡한 문자열이기 때문이다.

그래서 문자열을 **파서에 직접 먹여서** 확인한다. 이 클래스의 실패는
"화면의 모든 버튼이 죽었다" 와 같은 뜻이다.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from runtime.admin.internal_demo_chat_ui import INTERNAL_DEMO_CHAT_HTML

_RX_SCRIPT = re.compile(r"<script[^>]*>(.*?)</script>", re.S)


def _inline_scripts() -> str:
    blocks = _RX_SCRIPT.findall(INTERNAL_DEMO_CHAT_HTML)
    return "\n;\n".join(blocks)


class DemoUiScriptSyntaxTest(unittest.TestCase):
    def test_html_has_inline_script(self) -> None:
        js = _inline_scripts()
        self.assertGreater(len(js), 10_000, "인라인 스크립트를 찾지 못했습니다")

    def test_no_raw_newline_inside_single_quoted_string(self) -> None:
        """작은따옴표 문자열이 한 줄 안에서 닫히는지 본다.

        node 가 없는 환경에서도 이 사고 유형만은 잡아내는 가벼운 검사다.
        주석·정규식까지 해석하지 않으므로, 따옴표 **개수**가 홀수인 줄만
        의심한다 — 이번 사고가 정확히 그 형태였다.
        """
        offenders: list[str] = []
        for lineno, line in enumerate(_inline_scripts().splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("//"):
                continue
            # 이스케이프된 따옴표와 큰따옴표 안의 작은따옴표는 세지 않는다.
            scrubbed = line.replace("\\'", "").replace("\\\\", "")
            scrubbed = re.sub(r'"[^"]*"', "", scrubbed)
            scrubbed = re.sub(r"`[^`]*`", "", scrubbed)
            if scrubbed.count("'") % 2 == 1:
                offenders.append(f"{lineno}: {stripped[:90]}")
        self.assertEqual(
            offenders, [],
            "작은따옴표 문자열이 줄 안에서 닫히지 않았습니다 — JS 전체가 죽습니다",
        )

    @unittest.skipUnless(shutil.which("node"), "node 가 없어 파서 검사를 건너뜁니다")
    def test_script_parses(self) -> None:
        js = _inline_scripts()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "demo.js"
            path.write_text(js, encoding="utf-8")
            proc = subprocess.run(  # noqa: S603
                [shutil.which("node") or "node", "--check", str(path)],
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(
            proc.returncode, 0,
            "데모 화면 스크립트가 파싱되지 않습니다 — 모든 버튼이 동작하지 않습니다.\n"
            + (proc.stderr or proc.stdout)[:1500],
        )


if __name__ == "__main__":
    unittest.main()
