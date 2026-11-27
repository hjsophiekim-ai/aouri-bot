"""실제 검토 생성 경로(업로드 → 사전질문 답 → 검토 → 변경추적 Word·clean·검토의견서) e2e 하네스.

Usage: python scripts/redline_e2e.py CONTRACT_FILE OUT_JSON "검토 요청" [entity] [answers.json]
answers.json = {"질문 제목에 들어 있는 낱말": "답", ...} — 질문 제목에 낱말이 있으면 그 답을 쓴다(없으면 "미확정입니다.").
AI 키를 지우고 돌리므로 결정적·무과금이다(라이브 AI 경로는 별도).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LIVE = os.environ.get("REDLINE_E2E_LIVE") == "1"   # 1 이면 .env 의 AI 키로 실제(라이브) 경로를 탄다 — 과금됨
if not LIVE:
    os.environ["AOURIBOT_DOTENV_DISABLED"] = "1"
    for _k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        os.environ.pop(_k, None)

from runtime.tests.test_privacy_term_linkage import Server, _multipart, _post  # noqa: E402


def edits_of(review: dict) -> list[dict]:
    out = []
    for c in review.get("clause_results") or []:
        if not isinstance(c, dict):
            continue
        tier = str(c.get("risk_tier") or c.get("severity") or "")
        has_edit = bool(c.get("has_rewrite_change") or c.get("has_addition"))
        if tier not in ("HIGH", "MEDIUM") and not has_edit:
            continue
        out.append({
            "clause_id": c.get("clause_id"), "path": c.get("display_path"), "tier": tier,
            "keep": c.get("keep_as_is"), "edit": has_edit,
            "reason": str(c.get("rewrite_reason") or "")[:400],
            "original": str(c.get("original_text") or c.get("replace_text") or ""),
            "rewrite": str(c.get("suggested_rewrite") or "") if c.get("has_rewrite_change") else "",
            "addition": str(c.get("addition_text") or "") if c.get("has_addition") else "",
            "held": bool((c.get("redline_instruction") or {}).get("held")),
            "location": str((c.get("redline_instruction") or {}).get("edit_location") or ""),
            "integrity": c.get("redline_integrity"),
        })
    return out


def main() -> int:
    path, out_json, request = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    entity = sys.argv[4] if len(sys.argv) > 4 else ""
    amap = json.loads(Path(sys.argv[5]).read_text(encoding="utf-8")) if len(sys.argv) > 5 else {}
    srv = Server()
    try:
        up = _multipart(srv.base + "/api/upload", path, {"entity": entity, "contract_type": "", "review_focus": request})
        sid = up["question_session_id"]
        answers = {}
        for q in up.get("questions") or []:
            title = str(q.get("title") or "")
            ans = next((v for k, v in amap.items() if k in title), "미확정입니다.")
            answers[q.get("question_id") or q.get("id")] = ans
        _post(f"{srv.base}/api/question_sessions/{sid}/answers", {"answers": answers})
        review = _post(f"{srv.base}/api/question_sessions/{sid}/review", {})["review"]
        meta = review.get("clause_meta") or {}
        res: dict = {"sid": sid, "questions": {str(q.get("title")): answers.get(q.get("question_id") or q.get("id"))
                                               for q in up.get("questions") or []}}
        res["executive_summary"] = review.get("executive_summary")
        from runtime.review.text_extract import extract_text_from_file

        res["contract_text"] = extract_text_from_file(path).text   # 시스템이 쓴 것과 같은 추출본(기준 원문)
        res["request"] = request
        res["edits"] = edits_of(review)
        ff = meta.get("final_findings") or {}
        res["final_findings"] = {k: [(_x.get("clause_id"), _x.get("display_path"), _x.get("risk_tier") or _x.get("severity"))
                                     for _x in ff.get(k) or [] if isinstance(_x, dict)] for k in ("high_issues", "medium_issues")}
        res["business_brief_cards"] = [(c.get("no"), c.get("risk"), c.get("action_type"), c.get("title"), c.get("sources"))
                                       for c in (meta.get("business_brief") or {}).get("cards") or []]
        for k in ("verification_gate", "revision_set_check", "redline_integrity", "deal_flow", "review_status",
                  "review_status_detail", "overall_recommendation", "business_brief_sections", "final_docx_check"):
            v = meta.get(k)
            if k == "deal_flow" and isinstance(v, dict):
                v = {"role": v.get("role"), "unresolved": v.get("unresolved")}
            res[k] = v
        from runtime.review.docx_redline import docx_paragraph_texts

        for name, url in (("redline", "/api/revision/download_redline"), ("clean", "/api/revision/download_clean"),
                          ("report", "/api/revision/download_docx")):
            try:
                b = _post(srv.base + url, {"session_id": sid}, raw=True)
                out_json.with_name(out_json.stem + f"_{name}.docx").write_bytes(b)
                res[f"{name}_status"] = 200
                if name == "redline":
                    res["redline_accept"] = [p for p in docx_paragraph_texts(b, mode="accept") if p.strip()]
                    res["redline_reject"] = [p for p in docx_paragraph_texts(b, mode="reject") if p.strip()]
                if name == "clean":
                    res["clean_paras"] = [p for p in docx_paragraph_texts(b, mode="accept") if p.strip()]
            except Exception as exc:  # noqa: BLE001
                body = getattr(exc, "read", lambda: b"")()
                res[f"{name}_status"] = f"{getattr(exc, 'code', '')} {body[:300]!r}"
        out_json.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print("ok", out_json)
    finally:
        srv.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
