from __future__ import annotations

import json
import time
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.review.clause_level import build_clause_level_result
from runtime.review.docx_writer import build_revision_docx
from runtime.review.text_extract import extract_text_from_file
from runtime.rules.loader import RuleLoader
from runtime.services.query_service import RuleQueryService


def _article_int(v: object) -> int | None:
    s = str(v or "").strip()
    if not s:
        return None
    cur = ""
    for ch in s:
        if ch.isdigit():
            cur += ch
        elif cur:
            break
    return int(cur) if cur.isdigit() else None


def _pick_by_article(bundle: object, article: int) -> dict | None:
    if not hasattr(bundle, "clause_results"):
        return None
    for cr in getattr(bundle, "clause_results") or []:
        if isinstance(cr, dict) and _article_int(cr.get("article_number")) == int(article):
            return cr
    return None


def _pick_by_clause_id(bundle: object, clause_id: str) -> dict | None:
    cid = str(clause_id or "").strip()
    if not cid:
        return None
    if not hasattr(bundle, "clause_results"):
        return None
    for cr in getattr(bundle, "clause_results") or []:
        if isinstance(cr, dict) and str(cr.get("clause_id") or "") == cid:
            return cr
    return None


def main() -> int:
    docx_path = Path(r"C:\Users\FURSYS\Downloads\☆ 시디즈 26년 대리점(권역) 계약서 검토(법무팀).docx")
    if not docx_path.exists():
        raise SystemExit(f"missing input docx: {docx_path}")

    res = extract_text_from_file(docx_path)
    if not res.success:
        raise SystemExit(f"text extraction failed: {res.error}")

    service = RuleQueryService(RuleLoader())

    review_focus = "대리점법상 불이익 제공 / 거래상 지위 남용 / 경영간섭(영업자율 침해) / 계약해지(물량축소·공급중단·불이익조치) 남용"
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

    wanted_articles = [21, 23, 14, 11, 17, 8, 9, 10, 27]
    present_articles = {a: (_pick_by_article(bundle, a) is not None) for a in wanted_articles}

    idx_by_article: dict[int, int] = {}
    for i, cr in enumerate(bundle.clause_results or []):
        if not isinstance(cr, dict):
            continue
        a = _article_int(cr.get("article_number"))
        if a is None:
            continue
        if a not in idx_by_article:
            idx_by_article[a] = i

    order_ok = True
    dispute_idx = idx_by_article.get(27)
    for a in (21, 23, 14, 11, 17, 8, 9, 10):
        if a in idx_by_article and dispute_idx is not None:
            if idx_by_article[a] > dispute_idx:
                order_ok = False

    focus_map: dict[str, list[str]] = {}
    for cr in bundle.clause_results or []:
        if not isinstance(cr, dict):
            continue
        cid = str(cr.get("clause_id") or "")
        if not cid:
            continue
        for code in (cr.get("user_focus_matches") or []):
            if isinstance(code, str) and code.strip():
                focus_map.setdefault(code, []).append(cid)

    redline_targets = {21, 23, 14, 11, 17}
    redline_ok: dict[int, bool] = {}
    redline_debug: dict[int, dict] = {}
    for a in redline_targets:
        cr = _pick_by_article(bundle, a)
        redline_ok[a] = bool(isinstance(cr, dict) and isinstance(cr.get("suggested_rewrite"), str) and cr.get("suggested_rewrite").strip())
        if isinstance(cr, dict):
            redline_debug[a] = {
                "clause_id": cr.get("clause_id"),
                "article_number": cr.get("article_number"),
                "clause_title": cr.get("clause_title"),
                "clause_topic": cr.get("clause_topic"),
                "keep_as_is": bool(cr.get("keep_as_is")),
                "dedup_suppressed": bool(cr.get("dedup_suppressed")),
                "screening_only": bool(cr.get("screening_only")),
                "suggested_rewrite_len": len(str(cr.get("suggested_rewrite") or "")),
                "original_text_len": len(str(cr.get("original_text") or "")),
                "original_text_head": (str(cr.get("original_text") or "")[:120] if isinstance(cr.get("original_text"), str) else str(cr.get("original_text") or "")[:120]),
                "guardrail_block": cr.get("guardrail_block"),
            }

    dispute_title_ok = True
    dispute_debug = {}
    for cr in (bundle.clause_results or []):
        if not isinstance(cr, dict):
            continue
        issues = cr.get("detected_issue_list") if isinstance(cr.get("detected_issue_list"), list) else []
        for x in issues:
            if not isinstance(x, dict):
                continue
            if str(x.get("rule_id") or "") == "ACT-004" and not bool(x.get("summary_suppress")):
                t = str(x.get("issue_title") or "").strip()
                dispute_title_ok = ("국내 계약 분쟁조항 점검" not in t)
                dispute_debug = {
                    "clause_id": cr.get("clause_id"),
                    "display_path": cr.get("display_path"),
                    "issue_title": t,
                    "summary_suppress": bool(x.get("summary_suppress")),
                }
                break
        if dispute_debug:
            break

    cr_23_p3 = _pick_by_clause_id(bundle, "KR-23-p3")
    term_topic_ok = bool(isinstance(cr_23_p3, dict) and str(cr_23_p3.get("clause_topic") or "") == "termination")
    term_reason_ok = False
    if isinstance(cr_23_p3, dict) and isinstance(cr_23_p3.get("rewrite_reason"), str):
        rr = cr_23_p3.get("rewrite_reason") or ""
        term_reason_ok = any(k in rr for k in ("즉시", "시정", "최고", "시정기간", "중대한", "객관"))

    expected_changed = set(str(x) for x in (bundle.meta.get("changed_clause_ids") or []) if isinstance(x, str) and x)
    actual_changed = set(
        str(cr.get("clause_id") or "")
        for cr in (bundle.clause_results or [])
        if isinstance(cr, dict) and bool(cr.get("has_rewrite_change")) and str(cr.get("clause_id") or "")
    )
    consistency_ok = expected_changed == actual_changed

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

    out_md = Path(__file__).resolve().parents[2] / "docs" / "review_output" / "236_dealer_review_revalidation.md"
    out_md.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("# 236. Dealer review 재검증(시디즈 대리점 계약)")
    lines.append("")
    lines.append(f"- 입력 DOCX: {docx_path}")
    lines.append(f"- review_focus: {review_focus}")
    lines.append(f"- 실행 시간: {elapsed:.3f}s")
    lines.append("")
    lines.append("## 체크 결과")
    lines.append(f"- 사용자 요청 이슈 매핑 존재: {('OK' if any(focus_map.values()) else 'FAIL')}")
    lines.append(f"- 핵심 조항이 제27보다 우선 노출: {('OK' if order_ok else 'FAIL')}")
    lines.append(f"- 핵심 조항 redline candidate 생성(제21/23/14/11/17): {('OK' if all(redline_ok.values()) else 'FAIL')}")
    lines.append(f"- UI/Word canonical set(변경 조항 집합 일치): {('OK' if consistency_ok else 'FAIL')}")
    lines.append(f"- 핵심 이슈 요약에 '국내 계약 분쟁조항 점검' 미포함: {('OK' if dispute_title_ok else 'FAIL')}")
    lines.append(f"- 제23조 제3항 토픽=termination: {('OK' if term_topic_ok else 'FAIL')}")
    lines.append(f"- 제23조 제3항 사유(즉시해지/시정/객관화 축): {('OK' if term_reason_ok else 'FAIL')}")
    lines.append("")
    lines.append("## 핵심 조항 포함 여부")
    for a in wanted_articles:
        lines.append(f"- 제{a}조 포함: {'OK' if present_articles.get(a) else 'FAIL'} (index={idx_by_article.get(a)})")
    lines.append("")
    lines.append("## user_focus 매핑 요약(code → clause_ids)")
    for code, ids in sorted(focus_map.items(), key=lambda x: x[0]):
        lines.append(f"- {code}: {', '.join(ids[:10])}{'…' if len(ids) > 10 else ''}")
    lines.append("")
    lines.append("## 변경 조항 집합(일관성)")
    lines.append(f"- expected_changed_count(meta): {len(expected_changed)}")
    lines.append(f"- actual_changed_count(has_rewrite_change): {len(actual_changed)}")
    if not consistency_ok:
        lines.append(f"- mismatch(sample): {', '.join(sorted(list(expected_changed ^ actual_changed))[:20])}")
    lines.append("")
    if dispute_debug:
        lines.append("## 분쟁 이슈 디버그(ACT-004)")
        lines.append(f"- sample: {json.dumps(dispute_debug, ensure_ascii=False)}")
        lines.append("")
    if isinstance(cr_23_p3, dict):
        lines.append("## 제23조 제3항 디버그")
        lines.append(
            f"- clause_topic={cr_23_p3.get('clause_topic')} risk_tier={cr_23_p3.get('risk_tier')} must_fix={bool(cr_23_p3.get('must_fix'))}"
        )
        lines.append(f"- rewrite_reason={str(cr_23_p3.get('rewrite_reason') or '')[:240]}")
        lines.append(f"- suggested_rewrite_len={len(str(cr_23_p3.get('suggested_rewrite') or ''))}")
        lines.append("")

    out_md.write_text("\n".join(lines), encoding="utf-8")

    out_json = out_md.with_suffix(".json")
    out_json.write_text(
        json.dumps(
            {
                "elapsed_sec": round(elapsed, 3),
                "contract_profile": (bundle.meta.get("contract_profile") if isinstance(bundle.meta, dict) else None),
                "present_articles": present_articles,
                "idx_by_article": idx_by_article,
                "order_ok": order_ok,
                "focus_map": focus_map,
                "redline_ok": redline_ok,
                "redline_debug": redline_debug,
                "consistency_ok": consistency_ok,
                "expected_changed_count": len(expected_changed),
                "actual_changed_count": len(actual_changed),
                "dispute_title_ok": dispute_title_ok,
                "dispute_debug": dispute_debug,
                "term_topic_ok": term_topic_ok,
                "term_reason_ok": term_reason_ok,
                "term_23_p3": (cr_23_p3 if isinstance(cr_23_p3, dict) else None),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(out_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
