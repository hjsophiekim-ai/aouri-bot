from __future__ import annotations

import json
import os
import uuid
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class RevalidationResult:
    question_session_id: str
    classification: dict
    ai: dict | None
    tier_counts: dict | None
    clause_count: int | None
    issue_clause_count: int | None
    display_path_samples: list[str]
    context_text_count: int
    docx_size: int
    docx_has_strike: bool
    docx_has_guidance: bool
    docx_has_hier_paths: bool
    docx_has_meta_phrase: bool
    docx_has_bad_particle: bool
    docx_red_run_ratio: float
    saved_docx_path: str


def _multipart_upload(*, url: str, file_path: Path, fields: dict[str, str]) -> dict:
    boundary = "----aouribot" + uuid.uuid4().hex
    parts: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        parts.append(f"--{boundary}\r\n".encode("utf-8"))
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        parts.append((value or "").encode("utf-8"))
        parts.append(b"\r\n")

    def add_file(name: str, filename: str, content: bytes, content_type: str) -> None:
        parts.append(f"--{boundary}\r\n".encode("utf-8"))
        parts.append(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8"))
        parts.append(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        parts.append(content)
        parts.append(b"\r\n")

    for k, v in fields.items():
        add_field(k, v)

    data = file_path.read_bytes()
    add_file(
        "file",
        file_path.name,
        data,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)

    resp = urlopen(
        Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
    ).read()
    return json.loads(resp.decode("utf-8"))


def _post_json(url: str, payload: dict) -> dict:
    b = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    resp = urlopen(Request(url, data=b, method="POST", headers={"Content-Type": "application/json; charset=utf-8"})).read()
    return json.loads(resp.decode("utf-8"))


def _post_bytes(url: str, payload: dict) -> bytes:
    b = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return urlopen(Request(url, data=b, method="POST", headers={"Content-Type": "application/json; charset=utf-8"})).read()


def run(*, base_url: str, input_docx: Path, output_docx: Path) -> RevalidationResult:
    up = _multipart_upload(
        url=base_url.rstrip("/") + "/api/upload",
        file_path=input_docx,
        fields={"entity": "일룸/데스커", "contract_type": ""},
    )
    sid = str(up.get("question_session_id") or "")
    if not sid:
        raise RuntimeError(f"upload failed: {up}")

    rev = _post_json(base_url.rstrip("/") + f"/api/question_sessions/{sid}/review", {})
    review = rev.get("review") or {}
    meta = review.get("clause_meta") or {}
    clause_results = review.get("clause_results") or []

    paths = []
    ctx_count = 0
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        dp = cr.get("display_path")
        if isinstance(dp, str) and dp.strip():
            paths.append(dp.strip())
        ct = cr.get("context_text")
        if isinstance(ct, str) and ct.strip():
            ctx_count += 1

    docx = _post_bytes(base_url.rstrip("/") + "/api/revision/download_docx", {"session_id": sid})
    z = zipfile.ZipFile(BytesIO(docx))
    xml = z.read("word/document.xml").decode("utf-8", errors="ignore")

    output_docx.parent.mkdir(parents=True, exist_ok=True)
    output_docx.write_bytes(docx)

    red_runs = xml.count("w:color")
    run_count = xml.count("<w:r")
    ratio = float(red_runs) / float(run_count or 1)

    return RevalidationResult(
        question_session_id=sid,
        classification=up.get("classification") if isinstance(up.get("classification"), dict) else {},
        ai=review.get("ai") if isinstance(review.get("ai"), dict) else None,
        tier_counts=meta.get("tier_counts") if isinstance(meta.get("tier_counts"), dict) else None,
        clause_count=meta.get("clause_count") if isinstance(meta.get("clause_count"), int) else None,
        issue_clause_count=meta.get("issue_clause_count") if isinstance(meta.get("issue_clause_count"), int) else None,
        display_path_samples=paths[:8],
        context_text_count=ctx_count,
        docx_size=len(docx),
        docx_has_strike=("<w:strike" in xml),
        docx_has_guidance=("권장/참고(guidance)" in xml),
        docx_has_hier_paths=("제" in xml and "항" in xml and "호" in xml),
        docx_has_meta_phrase=("구매자 보호 방향" in xml or "buyer_favorable" in xml),
        docx_has_bad_particle=("상대방는" in xml),
        docx_red_run_ratio=ratio,
        saved_docx_path=str(output_docx),
    )


if __name__ == "__main__":
    base = os.environ.get("AOURIBOT_BASE_URL") or "http://127.0.0.1:8787"
    input_path = Path(r"C:\Users\FURSYS\Downloads\모션베드 앱개발 용역계약서_20260416.docx")
    output_path = Path(r"C:\Users\FURSYS\Desktop\aouribot\docs\review_output\aouribot_revision_모션베드_앱개발_20260416.docx")
    r = run(base_url=base, input_docx=input_path, output_docx=output_path)
    print(json.dumps(r.__dict__, ensure_ascii=False, indent=2))

