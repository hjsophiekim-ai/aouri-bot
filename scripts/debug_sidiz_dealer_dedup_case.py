from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


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


def _find_clause(crs: list[dict[str, Any]], *, clause_id: str | None = None, article: str | None = None, paragraph: str | None = None) -> dict[str, Any] | None:
    for cr in crs:
        if not isinstance(cr, dict):
            continue
        if clause_id is not None and str(cr.get("clause_id") or "") != clause_id:
            continue
        if article is not None and str(cr.get("article_number") or "") != str(article):
            continue
        if paragraph is not None and str(cr.get("paragraph_number") or "") != str(paragraph):
            continue
        return cr
    return None


def _brief(cr: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(cr, dict):
        return None
    return {
        "clause_id": cr.get("clause_id"),
        "display_path": cr.get("display_path"),
        "article_number": cr.get("article_number"),
        "paragraph_number": cr.get("paragraph_number"),
        "clause_title": cr.get("clause_title"),
        "keep_as_is": cr.get("keep_as_is"),
        "must_fix": cr.get("must_fix"),
        "risk_tier": cr.get("risk_tier"),
        "dedup_suppressed": cr.get("dedup_suppressed"),
        "dedup_primary_clause_id": cr.get("dedup_primary_clause_id"),
        "rewrite_reason": cr.get("rewrite_reason"),
        "suggested_rewrite_preview": (cr.get("suggested_rewrite")[:200] if isinstance(cr.get("suggested_rewrite"), str) else None),
        "original_text_preview": (cr.get("original_text")[:200] if isinstance(cr.get("original_text"), str) else None),
    }


if __name__ == "__main__":
    base = os.environ.get("AOURIBOT_BASE_URL") or "http://127.0.0.1:8787"
    default = Path(r"C:\Users\FURSYS\Downloads\☆ 시디즈 26년 대리점(권역) 계약서 검토(법무팀).docx")
    file_path = Path(os.environ.get("SIDIZ_DEALER_DOCX") or str(default))
    if not file_path.exists():
        raise SystemExit(f"not found: {file_path}")

    up = _post_multipart(base.rstrip("/") + "/api/upload", file_path)
    session_id = (
        (up.get("session_id") if isinstance(up, dict) else None)
        or (up.get("question_session_id") if isinstance(up, dict) else None)
        or (up.get("id") if isinstance(up, dict) else None)
    )
    if not isinstance(session_id, str) or not session_id:
        raise SystemExit(f"upload failed: {up}")

    _ = _post_json(base.rstrip("/") + f"/api/question_sessions/{session_id}/answers", {"answers": {}}, timeout=120.0)
    wrap = _post_json(base.rstrip("/") + f"/api/question_sessions/{session_id}/review", {}, timeout=240.0)
    review = wrap.get("review") if isinstance(wrap, dict) and isinstance(wrap.get("review"), dict) else wrap
    crs = review.get("clause_results") if isinstance(review, dict) and isinstance(review.get("clause_results"), list) else []

    c22 = _find_clause(crs, article="2", paragraph="2")
    mism: list[dict[str, Any]] = []
    for x in crs:
        if not (isinstance(x, dict) and x.get("dedup_suppressed") is True):
            continue
        pid = str(x.get("dedup_primary_clause_id") or "")
        primary = _find_clause(crs, clause_id=pid)
        if str(primary.get("article_number") or "") != str(x.get("article_number") or ""):
            mism.append({"secondary": _brief(x), "primary": _brief(primary)})
            break

    out = {"clause_2_2": _brief(c22), "first_article_mismatch": (mism[0] if mism else None)}
    print(json.dumps(out, ensure_ascii=False, indent=2))

