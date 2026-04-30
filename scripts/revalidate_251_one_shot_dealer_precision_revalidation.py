from __future__ import annotations

import json
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
    core_order_ok = True
    for a in (21, 23, 14, 11, 17, 8, 9, 10):
        if a in idx_by_article and dispute_idx is not None and idx_by_article[a] > dispute_idx:
            core_order_ok = False

    ui_issue_titles = [
        str(x.get("title") or x.get("rule_id") or "").strip()
        for x in (bundle.review.get("matched_rules") or [])
        if isinstance(x, dict) and not bool(x.get("summary_suppress")) and str(x.get("title") or x.get("rule_id") or "").strip()
    ]
    dispute_in_core_summary = any(("국내 계약 분쟁조항 점검" in t) for t in ui_issue_titles)

    cr_23_p3 = next((x for x in clause_results if isinstance(x, dict) and x.get("clause_id") == "KR-23-p3"), None)
    clause23_topic_ok = bool(isinstance(cr_23_p3, dict) and str(cr_23_p3.get("clause_topic") or "") == "termination")
    clause23_dispute_contamination_ok = True
    clause23_focus_ok = False
    if isinstance(cr_23_p3, dict):
        ft = cr_23_p3.get("factual_match_titles") if isinstance(cr_23_p3.get("factual_match_titles"), list) else []
        clause23_dispute_contamination_ok = not any(("분쟁" in str(x) or "관할" in str(x) or "준거법" in str(x)) for x in ft)
        mt = cr_23_p3.get("user_focus_match_titles") if isinstance(cr_23_p3.get("user_focus_match_titles"), list) else []
        clause23_focus_ok = any(("계약해지" in str(x)) for x in mt)

    mapping_table = bundle.meta.get("user_focus_mapping_table") if isinstance(bundle.meta, dict) else None
    mapping_ok = bool(isinstance(mapping_table, list) and any(isinstance(x, dict) and (x.get("matched_clause_ids") or []) for x in mapping_table))

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
    word_has_proposed = "제안 문안:" in doc_xml
    word_has_reason = "사유:" in doc_xml
    word_concrete_ok = bool(word_has_appendix and word_has_proposed and word_has_reason)

    ui_visible = [
        cr
        for cr in clause_results
        if isinstance(cr, dict)
        and (
            bool(cr.get("user_focus_hit"))
            or bool(cr.get("factual_hit"))
            or bool(cr.get("approval_required"))
            or bool(cr.get("high_risk"))
            or str(cr.get("risk_tier") or "").upper() in ("HIGH", "MEDIUM")
        )
    ]
    ui_word_same_ok = True
    missing_in_word = []
    for cr in ui_visible[:18]:
        sr = cr.get("suggested_rewrite")
        if not (isinstance(sr, str) and sr.strip()):
            continue
        needle = sr.strip()[:18]
        if needle and needle not in doc_xml:
            ui_word_same_ok = False
            missing_in_word.append(str(cr.get("clause_id") or ""))

    fail_reasons = []
    if dispute_in_core_summary:
        fail_reasons.append("ACT-004가 핵심 이슈 요약에 포함됨")
    if not clause23_topic_ok:
        fail_reasons.append("제23조 제3항 토픽이 termination이 아님")
    if not clause23_dispute_contamination_ok:
        fail_reasons.append("제23조 제3항이 분쟁 토픽으로 오염됨")
    if not mapping_ok:
        fail_reasons.append("user_focus 매핑 결과가 비어 있음")
    if not word_concrete_ok:
        fail_reasons.append("Word에 구체 제안 문안/사유/부록이 충분히 포함되지 않음")
    if not ui_word_same_ok:
        fail_reasons.append("UI-visible 제안 문안이 Word에 누락됨")
    if not core_order_ok:
        fail_reasons.append("핵심 조항이 제27보다 후순위로 노출됨")

    out_md = Path(__file__).resolve().parents[2] / "docs" / "review_output" / "251_one_shot_dealer_precision_revalidation.md"
    out_md.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("# 251. One-shot dealer precision 재검증(시디즈 대리점 계약)")
    lines.append("")
    lines.append(f"- 입력 DOCX: {docx_path}")
    lines.append(f"- review_focus: {review_focus}")
    lines.append("")
    lines.append("## 필수 확인")
    lines.append(f"- (1) 핵심 이슈 요약에서 제27/분쟁(ACT-004) 제외/후순위: {'OK' if not dispute_in_core_summary else 'FAIL'}")
    lines.append(f"- (2) 제23조 제3항 termination 분류: {'OK' if clause23_topic_ok else 'FAIL'}")
    lines.append(f"- (3) 제23조 제3항 dispute 오염 없음: {'OK' if clause23_dispute_contamination_ok else 'FAIL'}")
    lines.append(f"- (4) user_focus_issues 매핑 비어있지 않음: {'OK' if mapping_ok else 'FAIL'}")
    lines.append(f"- (5) Word에 구체 수정문구(제안 문안/사유/부록) 포함: {'OK' if word_concrete_ok else 'FAIL'}")
    lines.append(f"- (6) UI-visible 제안 문안이 Word에도 존재: {'OK' if ui_word_same_ok else 'FAIL'}")
    lines.append(f"- (7) 핵심 조항(21/23/14/11/17/8~10)이 제27보다 우선: {'OK' if core_order_ok else 'FAIL'}")
    lines.append("")
    lines.append("## 핵심 조항 index")
    for a in (21, 23, 14, 11, 17, 8, 9, 10, 27):
        lines.append(f"- 제{a}조 index={idx_by_article.get(a)}")
    lines.append("")
    if fail_reasons:
        lines.append("## 실패 사유")
        for r in fail_reasons:
            lines.append(f"- {r}")
        lines.append("")
    if missing_in_word:
        lines.append("## Word 누락(UI-visible)")
        lines.append("- " + ", ".join(missing_in_word[:30]))
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
                    "rewrite_reason_head": str(cr_23_p3.get("rewrite_reason") or "")[:200],
                    "why_this_is_core_issue": cr_23_p3.get("why_this_is_core_issue"),
                    "changed_segments": cr_23_p3.get("changed_segments"),
                },
                ensure_ascii=False,
            )
        )
        lines.append("")
    if isinstance(mapping_table, list):
        lines.append("## user_focus 매핑 테이블(meta)")
        for row in mapping_table[:8]:
            if not isinstance(row, dict):
                continue
            t0 = str(row.get("objective_title") or row.get("objective_code") or "").strip()
            ids = row.get("matched_clause_labels") if isinstance(row.get("matched_clause_labels"), list) else []
            ids = [str(x) for x in ids if isinstance(x, str) and x.strip()]
            lines.append(f"- {t0}: " + (" · ".join(ids[:6]) if ids else "(후보 조항 없음)"))
        lines.append("")

    out_md.write_text("\n".join(lines), encoding="utf-8")
    out_json = out_md.with_suffix(".json")
    out_json.write_text(
        json.dumps(
            {
                "idx_by_article": idx_by_article,
                "dispute_in_core_summary": dispute_in_core_summary,
                "clause23_topic_ok": clause23_topic_ok,
                "clause23_dispute_contamination_ok": clause23_dispute_contamination_ok,
                "mapping_ok": mapping_ok,
                "word_concrete_ok": word_concrete_ok,
                "ui_word_same_ok": ui_word_same_ok,
                "missing_in_word": missing_in_word,
                "core_order_ok": core_order_ok,
                "fail_reasons": fail_reasons,
                "clause23": cr_23_p3,
                "user_focus_mapping_table": mapping_table,
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

