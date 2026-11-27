"""저장된 검토 결과(04_review_deep.json)에 필수 검증 단계(verification_gate)를 실행한다 — 실제 계약 출력의 오탐·과적합 확인용.

Usage: python scripts/check_verification_gate.py RUN_DIR [RUN_DIR ...] [--json OUT.json]

각 RUN 에 대해 (1) 저장된 최종 수정안 그대로 검증(verify) — 기존 출력이 통과했을지, (2) 제거·재검증까지 하는 게이트(AI 없음)
— 실제 파이프라인에서 어떤 수정안이 빠지고 최종 상태가 무엇인지 보여 준다. AI 재작성은 실행하지 않는다(무과금·결정적).
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime.review import verification_gate as vg  # noqa: E402
from runtime.review.deal_scenarios import Parties  # noqa: E402


def load(run: Path) -> tuple[dict, str, str]:
    r = json.loads((run / "04_review_deep.json").read_text(encoding="utf-8"))["review"]
    focus = ""
    for name in ("00_run_log.json",):
        try:
            focus = json.loads((run / name).read_text(encoding="utf-8")).get("review_focus") or ""
        except Exception:  # noqa: BLE001
            pass
    answers = r.get("question_answers") if isinstance(r.get("question_answers"), dict) else {}
    return r, focus, "\n".join(f"- {k}: {v}" for k, v in answers.items() if str(v).strip())


def parties_of(meta: dict) -> Parties:
    pm = meta.get("party_map") or {}
    ours = [p["label"] for p in pm.get("parties") or [] if p.get("is_our_company") and p.get("label")]
    theirs = [p["label"] for p in pm.get("parties") or [] if not p.get("is_our_company") and p.get("label")]
    er = meta.get("entity_resolution") or {}
    al_o = [p.get("written_name") for p in er.get("parties") or [] if p.get("is_our_company") and p.get("written_name")]
    al_t = [p.get("written_name") for p in er.get("parties") or [] if not p.get("is_our_company") and p.get("written_name")]
    return Parties(ours=ours or ["Customer"], theirs=theirs or ["Supplier"], aliases_ours=al_o, aliases_theirs=al_t,
                   confirmed=bool(ours))


def one(run: Path) -> dict:
    r, focus, answers = load(run)
    meta = r.get("clause_meta") or {}
    P = parties_of(meta)
    crs = [c for c in r.get("clause_results") or [] if isinstance(c, dict)]
    clauses = r.get("original_clauses") or []
    before = vg.verify(clauses=clauses, clause_results=crs, parties=P, request_text=focus, answers_text=answers)
    crs2 = copy.deepcopy(crs)
    gate = vg.run_verification_gate(clause_results=crs2, clauses=clauses, parties=P, contract_text=r.get("text") or "",
                                    request_text=focus, answers_text=answers, provider=None)
    return {"run": str(run), "parties": {"ours": P.ours, "theirs": P.theirs},
            "live_edits": len(vg.live_edits(crs)), "changed_paths": before["changed_paths"],
            "saved_output": {"status": before["status"],
                             "critical": [{"category": p["category"], "code": p["code"], "paths": p["paths"], "message": p["message"]}
                                          for p in before["critical"]],
                             "residual_original": [{"code": p["code"], "paths": p["paths"]} for p in before["residual_original"]],
                             "grounds": before["grounds"], "undecided_values": before["undecided_values"][:10]},
            "gate": {"status": gate["status"], "removed": gate["removed_edits"], "history": gate["history"],
                     "unresolved": gate["unresolved"], "basis_needs_confirmation": gate["basis"]["needs_confirmation"]},
            "situations": before["situations"], "effects": before["effects"]}


def main() -> int:
    args = [a for a in sys.argv[1:]]
    out_json = ""
    if "--json" in args:
        i = args.index("--json")
        out_json = args[i + 1]
        del args[i:i + 2]
    rows = [one(Path(a)) for a in args]
    for x in rows:
        print(f"\n=== {x['run']}  (우리={x['parties']['ours']} 상대방={x['parties']['theirs']})")
        print(f"출력 수정안 {x['live_edits']}건 / 바뀐 조항 {len(x['changed_paths'])}개")
        print(f"[저장된 최종 출력 그대로 검증] {x['saved_output']['status']} — 차단 문제 {len(x['saved_output']['critical'])}건")
        for p in x["saved_output"]["critical"]:
            print(f"   - [{p['category']}] {p['code']} {p['paths']}: {p['message'][:220]}")
        for g in x["saved_output"]["grounds"]:
            print(f"   · 근거 확인: {g['code']} {g['paths']} ← {g['kind']}: {g['text'][:120]}")
        print(f"   원문 잔존(수정과 무관, 차단 안 함): {[p['code'] for p in x['saved_output']['residual_original']]}")
        print(f"[게이트 실행(AI 없음: 제거→재검증)] 최종 {x['gate']['status']}")
        for h in x["gate"]["history"]:
            print(f"   · {h['step']}: {h.get('status', '')} {('제거 ' + str(h['removed'])) if h.get('removed') else ''}")
        for u in x["gate"]["unresolved"]:
            print(f"   ⚠ 미해결 [{u['category']}] {u['paths']}: {u['detail'][:200]}")
        print("   [상황별]")
        for s in x["situations"]:
            print(f"     {s['result']:<5} {s['situation']}: 기대={s['expected'][:60]} / 실제={s['actual'][:90]}")
    if out_json:
        Path(out_json).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
