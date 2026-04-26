from __future__ import annotations

import json
import mimetypes
import uuid
from pathlib import Path
from urllib import request


def _multipart_body(fields: dict[str, str], *, file_field: str, filename: str, content: bytes) -> tuple[bytes, str]:
    boundary = "----aouribot" + uuid.uuid4().hex
    parts: list[bytes] = []
    for k, v in fields.items():
        parts.append(f"--{boundary}\r\n".encode("utf-8"))
        parts.append(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode("utf-8"))
        parts.append((v or "").encode("utf-8"))
        parts.append(b"\r\n")
    ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    parts.append(f"--{boundary}\r\n".encode("utf-8"))
    parts.append(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode("utf-8")
    )
    parts.append(f"Content-Type: {ctype}\r\n\r\n".encode("utf-8"))
    parts.append(content)
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), boundary


def main() -> None:
    url = "http://127.0.0.1:8787/api/upload"
    fp = Path("runtime/tests/fixtures/demo_upload.txt")
    body, boundary = _multipart_body(
        {"entity": "퍼시스", "contract_type": "대리점/위탁/유통"},
        file_field="file",
        filename=fp.name,
        content=fp.read_bytes(),
    )
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with request.urlopen(req, timeout=10) as resp:
        raw = resp.read()
    obj = json.loads(raw.decode("utf-8"))
    print("status=ok")
    print("question_session_id=", obj.get("question_session_id"))
    extraction = obj.get("extraction") if isinstance(obj.get("extraction"), dict) else {}
    print("extraction_method=", extraction.get("method"))
    print("extraction_text_length=", extraction.get("text_length"))
    print("extraction_text_sha256=", extraction.get("text_sha256"))
    preview = extraction.get("preview")
    if isinstance(preview, str):
        print("preview_200=", preview[:200])


if __name__ == "__main__":
    main()
