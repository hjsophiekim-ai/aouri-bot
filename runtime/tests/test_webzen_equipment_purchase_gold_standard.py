"""Gold standard regression test — 변호사형 전체계약 판단 (2026-08-31 지시).

물품 구매 및 설치 계약서(웹젠↔퍼시스, 갑=웹젠/발주자, 을=퍼시스/공급자) 기준.
이 계약은 갑(고객사)이 작성한 표준양식으로, 실제로 존재하는 불리한 조항
(지체상금 무상한·위약벌 배수·귀책불문 해지·하자책임 귀책불문 등)이 다수
있는 반면, 우리 회사(을=퍼시스)가 아직 갖추지 않은 PL보험·사고보고·사용자
매뉴얼·안전인증 같은 "없는 좋은 조항"은 자진해서 추가 제안하면 안 된다.

검증 대상:
  - Priority 1(실제 존재하는 불리한 조항) 반드시 HIGH: 제6조 제5·6항(지체상금
    무상한 + 실손해 중복청구), 제18조(계약금액 3배 위약벌), 제12조(귀책불문
    해지 + 편의해지), 제13조(하자책임 귀책불문 + 제3자 즉시면책)
  - MEDIUM 이상: 제11조(검수 반복불합격 즉시해지, 대금 전액 지급유예),
    제9조(포괄적 사고책임), 제2조(scope creep)
  - Priority 3(없는 조항 신설 권고, isr_/pi_ 체크리스트)는 기본 출력에서
    제외되어야 한다 — PL보험, 사고보고, 사용자 매뉴얼, 안전인증 등을 우리
    회사 의무로 자진 추가 제안하지 않는다.
"""
from __future__ import annotations

import os
import unittest

_FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "fixtures", "webzen_equipment_purchase_install.txt"
)


def _load_fixture() -> str:
    with open(_FIXTURE_PATH, encoding="utf-8") as f:
        return f.read()


class TestWebzenEquipmentPurchaseGoldStandard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = _load_fixture()
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService
        from runtime.review.clause_level import build_clause_level_result

        loader = RuleLoader()
        loader.load()
        service = RuleQueryService(loader)
        bundle = build_clause_level_result(
            service=service,
            entity="퍼시스",
            contract_type="물품공급 및 설치계약서",
            text=cls.text,
            filename="01.물품공급 및 설치 계약서_퍼시스_외부용.pdf",
            answers=None,
            review_focus=None,
            law_service=None,
            ai_provider=None,
            ai_model=None,
            ai_timeout_sec=None,
            ai_max_tokens=None,
            ai_temperature=None,
        )
        cls.crs = [cr for cr in bundle.clause_results if isinstance(cr, dict)]
        cls.by_id = {str(cr.get("clause_id") or ""): cr for cr in cls.crs}

    def _tier(self, clause_id: str) -> str:
        self.assertIn(clause_id, self.by_id, f"{clause_id} not found in clause_results at all")
        return str(self.by_id[clause_id].get("risk_tier") or "").upper()

    # ── Priority 1: 반드시 HIGH ─────────────────────────────────────────────

    def test_late_penalty_rate_uncapped_is_high(self):
        """제6조 제5항: 지체상금 일 1%(10/1000), 상한 없음 → HIGH."""
        self.assertEqual(self._tier("clr_late_penalty_rate_uncapped"), "HIGH")

    def test_penalty_cumulative_with_actual_damage_is_high(self):
        """제6조 제6항: 지체상금 외 실손해 별도청구(중복·누적 책임) → HIGH."""
        self.assertEqual(self._tier("clr_penalty_cumulative_with_actual_damage"), "HIGH")

    def test_penalty_multiple_of_contract_amount_is_high(self):
        """제18조 제5항: 손해 전부 배상 + 계약금액 3배 위약벌 → HIGH."""
        self.assertEqual(self._tier("clr_penalty_multiple_of_contract_amount"), "HIGH")

    def test_no_fault_termination_by_counterparty_is_high(self):
        """제12조 제2항 6호: 귀책사유 불문 미인도 해지 → HIGH."""
        self.assertEqual(self._tier("clr_no_fault_termination_by_counterparty"), "HIGH")

    def test_counterparty_convenience_termination_is_high(self):
        """제12조 제3항: 고객(갑) 편의(경영상 사유) 해지, 보상 규정 없음 → HIGH."""
        self.assertEqual(self._tier("clr_counterparty_convenience_termination_no_compensation"), "HIGH")

    def test_defect_liability_regardless_of_fault_is_high(self):
        """제13조 제1항: 제품 하자로 인한 손해는 귀책사유 불문 책임 → HIGH."""
        self.assertEqual(self._tier("clr_defect_liability_regardless_of_fault"), "HIGH")

    def test_immediate_indemnify_third_party_is_high(self):
        """제13조 제2항: 제3자 청구 즉시 면책 의무 → HIGH."""
        self.assertEqual(self._tier("clr_immediate_indemnify_third_party_claim"), "HIGH")

    # ── MEDIUM 이상 ──────────────────────────────────────────────────────

    def test_inspection_repeat_failure_termination_is_medium_or_higher(self):
        """제11조 제3항: 검수 2회 이상 불합격 시 귀책불문 즉시해지 → MEDIUM 이상."""
        self.assertIn(self._tier("clr_inspection_repeat_failure_immediate_termination"), ("MEDIUM", "HIGH"))

    def test_full_payment_withhold_is_medium_or_higher(self):
        """제11조 제5항: 검수 불합격 시 대금 전부 지급 유예 → MEDIUM 이상."""
        self.assertIn(self._tier("clr_full_payment_refusal_or_withhold"), ("MEDIUM", "HIGH"))

    def test_broad_accident_liability_is_medium_or_higher(self):
        """제9조: 제반사고에 대한 포괄적·무제한 책임 → MEDIUM 이상."""
        self.assertIn(self._tier("clr_broad_uncapped_accident_liability"), ("MEDIUM", "HIGH"))

    def test_scope_creep_is_medium_or_higher(self):
        """제2조 제5항: "갑"이 추가로 요구하는 사항을 포함한다(scope creep) → MEDIUM 이상."""
        self.assertIn(self._tier("clr_scope_creep_unilateral_additional_demand"), ("MEDIUM", "HIGH"))

    # ── Priority 3: 없는 조항 신설 권고는 기본 출력에서 제외 ──────────────────

    def test_no_unsolicited_new_obligation_suggestions_at_high_or_medium(self):
        """PL보험·사고보고·사용자매뉴얼·안전인증 등 '없는 조항 신설' 체크리스트
        항목(is_checklist_item=True)은 사용자가 요청하지 않은 이상 HIGH/MEDIUM으로
        노출되면 안 된다 — 우리 회사(공급자)의 새 의무를 자진 제안하지 않는다."""
        offenders = [
            cr.get("clause_id")
            for cr in self.crs
            if bool(cr.get("is_checklist_item"))
            and str(cr.get("risk_tier") or "").upper() in ("HIGH", "MEDIUM")
        ]
        self.assertEqual(offenders, [], f"체크리스트(누락조항) 항목이 억제되지 않음: {offenders}")

    def test_checklist_items_still_generated_but_demoted(self):
        """체크리스트 injector 자체는 여전히 동작하되(회귀 방지), Priority 3로
        강등되어 있어야 한다 — injector가 아예 안 돌아서 통과하는 거짓양성 방지."""
        demoted = [cr for cr in self.crs if bool(cr.get("_checklist_demoted"))]
        self.assertGreater(len(demoted), 0, "체크리스트 injector가 전혀 동작하지 않음(테스트 자체가 무의미해짐)")


if __name__ == "__main__":
    unittest.main()
