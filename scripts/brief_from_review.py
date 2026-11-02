"""저장된 검토 결과(04_review_deep.json)로 사업팀 전달본을 만든다 — 같은 최종 데이터에서 바로 재현(무과금).

Usage: python scripts/brief_from_review.py RUN_DIR [--answers 02_answers.json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime.review.business_brief import brief_text, build_business_brief  # noqa: E402


def brief_for_run(run: Path):
    d = json.loads((run / "04_review_deep.json").read_text(encoding="utf-8"))
    r = d.get("review") or d
    m = r.get("clause_meta") or {}
    ff = m.get("final_findings") or {}
    answers = {}
    if (run / "02_answers.json").exists():
        answers = json.loads((run / "02_answers.json").read_text(encoding="utf-8"))
    text = ""
    up = run / "01_upload.json"
    if up.exists():
        u = json.loads(up.read_text(encoding="utf-8"))
        text = str(u.get("text") or u.get("extracted_text") or "")
    clauses = r.get("original_clauses") or d.get("original_clauses") or []
    if not text:
        text = "\n".join(str(c.get("text") or "") for c in clauses if isinstance(c, dict))
    return build_business_brief(
        clause_results=r.get("clause_results"), high_issues=ff.get("high_issues"), medium_issues=ff.get("medium_issues"),
        user_review_coverage=m.get("user_review_coverage"), deal_assessment=m.get("deal_assessment"),
        revision_set_check=m.get("revision_set_check"), clauses=clauses, contract_text=text, answers=answers,
    )


if __name__ == "__main__":
    b = brief_for_run(Path(sys.argv[1]))
    sys.stdout.reconfigure(encoding="utf-8")
    print(brief_text(b))
