from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Case:
    name: str
    input_docx: Path
    out_docx: Path
    dispute_article: str


def _post_json(url: str, payload: dict[str, Any], *, timeout: float = 240.0) -> dict[str, Any]:
    b = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    resp = urlopen(Request(url, data=b, method="POST", headers={"Content-Type": "application/json; charset=utf-8"}), timeout=timeout).read()
    return json.loads(resp.decode("utf-8"))


def _post_multipart(url: str, file_path: Path, *, timeout: float = 240.0) -> dict[str, Any]:
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


def _post_bytes(url: str, payload: dict[str, Any], *, timeout: float = 360.0) -> bytes:
    b = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return urlopen(Request(url, data=b, method="POST", headers={"Content-Type": "application/json; charset=utf-8"}), timeout=timeout).read()


def _find_clause(crs: list[dict[str, Any]], *, article: str) -> dict[str, Any] | None:
    for cr in crs:
        if not isinstance(cr, dict):
            continue
        if str(cr.get("article_number") or "").strip() == str(article).strip():
            return cr
    return None


def _contains_any(hay: Any, needles: list[str]) -> bool:
    s = ""
    if isinstance(hay, str):
        s = hay
    else:
        try:
            s = json.dumps(hay, ensure_ascii=False)
        except Exception:
            s = str(hay)
    return any(n in s for n in needles)


def _count_phrase_in_rewrites(crs: list[dict[str, Any]], phrase: str) -> int:
    c = 0
    for cr in crs:
        if not isinstance(cr, dict):
            continue
        sr = cr.get("suggested_rewrite")
        if isinstance(sr, str) and phrase in sr:
            c += 1
    return c


def main() -> None:
    base = os.environ.get("AOURIBOT_BASE_URL") or "http://127.0.0.1:8787"
    dls = Path(r"C:\Users\FURSYS\Downloads")
    out_dir = Path(r"C:\Users\FURSYS\Desktop\aouribot\docs\review_output")
    out_dir.mkdir(parents=True, exist_ok=True)

    cases = [
        Case(
            name="sidiz_dealer",
            input_docx=dls / "☆ 시디즈 26년 대리점(권역) 계약서 검토(법무팀).docx",
            out_docx=out_dir / "aouribot_revision (5).docx",
            dispute_article="27",
        ),
        Case(
            name="desker_mate_consignment",
            input_docx=dls / "2026년 (주)일룸-데스커_DESKER MATE 위탁거래 계약서_260226 법무팀검토본.docx",
            out_docx=out_dir / "aouribot_revision (6).docx",
            dispute_article="17",
        ),
    ]

    report: list[str] = []
    report.append("# 211) 대리점/위탁거래 계약 정밀 재검증\n")
    report.append(f"- generated_at: `{time.strftime('%Y-%m-%d %H:%M:%S')}`\n")

    for case in cases:
        if not case.input_docx.exists():
            raise SystemExit(f"not found: {case.input_docx}")

        up = _post_multipart(base.rstrip("/") + "/api/upload", case.input_docx, timeout=360.0)
        session_id = (
            (up.get("question_session_id") if isinstance(up, dict) else None)
            or (up.get("session_id") if isinstance(up, dict) else None)
            or (up.get("id") if isinstance(up, dict) else None)
        )
        if not isinstance(session_id, str) or not session_id:
            raise SystemExit(f"upload failed: {up}")

        sess = _post_json(base.rstrip("/") + f"/api/question_sessions/{session_id}/answers", {"answers": {}}, timeout=120.0)
        _ = sess
        sess_doc = _post_json(base.rstrip("/") + f"/api/question_sessions/{session_id}/review_fast", {}, timeout=240.0) if False else None
        try:
            sess_doc = json.loads(urlopen(Request(base.rstrip("/") + f"/api/question_sessions/{session_id}", method="GET"), timeout=120.0).read().decode("utf-8"))
        except Exception:
            sess_doc = None
        questions = (
            (sess_doc.get("questions") if isinstance(sess_doc, dict) else None)
            if isinstance(sess_doc, dict) and isinstance(sess_doc.get("questions"), list)
            else []
        )
        wrap = _post_json(base.rstrip("/") + f"/api/question_sessions/{session_id}/review", {}, timeout=420.0)
        review = wrap.get("review") if isinstance(wrap, dict) and isinstance(wrap.get("review"), dict) else wrap
        crs = review.get("clause_results") if isinstance(review, dict) and isinstance(review.get("clause_results"), list) else []

        juris = None
        derived = review.get("derived_context") if isinstance(review, dict) else None
        if isinstance(derived, dict) and isinstance(derived.get("jurisdiction"), dict):
            juris = derived.get("jurisdiction")

        dispute = _find_clause(crs, article=case.dispute_article)
        dispute_ok = True
        if isinstance(dispute, dict):
            bad_dispute = ["다국가", "해외집행", "foreign", "international", "cross-border", "cross border", "판촉", "광고비", "반품", "판매장려금", "비용전가", "산업안전", "중대재해", "작업중지"]
            dispute_ok = not _contains_any({"sr": dispute.get("suggested_rewrite"), "rr": dispute.get("rewrite_reason")}, bad_dispute)
        else:
            dispute_ok = False

        privacy_ok = True
        for cr in crs:
            if not isinstance(cr, dict):
                continue
            if str(cr.get("clause_topic") or "") != "personal_data":
                continue
            bad_priv = ["산업안전", "중대재해", "작업중지", "보호구"]
            if _contains_any(cr.get("suggested_rewrite"), bad_priv) or _contains_any(cr.get("rewrite_reason"), bad_priv):
                privacy_ok = False
                break

        incident_phrase = "침해사고(보안사고/개인정보 유출)"
        incident_repeat = _count_phrase_in_rewrites(crs, incident_phrase)
        incident_ok = incident_repeat <= 2

        q_count_ok = (3 <= len(questions) <= 5)
        q_dealer_ok = sum(
            1
            for q in questions
            if isinstance(q, dict) and any(str(t).startswith("topic:dealer") for t in (q.get("tags") or []) if isinstance(t, str))
        ) >= 2
        q_irrelevant = any(
            isinstance(q, dict) and _contains_any(" ".join([str(q.get("title") or ""), str(q.get("description") or "")]), ["산업안전", "중대재해", "작업중지", "현장", "시공", "설치", "다국가", "해외집행"])
            for q in questions
        )
        q_ok = q_count_ok and q_dealer_ok and (not q_irrelevant)

        case.out_docx.write_bytes(_post_bytes(base.rstrip("/") + "/api/revision/download_docx", {"session_id": session_id}, timeout=420.0))

        report.append(f"## 케이스: {case.name}\n")
        report.append(f"- input: `{case.input_docx}`")
        report.append(f"- output: `{case.out_docx}`")
        report.append(f"- jurisdiction: `{json.dumps(juris, ensure_ascii=False) if juris is not None else None}`")
        report.append(f"- 분쟁조항(제{case.dispute_article}조) 해외/비용전가 문구 없음: `{dispute_ok}`")
        report.append(f"- 개인정보 조항에 안전/현장 문구 없음: `{privacy_ok}`")
        report.append(f"- 침해사고 문구 과다 반복(<=2): `{incident_ok}` (count={incident_repeat})")
        report.append(f"- 질문 3~5개 & 대리점 중심 & 무관 질문 없음: `{q_ok}` (count={len(questions)})\n")

        out_json = out_dir / f"211_{case.name}_review.json"
        out_json.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")

    out_md = Path(r"C:\Users\FURSYS\Desktop\aouribot\docs\review_output\211_dealer_contract_precision_revalidation.md")
    out_md.write_text("\n".join(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
