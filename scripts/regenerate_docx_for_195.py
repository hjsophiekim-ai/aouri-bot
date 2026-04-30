from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Case:
    input_docx: Path
    output_docx: Path


def _post_json(url: str, payload: dict[str, Any], *, timeout: float = 180.0) -> dict[str, Any]:
    b = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    resp = urlopen(Request(url, data=b, method="POST", headers={"Content-Type": "application/json; charset=utf-8"}), timeout=timeout).read()
    return json.loads(resp.decode("utf-8"))


def _post_multipart(url: str, file_path: Path, *, timeout: float = 180.0) -> dict[str, Any]:
    boundary = "----aouriBoundary7MA4YWxkTrZu0gW"
    fn = file_path.name
    content = file_path.read_bytes()
    body = b""
    body += (f"--{boundary}\r\n").encode("utf-8")
    body += (f'Content-Disposition: form-data; name="file"; filename="{fn}"\r\n').encode("utf-8")
    body += b"Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document\r\n\r\n"
    body += content + b"\r\n"
    body += (f"--{boundary}--\r\n").encode("utf-8")
    req = Request(url, data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Content-Length", str(len(body)))
    resp = urlopen(req, timeout=timeout).read()
    return json.loads(resp.decode("utf-8"))


def _post_bytes(url: str, payload: dict[str, Any], *, timeout: float = 240.0) -> bytes:
    b = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return urlopen(Request(url, data=b, method="POST", headers={"Content-Type": "application/json; charset=utf-8"}), timeout=timeout).read()


def main() -> None:
    base = os.environ.get("AOURIBOT_BASE_URL") or "http://127.0.0.1:8787"
    dls = Path(r"C:\Users\FURSYS\Downloads")
    out_dir = Path(r"C:\Users\FURSYS\Desktop\aouribot\docs\review_output")
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = [
        Case(
            input_docx=dls / "☆ 시디즈 26년 대리점(권역) 계약서 검토(법무팀).docx",
            output_docx=out_dir / "195_aouribot_revision_1_regenerated.docx",
        ),
        Case(
            input_docx=dls / "모션베드 앱개발 용역계약서_20260416.docx",
            output_docx=out_dir / "195_aouribot_revision2_regenerated.docx",
        ),
    ]

    for c in cases:
        if not c.input_docx.exists():
            raise SystemExit(f"not found: {c.input_docx}")
        up = _post_multipart(base.rstrip("/") + "/api/upload", c.input_docx, timeout=240.0)
        session_id = (
            (up.get("question_session_id") if isinstance(up, dict) else None)
            or (up.get("session_id") if isinstance(up, dict) else None)
            or (up.get("id") if isinstance(up, dict) else None)
        )
        if not isinstance(session_id, str) or not session_id:
            raise SystemExit(f"upload failed: {up}")
        _ = _post_json(base.rstrip("/") + f"/api/question_sessions/{session_id}/answers", {"answers": {}}, timeout=120.0)
        _ = _post_json(base.rstrip("/") + f"/api/question_sessions/{session_id}/review", {}, timeout=360.0)
        blob = _post_bytes(base.rstrip("/") + "/api/revision/download_docx", {"session_id": session_id}, timeout=360.0)
        c.output_docx.write_bytes(blob)
        print(json.dumps({"output": str(c.output_docx), "bytes": len(blob)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
