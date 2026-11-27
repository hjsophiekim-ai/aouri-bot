"""계약 전체 상황별 검증 게이트 — 요청별 수정안을 합친 결과가 충돌하면 함께 고치고, 못 고치면 내보내지 않는다(2026-11-03)."""
from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from runtime.review.deal_scenarios import Parties
from runtime.review.requested_clause_review import RequestBlock, RequestedReview, VerifiedEdit, to_findings
from runtime.review.scenario_gate import run_scenario_gate

O99 = ("Customer shall indemnify NDG against all claims by third parties to whom NDG is not liable internally in relation to Customer.")
O101 = ("If any claim is made on NDG by a third party based on infringement of proprietary rights and if NDG has executed the order "
        "complying with Customer’s standards, Customer shall be obliged to indemnify NDG against such claims.")
CLAUSES = [
    {"clause_id": "c99", "display_path": "Article 9.9", "text": O99, "article_number": "9", "paragraph_number": "9", "title": "Claims"},
    {"clause_id": "c101", "display_path": "Article 10.1", "text": O101, "article_number": "10", "paragraph_number": "1", "title": "IP"},
]
BAD99 = ("Customer shall indemnify NDG only against third party claims to the extent such claims arise out of Customer’s negligence. "
         "Customer shall not be liable to indemnify NDG for any third party claims relating to the Design Product except to the extent "
         "caused by Customer’s negligence.")
GOOD99 = ("Subject to Article 10.1, Customer shall indemnify NDG only against third party claims to the extent such claims arise out of "
          "Customer’s negligence. Customer shall not be liable to indemnify NDG for losses arising from the acts or omissions of NDG.")
NEW101 = ("If any claim is made on NDG by a third party based on infringement of proprietary rights, Customer shall, to the extent that "
          "such claim arises solely from Customer’s specifications, indemnify NDG against such claims.")


def _reviews() -> list[RequestedReview]:
    r4 = RequestedReview(block=RequestBlock(index=4, head="9.9", text="제9.9조 면책 검토", cited=["Article 9.9"]),
                         targets=[CLAUSES[0]], context=[CLAUSES[1]],
                         data={"risk": "HIGH", "action_type": "필수수정", "verdict": "수정 필요",
                               "action": "면책 범위를 우리 귀책 있는 손해로 한정하고 NDG 귀책 손해는 제외한다.",
                               "measures": [{"measure": "면책 범위 한정", "edit_index": 0}]},
                         edits=[VerifiedEdit(mode="replace", target_text=O99, new_text=BAD99)])
    r100 = RequestedReview(block=RequestBlock(index=101, head="10.1", text="10.1 재검토", cited=["Article 10.1"]),
                           targets=[CLAUSES[1]], context=[CLAUSES[0]],
                           data={"risk": "HIGH", "action_type": "필수수정", "verdict": "수정 필요",
                                 "action": "우리 사양이 원인인 경우로 한정한다.",
                                 "measures": [{"measure": "사양 원인 한정", "edit_index": 0}]},
                           edits=[VerifiedEdit(mode="replace", target_text=O101, new_text=NEW101)])
    return [r4, r100]


class FakeProvider:
    def __init__(self, payload: dict | None) -> None:
        self.payload, self.calls = payload, 0

    def complete(self, _req):  # noqa: ANN001
        self.calls += 1
        return SimpleNamespace(content=json.dumps(self.payload) if self.payload else "")


P = Parties(ours=["Customer"], theirs=["NDG"])


class ScenarioGateTest(unittest.TestCase):
    def test_joint_repair_resolves_conflict(self) -> None:
        rv = _reviews()
        prov = FakeProvider({"reviews": [{"key": "4", "action": "면책 범위를 우리 귀책 있는 손해로 한정하고 NDG 귀책 손해는 제외한다.",
                                          "edits": [{"mode": "replace", "target_text": O99, "new_text": GOOD99}],
                                          "measures": [{"measure": "면책 범위 한정", "edit_index": 0}]}]})
        res = run_scenario_gate(reviews=rv, clauses=CLAUSES, contract_text=O99 + " " + O101, parties=P,
                                request_text="", answers_text="", provider=prov, model="x")
        self.assertEqual(prov.calls, 1)
        self.assertFalse(res["blocking"], res["problems"])
        self.assertEqual(rv[0].edits[0].new_text, GOOD99)
        self.assertFalse(any(e.held for r in rv for e in r.edits))
        f = [x for x in to_findings(rv) if x["request_index"] == 4][0]
        self.assertEqual(f["request_status"], "반영")

    def test_unresolved_conflict_blocks_output(self) -> None:
        rv = _reviews()
        res = run_scenario_gate(reviews=rv, clauses=CLAUSES, contract_text=O99 + " " + O101, parties=P,
                                request_text="", answers_text="", provider=FakeProvider(None), model="x")
        self.assertTrue(res["held_by_gate"])
        held = [e for r in rv for e in r.edits if e.held]
        self.assertTrue(held and "계약 전체 검증 미통과" in held[0].hold_reason)
        fs = to_findings(rv)
        self.assertTrue(all(not f["has_rewrite_change"] for f in fs if f["display_path"] in ("Article 9.9", "Article 10.1")
                            and f.get("redline_instruction", {}).get("held")))
        st = {f["request_index"]: f["request_status"] for f in fs}
        self.assertIn(st[4], ("미반영", "부분 반영"))


if __name__ == "__main__":
    unittest.main()
