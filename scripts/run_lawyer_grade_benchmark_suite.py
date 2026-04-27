from __future__ import annotations

import json
import os
import sys
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))

from runtime.ai.config import load_ai_config
from runtime.ai.factory import create_ai_provider
from runtime.law.cache import JsonFileCache
from runtime.law.config import load_law_api_config
from runtime.law.search_service import LawSearchService
from runtime.review.clause_level import build_clause_level_result
from runtime.review.docx_writer import build_revision_docx
from runtime.rules.loader import RuleLoader
from runtime.services.query_service import RuleQueryService


@dataclass(frozen=True)
class BenchCase:
    case_id: str
    fixture_path: str
    entity: str
    contract_type: str


def _word_tokens(s: str) -> list[str]:
    import re

    t = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    return re.findall(r"[0-9A-Za-z가-힣]+|[^\s0-9A-Za-z가-힣]|\s+", t)


def _diff_ratio(a: str, b: str) -> float:
    import difflib

    aa = _word_tokens(a)
    bb = _word_tokens(b)
    sm = difflib.SequenceMatcher(a=aa, b=bb)
    changed = 0
    total = max(1, len(aa))
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        changed += (i2 - i1)
    return float(changed) / float(total)


def _docx_markers(docx_bytes: bytes) -> dict[str, Any]:
    z = zipfile.ZipFile(BytesIO(docx_bytes))
    xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    return {
        "docx_has_strike": ("<w:strike" in xml),
        "docx_has_red": ("w:color" in xml),
        "docx_red_run_ratio": (xml.count("w:color") / float(xml.count("<w:r") or 1)),
        "docx_has_legend": ("표시(legend):" in xml),
    }


def _score_bundle(*, bundle_meta: dict[str, Any], clause_results: list[dict[str, Any]], docx_markers: dict[str, Any]) -> tuple[int, list[str]]:
    notes: list[str] = []
    score = 0
    ai = bundle_meta.get("ai") if isinstance(bundle_meta.get("ai"), dict) else {}
    if bool(ai.get("enabled")) and bool(ai.get("used")):
        score += 15
    else:
        notes.append("ai_not_used")

    tier_counts = bundle_meta.get("tier_counts") if isinstance(bundle_meta.get("tier_counts"), dict) else {}
    must = int(tier_counts.get("must") or 0)
    if must > 0:
        score += 10
    else:
        notes.append("no_must_items")

    changed = 0
    ratios: list[float] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if not bool(cr.get("must_fix")):
            continue
        ot = str(cr.get("original_text") or "")
        rt = str(cr.get("suggested_rewrite") or "")
        if ot.strip() and rt.strip() and ot.strip() != rt.strip():
            changed += 1
            ratios.append(_diff_ratio(ot, rt))
    if changed > 0:
        avg = sum(ratios) / float(len(ratios) or 1)
        if avg <= 0.35:
            score += 15
        else:
            notes.append(f"rewrite_too_large(avg_ratio={avg:.2f})")
    else:
        notes.append("no_must_rewrites")

    if docx_markers.get("docx_has_strike") and docx_markers.get("docx_has_red"):
        score += 15
    else:
        notes.append("docx_redline_markers_missing")
    if docx_markers.get("docx_has_legend"):
        score += 5
    else:
        notes.append("docx_legend_missing")

    segs = sum(1 for cr in clause_results if isinstance(cr, dict) and isinstance(cr.get("changed_segments"), list) and cr.get("changed_segments"))
    if segs > 0:
        score += 10
    else:
        notes.append("changed_segments_empty")

    return min(score, 100), notes


def run() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    cases = [
        BenchCase("app_dev", "runtime/tests/fixtures/app_dev_contract.txt", "일룸/데스커", "앱개발/소프트웨어개발/SI/유지보수/SaaS"),
        BenchCase("purchase_install", "runtime/tests/fixtures/lg_purchase_installation.txt", "퍼시스", "장비공급/설치/시운전"),
        BenchCase("services", "runtime/tests/fixtures/services_consulting.txt", "all", "용역/컨설팅"),
        BenchCase("ads_model", "runtime/tests/fixtures/advertising_model.txt", "all", "광고/모델"),
        BenchCase("privacy", "runtime/tests/fixtures/dpa_privacy.txt", "all", "개인정보/처리위탁"),
        BenchCase("supply", "runtime/tests/fixtures/supply_purchase.txt", "all", "물품공급/구매/매매"),
        BenchCase("nda", "runtime/tests/fixtures/nda_basic.txt", "all", "NDA/비밀유지"),
        BenchCase("dealer", "runtime/tests/fixtures/dealer_agency.txt", "all", "대리점/유통"),
        BenchCase("upload_demo", "runtime/tests/fixtures/demo_upload.txt", "all", "all"),
        BenchCase("short", "runtime/tests/fixtures/short_summary.txt", "all", "all"),
    ]

    loader = RuleLoader()
    loader.load()
    service = RuleQueryService(loader)

    ai_cfg = load_ai_config()
    law_cfg = load_law_api_config()
    ai_mode = (os.getenv("AOURIBOT_BENCH_AI") or "auto").strip().lower()
    law_mode = (os.getenv("AOURIBOT_BENCH_LAW") or "auto").strip().lower()

    ai_provider = create_ai_provider(ai_cfg) if (ai_cfg.provider == "openai" and ai_cfg.api_key and ai_mode != "off") else None
    law_cache = JsonFileCache(path=repo_root / "aouri-bot" / "runtime" / "data" / "law_cache.json")
    law_service = LawSearchService(cfg=law_cfg, cache=law_cache) if (law_cfg.enabled and law_cfg.api_key and law_mode != "off") else None

    rows: list[dict[str, Any]] = []
    for c in cases:
        p = repo_root / "aouri-bot" / c.fixture_path
        text = p.read_text(encoding="utf-8") if p.exists() else ""
        bundle = build_clause_level_result(
            service=service,
            entity=c.entity,
            contract_type=c.contract_type,
            text=text,
            filename=p.name,
            answers=None,
            law_service=law_service,
            ai_provider=ai_provider,
            ai_model=ai_cfg.model if ai_provider else None,
            ai_timeout_sec=ai_cfg.timeout_sec if ai_provider else None,
            ai_max_tokens=min(max(ai_cfg.max_tokens, 2400), 3600) if ai_provider else None,
            ai_temperature=ai_cfg.temperature if ai_provider else None,
            max_clause_law_items=2 if law_service else 0,
        )

        original_clauses = [
            {
                "clause_id": cl.clause_id,
                "article_number": cl.article_number,
                "paragraph_number": cl.paragraph_number,
                "item_number": cl.item_number,
                "subitem_number": cl.subitem_number,
                "display_path": cl.display_path,
                "parent_clause_id": cl.parent_clause_id,
                "context_text": cl.context_text,
                "clause_title": cl.title,
                "text": cl.text,
            }
            for cl in (bundle.clauses or [])
        ]
        docx_bytes = build_revision_docx(
            entity=c.entity,
            contract_type=c.contract_type,
            filename=p.name,
            original_clauses=original_clauses,
            clause_results=bundle.clause_results,
            review_summary=(bundle.review.get("summary") if isinstance(bundle.review, dict) else None),
            law_search=None,
            questions=[],
        )
        markers = _docx_markers(docx_bytes)
        meta = bundle.meta if isinstance(bundle.meta, dict) else {}
        score, notes = _score_bundle(bundle_meta=meta, clause_results=bundle.clause_results, docx_markers=markers)
        rows.append(
            {
                "case_id": c.case_id,
                "contract_type": c.contract_type,
                "text_len": int(meta.get("text_length") or 0),
                "clause_count": int(meta.get("clause_count") or 0),
                "tier_counts": meta.get("tier_counts"),
                "ai": meta.get("ai"),
                "docx": markers,
                "score": score,
                "notes": notes,
            }
        )

    out_path = repo_root / "docs" / "review_output" / "180_lawyer_grade_benchmark_suite.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# 180) Lawyer-grade 벤치마크 스위트(초안)\n")
    lines.append(f"- ai_mode: `{ai_mode}` / law_mode: `{law_mode}`")
    lines.append("- 입력: runtime/tests/fixtures 기반 10종(확장 가능)\n")
    lines.append("## 결과 요약\n")
    for r in rows:
        lines.append(
            f"- {r['case_id']}: score={r['score']} tier_counts={r.get('tier_counts')} "
            f"ai_used={(r.get('ai') or {}).get('used') if isinstance(r.get('ai'), dict) else None} "
            f"docx_strike={(r.get('docx') or {}).get('docx_has_strike')} notes={','.join(r.get('notes') or [])}"
        )
    lines.append("\n## 산출 JSON(요약)\n")
    lines.append("```json")
    lines.append(json.dumps(rows, ensure_ascii=False, indent=2)[:12000])
    lines.append("```")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
