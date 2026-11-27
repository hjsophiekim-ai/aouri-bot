"""검토 실행 결과(04_review_deep.json)로 '수정안을 모두 넣은 계약' 의 상황별 결과를 계산해 보여 준다.

Usage: python scripts/check_scenarios.py RUN_DIR [--json OUT.json]

계약 원문(original_clauses)과 검토 결과의 살아 있는 수정안(변경추적본에 실제 적용된 것만 — redline_apply_report 기준)으로
수정 전/후 조항 지도를 만들고 runtime.review.deal_scenarios.evaluate 를 돌린다. 판정은 문구 포함 여부가 아니라 상황별
책임·권리·비용 결과다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime.review.deal_scenarios import Parties, evaluate  # noqa: E402
from runtime.review.scenario_gate import clause_maps_from_results  # noqa: E402


def main() -> int:
    run = Path(sys.argv[1])
    out_json = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else ""
    r = json.loads((run / "04_review_deep.json").read_text(encoding="utf-8"))["review"]
    meta = r.get("clause_meta") or {}
    pm = meta.get("party_map") or {}
    ours = [p["label"] for p in pm.get("parties") or [] if p.get("is_our_company")]
    theirs = [p["label"] for p in pm.get("parties") or [] if not p.get("is_our_company")]
    er = meta.get("entity_resolution") or {}
    al_o = [p.get("written_name") for p in er.get("parties") or [] if p.get("is_our_company") and p.get("written_name")]
    al_t = [p.get("written_name") for p in er.get("parties") or [] if not p.get("is_our_company") and p.get("written_name")]
    applied = {x.get("clause_id") for x in meta.get("redline_apply_report") or [] if x.get("status") == "applied"}
    original, revised = clause_maps_from_results(r.get("original_clauses") or [], r.get("clause_results") or [],
                                                 applied_ids=applied if meta.get("redline_apply_report") is not None else None)
    focus = ""
    try:
        focus = json.loads((run / "00_run_log.json").read_text(encoding="utf-8")).get("review_focus") or ""
    except Exception:  # noqa: BLE001
        pass
    answers = " ".join(str(v) for v in (r.get("question_answers") or {}).values()) if isinstance(r.get("question_answers"), dict) else ""
    desc: dict[str, str] = {}
    for cr in r.get("clause_results") or []:
        if isinstance(cr, dict) and cr.get("is_requested_clause_review") and cr.get("has_rewrite_change") \
                and (meta.get("redline_apply_report") is None or cr.get("clause_id") in applied):
            desc[str(cr.get("display_path"))] = (desc.get(str(cr.get("display_path")), "") + " " + str(cr.get("brief_action") or "")).strip()
    res = evaluate(original=original, revised=revised, parties=Parties(ours=ours or ["Customer"], theirs=theirs or ["Supplier"], aliases_ours=al_o, aliases_theirs=al_t),
                   request_text=focus, answers_text=answers, descriptions=desc)
    print(f"당사자: 우리={ours} 상대방={theirs}")
    print("\n[책임 — 상황별 결과 (수정 전 → 수정 후)]")
    for row in res["liability"]:
        print(f"- {row['label']}")
        for p in sorted(set(row["before"]) | set(row["after"])):
            print(f"    {p}: {row['before'].get(p, '정함 없음')} → {row['after'].get(p, '정함 없음')}")
    print("\n[책임한도]")
    for c in res["caps"]:
        print("  ", c)
    ren = res["renewal"]
    print("\n[연장] 의도:", ren.get("intent"), "| 수정 전:", ren.get("before_outcome"), "| 수정 후:", ren.get("after_outcome"))
    print("\n[종료 후 활동]", res["wind_down"]["paths"])
    for a in res["wind_down"]["activities"]:
        print("  ", a)
    print("\n[합의 기록]")
    for a in res["agreements"]:
        print(f"  - ({a['source']}) {a['content'][:100]} | 원문: {a['in_original']} | 수정안: {a['in_revision']}")
    print("\n[문제]")
    for p in res["problems"]:
        print(f"  [{p['severity']}] {p['code']} {p['paths']}: {p['message']}")
    if out_json:
        Path(out_json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nblock {len(res['blocking'])} / fix {len(res['to_fix']) - len(res['blocking'])} / warn {len(res['problems']) - len(res['to_fix'])}")
    return _assertions(res)


def _assertions(res: dict) -> int:
    """상황별 합격 기준 — 계약·조항 번호와 무관(상황 이름과 결과만 본다)."""
    codes = {p["code"] for p in res["problems"] if p["severity"] in ("block", "fix")}
    after = {row["scenario"]: row["after"] for row in res["liability"]}
    acts = {a["activity"]: a for a in res["wind_down"]["activities"]}
    ren = res["renewal"]
    checks = [
        ("S1 상대방 일반 과실 → 우리 책임 없음", not any(v == "책임 있음" for v in after.get("their_negligence", {}).values())),
        ("S1b 상대방 제공 디자인·지식재산 원인 → 우리 책임 없음", not any(v == "책임 있음" for v in after.get("their_design", {}).values())),
        ("S2 우리 제공 사양 → 조항 간 결론 하나(충돌 없음)",
         not ({"책임 있음", "책임 없음"} <= set(after.get("our_spec", {}).values())) and "LIABILITY_CONFLICT" not in codes),
        ("S2b 책임 방향(설명↔문구) 일치", "DIRECTION_MISMATCH" not in codes),
        ("S2c 책임한도: 건당/누적·비용·보호대상자 명시", not {"CAP_BASIS", "CAP_COSTS", "CAP_PERSONS"} & codes),
        ("S3 종료 후 재고 판매: 기간·사용권 있음",
         "재고 판매" not in acts or (acts["재고 판매"]["period"] and acts["재고 판매"]["license"])),
        ("S3b 종료 후 판매분 로열티 근거(계약기간 종료까지만 아님)", "WD_ROYALTY_TERM" not in codes),
        ("S4 무상 A/S·부품: 로열티 없음 명시, 비판매 로열티 없음",
         not {"ROYALTY_NONSALE", "ROYALTY_NONSALE_UNSTATED", "NEW_ROYALTY_BASE"} & codes),
        ("S4b 종료 후 판매분 A/S 포함·보증의무까지 사용권 존속", not {"WD_SERVICE_SCOPE", "WD_SERVICE_CAP"} & codes),
        ("S4c 기존 지역·표시 제한 유지", "WD_RESTRICTION" not in codes),
        ("S4d 종료 즉시 중단 조항과 연결·적용 범위", not {"WD_BLANKET_STOP", "WD_SCOPE", "WD_PERIOD", "WD_LICENSE"} & codes),
        ("S5 위반 없는 연장 → 상대방 동의 없이 연장",
         not (ren.get("intent") or {}).get("unless_breach")
         or (str(ren.get("after_outcome", "")).startswith(("자동", "우리 통지")) and not {c for c in codes if c.startswith("RENEWAL")})),
        ("S6 새 책임 확대 없음", "NEW_LIABILITY" not in codes),
    ]
    print("\n[상황별 판정]")
    for name, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    n = sum(ok for _, ok in checks)
    print(f"{'ALL PASS' if n == len(checks) else 'FAIL'} ({n}/{len(checks)})")
    return 0 if n == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
