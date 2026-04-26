from __future__ import annotations

import unittest

from runtime.questions.generator import generate_questions


class ClauseAwareQuestionTest(unittest.TestCase):
    def test_questions_change_by_contract_text(self) -> None:
        dealer_text = "위탁판매 대리점 계약. 판촉비 및 반품 비용은 을이 부담한다."
        privacy_text = "개인정보 처리위탁이 포함된다. 수탁자는 개인정보를 처리한다."

        q1 = generate_questions(
            entity="테스트",
            contract_type="위탁/대리점",
            detected_rule_ids=["RISK-006"],
            contract_text=dealer_text,
            clause_results=[{"related_rules": [{"rule_id": "RISK-006"}]}],
            max_questions=5,
        )
        q2 = generate_questions(
            entity="테스트",
            contract_type="개인정보/DPA",
            detected_rule_ids=[],
            contract_text=privacy_text,
            clause_results=[],
            max_questions=5,
        )
        self.assertGreaterEqual(len(q1), 3)
        self.assertGreaterEqual(len(q2), 3)
        self.assertNotEqual(q1[0].question_id, q2[0].question_id)
        self.assertTrue(any("dealer" in " ".join(x.tags) for x in q1))
        self.assertTrue(any("privacy" in " ".join(x.tags) for x in q2))


if __name__ == "__main__":
    unittest.main()

