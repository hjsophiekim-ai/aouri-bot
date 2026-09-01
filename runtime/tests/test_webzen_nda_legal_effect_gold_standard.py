"""Gold standard regression test — 변호사형 전체계약 판단 > NDA 범용 legal
effect reasoning (2026-09-01 지시).

퍼시스-웹젠 비밀유지협약서(NDA) 기준. 이 계약은 "웹젠과 상대사 중 비밀정보를
제공하는 자를 제공자, 제공받는 자를 수신자라 하고, 정보별로 제공자·수신자가
분별된다"는 상호(mutual) NDA다.

이 골든 테스트는 조항번호가 아니라 "법률효과"를 검증한다 — 아래 assertion들은
전부 조항 내용에 실제로 존재하는 legal-effect 패턴(간접손해 포함 무제한
배상, 제3자 연대책임, 최선노력 관리의무, 관련계약 해지, 윤리조항 클러스터,
존속기간 불명확)을 규칙 엔진(common_legal_risk.py)이 회사명·파일명·조항번호를
하드코딩하지 않고 탐지하는지 확인하기 위한 것이다. 특히 semantic mismatch
(반환·폐기 조항에 해지제한 문구 삽입, 양도조항의 연대책임을 지급보증으로
오독)가 재발하지 않는지가 핵심 검증 대상이다.
"""
from __future__ import annotations

import os
import unittest

_FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "webzen_nda.txt")


def _load_fixture() -> str:
    with open(_FIXTURE_PATH, encoding="utf-8") as f:
        return f.read()


class TestWebzenNdaLegalEffectGoldStandard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = _load_fixture()
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService
        from runtime.review.clause_level import build_clause_level_result
        from runtime.review.contract_classifier import classify_contract_detailed

        loader = RuleLoader()
        loader.load()
        service = RuleQueryService(loader)
        cls.detailed = classify_contract_detailed(
            entity="퍼시스", contract_type="비밀유지협약서(NDA)", text=cls.text,
            filename="02.비밀유지협약서_퍼시스_외부용.pdf",
        )
        bundle = build_clause_level_result(
            service=service,
            entity="퍼시스",
            contract_type="비밀유지협약서(NDA)",
            text=cls.text,
            filename="02.비밀유지협약서_퍼시스_외부용.pdf",
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
        cls.meta = bundle.meta

    def _tier(self, clause_id: str) -> str:
        self.assertIn(clause_id, self.by_id, f"{clause_id} not found in clause_results at all")
        return str(self.by_id[clause_id].get("risk_tier") or "").upper()

    # ── 계약유형/당사자 지위 (Layer 0 — document understanding) ────────────

    def test_contract_type_is_nda(self):
        self.assertEqual(self.detailed.contract_type, "nda_confidentiality")

    def test_dealer_profile_not_triggered_by_stale_contract_type_label(self):
        """실사례(2026-09-01): UI가 넘긴 contract_type 라벨이 실제로는
        "대리점/위탁/유통"이라는 무관한 stale 값이었는데, 그 문자열에
        "대리점"이 부분 포함되어 있다는 이유만으로 dealer_consignment
        profile로 오분류되어 조 번호 8/9/10=정산 하드코딩 체크리스트가
        NDA의 반환·양도금지 조항에 엉뚱한 "정산" 문구를 주입했다. canonical
        분류기(nda_confidentiality)가 이 라벨보다 우선해야 한다."""
        from runtime.review.priority_map import infer_contract_profile
        prof = infer_contract_profile(
            contract_type="대리점/위탁/유통", text=self.text, canonical_type_code="nda_confidentiality",
        )
        self.assertEqual(prof.profile, "general")

    def test_our_role_is_not_forced_into_fixed_bucket(self):
        """양사가 정보별로 제공자/수신자가 바뀌는 상호 NDA이므로, 퍼시스를
        수탁자 등 고정된 방향성 role로 강제 분류하면 안 된다."""
        from runtime.review.party_role import infer_party_role
        party = infer_party_role(
            entity="퍼시스", contract_type="비밀유지협약서(NDA)", text=self.text,
            answers={}, contract_type_code="nda_confidentiality",
        )
        self.assertNotIn(party.our_role, ("수탁자", "consignment_dealer", "dealer"))

    # ── legal-effect 탐지 (Layer 1/2) ────────────────────────────────────

    def test_uncapped_consequential_damages_detected_high(self):
        """제9조: 직접손해뿐 아니라 간접손해·예상손실·위자료·법률비용까지
        포함한 상한 없는 손해배상 범위 → HIGH."""
        self.assertEqual(self._tier("clr_uncapped_consequential_damages"), "HIGH")

    def test_third_party_joint_liability_detected(self):
        """제6조 제5항: 제3자/하청업체의 고의·과실에 대한 연대책임(선정·감독
        귀책 불문) → MEDIUM 이상."""
        self.assertIn(self._tier("clr_third_party_joint_liability_regardless_of_selection_fault"), ("MEDIUM", "HIGH"))

    def test_best_efforts_care_standard_detected(self):
        """제6조 제1항: '가능한 최선의 노력' 관리의무 기준의 모호함 → MEDIUM 이상."""
        self.assertIn(self._tier("clr_best_efforts_standard_of_care_ambiguous"), ("MEDIUM", "HIGH"))

    def test_related_contract_termination_detected(self):
        """제6조 제6항: 이 계약(NDA) 위반만으로 관련 정식 계약을 해지·해제
        가능 → MEDIUM 이상."""
        self.assertIn(self._tier("clr_breach_triggers_related_contract_termination"), ("MEDIUM", "HIGH"))

    def test_related_contract_termination_escalates_to_high_when_no_safeguards(self):
        """제6조 제6항 원문에는 위반의 중대성 제한/귀책사유 요건/시정기간·
        최고 절차가 전혀 없다(2026-09-01 실사례 — 실제 앱 사용 중 이 finding
        자체가 최종 리뷰 결과에서 통째로 사라진 사고가 있었음). 세 보호장치가
        전부 없으면 MEDIUM 고정이 아니라 HIGH로 격상되어야 한다."""
        cr = self.by_id["clr_breach_triggers_related_contract_termination"]
        self.assertEqual(str(cr.get("risk_tier")).upper(), "HIGH")
        self.assertEqual(cr.get("original_effect_tags"), ["cross_default"])

    def test_related_contract_termination_survives_into_final_filtered_output(self):
        """clr_breach_triggers_related_contract_termination이 raw clause_
        results에 존재하는 것만으로는 부족하다 — output_filter의 병합
        로직이 "제6조"라는 article 단위 display_path만 보고 같은 조 안의
        서로 다른 항(①최선노력/⑤제3자연대/⑥관련계약해지) 3건을 하나로
        뭉개 2건을 조용히 삭제하는 사고가 실제로 있었다(2026-09-01). 이
        finding이 실제로 사용자가 보는 최종 출력(high/medium_issues_
        filtered)에 살아남는지 직접 확인한다."""
        final_ids = {
            str(i.get("clause_id") or "")
            for i in (self.meta.get("high_issues_filtered") or []) + (self.meta.get("medium_issues_filtered") or [])
        }
        self.assertIn("clr_breach_triggers_related_contract_termination", final_ids)
        self.assertIn("clr_third_party_joint_liability_regardless_of_selection_fault", final_ids)
        self.assertIn("clr_best_efforts_standard_of_care_ambiguous", final_ids)

    def test_ethics_morality_overbreadth_cluster_detected_high(self):
        """제12조: 사생활 영역까지 포함하는 광범위 품위의무 + 최고절차 없는
        즉시해지(관련계약 포함) + 손해배상청구 포기 — 하나의 cluster로
        HIGH 판단."""
        self.assertEqual(self._tier("clr_ethics_morality_termination_waiver_cluster"), "HIGH")

    def test_indefinite_survival_detected(self):
        """제5조 제2항: 비밀유지의무가 '유효한 것으로 한다'고만 되어 있고
        구체적 존속기간(예: N년)이 없음 → MEDIUM 이상."""
        self.assertIn(self._tier("clr_confidentiality_survival_undefined"), ("MEDIUM", "HIGH"))

    # ── semantic mismatch 회귀 방지 (Layer 3 — rule validator) ──────────

    def test_return_destruction_not_falsely_classified_as_termination_issue(self):
        """제8조(비밀정보의 반환)는 반환·폐기 의무 조항이지 해지권 조항이
        아니다 — '해지 사유를 객관적 중대위반으로 한정' 같은 해지제한
        템플릿이 삽입되면 안 된다(semantic mismatch: return/destruction →
        termination)."""
        art8 = [cr for cr in self.crs if str(cr.get("article_number")) == "8"]
        for cr in art8:
            sr = str(cr.get("suggested_rewrite") or "")
            self.assertNotIn("시정기간", sr, f"제8조 rewrite에 해지제한 템플릿 오염: {sr!r}")
            self.assertNotIn("최고절차", sr, f"제8조 rewrite에 해지제한 템플릿 오염: {sr!r}")

    def test_assignment_joint_liability_not_falsely_classified_as_payment_guarantee(self):
        """제10조(양도 등의 금지)의 '양수인 또는 하청인 등과 연대하여
        책임을 진다'는 양도 시 원채무자 책임 존속 조항이지 미수금/지급보증
        조항이 아니다(semantic mismatch: joint liability on assignment →
        payment guarantee)."""
        art10 = [cr for cr in self.crs if str(cr.get("article_number")) == "10"]
        for cr in art10:
            blob = str(cr.get("suggested_rewrite") or "") + str(cr.get("rewrite_reason") or "")
            self.assertNotIn("미수금", blob, f"제10조 finding이 미수금/지급보증으로 오분류됨: {blob!r}")
            self.assertNotIn("지급보증", blob, f"제10조 finding이 미수금/지급보증으로 오분류됨: {blob!r}")

    def test_no_industry_specific_goods_checklist_leaked_into_nda(self):
        """실사례(2026-09-01): 이 NDA의 목적 조항 서두("집무실 가구 구매 및
        설치 업무")가 전체텍스트 키워드 스캔(_classify_contract_type_by_
        substance)을 오염시켜 _contract_class가 "project_installation"으로
        오분류된다 — 실제로 확인됨. 이 상태에서도 industry-specific
        제조물/설치 체크리스트(isr_*)가 raw clause_results에 전혀 생성되지
        않아야 한다(Contract Legal Map의 실제 급부 요약에는 물품·제조·설치
        신호가 없으므로)."""
        from runtime.review.clause_level import _classify_contract_type as _cc
        self.assertEqual(_cc("비밀유지협약서(NDA)", self.text, "x.pdf"), "project_installation")
        isr_ids = [str(cr.get("clause_id") or "") for cr in self.crs if str(cr.get("clause_id") or "").startswith("isr_")]
        self.assertEqual(isr_ids, [], f"NDA에 무관한 제조물/설치 체크리스트가 생성됨: {isr_ids}")

    def test_no_unsolicited_new_obligation_suggestions_at_high_or_medium(self):
        """PL보험·매뉴얼·안전인증 등 '없는 조항 신설' 체크리스트 항목은
        NDA에도 우리 회사의 새 의무로 자진 제안되면 안 된다."""
        offenders = [
            cr.get("clause_id")
            for cr in self.crs
            if bool(cr.get("is_checklist_item"))
            and str(cr.get("risk_tier") or "").upper() in ("HIGH", "MEDIUM")
        ]
        self.assertEqual(offenders, [], f"체크리스트(누락조항) 항목이 억제되지 않음: {offenders}")


if __name__ == "__main__":
    unittest.main()
