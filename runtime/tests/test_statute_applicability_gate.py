"""법률 적용요건 선판단 게이트 회귀테스트 (2026-09-10 지시).

골든 사고: "콘텐츠 제작 대가로 가구를 제공하는 대물교환(바터) 계약"에서
아우리봇이 **하도급법 대물변제 금지 위반**을 HIGH 로 올렸다.

하도급법은 원사업자가 제조·수리·건설·용역위탁 중 하나를 한 경우에만
적용되고, 용역위탁은 "용역업을 영위하는 사업자가 그 업에 따른 용역수행행위의
전부 또는 일부를 위탁"하거나 "위탁받은 용역을 재위탁"하는 경우로 법이
한정한다(법 제2조 제11항). 우리 그룹은 가구 제조·판매업을 영위할 뿐 영상제작을
업으로 하지 않으므로 하도급법이 적용되지 않는다.

이 테스트는 그 판단이 **양방향으로** 동작하는지를 고정한다 — 우리가 그 일을
업으로 하면(영상제작사가 편집을 외주) 적용되어야 하고, 업으로 하지 않으면
비적용이어야 한다. 회사명·계약명 하드코딩 없이 "우리 업 vs 위탁한 일"의
관계만으로 판단한다.
"""
from __future__ import annotations

import unittest

from runtime.review.statute_applicability_gate import (
    CONCLUSION_APPLICABLE,
    CONCLUSION_NEEDS_FACTS,
    CONCLUSION_NOT_APPLICABLE,
    assess_statutes,
    assess_subcontract_act,
    deactivate_inapplicable_statute_findings,
    infer_entrusted_domain,
    our_business_domains,
)

_BARTER_CONTENT_CONTRACT = """영상 콘텐츠 제작 및 채널 운영 계약서 (대물교환 방식)
"주식회사 갑사"(이하 "갑사")과 "주식회사 을사"는 대물교환 계약을 체결한다.
제3조 "갑사"은 갑사 제품(가구)을 제공한다.
제4조 "을사"는 영상 제작(숏폼 16편, 풀버전 3편)과 자사 YouTube 채널 운영을 수행한다.
제5조 본 계약은 상호 등가의 대가로 하는 대물교환 계약이며, 별도의 현금 대가를 지급하지 아니한다.
"""


class SubcontractActGateTest(unittest.TestCase):
    def test_furniture_maker_outsourcing_video_is_not_subcontract(self) -> None:
        """골든: 가구 제조·판매사가 자사 홍보 영상을 외주 준 것은 용역위탁이 아니다."""
        d = assess_subcontract_act(
            entity="퍼시스",
            text=_BARTER_CONTENT_CONTRACT,
            contract_type_code="advertising_content_production",
        )
        self.assertEqual(d.conclusion, CONCLUSION_NOT_APPLICABLE)
        self.assertFalse(d.applicable)
        self.assertTrue(d.blocked, "비적용이면 하도급법 전용 rule 을 꺼야 한다")
        self.assertIn("업으로", d.reason)
        self.assertIn("대물변제", d.disabled_topics)

    def test_video_producer_outsourcing_editing_is_subcontract(self) -> None:
        """반대 방향: 영상제작을 업으로 하는 사업자가 그 일부를 외주 주면 용역위탁."""
        d = assess_subcontract_act(
            entity="어느영상제작사",
            text=(
                "당사의 주된 사업인 영상 콘텐츠 제작 업무 중 편집 부분을 을에게 위탁한다. "
                "촬영 및 편집본 납품."
            ),
            contract_type_code="advertising_content_production",
        )
        self.assertEqual(d.conclusion, CONCLUSION_APPLICABLE)
        self.assertTrue(d.applicable)
        self.assertFalse(d.blocked)

    def test_furniture_oem_manufacturing_is_subcontract(self) -> None:
        """가구 제조·판매를 업으로 하면서 사양대로 제작을 맡기면 제조위탁이다."""
        d = assess_subcontract_act(
            entity="퍼시스",
            text="갑은 사양서에 따라 제작한 가구를 을에게 주문 제작 위탁한다. OEM 생산 위탁.",
            contract_type_code="",
        )
        self.assertEqual(d.conclusion, CONCLUSION_APPLICABLE)

    def test_re_entrustment_is_subcontract_regardless_of_our_business(self) -> None:
        """제3자로부터 수주한 일을 다시 맡기는 재위탁은 업 여부와 무관하게 적용."""
        d = assess_subcontract_act(
            entity="퍼시스",
            text="을은 발주처로부터 수주한 설치 용역을 병에게 재위탁한다.",
            contract_type_code="",
        )
        self.assertEqual(d.conclusion, CONCLUSION_APPLICABLE)

    def test_unknown_domain_is_not_asserted_either_way(self) -> None:
        """위탁 대상을 특정하지 못하면 '적용'도 '비적용'도 단정하지 않는다."""
        d = assess_subcontract_act(
            entity="퍼시스",
            text="갑과 을은 상호 협력하기로 한다. 본 합의는 신의성실에 따라 이행한다.",
            contract_type_code="",
        )
        self.assertEqual(d.conclusion, CONCLUSION_NEEDS_FACTS)
        self.assertFalse(d.blocked, "모르는 상태에서 rule 을 끄면 탐지 누락이 된다")
        self.assertTrue(d.facts_needed)


class BusinessDomainTest(unittest.TestCase):
    def test_group_default_covers_manufacturing_and_installation(self) -> None:
        domains = our_business_domains("퍼시스")
        self.assertIn("furniture_manufacturing", domains)
        self.assertIn("installation_service", domains)
        self.assertNotIn("content_production", domains)

    def test_per_company_override(self) -> None:
        domains = our_business_domains("바로스")
        self.assertEqual(domains, frozenset({"installation_service", "logistics"}))

    def test_entrusted_domain_inference(self) -> None:
        self.assertEqual(
            infer_entrusted_domain(text="숏폼 영상 제작 및 편집", contract_type_code=""),
            "content_production",
        )
        self.assertEqual(
            infer_entrusted_domain(text="", contract_type_code="software_dev"),
            "software_development",
        )


class DeactivationTest(unittest.TestCase):
    def test_inapplicable_statute_findings_are_removed(self) -> None:
        decisions = assess_statutes(
            entity="퍼시스",
            text=_BARTER_CONTENT_CONTRACT,
            contract_type_code="advertising_content_production",
        )
        clause_results = [
            {
                "clause_id": "counsel_legal_01",
                "rewrite_reason": "하도급법상 대물변제 금지 위반에 따른 과징금 위험",
            },
            {
                "clause_id": "KR-9-p1",
                "rewrite_reason": "저작권법상 2차적저작물작성권이 양도에 포함되는지 불명확",
            },
        ]
        removed = deactivate_inapplicable_statute_findings(clause_results, decisions)
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0]["clause_id"], "counsel_legal_01")
        self.assertEqual([c["clause_id"] for c in clause_results], ["KR-9-p1"])
        self.assertIn("업으로", removed[0]["reason"])

    def test_nothing_removed_when_statute_applies(self) -> None:
        decisions = assess_statutes(
            entity="퍼시스",
            text="갑은 사양서에 따라 제작한 가구를 을에게 주문 제작 위탁한다. OEM 생산 위탁.",
            contract_type_code="",
        )
        clause_results = [{"clause_id": "x", "rewrite_reason": "하도급대금 지급기한 미준수 위험"}]
        removed = deactivate_inapplicable_statute_findings(clause_results, decisions)
        self.assertEqual(removed, [])
        self.assertEqual(len(clause_results), 1)


if __name__ == "__main__":
    unittest.main()
