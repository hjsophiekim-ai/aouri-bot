"""필수 검증 단계(verification_gate) — 우리 관점·문구 의미·계약 전체 완결성, 실패 시 재작성·제거·출력 제한(2026-11-03).

사례는 계약 이름·조항 번호에 기대지 않는다: 영문 라이선스형(Customer/NDG)과 국문 공급형(갑/을) 두 벌로 같은 규칙을 본다.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from runtime.review.deal_scenarios import Parties
from runtime.review import verification_gate as vg

P = Parties(ours=["Customer"], theirs=["NDG"])

C_99 = "NDG shall indemnify and hold Customer harmless from all claims arising from NDG's negligence."
C_101 = "NDG shall indemnify Customer against all third party claims arising from the Design provided by NDG."
C_81 = "Customer shall provide warranty service for Design Products sold for twenty-four (24) months."
C_133 = "Upon termination or expiration of this Agreement, Customer shall immediately cease the manufacture and sale of Design Products."

CLAUSES = [
    {"display_path": "Article 8.1", "text": C_81},
    {"display_path": "Article 9.9", "text": C_99},
    {"display_path": "Article 10.1", "text": C_101},
    {"display_path": "Article 13.3", "text": C_133},
]


def _cr(cid: str, path: str, target: str, repl: str, desc: str, **kw) -> dict:
    return {"clause_id": cid, "display_path": path, "has_rewrite_change": True, "risk_tier": "HIGH", "original_text": target,
            "brief_action": desc, "rewrite_reason": desc, "suggested_rewrite": repl,
            "redline_instruction": {"edit_type": "replace", "target_text": target, "replacement_text": repl,
                                    "final_clause_text": repl}, **kw}


class FakeAI:
    """검증 문제를 받으면 정해 둔 수정 문구를 돌려준다 — 받은 프롬프트를 기록해 문제가 실제로 전달됐는지 본다."""

    def __init__(self, fixes: dict[str, str]):
        self.fixes = fixes
        self.prompts: list[str] = []

    def complete(self, req):
        user = getattr(req, "user", None) or json.dumps(getattr(req, "__dict__", {}), ensure_ascii=False, default=str)
        self.prompts.append(str(user))
        out = [{"id": k, "decision": "rewrite", "new_text": v, "description": "상대방 귀책·상대방 디자인 원인 손해는 상대방이 배상하도록 유지"}
               for k, v in self.fixes.items()]
        return SimpleNamespace(content=json.dumps({"fixes": out}, ensure_ascii=False))


def _codes(res):
    return {p["code"] for p in res["critical"]}


# ── 사례 1: 우리와 상대방의 역할이 뒤바뀐 수정 ─────────────────────────────────────

ROLE_SWAP = "Customer shall indemnify and hold NDG harmless from all claims arising from NDG's negligence."


def test_role_swap_detected_then_rewritten_and_reverified():
    crs = [_cr("F1", "Article 9.9", C_99, ROLE_SWAP, "상대방 책임을 명시: NDG 귀책 손해는 NDG가 배상하도록 정리")]
    first = vg.verify(clauses=CLAUSES, clause_results=crs, parties=P)
    assert first["status"] == vg.STATUS_FAIL
    cats = {p["category"] for p in first["critical"]}
    assert vg.CAT_DIRECTION in cats and vg.CAT_MISMATCH in cats
    assert {"OUR_LIABILITY_UP", "THEIR_LIABILITY_DOWN", "DESC_EFFECT_MISMATCH"} <= _codes(first)
    # 상황별: 상대방 귀책인데 우리가 책임
    sit = {r["situation"]: r for r in first["situations"]}
    assert sit["상대방 귀책"]["result"] == "불일치"
    fixed = "NDG shall indemnify and hold Customer harmless from all claims to the extent arising from NDG's negligence."
    ai = FakeAI({"F1": fixed})
    res = vg.run_verification_gate(clause_results=crs, clauses=CLAUSES, parties=P, contract_text=C_99, provider=ai)
    assert ai.prompts and "책임 방향 역전" in ai.prompts[0]
    assert res["status"] == vg.STATUS_PASS, res["unresolved"]
    assert crs[0]["redline_instruction"]["replacement_text"] == fixed and crs[0]["suggested_rewrite"] == fixed
    steps = [h["step"] for h in res["history"]]
    assert steps[0] == "검증 1" and any("재검증" in s for s in steps)
    assert res["history"][0]["status"] == vg.STATUS_FAIL and res["status"] == vg.STATUS_PASS
    assert res["version"] == vg.fingerprint(crs)


def test_role_swap_without_ai_is_removed_and_original_kept():
    crs = [_cr("F1", "Article 9.9", C_99, ROLE_SWAP, "상대방 책임을 명시: NDG 귀책 손해는 NDG가 배상하도록 정리")]
    res = vg.run_verification_gate(clause_results=crs, clauses=CLAUSES, parties=P, contract_text=C_99, provider=None)
    assert crs[0]["redline_instruction"]["held"] is True
    assert "필수 검증 미통과" in crs[0]["redline_instruction"]["hold_reason"]
    assert res["status"] != vg.STATUS_FAIL and not res["critical"]
    assert res["removed_edits"] and res["removed_edits"][0]["clause_id"] == "F1"
    assert not vg.RX_INTERNAL.search(res["removed_edits"][0]["reason"])


# ── 사례 2: 우리 한도를 두려다 상대방 책임한도를 신설 ─────────────────────────────

WRONG_CAP = C_101 + " NDG's total liability under this Article shall not exceed EUR 50.000 in the aggregate."


def test_counterparty_cap_wrongly_created():
    crs = [_cr("F2", "Article 10.1", C_101, WRONG_CAP, "우리 책임 한도를 EUR 50.000으로 제한")]
    res = vg.verify(clauses=CLAUSES, clause_results=crs, parties=P)
    assert "THEIR_CAP_NEW" in _codes(res)
    assert any(p["code"] == "DESC_EFFECT_MISMATCH" and "주체" in p["message"] for p in res["critical"])
    eff = next(r for r in res["effects"] if r["path"] == "Article 10.1")
    assert "상대방 책임한도 신설" in eff["effects"]
    # 근거가 있으면(사용자가 10.1 에 상대방 한도를 수용한다고 지시) 보호 축소로 막지 않는다 — 설명 불일치는 그대로 남는다
    res2 = vg.verify(clauses=CLAUSES, clause_results=crs, parties=P,
                     request_text="10.1 NDG 책임 한도 EUR 50.000 수용(로열티 인하와 교환)")
    assert "THEIR_CAP_NEW" not in _codes(res2)
    assert any(g["code"] == "THEIR_CAP_NEW" and g["kind"] == "사용자 지시" for g in res2["grounds"])


def test_fairness_alone_is_not_a_ground():
    crs = [_cr("F2", "Article 10.1", C_101, WRONG_CAP, "상호 공평을 위해 상대방 부담을 줄임")]
    res = vg.verify(clauses=CLAUSES, clause_results=crs, parties=P, request_text="10.1 상호 공평하게")
    p = next(p for p in res["critical"] if p["code"] == "THEIR_CAP_NEW")
    assert "상호 공평" in p["message"]


# ── 사례 3: 부정문으로 책임이 뒤집힘 ───────────────────────────────────────────────

NEGATED = "NDG shall not be obliged to indemnify Customer against any third party claims arising from the Design provided by NDG."


def test_negation_flip_detected_and_reading_shows_negation():
    crs = [_cr("F3", "Article 10.1", C_101, NEGATED, "NDG 디자인 원인 제3자 청구는 NDG가 배상하도록 명확히 함")]
    res = vg.verify(clauses=CLAUSES, clause_results=crs, parties=P)
    codes = _codes(res)
    assert "THEIR_DIRECTION_MISMATCH" in codes and "THEIR_LIABILITY_DOWN" in codes
    rd = res["readings"]["Article 10.1"][0]
    assert rd["누가"] == "상대방" and rd["부정"] == "있음"
    ai = FakeAI({"F3": C_101 + " This obligation applies notwithstanding any other provision of this Agreement."})
    out = vg.run_verification_gate(clause_results=crs, clauses=CLAUSES, parties=P, contract_text=C_101, provider=ai)
    assert out["status"] == vg.STATUS_PASS, out["unresolved"]


# ── 사례 4: 종료 후 재고 판매를 허용하면서 A/S 를 빠뜨림 ──────────────────────────

SELL_OFF = C_133 + (" After the termination or expiration of this Agreement, Customer may sell off its existing inventory of"
                    " Design Products for a period of six (6) months and may use the Design for that purpose.")
WITH_AS = SELL_OFF + (" Customer may also perform warranty and after-sales service, including the supply of spare parts, for all"
                      " Design Products sold before termination or during the sell-off period until the expiry of the applicable"
                      " warranty period, and may use the Design for that purpose; no royalty is payable for warranty repairs or"
                      " spare parts supplied free of charge.")


def test_post_termination_service_gap_detected_then_fixed():
    crs = [_cr("F4", "Article 13.3", C_133, SELL_OFF, "종료 후 재고 판매 허용", request_index=6)]
    res = vg.verify(clauses=CLAUSES, clause_results=crs, parties=P, request_text="6. 13.3 종료 후 재고 판매와 A/S 허용")
    assert "WD_SERVICE_MISSING" in _codes(res)
    sit = {r["situation"]: r for r in res["situations"]}
    assert sit["종료 후 A/S"]["result"] == "불일치"
    # 근거 없는 '6개월' 은 제안값(미합의)
    assert any("6" in u["value"] for u in res["undecided_values"])
    ai = FakeAI({"F4": WITH_AS})
    out = vg.run_verification_gate(clause_results=crs, clauses=CLAUSES, parties=P, contract_text=C_133, provider=ai,
                                   request_text="6. 13.3 종료 후 재고 판매와 A/S 허용")
    assert "WD_SERVICE_MISSING" not in _codes(out), out["unresolved"]
    assert out["status"] == vg.STATUS_PASS, out["unresolved"]
    assert any("미합의" in u for u in crs[0].get("undecided_terms") or [])


def test_unresolved_after_failed_repair_blocks_final_output():
    """AI 가 고치지 못하고 제거로도 해결되지 않는 문제(수정한 조항에 남은 공백)는 '검증 미통과 초안' 으로 남긴다."""
    crs = [_cr("F4", "Article 13.3", C_133, SELL_OFF, "종료 후 재고 판매 허용")]
    # 제거하면 공백도 사라지므로, 제거를 끈 상태(사용자가 요청한 핵심 수정 — remove_on_fail=False)로 출력 제한을 본다
    res = vg.run_verification_gate(clause_results=crs, clauses=CLAUSES, parties=P, contract_text=C_133,
                                   provider=FakeAI({}), remove_on_fail=False)
    assert res["status"] == vg.STATUS_FAIL
    assert res["unresolved"] and all(not vg.RX_INTERNAL.search(u["detail"]) for u in res["unresolved"])
    meta = {"verification_gate": vg.compact(res)}
    assert vg.is_failed(meta)


# ── 통과 사례·과적합 방지(국문 갑/을) ─────────────────────────────────────────────

def test_grounded_protective_edit_passes():
    o = "Customer shall indemnify NDG against all claims arising from the Design Products."
    n = "Customer shall indemnify NDG against all claims to the extent caused by Customer's negligence."
    cl = [{"display_path": "Article 9.9", "text": o}]
    crs = [_cr("G1", "Article 9.9", o, n, "우리 귀책 있는 손해로 한정")]
    res = vg.run_verification_gate(clause_results=crs, clauses=cl, parties=P, contract_text=o,
                                   request_text="9.9 우리 귀책 있는 손해로 한정해 주세요")
    assert res["status"] == vg.STATUS_PASS, res["unresolved"]
    eff = res["effects"][0]["effects"]
    assert any("우리 책임 감소" in e for e in eff)


PK = Parties(ours=["갑"], theirs=["을"])
K_CL = [{"display_path": "제9조 제1항", "text": "을은 을의 귀책사유로 갑에게 발생한 손해를 배상하여야 한다."},
        {"display_path": "제12조", "text": "갑은 을이 계약을 위반한 경우 이 계약을 해지할 수 있다."}]


def test_korean_contract_their_liability_removed_without_ground_is_removed():
    crs = [_cr("K1", "제9조 제1항", K_CL[0]["text"], "을은 을의 귀책사유로 갑에게 발생한 손해에 대하여 책임을 지지 아니한다.",
               "을의 배상 책임을 명확히 함")]
    res = vg.verify(clauses=K_CL, clause_results=crs, parties=PK)
    assert "THEIR_LIABILITY_DOWN" in _codes(res)
    out = vg.run_verification_gate(clause_results=crs, clauses=K_CL, parties=PK, contract_text=K_CL[0]["text"])
    assert crs[0]["redline_instruction"].get("held") and out["status"] != vg.STATUS_FAIL


def test_korean_our_right_removed_needs_ground():
    crs = [_cr("K2", "제12조", K_CL[1]["text"], "갑과 을은 상호 협의하여 이 계약을 해지한다.", "상호 공평하게 해지 절차 정비")]
    res = vg.verify(clauses=K_CL, clause_results=crs, parties=PK)
    assert "OUR_RIGHT_REMOVED" in _codes(res)
    res2 = vg.verify(clauses=K_CL, clause_results=crs, parties=PK, request_text="제12조 갑 단독 해지권 삭제에 동의(대금 5% 인하 조건)")
    assert "OUR_RIGHT_REMOVED" not in _codes(res2)


def test_low_tier_edit_is_not_verified_because_it_is_not_output():
    """변경추적본·클린본에 들어가지 않는 LOW 참고 문안은 검증 대상(같은 버전)에 넣지 않는다 — docx_redline 과 같은 기준."""
    crs = [_cr("L1", "Article 9.9", C_99, ROLE_SWAP, "참고 문안", risk_tier="LOW")]
    crs[0]["risk_tier"] = "LOW"
    res = vg.verify(clauses=CLAUSES, clause_results=crs, parties=P)
    assert res["status"] == vg.STATUS_NONE and not res["critical"]


def test_no_edits_no_failure():
    res = vg.run_verification_gate(clause_results=[], clauses=K_CL, parties=PK)
    assert res["status"] == vg.STATUS_NONE and not res["critical"]
    assert "우리가 확보해야 할 권리(요청·답변에 없음)" in res["basis"]["needs_confirmation"]


# ── 같은 버전 검증 — 수정이 바뀌면 이전 결과 폐기 ─────────────────────────────────

def test_stale_verification_is_discarded_and_rerun():
    crs = [_cr("G1", "Article 9.9", C_99, C_99 + " Such indemnity includes reasonable legal fees.", "상대방 배상 범위에 변호사비 포함")]
    res = vg.run_verification_gate(clause_results=crs, clauses=CLAUSES, parties=P, contract_text=C_99)
    assert res["status"] == vg.STATUS_PASS
    meta = {"verification_gate": vg.compact(res)}
    # 검증 뒤 누군가 수정안을 바꿈(역할 뒤바뀜) → 출력 직전 재검증으로 미통과
    crs[0]["redline_instruction"]["replacement_text"] = ROLE_SWAP
    crs[0]["suggested_rewrite"] = ROLE_SWAP
    cur = vg.ensure_current(meta, crs, CLAUSES)
    assert cur["version"] == vg.fingerprint(crs) and cur["version"] != res["version"]
    assert cur["status"] == vg.STATUS_FAIL
    assert "이전 검증 폐기" in cur["history"][-1]["step"]


def test_unconfirmed_our_party_never_passes():
    """우리 당사자를 확정하지 못했으면(기본값 이름) 수정안이 있는 한 방향 검증을 통과로 내지 않는다."""
    p = Parties(ours=["Customer"], theirs=["NDG"], confirmed=False)
    crs = [_cr("G1", "Article 9.9", C_99, C_99 + " Such indemnity includes reasonable legal fees.", "상대방 배상 범위에 변호사비 포함")]
    res = vg.run_verification_gate(clause_results=crs, clauses=CLAUSES, parties=p, contract_text=C_99)
    assert res["status"] == vg.STATUS_FAIL
    assert any(u["category"] == vg.CAT_BASIS for u in res["unresolved"])
    assert not crs[0]["redline_instruction"].get("held")   # 기준 미확정은 수정안을 지우지 않는다(확인 대상)
