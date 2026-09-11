"""내부통제 분리 + 상대방 역할 오분류 차단 (2026-09-11 지시 5·6번)."""
from __future__ import annotations

import unittest

from runtime.review.counterparty_role_gate import (
    REVIEW_FAILED_ROLE_CONFLICT,
    enforce_counterparty_role,
    find_role_conflicts,
)
from runtime.review.delivery_gate import NON_REMEDIABLE_STATUSES, REMEDIABLE_STATUSES
from runtime.review.internal_control_split import (
    looks_like_internal_control,
    split_internal_controls,
)


class InternalControlSplitTest(unittest.TestCase):
    def test_our_own_bookkeeping_is_not_a_contract_clause(self) -> None:
        for text in (
            "부가가치세 신고 시 공급시기를 확인하고 증빙을 보관한다.",
            "세무조정 과정에서 손금 산입 여부를 검토한다.",
            "재경팀 내부 승인 절차를 거쳐 전표를 처리한다.",
        ):
            with self.subTest(text=text):
                self.assertTrue(looks_like_internal_control(text))

    def test_an_obligation_on_the_counterparty_stays_a_clause(self) -> None:
        for text in (
            "을은 공급시기에 세금계산서를 발행하여 갑에게 교부한다.",
            "공급자는 관련 증빙을 5년간 보관하고 갑의 요청 시 제공한다.",
        ):
            with self.subTest(text=text):
                self.assertFalse(looks_like_internal_control(text))

    def test_internal_control_finding_loses_its_clause_text(self) -> None:
        cr = {
            "clause_id": "t1",
            "display_path": "제9조",
            "original_text": "",
            "suggested_rewrite": "법인세 신고 시 손금 산입 여부를 세무조정으로 확인한다.",
            "risk_tier": "HIGH",
        }
        moved = split_internal_controls([cr])
        self.assertTrue(moved)
        self.assertIsNone(cr["suggested_rewrite"])
        self.assertTrue(cr["internal_control_item"])
        self.assertIn("내부 확인사항", cr["recommendation_text"])
        self.assertEqual(cr["risk_tier"], "MEDIUM", "내부 절차로 해소되는데 HIGH로 남았다")

    def test_a_real_clause_edit_is_left_alone(self) -> None:
        original = "을은 대금을 청구할 수 있다."
        cr = {
            "clause_id": "t2",
            "original_text": original,
            "suggested_rewrite": original + " 세금계산서는 공급시기에 발행하여 갑에게 교부한다.",
            "risk_tier": "MEDIUM",
        }
        self.assertEqual(split_internal_controls([cr]), [])
        self.assertTrue(cr["suggested_rewrite"])


class CounterpartyRoleGateTest(unittest.TestCase):
    def test_both_parties_cannot_hold_the_same_role(self) -> None:
        conflicts = find_role_conflicts(
            {"our_role": "supplier", "counterparty_role": "supplier"}
        )
        self.assertTrue(conflicts)
        self.assertIn("supplier", conflicts[0])

    def test_a_missing_counterparty_role_is_a_conflict(self) -> None:
        self.assertTrue(find_role_conflicts({"our_role": "buyer", "counterparty_role": ""}))

    def test_identical_labels_are_a_conflict(self) -> None:
        conflicts = find_role_conflicts({
            "our_role": "buyer", "counterparty_role": "supplier",
            "our_label": "갑", "counterparty_label": "갑",
        })
        self.assertTrue(conflicts)

    def test_a_consistent_pairing_passes(self) -> None:
        self.assertEqual(
            find_role_conflicts({
                "our_role": "supplier", "counterparty_role": "buyer",
                "our_label": "을", "counterparty_label": "갑",
            }),
            [],
        )

    def test_contract_self_declaration_overrides_a_wrong_judgment(self) -> None:
        text = '공급자: 주식회사 퍼시스(이하 "공급자"라 한다)'
        conflicts = find_role_conflicts(
            {"our_role": "buyer", "counterparty_role": "supplier"},
            contract_text=text,
        )
        self.assertTrue(conflicts, "계약서가 우리를 공급자로 적었는데 구매자 판정을 통과시켰다")

    def test_the_gate_sets_a_status_without_touching_findings(self) -> None:
        report = enforce_counterparty_role(
            {"our_role": "supplier", "counterparty_role": "supplier"}
        )
        self.assertEqual(report["status"], REVIEW_FAILED_ROLE_CONFLICT)
        self.assertIn("확인", report["detail"])

    def test_the_status_still_allows_delivery(self) -> None:
        """다운로드를 막지 않는다 — 사유를 문서에 싣되 전달은 계속된다."""
        self.assertIn(REVIEW_FAILED_ROLE_CONFLICT, REMEDIABLE_STATUSES)
        self.assertNotIn(REVIEW_FAILED_ROLE_CONFLICT, NON_REMEDIABLE_STATUSES)


if __name__ == "__main__":
    unittest.main()
