"""e2e 실행 폴더의 다운로드 산출물(05~08)을 판정용 텍스트(05_report.txt …)로 바꾼다.

운영 코드와 같은 추출기(text_extract)를 쓴다 — 사람이 파일을 열어 읽는 내용과 같다.

Usage: python scripts/run_texts.py RUN_DIR [RUN_DIR ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.review.text_extract import extract_text_from_file  # noqa: E402

NAMES = ("05_report.docx", "06_report.pdf", "07_redline.docx", "08_clean.docx", "09_brief.docx", "10_brief.pdf")


def convert(run: Path) -> list[str]:
    done = []
    for name in NAMES:
        src = run / name
        if not src.exists():
            continue
        res = extract_text_from_file(src)
        text = getattr(res, "text", None) or ""
        src.with_suffix(".txt").write_text(text, encoding="utf-8")
        done.append(f"{name}: {len(text)}자")
    return done


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        print(arg, convert(Path(arg)))
