"""검토 결과(04_review_deep.json)에서 판단에 쓰인 핵심만 뽑아 본다 — 전달본 절, 요청 답변, 살아남은/버려진 finding.

Usage: python scripts/dump_review_summary.py RUN_DIR
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

run = Path(sys.argv[1])
d = json.loads((run / "04_review_deep.json").read_text(encoding="utf-8"))
rr = d.get("review_result") or d.get("review") or d
m = rr.get("clause_meta") or {}
print("== verdict/sections")
for head, rows in m.get("business_brief_sections") or []:
    print("##", head)
    for st, tx in rows:
        print(f"  [{st}] {tx[:600]}")
print("== coverage")
for r in m.get("user_review_coverage") or []:
    print(" -", r.get("relevant_clause"), "|", r.get("review_status"), "|", str(r.get("direct_answer"))[:200])
print("== findings")
for c in rr.get("clause_results") or []:
    flag = "DROP" if c.get("dedup_suppressed") else ("KEEP" if c.get("keep_as_is") else "LIVE")
    why = c.get("dedup_reason") or c.get("senior_audit_removed") or c.get("global_cross_clause_suppressed_topic") \
        or c.get("original_text_absent_reason") or c.get("dedup_merged_into") or c.get("merged_into") or ""
    print(f" {flag} {c.get('risk_tier')} {c.get('clause_id')} {c.get('display_path')} | {str(c.get('issue_title') or '')[:70]} | {str(why)[:120]}")
print("== party_map", json.dumps(m.get("party_map"), ensure_ascii=False)[:400])
print("== profile", m.get("contract_profile"), m.get("overall_recommendation"), m.get("review_status"))
