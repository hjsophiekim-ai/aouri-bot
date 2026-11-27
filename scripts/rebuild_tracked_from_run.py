"""저장된 실행(04_review_deep.json + 원본 입력)으로 변경추적본·클린본·변경 묶음을 다시 만든다 — 엔진 수정 확인용(무과금).

Usage: python scripts/rebuild_tracked_from_run.py RUN_DIR INPUT_FILE OUT_DIR
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime.review.delivery_docs import build_tracked_docs  # noqa: E402
from runtime.review.text_extract import extract_text_from_file  # noqa: E402


def main() -> int:
    run, inp, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    rr = json.loads((run / "04_review_deep.json").read_text(encoding="utf-8"))["review"]
    session = {"text": extract_text_from_file(inp).text, "input": {"filename": inp.name}}
    if inp.suffix.lower() == ".docx":
        session["original_docx_b64"] = base64.b64encode(inp.read_bytes()).decode()
    docs = build_tracked_docs(session, rr)
    (out / "07_redline.docx").write_bytes(docs["redline"])
    (out / "08_clean.docx").write_bytes(docs["clean"])
    rr.setdefault("clause_meta", {})["change_set"] = docs["change_set"]
    rr["clause_meta"]["redline_apply_report"] = docs["report"]
    (out / "04_review_deep.json").write_text(json.dumps({"review": rr}, ensure_ascii=False), encoding="utf-8")
    (out / "report.json").write_text(json.dumps(docs["report"], ensure_ascii=False, indent=1), encoding="utf-8")
    for r in docs["report"]:
        print(r["status"], r["path"], r["reason"][:80], "group", r.get("change_group"), r.get("para_range"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
