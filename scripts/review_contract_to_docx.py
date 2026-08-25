"""End-to-end contract review CLI: input DOCX → lawyer-grade review DOCX.

Pipeline:
  1. Extract text from input file
  2. Classify contract (type, entity)
  3. Build detailed contract profile
  4. Run review pipeline (rule-based + optional AI)
  5. Inject mandatory issues for consignment dealer contracts
  6. Apply severity reclassification
  7. Apply hallucination guard
  8. Generate DOCX with colors and proper structure

Usage:
    python scripts/review_contract_to_docx.py \
        --input "OPC_퍼시스_판매대리점_계약서.docx" \
        --output "aouribot_review.docx" \
        --company "퍼시스" \
        --mode legal-team \
        --include-low false
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="아우리봇 계약 검토 DOCX 생성")
    p.add_argument("--input", "-i", required=True, help="계약서 파일 경로")
    p.add_argument("--output", "-o", default="aouribot_review_output.docx")
    p.add_argument("--company", default="퍼시스")
    p.add_argument("--contract-type", default="")
    p.add_argument("--mode", default="legal-team", choices=["legal-team", "fast"])
    p.add_argument("--include-low", default="false", choices=["true", "false"])
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    include_low = args.include_low.lower() == "true"
    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"[ERROR] 파일 없음: {input_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[아우리봇] 분석 시작: {input_path.name}")

    # ── Step 1: Extract text ───────────────────────────────────────────────
    from runtime.review.text_extract import extract_text_from_file
    result = extract_text_from_file(input_path)
    if not result.success or not (result.text or "").strip():
        try:
            text = input_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            text = ""
    else:
        text = result.text or ""

    if not text.strip():
        print("[ERROR] 텍스트 추출 실패", file=sys.stderr)
        sys.exit(1)
    print(f"[아우리봇] 텍스트 추출 완료: {len(text):,}자")

    # ── Step 2: Classify ───────────────────────────────────────────────────
    from runtime.review.classify import classify
    from runtime.review.contract_classifier import classify_contract_detailed

    cl = classify(
        entity=args.company or None,
        contract_type=args.contract_type or None,
        text=text,
        filename=input_path.name,
        file_path=str(input_path),
    )
    entity = cl.entity
    contract_type = cl.contract_type

    detailed = classify_contract_detailed(
        entity=entity,
        contract_type=contract_type,
        text=text,
        filename=input_path.name,
    )
    ct_code = detailed.contract_type

    print(f"[아우리봇] 계약유형: {ct_code} | 우리 회사: {detailed.our_party}")

    # ── Step 3: Run pipeline ───────────────────────────────────────────────
    from runtime.rules.loader import RuleLoader
    from runtime.services.query_service import RuleQueryService

    loader = RuleLoader()
    loader.load()
    service = RuleQueryService(loader)

    # AI setup
    ai_provider = ai_model = ai_timeout_sec = ai_max_tokens = ai_temperature = None
    if os.environ.get("OPENAI_API_KEY") and args.mode == "legal-team":
        try:
            from runtime.ai.provider import create_provider
            ai_provider = create_provider()
            ai_model = os.environ.get("AI_MODEL", "gpt-4.1")
            ai_timeout_sec, ai_max_tokens, ai_temperature = 45.0, 2000, 0.1
            print(f"[아우리봇] AI 검토 활성화: {ai_model}")
        except Exception:
            print("[아우리봇] AI 비활성화 — 규칙 기반 모드")

    from runtime.review.clause_level import build_clause_level_result

    bundle = build_clause_level_result(
        service=service,
        entity=entity,
        contract_type=contract_type,
        text=text,
        filename=input_path.name,
        answers=None,
        review_focus=None,
        law_service=None,
        ai_provider=ai_provider,
        ai_model=ai_model,
        ai_timeout_sec=ai_timeout_sec,
        ai_max_tokens=ai_max_tokens,
        ai_temperature=ai_temperature,
    )

    clause_results = list(bundle.clause_results)

    # ── Step 4a: Content production checklist (콘텐츠 제작 계약 전용) ─────
    _CONTENT_TYPES = {"advertising_content_production", "content_production_service",
                      "creative_agency_service", "content_production"}
    _CONTENT_TEXT_SIGNALS = ["콘텐츠 제작", "광고 콘텐츠", "저작권 이전", "소유권의 귀속",
                              "제작 견적서", "콘텐츠의 제출 및 검수", "시안", "촬영"]
    if ct_code in _CONTENT_TYPES or any(kw in text for kw in _CONTENT_TEXT_SIGNALS):
        try:
            from runtime.review.checklists.content_production import run_content_production_checklist
            content_issues = run_content_production_checklist(
                text=text,
                contract_type_code=ct_code,
                entity=entity,
                counterparty=detailed.counterparty,
            )
            # Insert at front (highest priority)
            new_crs = [ci.to_issue_dict() for ci in content_issues]
            # Remove generic advisory checklist items that conflict with clause-based issues
            _GENERIC_ADVISORY = {
                "svc_prepayment_guarantee", "svc_inspection_before_payment",
                "svc_deliverable_definition", "svc_refund_on_incomplete",
                "svc_delay_response", "svc_post_use_scope",
            }
            clause_results = [
                cr for cr in clause_results
                if not (isinstance(cr, dict) and str(cr.get("clause_id") or "") in _GENERIC_ADVISORY)
            ]
            clause_results = new_crs + clause_results
            print(f"[아우리봇] 콘텐츠 제작 체크리스트: {len(new_crs)}개 이슈 주입")
        except Exception as e:
            print(f"[아우리봇] 콘텐츠 체크리스트 오류: {e}", file=__import__("sys").stderr)

    # ── Step 4b: Inject mandatory issues (dealer contracts) ───────────────
    from runtime.review.mandatory_issues import inject_mandatory_issues

    clause_results = inject_mandatory_issues(
        full_text=text,
        clause_results=clause_results,
        contract_type_code=ct_code,
        is_counterparty_form=True,  # Most dealer contracts are counterparty's form
    )

    # ── Step 5: Severity reclassification ─────────────────────────────────
    from runtime.review.severity_reclassifier import reclassify_for_consignment_dealer

    if ct_code in ("consignment_sales_agency", "direct_customer_sales_support", "dealer_agency"):
        for cr in clause_results:
            if not isinstance(cr, dict) or cr.get("is_mandatory"):
                continue
            if bool(cr.get("dedup_suppressed")) or bool(cr.get("keep_as_is")):
                continue
            cur_sev = str(cr.get("risk_tier") or "LOW").upper()
            new_sev, reasons = reclassify_for_consignment_dealer(
                severity=cur_sev,
                clause_text=str(cr.get("original_text") or ""),
                clause_title=str(cr.get("clause_title") or ""),
            )
            if new_sev != cur_sev:
                cr["risk_tier"] = new_sev
                cr["severity"] = new_sev
                if new_sev == "HIGH":
                    cr["high_risk"] = True
                    cr["must_fix"] = True

    # ── Step 6: Hallucination guard ───────────────────────────────────────
    from runtime.review.hallucination_guard import check_revision_text

    for cr in clause_results:
        if not isinstance(cr, dict) or cr.get("is_mandatory"):
            continue
        sr = str(cr.get("suggested_rewrite") or "").strip()
        if not sr:
            continue
        guard = check_revision_text(sr, contract_type_code=ct_code)
        if not guard.is_clean:
            cr["suggested_rewrite"] = None
            cr["has_rewrite_change"] = False

    # ── Stats ──────────────────────────────────────────────────────────────
    high_count = sum(1 for cr in clause_results if str(cr.get("risk_tier") or "").upper() == "HIGH")
    medium_count = sum(1 for cr in clause_results if str(cr.get("risk_tier") or "").upper() == "MEDIUM")
    low_count = sum(1 for cr in clause_results if str(cr.get("risk_tier") or "").upper() == "LOW")
    print(f"[아우리봇] 검토 완료: HIGH {high_count}건 / MEDIUM {medium_count}건 / LOW {low_count}건")

    # ── Step 7: Generate DOCX ─────────────────────────────────────────────
    from runtime.review.legal_review_docx import build_legal_review_docx

    original_clauses = [
        {
            "clause_id": c.clause_id,
            "article_number": c.article_number,
            "paragraph_number": c.paragraph_number,
            "clause_title": c.title,
            "display_path": c.display_path,
            "text": c.text,
        }
        for c in bundle.clauses
    ]

    docx_bytes = build_legal_review_docx(
        entity=entity,
        contract_type=contract_type,
        filename=input_path.name,
        clause_results=clause_results,
        original_clauses=original_clauses,
        detailed_contract_profile=detailed.to_dict(),
        include_low=include_low,
        contract_type_code=ct_code,
        is_counterparty_form=True,
    )

    output_path.write_bytes(docx_bytes)
    print(f"[아우리봇] DOCX 생성 완료: {output_path}")

    # ── Summary ────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"계약명: {input_path.name}")
    print(f"계약유형: {ct_code}")
    print(f"우리 회사: {detailed.our_party}")
    print(f"우리 측 지위: {detailed.our_legal_role}")
    print(f"HIGH: {high_count}건")
    print(f"MEDIUM: {medium_count}건")
    print(f"LOW excluded: {low_count}건 (기본 출력 제외)")
    print(f"Output: {output_path.resolve()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
