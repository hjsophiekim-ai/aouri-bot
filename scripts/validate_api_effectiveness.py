from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class CaseResult:
    name: str
    ai_used: bool
    ai_selected_count: int | None
    law_enabled: bool
    law_query_count: int | None
    law_total_refs: int
    clause_law_total_refs: int
    clause_law_nonempty_clauses: int
    clause_results_count: int
    rewrites_count: int
    changed_segments_count: int


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    b = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    resp = urlopen(Request(url, data=b, method="POST", headers={"Content-Type": "application/json; charset=utf-8"})).read()
    return json.loads(resp.decode("utf-8"))


def _count_law_refs(law_search: dict[str, Any] | None) -> int:
    if not isinstance(law_search, dict):
        return 0
    results = law_search.get("results")
    if not isinstance(results, dict):
        return 0
    n = 0
    for k in ("laws", "precedents", "interpretations"):
        arr = results.get(k)
        if isinstance(arr, list):
            n += sum(1 for x in arr if isinstance(x, dict) and isinstance(x.get("title"), str) and x["title"].strip())
    return n


def run_case(*, base_url: str, name: str, text: str, entity: str, contract_type: str, ai_mode: str, law_mode: str) -> CaseResult:
    obj = _post_json(
        base_url.rstrip("/") + "/api/review/analyze",
        {"entity": entity, "contract_type": contract_type, "text": text, "ai_mode": ai_mode, "law_mode": law_mode},
    )
    ai = obj.get("ai") if isinstance(obj.get("ai"), dict) else {}
    law = obj.get("law_search") if isinstance(obj.get("law_search"), dict) else {}
    cr = obj.get("clause_results") if isinstance(obj.get("clause_results"), list) else []
    meta = obj.get("clause_meta") if isinstance(obj.get("clause_meta"), dict) else {}
    meta_ai = meta.get("ai") if isinstance(meta.get("ai"), dict) else {}

    rewrites = 0
    segs = 0
    clause_law_refs = 0
    clause_law_nonempty = 0
    for x in cr:
        if not isinstance(x, dict):
            continue
        sr = x.get("suggested_rewrite")
        if isinstance(sr, str) and sr.strip():
            rewrites += 1
        cs = x.get("changed_segments")
        if isinstance(cs, list) and cs:
            segs += 1
        rl = x.get("related_laws")
        n = _count_law_refs(rl) if isinstance(rl, dict) else 0
        clause_law_refs += n
        if n > 0:
            clause_law_nonempty += 1

    return CaseResult(
        name=name,
        ai_used=bool(ai.get("used")),
        ai_selected_count=(int(meta_ai.get("selected_count")) if isinstance(meta_ai.get("selected_count"), int) else None),
        law_enabled=bool(isinstance(law, dict) and law.get("enabled") is True),
        law_query_count=(len(law.get("queries") or []) if isinstance(law.get("queries"), list) else None),
        law_total_refs=_count_law_refs(law),
        clause_law_total_refs=clause_law_refs,
        clause_law_nonempty_clauses=clause_law_nonempty,
        clause_results_count=len(cr),
        rewrites_count=rewrites,
        changed_segments_count=segs,
    )


def write_report(*, out_path: Path, base_url: str, results: list[CaseResult]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# 181) API 효과 검증(자동)\n")
    lines.append(f"- base_url: `{base_url}`")
    lines.append(f"- generated_at: `{time.strftime('%Y-%m-%d %H:%M:%S')}`\n")
    lines.append("## 케이스 요약\n")
    for r in results:
        lines.append(
            f"- {r.name}: ai_used={r.ai_used}, ai_selected={r.ai_selected_count}, "
            f"law_enabled={r.law_enabled}, law_queries={r.law_query_count}, law_refs={r.law_total_refs}, "
            f"clause_law_refs={r.clause_law_total_refs}, clause_law_nonempty={r.clause_law_nonempty_clauses}, "
            f"clauses={r.clause_results_count}, rewrites={r.rewrites_count}, changed_segments={r.changed_segments_count}"
        )
    lines.append("\n## 판정 기준(요지)\n")
    lines.append("- AI 효과: ai_mode=auto/on에서 ai_used=true이고, ai_mode=off 대비 rewrites/changed_segments가 증가 또는 품질 지표가 개선되는지 확인")
    lines.append("- Law 효과: law_mode=auto/on에서 law_enabled=true이며, law_mode=off 대비 law_refs가 증가하는지 확인")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    base = os.environ.get("AOURIBOT_BASE_URL") or "http://127.0.0.1:8787"
    text_path = Path("runtime/tests/fixtures/app_dev_contract.txt")
    text = text_path.read_text(encoding="utf-8")
    entity = "일룸/데스커"
    contract_type = "앱개발/소프트웨어개발/SI/유지보수/SaaS"

    runs = [
        ("auto", "auto"),
        ("off", "auto"),
        ("auto", "off"),
        ("off", "off"),
    ]
    out: list[CaseResult] = []
    for ai_mode, law_mode in runs:
        out.append(
            run_case(
                base_url=base,
                name=f"ai={ai_mode}, law={law_mode}",
                text=text,
                entity=entity,
                contract_type=contract_type,
                ai_mode=ai_mode,
                law_mode=law_mode,
            )
        )
    write_report(
        out_path=Path(r"C:\Users\FURSYS\Desktop\aouribot\docs\review_output\181_api_effectiveness_validation.md"),
        base_url=base,
        results=out,
    )
    print(json.dumps([r.__dict__ for r in out], ensure_ascii=False, indent=2))
