#!/usr/bin/env python3
"""
Aouribot Redline Generator — CLI 도구

사용법:
  python scripts/generate_redline.py <input.docx> [options]

출력:
  (A) redline_<이름>.docx  — tracked changes + Word 코멘트
  (B) clean_<이름>.docx    — 변경사항 수락 완료 (날인용)
  (C) 검토보고서.docx      — 리스크 요약 DOCX

예시:
  python scripts/generate_redline.py 위탁운영계약서.docx --entity 퍼시스 --type 위탁운영
  python scripts/generate_redline.py NDA.docx --entity 퍼시스 --type NDA --author 퍼시스법무
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# 패키지 루트를 sys.path에 추가
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="계약서 DOCX에 AI 법무검토 tracked changes 적용",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input", help="원본 계약서 DOCX 파일 경로")
    parser.add_argument("--entity",  "-e", default="퍼시스", help="의뢰인 (기본: 퍼시스)")
    parser.add_argument("--type",    "-t", default="",      help="계약 유형 (예: NDA, 위탁운영)")
    parser.add_argument("--focus",   "-f", default="",      help="중점 검토 내용")
    parser.add_argument("--author",  "-a", default="퍼시스법무", help="작성자 표시 (기본: 퍼시스법무)")
    parser.add_argument("--outdir",  "-o", default=".",     help="출력 디렉토리 (기본: 현재)")
    parser.add_argument("--no-ai",   action="store_true",   help="AI LLM 호출 없이 룰 기반만 실행")
    parser.add_argument("--validate", "-v", action="store_true", help="출력 DOCX 검증 실행")
    args = parser.parse_args()

    src = Path(args.input).resolve()
    if not src.exists():
        print(f"[ERROR] 파일이 없습니다: {src}")
        sys.exit(1)
    if src.suffix.lower() != ".docx":
        print(f"[ERROR] DOCX 파일만 지원합니다: {src.suffix}")
        sys.exit(1)

    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    stem = src.stem

    print(f"\n[1/4] 파일 읽기: {src.name}")
    original_bytes = src.read_bytes()

    print(f"[2/4] 텍스트 추출 및 법무 분석 시작...")
    from runtime.review.text_extract import extract_text_from_file
    from runtime.review.clause_level import build_clause_level_result
    from runtime.rules.loader import RuleLoader
    from runtime.services.query_service import RuleQueryService
    from runtime.ai.config import load_ai_config
    from runtime.ai.factory import create_ai_provider

    extraction = extract_text_from_file(src)
    if not extraction.success:
        print(f"[ERROR] 텍스트 추출 실패: {extraction.error}")
        sys.exit(1)
    print(f"  추출 완료: {len(extraction.text)}자 ({extraction.method})")

    # AI 설정
    ai_provider = None
    ai_model = None
    ai_cfg = None
    if not args.no_ai:
        try:
            ai_cfg = load_ai_config()
            if ai_cfg.api_key:
                ai_provider = create_ai_provider(ai_cfg)
                ai_model = ai_cfg.model
                print(f"  AI: {ai_cfg.provider} / {ai_model}")
            else:
                print("  AI: 미설정 (API 키 없음) — 룰 기반만 실행")
        except Exception as e:
            print(f"  AI 설정 오류 (무시): {e}")

    loader = RuleLoader()
    service = RuleQueryService(loader)

    entity = args.entity or "퍼시스"
    contract_type = args.type or ""
    review_focus = args.focus or None

    bundle = build_clause_level_result(
        service=service,
        entity=entity,
        contract_type=contract_type,
        text=extraction.text,
        filename=src.name,
        answers=None,
        review_focus=review_focus,
        law_service=None,
        ai_provider=ai_provider,
        ai_model=ai_model,
        ai_timeout_sec=ai_cfg.timeout_sec if ai_cfg and ai_provider else None,
        ai_max_tokens=min(ai_cfg.max_tokens, 3600) if ai_cfg and ai_provider else None,
        ai_temperature=ai_cfg.temperature if ai_cfg and ai_provider else None,
        max_clause_law_items=0,
    )
    clause_results = bundle.clause_results or []
    high = sum(1 for c in clause_results if (c.get("risk_tier") or "").upper() == "HIGH")
    med  = sum(1 for c in clause_results if (c.get("risk_tier") or "").upper() == "MEDIUM")
    print(f"  분석 완료: HIGH={high} MEDIUM={med} 전체={len(clause_results)}")

    print(f"\n[3/4] Redline DOCX 생성 중...")
    from runtime.review.redline_builder import build_redline_from_analysis
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        redline_bytes, clean_bytes = build_redline_from_analysis(
            original_bytes=original_bytes,
            clause_results=clause_results,
            author=args.author,
            date=date_str,
        )
    except Exception as e:
        print(f"[ERROR] Redline 생성 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    redline_path = outdir / f"redline_{stem}.docx"
    clean_path   = outdir / f"clean_{stem}.docx"
    redline_path.write_bytes(redline_bytes)
    clean_path.write_bytes(clean_bytes)
    print(f"  (A) {redline_path}  ({len(redline_bytes)//1024} KB)")
    print(f"  (B) {clean_path}   ({len(clean_bytes)//1024} KB)")

    print(f"\n[4/4] 검토보고서.docx 생성 중...")
    try:
        from runtime.review.docx_writer import build_revision_docx
        from runtime.review.clause_extraction import extract_clauses
        clauses, _ = extract_clauses(extraction.text)
        original_clauses_for_docx = [
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
            for c in (clauses or [])
        ]
        report_bytes = build_revision_docx(
            entity=entity,
            contract_type=contract_type,
            filename=src.name,
            original_clauses=original_clauses_for_docx,
            clause_results=clause_results,
            review_summary=dict(bundle.review),
            final_review_context=(bundle.meta.get("final_review_context") if isinstance(bundle.meta, dict) else None),
        )
        report_path = outdir / f"검토보고서_{stem}.docx"
        report_path.write_bytes(report_bytes)
        print(f"  (C) {report_path}  ({len(report_bytes)//1024} KB)")
    except Exception as e:
        print(f"  [WARN] 검토보고서 생성 실패 (redline/clean은 정상): {e}")

    if args.validate:
        print(f"\n[검증] DOCX 구조 검사...")
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent / "office"))
        from validate import validate
        for p in [redline_path, clean_path]:
            print(f"  {p.name}:")
            validate(str(p))

    print(f"\n완료! 출력 디렉토리: {outdir}/")
    print(f"  (A) redline_{stem}.docx  — tracked changes + Word 코멘트")
    print(f"  (B) clean_{stem}.docx    — 날인용 클린본")
    print(f"  (C) 검토보고서_{stem}.docx — 결재용 리포트")


if __name__ == "__main__":
    main()
