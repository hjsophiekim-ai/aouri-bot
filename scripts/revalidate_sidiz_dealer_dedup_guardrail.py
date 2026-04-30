from __future__ import annotations

import json
import os
import time
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


def _find_clause(crs: list[dict[str, Any]], *, article: str, paragraph: str | None = None) -> dict[str, Any] | None:
    for cr in crs:
        if not isinstance(cr, dict):
            continue
        if str(cr.get("article_number") or "") != str(article):
            continue
        if paragraph is not None and str(cr.get("paragraph_number") or "") != str(paragraph):
            continue
        return cr
    return None


def _contains_ref(obj: Any, needle: str) -> bool:
    if obj is None:
        return False
    if isinstance(obj, str):
        return needle in obj
    if isinstance(obj, dict):
        return any(_contains_ref(v, needle) for v in obj.values())
    if isinstance(obj, list):
        return any(_contains_ref(v, needle) for v in obj)
    return False


def write_report(out_path: Path, *, file_path: Path, review: dict[str, Any], checks: dict[str, Any]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# 202) 시디즈 대리점 계약 dedup/keep_as_is 가드레일 재검증\n")
    lines.append(f"- source: `{file_path}`")
    lines.append(f"- generated_at: `{time.strftime('%Y-%m-%d %H:%M:%S')}`\n")
    lines.append("## 체크 결과\n")
    for k, v in checks.items():
        lines.append(f"- {k}: `{v}`")
    lines.append("\n## 참고(요약)\n")
    meta = review.get("clause_meta") if isinstance(review, dict) else None
    if isinstance(meta, dict):
        lines.append(f"- clause_count: `{meta.get('clause_count')}`")
        lines.append(f"- issue_clause_count: `{meta.get('issue_clause_count')}`")
        ai = meta.get("ai")
        if isinstance(ai, dict):
            lines.append(f"- ai.used: `{ai.get('used')}` / selected_count: `{ai.get('selected_count')}`")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    clause_2_2 = _find_clause(crs, article="2", paragraph="2")
    if clause_2_2 is None:
        cands = [
            x
            for x in crs
            if isinstance(x, dict)
            and any(k in str(x.get("original_text") or "") for k in ("공정거래법", "대리점법", "개인정보보호법"))
            and any(k in str(x.get("clause_title") or "") for k in ("기본", "원칙", "준수", "총칙"))
        ]
        clause_2_2 = cands[0] if cands else None

    checks: dict[str, Any] = {}
    checks["1) 제2조 제2항 keep_as_is"] = bool(isinstance(clause_2_2, dict) and clause_2_2.get("keep_as_is") is True)
    checks["2) 제2조 제2항 rewrite 없음"] = bool(isinstance(clause_2_2, dict) and not (isinstance(clause_2_2.get("suggested_rewrite"), str) and clause_2_2.get("suggested_rewrite").strip()))
    checks["3) 제2조 제2항 dedup 문구 없음"] = bool(
        isinstance(clause_2_2, dict) and not _contains_ref(clause_2_2.get("rewrite_reason"), "동일 취지 중복") and not _contains_ref(clause_2_2.get("rewrite_reason"), "대표 반영")
    )

    dedup_supp = [x for x in crs if isinstance(x, dict) and x.get("dedup_suppressed") is True]
    checks["4) dedup_suppressed 건수"] = len(dedup_supp)
    ok_intra = True
    mismatches: list[dict[str, Any]] = []
    for x in dedup_supp:
        pid = str(x.get("dedup_primary_clause_id") or "")
        primary = next((y for y in crs if isinstance(y, dict) and str(y.get("clause_id") or "") == pid), None)
        if not isinstance(primary, dict):
            ok_intra = False
            mismatches.append({"type": "missing_primary", "clause_id": x.get("clause_id"), "primary": pid})
            break
        if str(primary.get("article_number") or "") != str(x.get("article_number") or ""):
            ok_intra = False
            mismatches.append(
                {
                    "type": "article_mismatch",
                    "clause_id": x.get("clause_id"),
                    "a": x.get("article_number"),
                    "primary": pid,
                    "primary_a": primary.get("article_number"),
                }
            )
            break
    checks["5) dedup은 같은 조문군 내부만"] = ok_intra

    checks["6) rewrite 없는 조항에 dedup 문구 부착 없음"] = all(
        not (
            (not (isinstance(x.get("suggested_rewrite"), str) and x.get("suggested_rewrite").strip()))
            and _contains_ref(x.get("rewrite_reason"), "대표 반영")
        )
        for x in crs
        if isinstance(x, dict)
    )

    checks["7) 난민법 노출 없음"] = not _contains_ref(review, "난민법")

    out = Path(r"C:\Users\FURSYS\Desktop\aouribot\docs\review_output\202_sidiz_dealer_dedup_guardrail_revalidation.md")
    write_report(out, file_path=file_path, review=review, checks=checks | {"debug.mismatches": mismatches[:5]})
    print(json.dumps(checks, ensure_ascii=False, indent=2))
