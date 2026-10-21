"""운영 경로 e2e: 업로드 → 사전질문 → 답변 → 검토(fast+deep) → 다운로드(DOCX/PDF/Redline/Clean).

데모 화면(internal_demo_chat_ui)이 호출하는 순서를 그대로 HTTP 로 따라간다.
내부 함수가 아니라 실행 중인 서버를 친다 — 서버가 어떤 코드로 떠 있는지는
/health 와 serve.py --status 로 따로 남긴다.

Usage:
    python scripts/e2e_upload_review_download.py --input X.pdf --out-dir DIR \
        [--entity 퍼시스] [--review-focus "..."] [--answers answers.json]

--answers 가 없으면 각 질문의 첫 번째 선택지(없으면 "확인 필요")로 답한다.
AI 질문 ID 는 실행마다 바뀌므로 --answers 의 키는 정확한 ID 외에 "*접미어"
(예: "*ip-scope") 로도 쓸 수 있고, "__default__" 는 나머지 질문의 답이 된다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def _multipart(url: str, file_path: Path, fields: dict[str, str]) -> dict:
    boundary = "----aouribot" + uuid.uuid4().hex
    parts: list[bytes] = []
    for k, v in fields.items():
        if v is None:
            continue
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n".encode())
        parts.append(str(v).encode("utf-8") + b"\r\n")
    ctype = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{file_path.name}\"\r\n"
        f"Content-Type: {ctype}\r\n\r\n".encode("utf-8")
    )
    parts.append(file_path.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = Request(url, data=b"".join(parts), method="POST",
                  headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    return json.loads(urlopen(req, timeout=900).read().decode("utf-8"))


def _post(url: str, payload: dict | None, *, raw: bool = False):
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=data, method="POST", headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        body = urlopen(req, timeout=1800).read()
    except HTTPError as exc:
        return {"_http_error": exc.code, "_body": exc.read().decode("utf-8", "replace")[:4000]}
    return body if raw else json.loads(body.decode("utf-8"))


def _default_answers(questions: list[dict]) -> dict:
    out: dict[str, str] = {}
    for q in questions:
        if not isinstance(q, dict):
            continue
        qid = str(q.get("id") or q.get("question_id") or q.get("key") or "")
        if not qid:
            continue
        opts = q.get("options") or q.get("choices") or []
        first = opts[0] if opts else None
        if isinstance(first, dict):
            first = first.get("value") or first.get("label")
        out[qid] = str(first) if first else "확인 필요"
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--base-url", default="http://127.0.0.1:8787")
    ap.add_argument("--entity", default="")
    ap.add_argument("--contract-type", default="")
    ap.add_argument("--review-focus", default="")
    ap.add_argument("--answers", default="")
    args = ap.parse_args()

    src = Path(args.input)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    base = args.base_url.rstrip("/")
    log: dict = {
        "review_focus": args.review_focus,
        "answers_spec": args.answers,
        "input": str(src),
        "input_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "health": json.loads(urlopen(base + "/health").read().decode("utf-8")),
    }

    up = _multipart(base + "/api/upload", src, {
        "entity": args.entity, "contract_type": args.contract_type, "review_focus": args.review_focus,
    })
    (out / "01_upload.json").write_text(json.dumps(up, ensure_ascii=False, indent=2), encoding="utf-8")
    sid = str(up.get("question_session_id") or "")
    if not sid:
        raise SystemExit(f"upload failed: {str(up)[:500]}")
    log["session_id"] = sid
    questions = up.get("questions") or []

    answers = _default_answers(questions)
    with_options = {str(q.get("question_id") or q.get("id") or "") for q in questions
                    if isinstance(q, dict) and (q.get("options") or q.get("choices"))}
    if args.answers:
        spec = json.loads(Path(args.answers).read_text(encoding="utf-8"))
        for qid in list(answers):
            hit = spec.get(qid)
            if hit is None:
                hit = next((v for k, v in spec.items() if k.startswith("*") and qid.endswith(k[1:])), None)
            if hit is None and qid not in with_options:
                hit = spec.get("__default__")
            if hit is None:
                hit = answers[qid]
            answers[qid] = hit
    (out / "02_answers.json").write_text(json.dumps(answers, ensure_ascii=False, indent=2), encoding="utf-8")
    _post(f"{base}/api/question_sessions/{sid}/answers", {"answers": answers})

    t0 = time.time()
    fast = _post(f"{base}/api/question_sessions/{sid}/review_fast", {})
    (out / "03_review_fast.json").write_text(json.dumps(fast, ensure_ascii=False, indent=2), encoding="utf-8")
    deep = _post(f"{base}/api/question_sessions/{sid}/review", {})
    log["review_sec"] = round(time.time() - t0, 1)
    (out / "04_review_deep.json").write_text(json.dumps(deep, ensure_ascii=False, indent=2), encoding="utf-8")
    review = (deep or {}).get("review") or {}
    log["ai"] = review.get("ai")

    downloads = {
        "05_report.docx": ("/api/revision/download_docx", {"session_id": sid}),
        "06_report.pdf": ("/api/revision/download_pdf", {"session_id": sid}),
        "07_redline.docx": ("/api/revision/download_redline", {"session_id": sid}),
        "08_clean.docx": ("/api/revision/download_clean", {"session_id": sid}),
    }
    log["downloads"] = {}
    for name, (ep, payload) in downloads.items():
        body = _post(base + ep, payload, raw=True)
        if isinstance(body, dict):
            log["downloads"][name] = body
            continue
        (out / name).write_bytes(body)
        log["downloads"][name] = {"bytes": len(body)}
    log["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    (out / "00_run_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(log, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
