"""AI 경로 hold-out — 실제 LLM 을 켠 상태로 계약유형별 검토를 돌린다.

pytest 하네스는 conftest 가 키를 제거해 AI-off 로만 돈다. AI 경로에서만
나타나는 오염(에이전트가 다른 유형의 논점을 끌어오는 등)을 잡으려면 이렇게
따로 확인해야 한다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# cwd 에 의존하지 않는다 — 이 파일 위치 기준으로 code repo 루트를 잡는다
# (tech_repo_layout: 외부 aouribot 아래에 runtime 트리를 만들지 말 것).
ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, ROOT)

from runtime.ai.config import load_ai_config  # noqa: E402
from runtime.ai.factory import create_ai_provider, is_ai_enabled  # noqa: E402
from runtime.review.clause_level import build_clause_level_result  # noqa: E402
from runtime.rules.loader import RuleLoader  # noqa: E402
from runtime.services.query_service import RuleQueryService  # noqa: E402

FIX = Path(ROOT) / "runtime" / "tests" / "fixtures"

CASES = [
    ("nda", "webzen_nda.txt", "NDA/비밀유지", ("판매장려금", "지체상금", "숏폼", "기성고")),
    ("license", "_lm_license_1.txt", "라이선스", ("판매장려금", "판촉비", "기성고", "착공")),
    ("construction", "construction_works_contract.txt", "공사도급", ("숏폼", "협찬 표시", "소스코드", "판매장려금")),
    ("dealer", "dealer_agency.txt", "대리점/유통", ("기성고", "착공", "숏폼", "소스코드")),
    ("service", "services_consulting.txt", "용역/자문", ("판매장려금", "기성고", "숏폼")),
]

cfg = load_ai_config()
print("AI:", is_ai_enabled(cfg), cfg.provider, cfg.model)
provider = create_ai_provider(cfg)

loader = RuleLoader()
loader.load()
service = RuleQueryService(loader)

summary: list[str] = []
for key, fixture, ctype, banned in CASES:
    text = (FIX / fixture).read_text(encoding="utf-8")
    bundle = build_clause_level_result(
        service=service, entity="퍼시스", contract_type=ctype, text=text,
        filename=fixture, answers=None, review_focus=None, law_service=None,
        ai_provider=provider, ai_model=cfg.model,
        ai_timeout_sec=cfg.timeout_sec, ai_max_tokens=cfg.max_tokens,
        ai_temperature=cfg.temperature,
    )
    meta = bundle.meta
    ls = meta.get("legal_state") or {}
    gate = meta.get("final_counsel_gate") or {}
    ff = meta.get("final_findings") or {}
    live = [
        c for c in bundle.clause_results
        if isinstance(c, dict) and not c.get("dedup_suppressed") and not c.get("keep_as_is")
    ]

    contamination: list[str] = []
    for c in live:
        blob = " ".join(
            str(c.get(k) or "")
            for k in (
                "issue_title", "problem", "rewrite_reason", "legal_business_reason",
                "suggested_rewrite", "recommendation_text",
            )
        )
        for term in banned:
            if term in blob and term not in text:
                contamination.append(f"{c.get('clause_id')}:{term}")

    failed = [c["key"] for c in (gate.get("checks") or []) if not c.get("ok")]
    ok = not contamination and not failed
    summary.append(
        f"{'PASS' if ok else 'FAIL'} {key:13s} type={ls.get('contract_type'):24s} "
        f"txn={ls.get('transaction_type'):22s} HIGH={ff.get('high_count')} MED={ff.get('medium_count')}"
    )
    if contamination:
        summary.append(f"       오염: {contamination[:4]}")
    if failed:
        for c in gate.get("checks") or []:
            if not c.get("ok"):
                summary.append(f"       자가점검 실패 {c['key']}: {str(c.get('detail') or '')[:120]}")
    ca = meta.get("counsel_agent") or {}
    if ca.get("issues"):
        for i in ca["issues"][:3]:
            summary.append(f"       [{i['severity']}/{i['axis']}] {i['title'][:70]}")

print()
print("\n".join(summary))
