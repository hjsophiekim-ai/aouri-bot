from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.review.clause_level import build_clause_level_result
from runtime.review.docx_writer import build_revision_docx
from runtime.review.text_extract import extract_text_from_file
from runtime.rules.loader import RuleLoader
from runtime.services.query_service import RuleQueryService
from runtime.questions.generator import generate_questions


def _pick_clause_ids(bundle: dict) -> tuple[list[str], list[str]]:
    meta = bundle.get("clause_meta") if isinstance(bundle.get("clause_meta"), dict) else {}
    expected = meta.get("changed_clause_ids") if isinstance(meta.get("changed_clause_ids"), list) else []
    expected_ids = [str(x) for x in expected if isinstance(x, str) and x]
    clause_results = bundle.get("clause_results") if isinstance(bundle.get("clause_results"), list) else []
    actual_ids = [
        str(cr.get("clause_id") or "")
        for cr in clause_results
        if isinstance(cr, dict) and bool(cr.get("has_rewrite_change")) and str(cr.get("clause_id") or "")
    ]
    return expected_ids, actual_ids


def main() -> int:
    docx_path = Path(r"C:\Users\FURSYS\Downloads\☆ 시디즈 26년 대리점(권역) 계약서 검토(법무팀).docx")
    if not docx_path.exists():
        raise SystemExit(f"missing input docx: {docx_path}")

    res = extract_text_from_file(docx_path)
    if not res.success:
        raise SystemExit(f"text extraction failed: {res.error}")

    service = RuleQueryService(RuleLoader())

    review_focus = "대리점법 불이익 제공, 경영간섭, 비용전가, 계약해지 남용"
    answers = {
        "Q-DL-001-form": "yes",
        "Q-DL-002-cost-shift": "yes",
        "Q-DL-003-settlement": "yes",
        "Q-DL-004-termination": "yes",
        "Q-DL-006-unfair-interference": "yes",
    }

    t0 = time.time()
    bundle = build_clause_level_result(
        service=service,
        entity="퍼시스",
        contract_type="대리점/유통",
        text=res.text,
        filename=docx_path.name,
        answers=answers,
        review_focus=review_focus,
        law_service=None,
        ai_provider=None,
        ai_model=None,
        ai_timeout_sec=None,
        ai_max_tokens=None,
        ai_temperature=None,
        max_clause_law_items=0,
    )
    elapsed = time.time() - t0

    out = {
        "input": {"docx": str(docx_path), "review_focus": review_focus},
        "elapsed_sec": round(elapsed, 3),
        "jurisdiction": (bundle.meta.get("final_review_context") or {}).get("jurisdiction") if isinstance(bundle.meta, dict) else None,
        "focus_issues": ((bundle.meta.get("final_review_context") or {}).get("user_focus_issues") if isinstance(bundle.meta, dict) else None),
        "focus_hit_count": sum(1 for cr in bundle.clause_results if isinstance(cr, dict) and bool(cr.get("user_focus_hit"))),
        "factual_hit_count": sum(1 for cr in bundle.clause_results if isinstance(cr, dict) and bool(cr.get("factual_hit"))),
        "top_clause_ids": [str(cr.get("clause_id") or "") for cr in (bundle.clause_results or [])[:12] if isinstance(cr, dict)],
        "domestic_dispute_reasoning_violation": [],
        "consistency": {},
        "question_ids": [],
        "clause8": None,
    }

    for cr in bundle.clause_results:
        if not isinstance(cr, dict):
            continue
        if str(cr.get("clause_topic") or "") != "dispute":
            continue
        rr = str(cr.get("rewrite_reason") or "")
        if (bundle.meta.get("final_review_context") or {}).get("jurisdiction", {}).get("kind") == "domestic_korea":
            if any(x in rr for x in ("해외", "집행", "다국가", "cross-border", "cross border")):
                out["domestic_dispute_reasoning_violation"].append(
                    {"clause_id": cr.get("clause_id"), "rewrite_reason": rr[:240]}
                )

    expected_changed, actual_changed = _pick_clause_ids(
        {"clause_results": bundle.clause_results, "clause_meta": bundle.meta}
    )
    out["consistency"] = {
        "expected_changed_count": len(expected_changed),
        "actual_changed_count": len(actual_changed),
        "mismatch": sorted(list(set(expected_changed) ^ set(actual_changed)))[:30],
    }

    qs = generate_questions(
        entity="퍼시스",
        contract_type="대리점/유통",
        detected_rule_ids=[r.get("rule_id") for r in (bundle.review.get("matched_rules") or []) if isinstance(r, dict)],
        law_topics=None,
        contract_text=res.text,
        clause_results=bundle.clause_results,
        max_questions=5,
        review_focus=review_focus,
    )
    out["question_ids"] = [q.question_id for q in qs]

    clause8 = None
    for cr in bundle.clause_results:
        if isinstance(cr, dict) and str(cr.get("article_number") or "").strip() == "8":
            clause8 = {
                "clause_id": cr.get("clause_id"),
                "display_path": cr.get("display_path"),
                "clause_title": cr.get("clause_title"),
                "user_focus_hit": bool(cr.get("user_focus_hit")),
                "factual_hit": bool(cr.get("factual_hit")),
                "has_rewrite_change": bool(cr.get("has_rewrite_change")),
                "change_record": cr.get("change_record"),
                "rewrite_reason": cr.get("rewrite_reason"),
            }
            break
    out["clause8"] = clause8

    original_clauses = [
        {
            "clause_id": c.clause_id,
            "article_number": c.article_number,
            "paragraph_number": c.paragraph_number,
            "item_number": c.item_number,
            "subitem_number": c.subitem_number,
            "display_path": c.display_path,
            "parent_clause_id": c.parent_clause_id,
            "context_text": c.context_text,
            "clause_title": c.title,
            "text": c.text,
        }
        for c in (bundle.clauses or [])
    ]
    _ = build_revision_docx(
        entity="퍼시스",
        contract_type="대리점/유통",
        filename=docx_path.name,
        original_clauses=original_clauses,
        clause_results=bundle.clause_results,
        review_summary=(bundle.review.get("summary") if isinstance(bundle.review, dict) else None),
        law_search=None,
        questions=[],
        answers=answers,
        final_review_context=(bundle.meta.get("final_review_context") if isinstance(bundle.meta, dict) else None),
    )

    out_path = Path(__file__).resolve().parents[1] / "runtime" / "data" / "revalidate_220_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
