from __future__ import annotations

import json
import mimetypes
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

BASE = "http://127.0.0.1:8787"


def _post_json(path: str, payload: dict[str, Any], *, timeout: int = 60) -> tuple[int, dict[str, Any]]:
    req = request.Request(
        BASE + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw.decode("utf-8"))
    except error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw.decode("utf-8"))
        except Exception:
            return exc.code, {"error": raw.decode("utf-8", errors="replace")[:4000]}


def _upload_file(path: str, *, entity: str, contract_type: str, timeout: int = 60) -> tuple[int, dict[str, Any]]:
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
    parts.append(f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'.encode("utf-8"))
    parts.append(f"Content-Type: {ctype}\r\n\r\n".encode("utf-8"))
    parts.append(fp.read_bytes())
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)
    req = request.Request(
        BASE + "/api/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw.decode("utf-8"))
    except error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw.decode("utf-8"))
        except Exception:
            return exc.code, {"error": raw.decode("utf-8", errors="replace")[:4000]}


def _download_docx(session_id: str, *, timeout: int = 60) -> tuple[int, str, bytes]:
    req = request.Request(
        BASE + "/api/revision/download_docx",
        data=json.dumps({"session_id": session_id}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            ct = resp.headers.get("Content-Type") or ""
            data = resp.read()
            return resp.status, ct, data
    except error.HTTPError as exc:
        ct = exc.headers.get("Content-Type") or ""
        data = exc.read()
        return exc.code, ct, data


@dataclass(frozen=True)
class Case:
    name: str
    path: str
    entity: str
    contract_type: str


def _sanitize_preview(text: str, n: int = 200) -> str:
    s = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    return s[:n]


def _write_md(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    out_dir = root / "docs" / "review_output"

    cases = [
        Case("물품공급/구매", "runtime/tests/fixtures/supply_purchase.txt", "퍼시스", "물품공급/구매"),
        Case("용역/자문", "runtime/tests/fixtures/services_consulting.txt", "시디즈", "용역/자문"),
        Case("대리점/유통", "runtime/tests/fixtures/demo_upload.txt", "퍼시스", "대리점/유통"),
        Case("개인정보/DPA", "runtime/tests/fixtures/dpa_privacy.txt", "일룸", "개인정보/DPA"),
        Case("광고/모델계약", "runtime/tests/fixtures/advertising_model.txt", "바로스", "광고/모델계약"),
    ]

    md_131: list[str] = []
    md_131.append("# 131. DOCX 수정본 출력 검증")
    md_131.append("")
    md_131.append("## 검증 항목")
    md_131.append("- /api/upload → 추출 텍스트 존재")
    md_131.append("- /api/revision/suggest(session_id) → clause_results/meta(docx_allowed) 반환")
    md_131.append("- /api/revision/download_docx(session_id) → docx(zip) 바이너리 반환")
    md_131.append("")

    table_rows: list[str] = []

    for c in cases:
        t0 = time.time()
        st_up, up = _upload_file(c.path, entity=c.entity, contract_type=c.contract_type)
        ext = up.get("extraction") if isinstance(up.get("extraction"), dict) else {}
        sid = up.get("question_session_id")
        st_rev, rev = _post_json("/api/revision/suggest", {"session_id": sid})
        meta = rev.get("meta") if isinstance(rev.get("meta"), dict) else {}
        clause_results = rev.get("clause_results") if isinstance(rev.get("clause_results"), list) else []
        st_docx, ct, docx = _download_docx(str(sid))
        dt = time.time() - t0

        ok_zip = (docx[:2] == b"PK")
        sha12 = str(ext.get("text_sha256") or "")[:12]

        table_rows.append(
            "| "
            + " | ".join(
                [
                    c.name,
                    str(st_up),
                    str(ext.get("text_length") or ""),
                    sha12,
                    str(st_rev),
                    str(len(clause_results)),
                    str(meta.get("docx_allowed")),
                    str(st_docx),
                    "OK" if ok_zip else "FAIL",
                    str(len(docx)),
                    f"{dt:.2f}s",
                ]
            )
            + " |"
        )

        md_131.append(f"## {c.name}")
        md_131.append(f"- upload status: {st_up}")
        md_131.append(f"- extraction.text_length: {ext.get('text_length')}")
        md_131.append(f"- extraction.text_sha256(12): {sha12}")
        md_131.append("- extraction.preview(160):")
        md_131.append("")
        md_131.append("```")
        md_131.append(_sanitize_preview(str(ext.get("preview") or ""), 160))
        md_131.append("```")
        md_131.append(f"- revision/suggest status: {st_rev}")
        md_131.append(f"- clause_results: {len(clause_results)}")
        md_131.append(f"- meta.docx_allowed: {meta.get('docx_allowed')}")
        md_131.append(f"- meta.warnings: {meta.get('warnings')}")
        md_131.append(f"- download_docx status: {st_docx}")
        md_131.append(f"- docx Content-Type: {ct}")
        md_131.append(f"- docx zip signature(PK): {ok_zip}")
        md_131.append(f"- docx bytes: {len(docx)}")
        md_131.append("")

    md_133: list[str] = []
    md_133.append("# 133. 5개 계약서 조항별 수정 제안 + DOCX 결과물 검증")
    md_133.append("")
    md_133.append("## 주의")
    md_133.append("- 저장소에 실제 계약서 원본 파일이 포함되어 있지 않아, 검증은 비식별 샘플 텍스트 fixture 5건으로 수행했습니다.")
    md_133.append("- 민감정보 노출 방지를 위해 본문은 160자 미리보기만 기록합니다.")
    md_133.append("")
    md_133.append("## 요약 표")
    md_133.append("| 문서 | upload | text_len | sha(12) | suggest | clauses | docx_allowed | docx | zip | bytes | time |")
    md_133.append("|---|---:|---:|---|---:|---:|---:|---:|---|---:|---:|")
    md_133.extend(table_rows)
    md_133.append("")

    st_up, up = _upload_file("runtime/tests/fixtures/short_summary.txt", entity="퍼시스", contract_type="기타")
    sid = up.get("question_session_id")
    st_docx, ct, raw = _download_docx(str(sid))
    blocked = st_docx >= 400
    md_133.append("## Guardrail 확인(짧은 요약문만 있는 경우)")
    md_133.append(f"- short_summary upload status: {st_up}")
    md_133.append(f"- download_docx status: {st_docx} (blocked={blocked})")
    if ct:
        md_133.append(f"- Content-Type: {ct}")
    if ct.startswith("application/json"):
        try:
            obj = json.loads(raw.decode("utf-8"))
            if isinstance(obj, dict):
                md_133.append(f"- error: {obj.get('error')}")
                meta = obj.get("meta")
                if isinstance(meta, dict):
                    md_133.append(f"- meta.warnings: {meta.get('warnings')}")
        except Exception:
            pass
    md_133.append("")

    _write_md(out_dir / "131_docx_revision_output_validation.md", "\n".join(md_131) + "\n")
    _write_md(out_dir / "133_real_contract_clause_revision_validation.md", "\n".join(md_133) + "\n")


if __name__ == "__main__":
    main()

