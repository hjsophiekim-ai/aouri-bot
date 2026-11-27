"""이미 검토한 세션의 다운로드 파일(05~10)을 다시 받는다 — 검토(AI)를 다시 돌리지 않고 같은 검토 결과에서 생성.

Usage: python scripts/redownload_session.py RUN_DIR [--base-url http://127.0.0.1:8787]

RUN_DIR/session.json 또는 00_run_log.json 의 session_id 를 쓴다. 받은 파일은 RUN_DIR 에 덮어쓰고 텍스트로 풀어 둔다(run_texts).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def _sid(run: Path) -> str:
    for name in ("00_run_log.json", "session.json", "01_upload.json"):
        p = run / name
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            for k in ("session_id", "sid"):
                if d.get(k):
                    return str(d[k])
            if isinstance(d.get("session"), dict) and d["session"].get("session_id"):
                return str(d["session"]["session_id"])
    raise SystemExit("session_id 를 찾지 못함")


def main() -> int:
    run = Path(sys.argv[1])
    base = sys.argv[sys.argv.index("--base-url") + 1] if "--base-url" in sys.argv else "http://127.0.0.1:8787"
    sid = _sid(run)
    downloads = {
        "05_report.docx": ("/api/revision/download_docx", {"session_id": sid}),
        "06_report.pdf": ("/api/revision/download_pdf", {"session_id": sid}),
        "07_redline.docx": ("/api/revision/download_redline", {"session_id": sid}),
        "08_clean.docx": ("/api/revision/download_clean", {"session_id": sid}),
        "09_brief.docx": ("/api/revision/download_docx", {"session_id": sid, "view": "brief"}),
        "10_brief.pdf": ("/api/revision/download_pdf", {"session_id": sid, "view": "brief"}),
    }
    for name, (ep, payload) in downloads.items():
        req = Request(base + ep, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=600) as resp:  # noqa: S310 - 로컬 서버
                body = resp.read()
        except HTTPError as exc:
            print(f"{name}: HTTP {exc.code}")
            continue
        (run / name).write_bytes(body)
        print(f"{name}: {len(body)} bytes")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "run_texts.py"), str(run)], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
