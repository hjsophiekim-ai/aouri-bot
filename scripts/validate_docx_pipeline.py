from __future__ import annotations

import json
import mimetypes
import uuid
from pathlib import Path
from urllib import request


def _upload_txt(*, path: str, entity: str, contract_type: str) -> dict:
    base = "http://127.0.0.1:8787"
    fp = Path(path)
    boundary = "----aouribot" + uuid.uuid4().hex
    parts: list[bytes] = []
    for k, v in {"entity": entity, "contract_type": contract_type}.items():
        parts.append(f"--{boundary}\r\n".encode("utf-8"))
        parts.append(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode("utf-8"))
        parts.append(v.encode("utf-8"))
        parts.append(b"\r\n")
    fname = fp.name
    ctype = mimetypes.guess_type(fname)[0] or "application/octet-stream"
    parts.append(f"--{boundary}\r\n".encode("utf-8"))
    parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'.encode("utf-8")
    )
    parts.append(f"Content-Type: {ctype}\r\n\r\n".encode("utf-8"))
    parts.append(fp.read_bytes())
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)
    req = request.Request(
        base + "/api/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))


def _post_json(path: str, payload: dict) -> dict:
    base = "http://127.0.0.1:8787"
    req = request.Request(
        base + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))


def _download_docx(session_id: str) -> tuple[str, bytes]:
    base = "http://127.0.0.1:8787"
    req = request.Request(
        base + "/api/revision/download_docx",
        data=json.dumps({"session_id": session_id}).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with request.urlopen(req, timeout=60) as resp:
        ct = resp.headers.get("Content-Type") or ""
        data = resp.read()
    return ct, data


def main() -> None:
    up = _upload_txt(
        path="runtime/tests/fixtures/demo_upload.txt",
        entity="퍼시스",
        contract_type="대리점/위탁/유통",
    )
    sid = up.get("question_session_id")
    print("session_id:", sid)
    ext = up.get("extraction") if isinstance(up.get("extraction"), dict) else {}
    print("extraction_text_length:", ext.get("text_length"))
    print("extraction_text_sha256:", ext.get("text_sha256"))
    print("preview_120:", (ext.get("preview") or "")[:120])

    rev = _post_json("/api/revision/suggest", {"session_id": sid})
    meta = rev.get("meta") if isinstance(rev.get("meta"), dict) else {}
    print("clause_results:", len(rev.get("clause_results") or []))
    print("docx_allowed:", meta.get("docx_allowed"))
    print("warnings:", meta.get("warnings"))

    ct, data = _download_docx(str(sid))
    print("docx_content_type:", ct)
    print("docx_magic:", data[:4].hex())
    print("docx_bytes:", len(data))


if __name__ == "__main__":
    main()

