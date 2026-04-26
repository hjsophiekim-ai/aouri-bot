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
from runtime.rules.loader import RuleLoader
from runtime.services.query_service import RuleQueryService


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
    with request.urlopen(req, timeout=90) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))


def _post_json(base: str, path: str, payload: dict) -> dict:
    req = request.Request(
        base + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with request.urlopen(req, timeout=120) as resp:
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
        with request.urlopen(req, timeout=120) as resp:
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

    lg_fixture = repo_root / "runtime" / "tests" / "fixtures" / "lg_purchase_installation.txt"
    cases: list[tuple[str, Path]] = [("lg_fixture", lg_fixture)]
    lg_real = repo_root / "runtime" / "tests" / "fixtures" / "lg_purchase_installation_real.docx"
    if lg_real.exists():
        cases.append(("lg_real_docx", lg_real))

    law_cfg = load_law_api_config()

    lines_153: list[str] = []
    lines_153.append("# 153. LG Purchase/Installation Revalidation")
    lines_153.append("")
    lines_153.append("## 실행 환경")
    lines_153.append(f"- LAW_API_ENABLED: {bool(law_cfg.enabled)}")
    lines_153.append(f"- LAW_API_KEY_present: {bool(law_cfg.api_key)}")
    lines_153.append(f"- base_url: {law_cfg.base_url}")
    lines_153.append("")

    overall_ok = True
    for name, path in cases:
        b = path.read_bytes()
        up = _upload_file(
            base=base,
            file_bytes=b,
            filename=path.name,
            entity="퍼시스",
            contract_type="장비공급/설치/시운전",
        )
        sid = str(up.get("question_session_id") or "")
        ext = up.get("extraction") if isinstance(up.get("extraction"), dict) else {}
        qs = up.get("questions") if isinstance(up.get("questions"), list) else []
        lines_153.append(f"## 케이스: {name}")
        lines_153.append(f"- filename: {path.name}")
        lines_153.append(f"- extraction.success: {bool(ext.get('success'))}")
        lines_153.append(f"- extraction.text_length: {ext.get('text_length')}")
        lines_153.append(f"- questions.count: {len(qs)}")
        for q in qs[:5]:
            if isinstance(q, dict):
                lines_153.append(f"  - {q.get('question_id')}: {q.get('title')}")

        rev = _post_json(base, "/api/revision/suggest", {"session_id": sid})
        meta = rev.get("meta") if isinstance(rev.get("meta"), dict) else {}
        crs = rev.get("clause_results") if isinstance(rev.get("clause_results"), list) else []
        lines_153.append(f"- review_posture: {meta.get('review_posture')}")
        lines_153.append(f"- clause_results.count: {len(crs)}")
        lines_153.append(f"- docx_allowed: {meta.get('docx_allowed')}")
        lines_153.append(f"- warnings: {meta.get('warnings')}")
        overall_ok = overall_ok and (meta.get("review_posture") == "buyer_favorable")

        ct, docx_bytes = _download_docx(base, sid)
        lines_153.append(f"- download.content_type: {ct}")
        lines_153.append(f"- download.bytes: {len(docx_bytes)}")
        if ct.startswith("application/vnd.openxmlformats-officedocument.wordprocessingml.document"):
            has_xml = _docx_has_xml_string_in_text_nodes(docx_bytes)
            lines_153.append(f"- docx.text_contains_word_xml_string: {has_xml}")
            overall_ok = overall_ok and (not has_xml)
        else:
            preview = docx_bytes.decode("utf-8", errors="replace")[:240]
            lines_153.append(f"- docx.download_error_preview: {preview}")
            overall_ok = False
        lines_153.append("")

    lines_153.append("## 실파일(LG 계약서) 적용 방법")
    lines_153.append("- `runtime/tests/fixtures/lg_purchase_installation_real.docx`로 저장 후 이 스크립트를 재실행하면 동일 검증을 수행한다.")
    _write_md(out_dir / "153_lg_purchase_installation_revalidation.md", "\n".join(lines_153) + "\n")

    lines_154: list[str] = []
    lines_154.append("# 154. Why LG Review Was Not Good Enough")
    lines_154.append("")
    lines_154.append("## 관찰된 구조적 원인(현재 코드 기준)")
    lines_154.append("- 1) party orientation 실패: 계약서에서 구매자/공급자 역할을 정확히 분해하는 레이어가 없고, posture는 계약유형/키워드 기반 heuristic이다.")
    lines_154.append("- 2) clause identity mismatch: clause_id/제목은 텍스트 패턴 기반이라, 원본 문서 스타일/번호 체계가 복잡하면 매핑이 흔들릴 수 있다(불일치 시 docx 생성 실패로 방어).")
    lines_154.append("- 3) law grounding mismatch: entity 우선 토픽에 의해 무관 법령이 섞일 수 있었고, 컨텍스트 기반 필터/리랭크를 추가했으나 issue-type 템플릿 기반 좁은 검색은 추가 개선 여지가 있다.")
    lines_154.append("- 4) rewrite genericity: 템플릿 복붙을 제거하고 조항 기반 패치로 전환했지만, 실제 법무 품질은 더 많은 rule_id별 패치/역할(구매자/공급자) 인식이 필요하다.")
    lines_154.append("- 5) redline granularity 실패: 줄 단위 강조에서 토큰 diff 기반 run 생성으로 개선했지만, 문장/항목 단위 구조를 더 정교히 보존할 필요가 있다.")
    lines_154.append("- 6) docx readability 문제: clean copy 반복을 제거하고(변경 조항만) 표지/요약/부록/표 구조로 재구성했으나, 상대방/계약명 등 메타데이터 입력 수집을 더 강화해야 한다.")
    _write_md(out_dir / "154_why_lg_review_was_not_good_enough.md", "\n".join(lines_154) + "\n")

    lines_155: list[str] = []
    lines_155.append("# 155. Buyer-favorable Review Readiness")
    lines_155.append("")
    lines_155.append("## 평가 기준")
    lines_155.append("- 1) 당사 보호 방향으로 검토하는가: 부분 도달(heuristic posture + 일부 룰 패치)")
    lines_155.append("- 2) 계약유형별로 질문이 달라지는가: 부분 도달(계약 텍스트/조항 기반 상위 3~5개)")
    lines_155.append("- 3) 조항 매핑이 정확한가: 부분 도달(불일치 시 docx 생성 실패로 방어)")
    lines_155.append("- 4) 적용 법령이 계약유형과 맞는가: 부분 도달(컨텍스트 기반 필터/리랭크, 대리점법 우선 토픽 조건부 제거)")
    lines_155.append("- 5) 수정문안이 clause-specific하고 실무적으로 타당한가: 부분 도달(템플릿 복붙 제거 + 패치 기반)")
    lines_155.append("- 6) Word redline이 실제 법무 검토용으로 쓸 만한가: 부분 도달(변경 조항만 출력 + 변경 부분만 색/취소선)")
    lines_155.append("")
    grade = "부분 도달" if overall_ok else "미도달"
    lines_155.append("## 최종 판정(3단계)")
    lines_155.append(f"- {grade}")
    lines_155.append("")
    lines_155.append("## 근거")
    lines_155.append("- LG fixture 및(선택) 실파일 업로드 기반 재검증 결과를 153 문서로 기록")
    _write_md(out_dir / "155_buyer_favorable_review_readiness.md", "\n".join(lines_155) + "\n")

    httpd.shutdown()
    httpd.server_close()


if __name__ == "__main__":
    main()

