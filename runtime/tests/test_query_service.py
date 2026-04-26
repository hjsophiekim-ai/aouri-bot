from __future__ import annotations

import unittest

from runtime.rules.loader import RuleLoader
from runtime.services.query_service import ReviewInput, RuleQueryService


class QueryServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = RuleQueryService(RuleLoader())

    def test_decision_rules_exclude_backlog(self) -> None:
        rules = self.service.list_rules(include_backlog=False)
        statuses = {r["rule_status"] for r in rules}
        self.assertNotIn("unconfirmed_backlog", statuses)

    def test_backlog_reference_only(self) -> None:
        backlog = self.service.list_backlog()
        self.assertTrue(len(backlog) > 0)
        self.assertTrue(all(r["rule_status"] == "unconfirmed_backlog" for r in backlog))

    def test_analyze_detects_approval_required_rules(self) -> None:
        text = (
            "본 계약은 without limitation 책임을 부담한다. "
            "또한 상대방을 indemnify 한다. "
            "대리점 비용부담을 요구한다."
        )
        result = self.service.analyze(
            ReviewInput(entity="퍼시스", contract_type="대리점/위탁/유통", text=text)
        )
        self.assertGreaterEqual(result["summary"]["approval_required_match_count"], 1)
        ids = {r["rule_id"] for r in result["approval_required_matches"]}
        self.assertTrue({"RISK-001", "RISK-002", "RISK-006"} & ids)


if __name__ == "__main__":
    unittest.main()

