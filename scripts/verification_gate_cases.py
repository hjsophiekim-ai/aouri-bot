"""필수 검증 단계 — 실패 사례 4종 + 통과·국문 사례의 '기대 결과 → 실제 결과 → 탐지 → 재작성/제거 → 재검증' 기록을 만든다.

Usage: python scripts/verification_gate_cases.py [OUT.txt]

AI 재작성은 결정적 가짜 응답(FakeAI)으로 재현한다 — 실제 AI 가 어떤 문구를 낼지는 이 기록의 대상이 아니고, 코드가 (1) 문제를
AI 에 넘기는지 (2) 돌아온 문구를 계약 전체로 다시 검증하는지 (3) 못 고치면 제거·출력 제한을 하는지를 보인다.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime.review import verification_gate as vg  # noqa: E402
from runtime.review.deal_scenarios import Parties  # noqa: E402

P = Parties(ours=["Customer"], theirs=["NDG"])
C_81 = "Customer shall provide warranty service for Design Products sold for twenty-four (24) months."
C_99 = "NDG shall indemnify and hold Customer harmless from all claims arising from NDG's negligence."
C_101 = "NDG shall indemnify Customer against all third party claims arising from the Design provided by NDG."
C_133 = "Upon termination or expiration of this Agreement, Customer shall immediately cease the manufacture and sale of Design Products."
CLAUSES = [{"display_path": p, "text": t} for p, t in
           (("Article 8.1", C_81), ("Article 9.9", C_99), ("Article 10.1", C_101), ("Article 13.3", C_133))]
SELL_OFF = C_133 + (" After the termination or expiration of this Agreement, Customer may sell off its existing inventory of"
                    " Design Products for a period of six (6) months and may use the Design for that purpose.")


class FakeAI:
    def __init__(self, fixes: dict[str, str]):
        self.fixes, self.calls = fixes, 0

    def complete(self, req):
        self.calls += 1
        return SimpleNamespace(content=json.dumps({"fixes": [{"id": k, "decision": "rewrite", "new_text": v,
                                                              "description": "검증 문제를 반영해 다시 씀"} for k, v in self.fixes.items()]},
                                                  ensure_ascii=False))


def cr(cid: str, path: str, target: str, repl: str, desc: str) -> dict:
    return {"clause_id": cid, "display_path": path, "has_rewrite_change": True, "risk_tier": "HIGH", "original_text": target,
            "brief_action": desc, "rewrite_reason": desc, "suggested_rewrite": repl,
            "redline_instruction": {"edit_type": "replace", "target_text": target, "replacement_text": repl, "final_clause_text": repl}}


CASES = [
    {
        "name": "1. 우리·상대방 역할이 뒤바뀐 수정(배상 주체 역전)",
        "clauses": CLAUSES, "parties": P,
        "edit": cr("F1", "Article 9.9", C_99, "Customer shall indemnify and hold NDG harmless from all claims arising from NDG's negligence.",
                   "상대방 책임을 명시: NDG 귀책 손해는 NDG가 배상하도록 정리"),
        "expected": "상대방 귀책 → 상대방(NDG) 책임, 우리 책임 없음. 설명(상대방 책임 명시)과 문구 주체가 같아야 함",
        "fix": "NDG shall indemnify and hold Customer harmless from all claims to the extent arising from NDG's negligence.",
        "request": "",
    },
    {
        "name": "2. 우리 책임한도를 두려다 상대방 책임한도를 신설",
        "clauses": CLAUSES, "parties": P,
        "edit": cr("F2", "Article 10.1", C_101, C_101 + " NDG's total liability under this Article shall not exceed EUR 50.000 in the aggregate.",
                   "우리 책임 한도를 EUR 50.000으로 제한"),
        "expected": "NDG 디자인 원인 청구는 NDG가 한도 없이 배상(상대방 한도 신설은 사용자 지시·합의·교환조건이 있어야 함)",
        "fix": C_101,
        "request": "",
    },
    {
        "name": "3. 부정문으로 책임이 뒤집힘",
        "clauses": CLAUSES, "parties": P,
        "edit": cr("F3", "Article 10.1", C_101,
                   "NDG shall not be obliged to indemnify Customer against any third party claims arising from the Design provided by NDG.",
                   "NDG 디자인 원인 제3자 청구는 NDG가 배상하도록 명확히 함"),
        "expected": "NDG 디자인 원인 청구 → NDG 책임 있음(설명과 같은 방향)",
        "fix": C_101 + " This obligation applies notwithstanding any other provision of this Agreement.",
        "request": "",
    },
    {
        "name": "4. 종료 후 재고 판매는 허용했지만 A/S 가 빠짐",
        "clauses": CLAUSES, "parties": P,
        "edit": cr("F4", "Article 13.3", C_133, SELL_OFF, "종료 후 재고 판매 허용"),
        "expected": "종료 후 판매·주문분의 A/S·보증수리 근거(기간·사용권)가 있음, 비판매 A/S 에 로열티 없음",
        "fix": SELL_OFF + (" Customer may also perform warranty and after-sales service, including the supply of spare parts, for all"
                           " Design Products sold before termination or during the sell-off period until the expiry of the applicable"
                           " warranty period, and may use the Design for that purpose; no royalty is payable for warranty repairs or"
                           " spare parts supplied free of charge."),
        "request": "6. 13.3 종료 후 재고 판매와 A/S 허용",
    },
]

PK = Parties(ours=["갑"], theirs=["을"])
K_CL = [{"display_path": "제9조 제1항", "text": "을은 을의 귀책사유로 갑에게 발생한 손해를 배상하여야 한다."},
        {"display_path": "제12조", "text": "갑은 을이 계약을 위반한 경우 이 계약을 해지할 수 있다."}]
CASES += [
    {
        "name": "5. (다른 유형·국문) 상대방 배상책임을 부정문으로 면제",
        "clauses": K_CL, "parties": PK,
        "edit": cr("K1", "제9조 제1항", K_CL[0]["text"], "을은 을의 귀책사유로 갑에게 발생한 손해에 대하여 책임을 지지 아니한다.",
                   "을의 배상 책임을 명확히 함"),
        "expected": "을 귀책 손해는 을이 배상", "fix": None, "request": "",
    },
    {
        "name": "6. (다른 유형·국문) '상호 공평' 을 이유로 우리 해지권 삭제",
        "clauses": K_CL, "parties": PK,
        "edit": cr("K2", "제12조", K_CL[1]["text"], "갑과 을은 상호 협의하여 이 계약을 해지한다.", "상호 공평하게 해지 절차 정비"),
        "expected": "갑(우리)의 위반 해지권 유지 — 근거(지시·합의·교환조건) 없으면 삭제 불가", "fix": None, "request": "",
    },
]


def show(res: dict, out: list[str]) -> None:
    out.append(f"   상태: {res['status']}  (검증 버전 {res['version']})")
    for p in res["critical"]:
        out.append(f"   ✗ [{p['category']}] {p['message']}")
    for g in res.get("grounds") or []:
        out.append(f"   · 근거 확인: {g['kind']} — {g['text'][:160]}")
    for e in res["effects"]:
        out.append(f"   효과 {e['path']}: {', '.join(e['effects'])}")
    for path, rows in (res.get("readings") or {}).items():
        for r in rows[:1]:
            out.append(f"   문구 재해석 {path}: 누가={r['누가']} / 누구에게={r['누구에게']} / 조건={r['조건'][:60]} / 무엇을={r['무엇을'][:60]}"
                       f" / 언제까지={r['언제까지']} / 예외·한도={r['예외·한도'][:80]} / 부정={r['부정']}")
    for s in res["situations"]:
        if s["result"] != "해당 없음":
            out.append(f"   상황 [{s['result']}] {s['situation']}: 기대={s['expected']} | 실제={s['actual']}")


def main() -> int:
    out: list[str] = []
    for c in CASES:
        out.append("=" * 100)
        out.append(c["name"])
        out.append(f"기대 결과(검토 목적·설명에서 먼저 정함): {c['expected']}")
        crs = [copy.deepcopy(c["edit"])]
        out.append(f"수정 문구: {crs[0]['suggested_rewrite']}")
        out.append("[1] 최초 검증")
        show(vg.verify(clauses=c["clauses"], clause_results=crs, parties=c["parties"], request_text=c["request"]), out)
        if c["fix"]:
            crs_a = [copy.deepcopy(c["edit"])]
            ai = FakeAI({c["edit"]["clause_id"]: c["fix"]})
            res = vg.run_verification_gate(clause_results=crs_a, clauses=c["clauses"], parties=c["parties"],
                                           contract_text=" ".join(x["text"] for x in c["clauses"]), provider=ai, request_text=c["request"])
            out.append(f"[2] AI 재작성 → 재검증 (AI 호출 {ai.calls}회)")
            out.append(f"   재작성 문구: {crs_a[0]['redline_instruction']['replacement_text']}")
            for h in res["history"]:
                out.append(f"   · {h['step']}: {h.get('status', h.get('result', ''))} (버전 {h.get('version', '-')})")
            show(res, out)
            if crs_a[0].get("undecided_terms"):
                out.append(f"   미확정 값 표시: {crs_a[0]['undecided_terms']}")
        crs_b = [copy.deepcopy(c["edit"])]
        res_b = vg.run_verification_gate(clause_results=crs_b, clauses=c["clauses"], parties=c["parties"],
                                         contract_text=" ".join(x["text"] for x in c["clauses"]), provider=None, request_text=c["request"])
        out.append("[3] AI 없이(또는 AI 가 못 고침) — 근거 없는·역전된 수정안 제거 → 재검증")
        for h in res_b["history"]:
            out.append(f"   · {h['step']}: {h.get('status', '')} {('제거 ' + str(h['removed'])) if h.get('removed') else ''}")
        out.append(f"   최종: {res_b['status']} / 보류 사유: {(crs_b[0].get('redline_instruction') or {}).get('hold_reason', '-')[:200]}")
        for u in res_b["unresolved"]:
            out.append(f"   ⚠ 미해결 [{u['category']}] {u['paths']}: {u['detail'][:200]}")
        crs_c = [copy.deepcopy(c["edit"])]
        res_c = vg.run_verification_gate(clause_results=crs_c, clauses=c["clauses"], parties=c["parties"],
                                         contract_text=" ".join(x["text"] for x in c["clauses"]), provider=FakeAI({}),
                                         request_text=c["request"], remove_on_fail=False)
        out.append(f"[4] 제거하지 않고 남긴 경우의 출력 판정: {res_c['status']}"
                   + (" → 최종본·서명 가능 판정 금지, 변경추적본·클린본에 '검증 미통과 초안' 표지" if res_c["status"] == vg.STATUS_FAIL else ""))
    text = "\n".join(out)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
