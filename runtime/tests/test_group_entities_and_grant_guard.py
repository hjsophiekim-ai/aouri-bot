"""퍼시스그룹 계열사 인식 + 상대방 권리 신설 차단.

2026-09-11 지시 두 건을 고정한다.

  · 계열사(퍼시스·일룸·데스커·시디즈·레터스·퍼플식스·해외법인·지주)를 "우리
    회사 측"으로 인식하고, 바로스 → 레터스 상호 변경을 반영한다.
  · 상대방에게 없던 이의권·방어권·시정기간·책임제한을 만들어주는 수정과,
    선이행 구조에서 즉시해지·환수·보전권을 깎는 수정을 막는다.
"""
from __future__ import annotations

import unittest

from runtime.review.counterparty_grant_guard import (
    enforce_no_new_counterparty_rights,
    newly_granted_rights,
    weakened_recovery_rights,
)
from runtime.review.group_entities import (
    entity_advisories,
    entity_business_domains,
    find_group_entities,
    is_group_entity,
    is_intra_group,
    our_side_labels,
    resolve_entity,
)
from runtime.review.statute_applicability_gate import our_business_domains


class GroupEntityRegistryTest(unittest.TestCase):
    def test_every_named_affiliate_is_recognised_as_our_side(self) -> None:
        for name in (
            "퍼시스", "일룸", "데스커", "시디즈", "레터스", "퍼플식스",
            "퍼시스 베트남", "시디즈 아메리카", "퍼시스 아메리카",
            "일룸 타이완", "퍼시스 지주", "일룸 지주",
        ):
            with self.subTest(name=name):
                self.assertTrue(is_group_entity(name), f"{name}을 계열사로 인식하지 못했다")

    def test_outside_counterparties_are_not_our_side(self) -> None:
        for name in ("가나컨텐츠", "가나오피스", "주식회사 대한물산", ""):
            with self.subTest(name=name):
                self.assertFalse(is_group_entity(name))

    def test_baros_resolves_to_its_current_name_letus(self) -> None:
        old = resolve_entity("바로스")
        new = resolve_entity("주식회사 레터스")
        self.assertIsNotNone(old)
        self.assertIsNotNone(new)
        self.assertEqual(old.key, new.key, "바로스와 레터스가 다른 법인으로 잡혔다")
        self.assertEqual(new.name, "레터스", "현재 법인명이 레터스가 아니다")

    def test_longer_affiliate_name_wins_over_its_prefix(self) -> None:
        """"퍼시스"가 "퍼시스 아메리카"로, 또는 그 반대로 잡히면 안 된다."""
        self.assertEqual(resolve_entity("퍼시스").key, "fursys")
        self.assertEqual(resolve_entity("퍼시스 아메리카").key, "fursys_america")
        self.assertEqual(resolve_entity("퍼시스 지주").key, "fursys_holdings")
        self.assertEqual(resolve_entity("일룸").key, "iloom")
        self.assertEqual(resolve_entity("일룸 타이완").key, "iloom_taiwan")

    def test_corporate_form_and_spacing_do_not_matter(self) -> None:
        for variant in ("(주)일룸", "주식회사 일룸", "일룸 주식회사", "iloom", "ILOOM"):
            with self.subTest(variant=variant):
                self.assertEqual(resolve_entity(variant).key, "iloom")

    def test_letus_keeps_its_logistics_and_installation_business(self) -> None:
        """상호가 바뀌어도 업(業)은 따라와야 하도급법 판단이 유지된다."""
        for name in ("바로스", "레터스"):
            with self.subTest(name=name):
                domains = entity_business_domains(name)
                self.assertEqual(domains, frozenset({"installation_service", "logistics"}))
                self.assertEqual(our_business_domains(name), domains)

    def test_content_production_is_no_affiliate_business(self) -> None:
        """어느 계열사도 콘텐츠 제작을 업으로 하지 않는다 — 하도급법 비적용의 근거."""
        for name in ("퍼시스", "일룸", "시디즈", "레터스", "데스커"):
            with self.subTest(name=name):
                self.assertNotIn("content_production", our_business_domains(name))
                self.assertNotIn("advertising_marketing", our_business_domains(name))

    def test_our_side_labels_pick_up_the_affiliate_named_in_the_contract(self) -> None:
        text = "본 계약은 주식회사 일룸(이하 '갑')과 가나컨텐츠(이하 '을') 간에 체결한다."
        labels = our_side_labels(text)
        self.assertIn("일룸", labels)
        self.assertNotIn("가나컨텐츠", labels)

    def test_former_name_in_an_old_document_raises_an_identity_check(self) -> None:
        text = "2019년 체결. 당사자: 주식회사 바로스"
        advisories = entity_advisories(text)
        detail = " ".join(a["detail"] for a in advisories)
        self.assertIn("레터스", detail)
        self.assertIn("동일성", detail)

    def test_desker_brand_raises_a_legal_name_check(self) -> None:
        advisories = entity_advisories("공급자: 데스커")
        self.assertTrue(any("데스커" == a["entity"] for a in advisories))
        self.assertIn("법인명", " ".join(a["detail"] for a in advisories))

    def test_overseas_affiliate_raises_an_english_name_check(self) -> None:
        advisories = entity_advisories("Party A: 퍼시스 베트남")
        self.assertTrue(any(a["kind"] == "overseas" for a in advisories))

    def test_intra_group_contract_is_flagged_not_silently_treated_as_arms_length(self) -> None:
        self.assertTrue(is_intra_group("갑: 일룸, 을: 시디즈"))
        self.assertFalse(is_intra_group("갑: 일룸, 을: 가나컨텐츠"))
        details = " ".join(a["detail"] for a in entity_advisories("갑: 일룸, 을: 시디즈"))
        self.assertIn("내부거래", details)

    def test_finding_entities_in_a_contract_body(self) -> None:
        found = {e.key for e in find_group_entities("갑 시디즈, 을 레터스, 병 외부업체")}
        self.assertEqual(found, {"sidiz", "letus"})


class CounterpartyGrantGuardTest(unittest.TestCase):
    def test_detects_rights_the_original_never_gave(self) -> None:
        original = "을은 갑에게 발생한 모든 손해를 배상한다."
        proposed = (
            "을은 갑에게 발생한 모든 손해를 배상한다. "
            "다만 을은 배상 청구에 대하여 14일 이내에 이의를 제기할 수 있다."
        )
        self.assertIn("이의권", newly_granted_rights(original, proposed))

    def test_a_right_already_in_the_original_is_not_counted_as_new(self) -> None:
        original = "을은 배상 청구에 대하여 이의를 제기할 수 있다."
        self.assertEqual(newly_granted_rights(original, original + " 추가 문구."), [])

    def test_reverts_a_proposal_that_hands_the_counterparty_a_new_defence(self) -> None:
        cr = {
            "clause_id": "c1",
            "display_path": "제10조",
            "original_text": "을은 갑에게 발생한 모든 손해를 배상하여야 한다.",
            "suggested_rewrite": (
                "을은 갑에게 발생한 모든 손해를 배상하여야 한다. "
                "을은 자신의 비용으로 방어 및 화해 절차에 참여할 권리를 가진다."
            ),
            "risk_tier": "MEDIUM",
        }
        blocked = enforce_no_new_counterparty_rights([cr], our_labels=("갑",))
        self.assertTrue(blocked)
        self.assertTrue(cr["keep_as_is"])
        self.assertIsNone(cr["suggested_rewrite"])
        self.assertIn("유지", cr["recommendation_text"])

    def test_a_clause_that_burdens_us_may_still_be_capped(self) -> None:
        """우리가 부담자인 조항에 한도를 넣는 것은 우리를 보호하는 수정이다."""
        cr = {
            "clause_id": "c2",
            "display_path": "제11조",
            "original_text": "갑은 을에게 발생한 모든 손해를 배상하여야 한다.",
            "suggested_rewrite": (
                "갑은 을에게 발생한 모든 손해를 배상하여야 한다. "
                "다만 갑의 책임은 수령한 대가의 총액을 초과하지 아니한다."
            ),
            "risk_tier": "MEDIUM",
        }
        self.assertEqual(enforce_no_new_counterparty_rights([cr], our_labels=("갑",)), [])
        self.assertTrue(cr["suggested_rewrite"])

    def test_a_clause_that_is_bad_for_us_is_still_fixable(self) -> None:
        """상대방이 자기 책임을 전부 면제하는 조항은 우리에게 불리하다.

        "우리가 부담자가 아니다"를 "우리에게 유리하다"로 읽으면, 정작 고쳐야 할
        면책 조항이 보호 대상이 되어 살아남는다.
        """
        cr = {
            "clause_id": "c3",
            "display_path": "제15조",
            "original_text": "공급자는 어떠한 경우에도 구매자에 대하여 일체의 책임이 없다.",
            "suggested_rewrite": (
                "공급자의 면책은 구매자의 귀책 범위에 한하며, 구매자는 제3자 청구에 "
                "대하여 이의를 제기할 수 있다."
            ),
            "risk_tier": "HIGH",
        }
        self.assertEqual(enforce_no_new_counterparty_rights([cr], our_labels=("구매자",)), [])
        self.assertTrue(cr["suggested_rewrite"])

    def test_pre_performer_keeps_immediate_termination(self) -> None:
        original = "갑은 을의 불이행 시 통지 없이 즉시 해지하고 기납품물의 반환을 청구할 수 있다."
        proposed = (
            "갑은 을의 불이행 시 30일 전까지 시정을 요구하는 서면 최고를 한 후 "
            "해지할 수 있다."
        )
        self.assertTrue(weakened_recovery_rights(original, proposed))
        cr = {
            "clause_id": "c4",
            "display_path": "제12조",
            "original_text": original,
            "suggested_rewrite": proposed,
            "risk_tier": "HIGH",
        }
        blocked = enforce_no_new_counterparty_rights(
            [cr], our_labels=("갑",), we_perform_first=True,
        )
        self.assertTrue(blocked, "선이행 구조인데 즉시해지 약화를 막지 못했다")
        self.assertIn("선이행", " ".join(blocked[0]["reasons"]))

    def test_recovery_right_already_conditioned_is_left_alone(self) -> None:
        original = "갑은 을이 시정 요구에 응하지 아니한 경우에 한하여 해지할 수 있다."
        proposed = original + " 해지 통지는 서면으로 한다."
        self.assertEqual(weakened_recovery_rights(original, proposed), [])


if __name__ == "__main__":
    unittest.main()
