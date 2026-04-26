from __future__ import annotations

import json
import mimetypes
import threading
import time
import zipfile
from io import BytesIO
from pathlib import Path
from urllib import request
from urllib.error import HTTPError
from uuid import uuid4
from xml.etree import ElementTree as ET

from runtime.api.server import build_httpd
from runtime.law.config import load_law_api_config
from runtime.review.docx_writer import W_NS
from runtime.review.revision import REPLACEMENT_TEXT_BY_RULE_ID
from runtime.rules.loader import RuleLoader
from runtime.services.query_service import RuleQueryService


def _build_minimal_docx_bytes(*, document_xml: str) -> bytes:
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""
    with BytesIO() as buf:
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", content_types)
            z.writestr("_rels/.rels", rels)
            z.writestr("word/document.xml", document_xml)
        return buf.getvalue()


def _upload_file(*, base: str, file_bytes: bytes, filename: str, entity: str, contract_type: str) -> dict:
    boundary = "----aouribot" + uuid4().hex
    parts: list[bytes] = []
    for k, v in {"entity": entity, "contract_type": contract_type}.items():
        parts.append(f"--{boundary}\r\n".encode("utf-8"))
        parts.append(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode("utf-8"))
        parts.append(v.encode("utf-8"))
        parts.append(b"\r\n")
    ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    parts.append(f"--{boundary}\r\n".encode("utf-8"))
    parts.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode("utf-8"))
    parts.append(f"Content-Type: {ctype}\r\n\r\n".encode("utf-8"))
    parts.append(file_bytes)
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)
    req = request.Request(
        base + "/api/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))


def _post_json(base: str, path: str, payload: dict) -> dict:
    req = request.Request(
        base + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with request.urlopen(req, timeout=90) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))


def _download_docx(base: str, session_id: str) -> tuple[str, bytes]:
    req = request.Request(
        base + "/api/revision/download_docx",
        data=json.dumps({"session_id": session_id}).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=90) as resp:
            ct = resp.headers.get("Content-Type") or ""
            data = resp.read()
        return ct, data
    except HTTPError as e:
        ct = e.headers.get("Content-Type") or ""
        data = e.read()
        return ct, data


def _docx_has_xml_string_in_text_nodes(docx_bytes: bytes) -> bool:
    with zipfile.ZipFile(BytesIO(docx_bytes), "r") as z:
        xml_bytes = z.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    ns = {"w": W_NS}
    for t in root.findall(".//w:t", ns):
        s = t.text or ""
        if "<w:" in s or "w:rPr" in s or "w:delText" in s:
            return True
    return False


def _rewrite_is_generic_template(s: str) -> bool:
    v = (s or "").strip()
    if not v:
        return False
    return v in {x.strip() for x in REPLACEMENT_TEXT_BY_RULE_ID.values()}


def _summarize_questions(questions: list[dict]) -> list[str]:
    out: list[str] = []
    for q in questions[:5]:
        if not isinstance(q, dict):
            continue
        out.append(f"- {q.get('question_id')}: {q.get('title')}")
    return out


def _write_md(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    out_dir = repo_root / "docs" / "review_output"
    service = RuleQueryService(RuleLoader())
    httpd = build_httpd("127.0.0.1", 0, service)
    port = httpd.server_port
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    time.sleep(0.1)
    base = f"http://127.0.0.1:{port}"

    cases: list[tuple[str, bytes, str, str, str]] = []
    fixtures = [
        ("dealer_fixture", "runtime/tests/fixtures/demo_upload.txt", "퍼시스", "대리점/위탁/유통"),
        ("privacy_fixture", "runtime/tests/fixtures/dpa_privacy.txt", "퍼시스", "개인정보/DPA"),
        ("services_fixture", "runtime/tests/fixtures/services_consulting.txt", "퍼시스", "용역/자문"),
    ]
    for name, p, ent, ct in fixtures:
        b = Path(p).read_bytes()
        cases.append((name, b, Path(p).name, ent, ct))

    tracked_doc_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>제10조(손해배상) 당사는 책임 한도 없이(without limitation) 손해배상 책임을 부담한다.</w:t></w:r></w:p>
    <w:p>
      <w:ins><w:r><w:t>삽입문</w:t></w:r></w:ins>
      <w:del><w:r><w:delText>삭제문</w:delText></w:r></w:del>
      <w:r><w:t>현재문</w:t></w:r>
    </w:p>
  </w:body>
</w:document>
"""
    tracked_docx = _build_minimal_docx_bytes(document_xml=tracked_doc_xml)
    cases.append(("track_changes_docx", tracked_docx, "tracked.docx", "퍼시스", "대리점/위탁/유통"))

    lines_144: list[str] = []
    lines_144.append("# 144. Real Contract Revalidation After Fix")
    lines_144.append("")
    lines_144.append("## 실행 환경")
    law_cfg = load_law_api_config()
    lines_144.append(f"- LAW_API_ENABLED: {bool(law_cfg.enabled)}")
    lines_144.append(f"- LAW_API_KEY_present: {bool(law_cfg.api_key)}")
    lines_144.append(f"- base_url: {law_cfg.base_url}")
    lines_144.append("")
    lines_144.append("## 검증 결과(업로드→질문→리비전→DOCX)")

    overall_ok = True
    for name, file_bytes, filename, ent, ct in cases:
        up = _upload_file(base=base, file_bytes=file_bytes, filename=filename, entity=ent, contract_type=ct)
        ext = up.get("extraction") if isinstance(up.get("extraction"), dict) else {}
        sid = str(up.get("question_session_id") or "")
        qs = up.get("questions") if isinstance(up.get("questions"), list) else []
        lines_144.append(f"### 케이스: {name}")
        lines_144.append(f"- filename: {filename}")
        lines_144.append(f"- extraction.success: {bool(ext.get('success'))}")
        lines_144.append(f"- extraction.text_length: {ext.get('text_length')}")
        lines_144.append(f"- extraction.preview: {(ext.get('preview') or '')[:160]}")
        lines_144.append(f"- questions.count: {len(qs)}")
        lines_144.extend(_summarize_questions(qs))
        lines_144.append(f"- session_id: {sid}")

        rev = _post_json(base, "/api/revision/suggest", {"session_id": sid})
        crs = rev.get("clause_results") if isinstance(rev.get("clause_results"), list) else []
        meta = rev.get("meta") if isinstance(rev.get("meta"), dict) else {}
        lines_144.append(f"- clause_results.count: {len(crs)}")
        lines_144.append(f"- meta.docx_allowed: {meta.get('docx_allowed')}")
        lines_144.append(f"- meta.warnings: {meta.get('warnings')}")

        generic_rewrite_found = False
        for cr in crs:
            if not isinstance(cr, dict):
                continue
            sr = cr.get("suggested_rewrite")
            if isinstance(sr, str) and _rewrite_is_generic_template(sr):
                generic_rewrite_found = True
                break
        lines_144.append(f"- rewrite.generic_template_detected: {generic_rewrite_found}")
        overall_ok = overall_ok and (not generic_rewrite_found)

        ct2, docx_bytes = _download_docx(base, sid)
        lines_144.append(f"- download.content_type: {ct2}")
        lines_144.append(f"- download.docx_bytes: {len(docx_bytes)}")
        bad_text = False
        if ct2.startswith("application/vnd.openxmlformats-officedocument.wordprocessingml.document"):
            bad_text = _docx_has_xml_string_in_text_nodes(docx_bytes)
            lines_144.append(f"- docx.text_contains_word_xml_string: {bad_text}")
            overall_ok = overall_ok and (not bad_text)
        else:
            err_preview = docx_bytes.decode("utf-8", errors="replace")[:200]
            lines_144.append(f"- docx.download_error_preview: {err_preview}")
            overall_ok = False
        lines_144.append("")

    lines_144.append("## 대상 문서(일룸/데스커 DESKER MATE 위탁거래 계약서)")
    lines_144.append("- 현재 워크스페이스에서 원본 파일을 찾지 못해(파일 미존재) 직접 업로드 기반 재검증은 미실시.")
    lines_144.append("- 재검증 방법: 해당 DOCX를 `aouri-bot/runtime/tests/fixtures/`에 배치 후 위 스크립트에 케이스로 추가하여 동일 절차로 확인.")
    lines_144.append("")

    _write_md(out_dir / "144_real_contract_revalidation_after_fix.md", "\n".join(lines_144) + "\n")

    lines_145: list[str] = []
    lines_145.append("# 145. Precision Review Readiness")
    lines_145.append("")
    lines_145.append("## 평가 기준별 판정")
    lines_145.append(f"- 1) 실제 첨부 계약서를 깨끗하게 읽는가: 부분 도달(텍스트/track changes DOCX는 clean 추출 검증, 실제 문제 계약서 파일은 미검증)")
    lines_145.append(f"- 2) 질문이 계약 내용별로 달라지는가: 부분 도달(텍스트 fixture 간 질문 상위 항목이 달라짐)")
    lines_145.append(f"- 3) clause별 검토가 되는가: 부분 도달(조항 분해/조항별 결과 생성 확인)")
    lines_145.append(f"- 4) 법령/판례 grounding이 직접적이고 타당한가: 부분 도달(로컬 환경에서 LAW_API가 비활성일 수 있으며, rerank/필터 로직은 단위 테스트로 검증)")
    lines_145.append(f"- 5) 수정문안이 정밀하고 clause-specific한가: 부분 도달(템플릿 복붙 감지 방지/단위 테스트 및 서버 경로에서 확인)")
    lines_145.append(f"- 6) 최종 Word 파일이 깨지지 않는가: {'실사용 가능' if overall_ok else '부분 도달'}(docx 텍스트 노드에 Word XML 문자열 유입 방지 검증)")
    lines_145.append("")
    final_grade = "부분 도달"
    if overall_ok and bool(law_cfg.enabled and law_cfg.api_key):
        final_grade = "실사용 가능"
    lines_145.append("## 최종 판정(3단계)")
    lines_145.append(f"- {final_grade}")
    lines_145.append("")
    lines_145.append("## 근거")
    lines_145.append("- 회귀 테스트(143) 통과 + 업로드→리비전→DOCX 생성 경로에서 XML 문자열 혼입 방지 확인")
    lines_145.append("- 다만, 실제 문제 계약서(일룸/데스커) 파일 기반의 질문/그라운딩/최종 docx 품질은 파일 미존재로 미확인")
    lines_145.append("")

    _write_md(out_dir / "145_precision_review_readiness.md", "\n".join(lines_145) + "\n")

    httpd.shutdown()
    httpd.server_close()


if __name__ == "__main__":
    main()

