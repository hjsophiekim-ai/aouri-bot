from __future__ import annotations

import json
import time
import zipfile
from io import BytesIO
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


def _pick_by_clause_id(clause_results: list[dict], clause_id: str) -> dict | None:
    cid = str(clause_id or "").strip()
    if not cid:
        return None
    for cr in clause_results or []:
        if isinstance(cr, dict) and str(cr.get("clause_id") or "") == cid:
            return cr
    return None


def _pick_by_article(clause_results: list[dict], article: int) -> dict | None:
    for cr in clause_results or []:
        if isinstance(cr, dict) and _article_int(cr.get("article_number")) == int(article):
            return cr
    return None


def _ui_visible_ids(clause_results: list[dict]) -> set[str]:
    out: set[str] = set()
    for cr in clause_results or []:
        if not isinstance(cr, dict):
            continue
        tier = str(cr.get("risk_tier") or "").strip().upper()
        if tier not in ("HIGH", "MEDIUM", "LOW"):
            continue
        if bool(cr.get("user_focus_hit")) or bool(cr.get("factual_hit")) or bool(cr.get("approval_required")) or bool(cr.get("high_risk")) or tier in ("HIGH", "MEDIUM"):
            cid = str(cr.get("clause_id") or "").strip()
            if cid:
                out.add(cid)
    return out


def _unzip_document_xml(docx_bytes: bytes) -> str:
    buf = BytesIO(docx_bytes)
    with zipfile.ZipFile(buf, "r") as z:
        xml = z.read("word/document.xml")
    return xml.decode("utf-8", errors="replace")


def main() -> int:
    candidates = [
        Path(r"C:\Users\FURSYS\Downloads\☆ 시디즈 26년 대리점(권역) 계약서 검토(법무팀).docx"),
        Path(r"C:\Users\FURSYS\Downloads\☆ 시디즈 26년 대리점(권역) 계약서 검토(법무팀) (1).docx"),
        Path(r"C:\Users\FURSYS\Downloads\☆ 시디즈 26년 대리점(권역) 계약서 검토(법무팀)(시디즈수정).docx"),
    ]
    docx_path = next((p for p in candidates if p.exists()), None)
    if docx_path is None:
        raise SystemExit("missing input docx: sidiz dealer contract")

    res = extract_text_from_file(docx_path)
    if not res.success:
        raise SystemExit(f"text extraction failed: {res.error}")

    service = RuleQueryService(RuleLoader())

    review_focus = (
        "대리점법상 불이익 제공 / 거래상 지위 남용 / 경영간섭(영업자율 침해) / "
        "계약해지(물량축소·공급중단·불이익조치) 남용"
    )
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
        entity="시디즈",
        contract_type="대리점/위탁/유통",
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

    clause_results = bundle.clause_results or []

    idx_by_article: dict[int, int] = {}
    for i, cr in enumerate(clause_results):
        if not isinstance(cr, dict):
            continue
        a = _article_int(cr.get("article_number"))
        if a is None:
            continue
        if a not in idx_by_article:
            idx_by_article[a] = i

    dispute_idx = idx_by_article.get(27)
    order_ok = True
    for a in (21, 23, 14, 11, 17, 8, 9, 10):
        if a in idx_by_article and dispute_idx is not None and idx_by_article[a] > dispute_idx:
            order_ok = False

    cr_23_p3 = _pick_by_clause_id(clause_results, "KR-23-p3")
    clause23_topic_ok = bool(isinstance(cr_23_p3, dict) and str(cr_23_p3.get("clause_topic") or "") == "termination")
    clause23_focus_ok = False
    clause23_contamination_ok = True
    if isinstance(cr_23_p3, dict):
        mt = cr_23_p3.get("user_focus_match_titles") if isinstance(cr_23_p3.get("user_focus_match_titles"), list) else []
        clause23_focus_ok = any(("계약해지" in str(x)) for x in mt)
        ft = cr_23_p3.get("factual_match_titles") if isinstance(cr_23_p3.get("factual_match_titles"), list) else []
        clause23_contamination_ok = not any(("분쟁" in str(x) or "관할" in str(x) or "준거법" in str(x)) for x in ft)

    matched_rules = bundle.review.get("matched_rules") if isinstance(bundle.review, dict) else []
    ui_issue_titles = [
        str(x.get("title") or x.get("rule_id") or "").strip()
        for x in matched_rules
        if isinstance(x, dict) and not bool(x.get("summary_suppress")) and str(x.get("title") or x.get("rule_id") or "").strip()
    ]
    dispute_in_ui_issues = any(("국내 계약 분쟁조항 점검" in t) for t in ui_issue_titles)

    ui_visible_ids = _ui_visible_ids(clause_results)
    ui_visible_missing_rewrite = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        cid = str(cr.get("clause_id") or "")
        if cid not in ui_visible_ids:
            continue
        if bool(cr.get("keep_as_is")):
            continue
        tier = str(cr.get("risk_tier") or "").strip().upper()
        if tier in ("HIGH", "MEDIUM"):
            sr = cr.get("suggested_rewrite")
            if not (isinstance(sr, str) and sr.strip()):
                ui_visible_missing_rewrite.append(f"{cid}:{tier}")

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
    docx_bytes = build_revision_docx(
        entity="시디즈",
        contract_type="대리점/위탁/유통",
        filename=docx_path.name,
        original_clauses=original_clauses,
        clause_results=clause_results,
        review_summary=(bundle.review.get("summary") if isinstance(bundle.review, dict) else None),
        law_search=None,
        questions=[],
        answers=answers,
        final_review_context=(bundle.meta.get("final_review_context") if isinstance(bundle.meta, dict) else None),
    )
    doc_xml = _unzip_document_xml(docx_bytes)

    word_has_appendix = "9) 조항별 구체적 수정안 부록" in doc_xml
    word_has_clause23_anchor = ("제23조" in doc_xml) and ("시정기간" in doc_xml or "서면" in doc_xml)
    word_has_rewrite_block = ("제안 문안:" in doc_xml) and ("사유:" in doc_xml)

    out_md = Path(__file__).resolve().parents[2] / "docs" / "review_output" / "243_dealer_precision_revalidation_v2.md"
    out_md.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("# 243. Dealer precision 재검증 v2(시디즈 대리점 계약)")
    lines.append("")
    lines.append(f"- 입력 DOCX: {docx_path}")
    lines.append(f"- review_focus: {review_focus}")
    lines.append(f"- 실행 시간: {elapsed:.3f}s")
    lines.append("")
    lines.append("## 필수 확인 결과")
    lines.append(f"- (1) 핵심 이슈 요약에서 제27조/분쟁(ACT-004) 1차 제외: {'OK' if not dispute_in_ui_issues else 'FAIL'}")
    lines.append(f"- (2) 제23조 제3항 쟁점이 termination 축으로 분류: {'OK' if clause23_topic_ok else 'FAIL'}")
    lines.append(f"- (2-1) 제23조 제3항 user_focus(해지 남용) 연결: {'OK' if clause23_focus_ok else 'FAIL'}")
    lines.append(f"- (2-2) 제23조 제3항 분쟁 토픽 오염 없음: {'OK' if clause23_contamination_ok else 'FAIL'}")
    lines.append(f"- (3) 제21/23/14/11/17이 제27보다 우선 검토: {'OK' if order_ok else 'FAIL'}")
    lines.append(f"- (4) Word에 구체 제안 문안 포함(부록/가이던스): {'OK' if (word_has_rewrite_block and word_has_appendix) else 'FAIL'}")
    lines.append(f"- (5) Word에 제23조 해지 redline/제안 문안 실재: {'OK' if word_has_clause23_anchor else 'FAIL'}")
    lines.append(f"- (6) UI-visible(HIGH/MEDIUM) 조항 제안 문안 누락 없음: {'OK' if not ui_visible_missing_rewrite else 'FAIL'}")
    lines.append("")
    lines.append("## 핵심 조항 포함/순서")
    for a in (21, 23, 14, 11, 17, 27):
        lines.append(f"- 제{a}조 index={idx_by_article.get(a)}")
    lines.append("")
    if ui_issue_titles:
        lines.append("## 핵심 이슈 요약(UI 기준)")
        for t in ui_issue_titles[:8]:
            lines.append(f"- {t}")
        lines.append("")
    if ui_visible_missing_rewrite:
        lines.append("## 누락 상세(HIGH/MEDIUM 제안 문안)")
        lines.append("- " + ", ".join(ui_visible_missing_rewrite[:30]))
        lines.append("")
    if isinstance(cr_23_p3, dict):
        lines.append("## 제23조 제3항 디버그")
        lines.append(
            json.dumps(
                {
                    "clause_id": cr_23_p3.get("clause_id"),
                    "display_path": cr_23_p3.get("display_path"),
                    "clause_topic": cr_23_p3.get("clause_topic"),
                    "risk_tier": cr_23_p3.get("risk_tier"),
                    "must_fix": bool(cr_23_p3.get("must_fix")),
                    "user_focus_match_titles": cr_23_p3.get("user_focus_match_titles"),
                    "factual_match_titles": cr_23_p3.get("factual_match_titles"),
                    "rewrite_reason_head": str(cr_23_p3.get("rewrite_reason") or "")[:180],
                    "suggested_rewrite_head": str(cr_23_p3.get("suggested_rewrite") or "")[:220],
                },
                ensure_ascii=False,
            )
        )
        lines.append("")

    out_md.write_text("\n".join(lines), encoding="utf-8")

    out_json = out_md.with_suffix(".json")
    out_json.write_text(
        json.dumps(
            {
                "elapsed_sec": round(elapsed, 3),
                "idx_by_article": idx_by_article,
                "order_ok": order_ok,
                "ui_issue_titles": ui_issue_titles,
                "dispute_in_ui_issues": dispute_in_ui_issues,
                "clause23": cr_23_p3,
                "clause23_topic_ok": clause23_topic_ok,
                "clause23_focus_ok": clause23_focus_ok,
                "clause23_contamination_ok": clause23_contamination_ok,
                "word_has_appendix": word_has_appendix,
                "word_has_rewrite_block": word_has_rewrite_block,
                "word_has_clause23_anchor": word_has_clause23_anchor,
                "ui_visible_missing_rewrite": ui_visible_missing_rewrite,
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

