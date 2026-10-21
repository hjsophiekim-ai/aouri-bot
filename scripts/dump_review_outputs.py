"""e2e 실행 폴더의 DOCX·PDF 출력물을 사람이 읽는 텍스트로 떨궈 둔다.

python-docx 없이 word/document.xml 을 직접 읽는다(서버 인터프리터와 같은 조건).
PDF 는 업로드 추출기(text_extract)로 읽는다 — 사용자가 보는 글자 그대로를 남긴다.

Usage: python scripts/dump_review_outputs.py RUN_DIR
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def docx_text(path: Path) -> str:
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
    out: list[str] = []
    for para in re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S):
        # 삭제 표시(w:delText)는 [-…-], 삽입(w:ins 안 w:t)은 그대로 — Redline 확인용
        text = ""
        for m in re.finditer(r"<w:(t|delText)(?: [^>]*)?>([^<]*)</w:\1>", para):
            text += f"[-{m.group(2)}-]" if m.group(1) == "delText" else m.group(2)
        if text.strip():
            out.append(text)
    return "\n".join(out)


def main() -> None:
    run = Path(sys.argv[1])
    from runtime.review.text_extract import extract_text_from_file

    for f in sorted(run.iterdir()):
        if f.suffix == ".docx":
            (run / (f.stem + ".txt")).write_text(docx_text(f), encoding="utf-8")
        elif f.suffix == ".pdf":
            r = extract_text_from_file(f)
            (run / (f.stem + ".txt")).write_text(getattr(r, "text", None) or str(r), encoding="utf-8")


if __name__ == "__main__":
    main()
