"""단위 테스트 — statute_applicability_calibration.py(2026-09-04 지시).

대리점법(floor)/하도급법(ceiling) 보정 함수를 구조 신호별로 독립
검증한다. 조항번호·회사명·상품명과 무관한 범용 신호만 사용한다.
"""
from __future__ import annotations

import unittest

from runtime.review.statute_applicability_calibration import (
    calibrate_dealer_act_applicability,
    calibrate_statute_applicability_results,
    calibrate_subcontract_act_applicability,
    has_economic_operational_linkage_signal,
    has_existing_dealer_relationship_signal,
)

_LINKED_TEXT = (
    "본 계약은 기존 위탁판매(운영) 계약과는 별도로 체결한다. "
    "본 계약의 유효기간은 기존 위탁판매(운영) 계약의 계약기간과 동일하게 적용하며, "
    "위탁판매(운영) 계약이 중도 해지되는 경우 본 계약도 그 효력을 상실한다. "
    "매장 단말기를 통하여 결제가 완료된 판매 건에 대하여 수수료를 지급한다."
)
_STANDALONE_TEXT = "본 계약은 신규 거래처와 체결하는 완전히 독립적인 판매지원 용역계약이다."


def _stub(statute: str, risk_level: str = "확인 필요") -> dict:
    return {
        "statute": statute, "applicability": "확인 필요", "reasoning": "",
        "additional_facts_needed": [], "related_clauses": [], "risk_level": risk_level,
        "source": "stub_no_ai",
    }


class SignalDetectionTest(unittest.TestCase):
    def test_existing_relationship_from_legal_map_field(self) -> None:
        self.assertTrue(has_existing_dealer_relationship_signal("", {"existing_related_contract": "기존 계약 있음"}))

    def test_existing_relationship_from_text_signal(self) -> None:
        self.assertTrue(has_existing_dealer_relationship_signal("기존 위탁판매 계약이 있다.", None))

    def test_no_existing_relationship_signal(self) -> None:
        self.assertFalse(has_existing_dealer_relationship_signal(_STANDALONE_TEXT, {}))

    def test_linkage_detected_via_term_and_termination(self) -> None:
        self.assertTrue(has_economic_operational_linkage_signal(_LINKED_TEXT))

    def test_linkage_detected_via_pos_reuse_alone(self) -> None:
        self.assertTrue(has_economic_operational_linkage_signal("매장 단말기를 통하여 결제한다."))

    def test_no_linkage_signal(self) -> None:
        self.assertFalse(has_economic_operational_linkage_signal(_STANDALONE_TEXT))


class DealerActCalibrationTest(unittest.TestCase):
    def test_floors_low_to_medium_when_relationship_and_linkage_present(self) -> None:
        out = calibrate_dealer_act_applicability(_stub("대리점법", "LOW"), _LINKED_TEXT, {})
        self.assertEqual(out["risk_level"], "MEDIUM")
        self.assertEqual(out["applicability"], "있음(추가 확인 필요)")

    def test_floors_stub_unknown_to_medium(self) -> None:
        out = calibrate_dealer_act_applicability(_stub("대리점법", "확인 필요"), _LINKED_TEXT, {})
        self.assertEqual(out["risk_level"], "MEDIUM")

    def test_does_not_downgrade_already_high(self) -> None:
        out = calibrate_dealer_act_applicability(_stub("대리점법", "HIGH"), _LINKED_TEXT, {})
        self.assertEqual(out["risk_level"], "HIGH")

    def test_no_change_without_existing_relationship(self) -> None:
        stub = _stub("대리점법", "LOW")
        out = calibrate_dealer_act_applicability(stub, _STANDALONE_TEXT, {})
        self.assertEqual(out, stub)

    def test_non_dealer_act_statute_untouched(self) -> None:
        stub = _stub("공정거래법", "LOW")
        out = calibrate_dealer_act_applicability(stub, _LINKED_TEXT, {})
        self.assertEqual(out, stub)

    def test_autonomy_clause_present_skips_extra_facts_needed(self) -> None:
        text_with_autonomy = _LINKED_TEXT + " 을이 본 계약 체결을 거절하더라도 불이익이 발생하지 아니한다."
        out = calibrate_dealer_act_applicability(_stub("대리점법", "LOW"), text_with_autonomy, {})
        self.assertEqual(out["risk_level"], "MEDIUM")
        self.assertEqual(out["additional_facts_needed"], [])


class SubcontractActCalibrationTest(unittest.TestCase):
    def test_caps_medium_to_low_without_regulated_activity(self) -> None:
        out = calibrate_subcontract_act_applicability(_stub("하도급법", "MEDIUM"), _LINKED_TEXT)
        self.assertEqual(out["risk_level"], "LOW")
        self.assertEqual(out["applicability"], "낮음")

    def test_caps_high_to_low_without_regulated_activity(self) -> None:
        out = calibrate_subcontract_act_applicability(_stub("하도급법", "HIGH"), _LINKED_TEXT)
        self.assertEqual(out["risk_level"], "LOW")

    def test_resolves_unknown_stub_to_low(self) -> None:
        out = calibrate_subcontract_act_applicability(_stub("하도급법", "확인 필요"), _LINKED_TEXT)
        self.assertEqual(out["risk_level"], "LOW")

    def test_does_not_touch_when_regulated_activity_present(self) -> None:
        text = _LINKED_TEXT + " 특정 사양에 따라 주문 제작을 위탁한다(제조위탁)."
        stub = _stub("하도급법", "MEDIUM")
        out = calibrate_subcontract_act_applicability(stub, text)
        self.assertEqual(out, stub)

    def test_non_subcontract_act_statute_untouched(self) -> None:
        stub = _stub("공정거래법", "MEDIUM")
        out = calibrate_subcontract_act_applicability(stub, _LINKED_TEXT)
        self.assertEqual(out, stub)


class CalibrateAllResultsTest(unittest.TestCase):
    def test_applies_both_calibrations_in_one_pass(self) -> None:
        results = [_stub("대리점법", "LOW"), _stub("하도급법", "MEDIUM"), _stub("공정거래법", "MEDIUM")]
        out = calibrate_statute_applicability_results(results, _LINKED_TEXT, {})
        by_statute = {r["statute"]: r for r in out}
        self.assertEqual(by_statute["대리점법"]["risk_level"], "MEDIUM")
        self.assertEqual(by_statute["하도급법"]["risk_level"], "LOW")
        self.assertEqual(by_statute["공정거래법"]["risk_level"], "MEDIUM")


if __name__ == "__main__":
    unittest.main()
