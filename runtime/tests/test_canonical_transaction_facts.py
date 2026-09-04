"""단위 테스트 — canonical_transaction_facts.py(2026-09-04 지시).

사전질문 답변을 구조화된 사실관계로 승격하고, 그 사실관계로 남은
자리표시자를 치환/검출하는 순수 함수들을 독립적으로 검증한다.
"""
from __future__ import annotations

import unittest

from runtime.review.canonical_transaction_facts import (
    build_ai_fact_directive,
    build_canonical_transaction_facts,
    build_canonical_transaction_facts_from_answers,
    find_unresolved_fact_placeholders,
    resolved_mandatory_fields,
    resolved_party_label,
    substitute_resolved_placeholders,
)


class BuildCanonicalTransactionFactsTest(unittest.TestCase):
    def test_resale_structure_true_when_seller_equals_owner(self) -> None:
        facts = build_canonical_transaction_facts({"seller": "(주)일룸", "owner_of_goods": "일룸"})
        self.assertTrue(facts["resale_structure"])

    def test_resale_structure_false_when_seller_differs_from_owner(self) -> None:
        facts = build_canonical_transaction_facts({"seller": "(주)일룸", "owner_of_goods": "다른회사"})
        self.assertFalse(facts["resale_structure"])

    def test_missing_fields_are_none_not_guessed(self) -> None:
        facts = build_canonical_transaction_facts({})
        self.assertIsNone(facts["seller"])
        self.assertIsNone(facts["owner_of_goods"])
        self.assertFalse(facts["resale_structure"])

    def test_from_answers_maps_question_ids_to_fields(self) -> None:
        facts = build_canonical_transaction_facts_from_answers({
            "Q-TXN-001-seller": "(주)일룸",
            "Q-TXN-002-owner": "(주)일룸",
            "Q-TXN-008-relationship-type": "sales_support_service",
        })
        self.assertEqual(facts["seller"], "(주)일룸")
        self.assertTrue(facts["resale_structure"])
        self.assertTrue(facts["sales_support_provider"])


class ResolvedMandatoryFieldsTest(unittest.TestCase):
    def test_only_resolved_fields_listed(self) -> None:
        facts = build_canonical_transaction_facts({"seller": "일룸"})
        self.assertEqual(resolved_mandatory_fields(facts), ["seller"])

    def test_empty_when_nothing_resolved(self) -> None:
        self.assertEqual(resolved_mandatory_fields(build_canonical_transaction_facts({})), [])


class ResolvedPartyLabelTest(unittest.TestCase):
    def test_same_entity_returns_single_name(self) -> None:
        facts = build_canonical_transaction_facts({"seller": "(주)일룸", "owner_of_goods": "일룸"})
        self.assertEqual(resolved_party_label(facts), "(주)일룸")

    def test_different_entities_returns_both_with_roles(self) -> None:
        facts = build_canonical_transaction_facts({"seller": "A사", "owner_of_goods": "B사"})
        self.assertEqual(resolved_party_label(facts), "A사(판매자)/B사(소유자)")

    def test_only_seller_known_returns_seller(self) -> None:
        facts = build_canonical_transaction_facts({"seller": "일룸"})
        self.assertEqual(resolved_party_label(facts), "일룸")

    def test_nothing_known_returns_none(self) -> None:
        self.assertIsNone(resolved_party_label(build_canonical_transaction_facts({})))


class SubstitutePlaceholdersTest(unittest.TestCase):
    def test_substitutes_bracket_placeholder_with_resolved_name(self) -> None:
        facts = build_canonical_transaction_facts({"seller": "일룸", "owner_of_goods": "일룸"})
        clause_results = [{
            "clause_id": "clr_x",
            "suggested_rewrite": "책임은 [실제 판매자/소유자]가 부담한다.",
        }]
        touched = substitute_resolved_placeholders(clause_results, facts)
        self.assertEqual(touched, ["clr_x"])
        self.assertEqual(clause_results[0]["suggested_rewrite"], "책임은 일룸가 부담한다.")

    def test_does_nothing_when_facts_unresolved(self) -> None:
        clause_results = [{"clause_id": "clr_x", "suggested_rewrite": "[실제 판매자/소유자]가 부담한다."}]
        touched = substitute_resolved_placeholders(clause_results, build_canonical_transaction_facts({}))
        self.assertEqual(touched, [])
        self.assertIn("[실제 판매자/소유자]", clause_results[0]["suggested_rewrite"])

    def test_no_placeholder_present_is_a_noop(self) -> None:
        facts = build_canonical_transaction_facts({"seller": "일룸"})
        clause_results = [{"clause_id": "clr_y", "suggested_rewrite": "정상적인 문구입니다."}]
        self.assertEqual(substitute_resolved_placeholders(clause_results, facts), [])


class FindUnresolvedPlaceholdersTest(unittest.TestCase):
    def test_finds_remaining_placeholder_after_facts_resolved(self) -> None:
        facts = build_canonical_transaction_facts({"seller": "일룸"})
        clause_results = [{"clause_id": "clr_z", "rewrite_reason": "당사자는 [확인 필요] 상태이다.", "dedup_suppressed": False}]
        found = find_unresolved_fact_placeholders(clause_results, facts)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["clause_id"], "clr_z")

    def test_suppressed_findings_are_ignored(self) -> None:
        facts = build_canonical_transaction_facts({"seller": "일룸"})
        clause_results = [{"clause_id": "clr_z", "rewrite_reason": "[확인 필요]", "dedup_suppressed": True}]
        self.assertEqual(find_unresolved_fact_placeholders(clause_results, facts), [])

    def test_no_facts_resolved_means_no_check(self) -> None:
        clause_results = [{"clause_id": "clr_z", "rewrite_reason": "[확인 필요]", "dedup_suppressed": False}]
        self.assertEqual(find_unresolved_fact_placeholders(clause_results, build_canonical_transaction_facts({})), [])


class BuildAiFactDirectiveTest(unittest.TestCase):
    def test_empty_when_no_facts(self) -> None:
        self.assertEqual(build_ai_fact_directive(build_canonical_transaction_facts({})), "")

    def test_includes_resolved_values_and_no_guess_instruction(self) -> None:
        facts = build_canonical_transaction_facts({"seller": "(주)일룸", "owner_of_goods": "(주)일룸"})
        directive = build_ai_fact_directive(facts)
        self.assertIn("(주)일룸", directive)
        self.assertIn("미확인", directive)  # "미확인"이라 쓰지 말라는 지시 문구 자체는 포함
        self.assertIn("재판매", directive)


if __name__ == "__main__":
    unittest.main()
