from __future__ import annotations

import unittest

from runtime.review.classify import classify
from runtime.review.priority_map import infer_contract_profile
from runtime.questions.generator import generate_questions
from runtime.law.search_service import _infer_contract_profile as infer_law_profile


class OperationsContractFlowTest(unittest.TestCase):
    def test_ops_contract_type_classifier_prefers_ops_over_generic_delegation(self) -> None:
        text = "운영대행 계약에 따라 라운지 운영 및 운영인력 배치, 보고/자료제출, 검수, 정산을 수행한다."
        r = classify(entity=None, contract_type=None, text=text, filename="(데스커 라운지 대구) 운영대행 계약.txt")
        self.assertEqual("운영대행/위탁운영/공간운영/서비스위탁", r.contract_type)

    def test_ops_profile_inference(self) -> None:
        text = "위탁운영 및 시설관리, 운영수수료 정산, 하도급 사전승인, 안전관리 책임을 규정한다."
        prof = infer_contract_profile(contract_type="운영대행/위탁운영/공간운영/서비스위탁", text=text)
        self.assertEqual("ops_outsourcing", prof.profile)

    def test_ops_question_set_does_not_include_appdev_questions(self) -> None:
        text = "운영대행 범위, 보고서 제출, 검수, 운영인력 배치, 정산, 하도급 승인, 안전관리, 기밀유지, 계약해지"
        qs = generate_questions(
            entity="데스커",
            contract_type="운영대행/위탁운영/공간운영/서비스위탁",
            detected_rule_ids=[],
            contract_text=text,
            clause_results=[],
            max_questions=5,
            review_focus="대리점법 불이익 제공/경영간섭/계약해지 남용",
        )
        qids = [q.question_id for q in qs]
        self.assertTrue(any(qid.startswith("Q-OPS-") for qid in qids))
        self.assertFalse(any(qid.startswith("Q-AD-") for qid in qids))
        self.assertFalse(any("open" in (qid.lower()) or "oss" in (qid.lower()) for qid in qids))

    def test_law_profile_inference_prefers_operations(self) -> None:
        text = "운영대행, 인력 배치, 운영수수료 정산, 하도급 승인, 안전관리"
        p = infer_law_profile(contract_type="운영대행/위탁운영/공간운영/서비스위탁", text=text)
        self.assertEqual("operations", p)


if __name__ == "__main__":
    unittest.main()

