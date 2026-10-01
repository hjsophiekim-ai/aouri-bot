"""Final Senior Counsel Audit 회귀테스트 (2026-09-30 범용 최종보정).

단위 케이스는 한글날 3자 협업계약을 **실제 AI 로** 검토한 결과(40건: HIGH 5·MEDIUM 6·
LOW 29)에서 나온 결함을 그대로 옮겼다. 골든 답안(웹젠·그림닷컴·시험용역·공사도급)이
확인한 판단은 감사가 건드리지 않아야 한다 — 그 파일들이 함께 지킨다.
"""
from __future__ import annotations

import logging
import unittest
from pathlib import Path

from runtime.review.clause_extraction import extract_clauses
from runtime.review.contract_composition import build_contract_composition
from runtime.review.effect_risk_package import build_effect_risk_packages
from runtime.review.entity_resolution import collapse_dual_party, resolve_entities
from runtime.review.jurisdiction_risk_calibration import (
    calibrate_jurisdiction_finding_severity,
    dispute_needs_review,
)
from runtime.review.senior_counsel_audit import our_company_pays, run_senior_counsel_audit

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "hangul_day_100th_alloso_3party_contract.txt"


def _text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def _audit(findings: list[dict], *, archetype: str = "ip_license", text: str | None = None) -> dict:
    t = text if text is not None else _text()
    return run_senior_counsel_audit(
        findings, text=t, clauses=extract_clauses(t)[0],
        entity_resolution=resolve_entities(t, entity="시디즈"), archetype=archetype,
    )


def _f(cid: str, tier: str, title: str, **kw) -> dict:
    d = {"clause_id": cid, "risk_tier": tier, "severity": tier,
         "detected_issue_list": [{"issue_title": title}], "problem": kw.pop("problem", "문제 서술")}
    d.update(kw)
    return d


class GroundingTest(unittest.TestCase):
    def test_new_article_claim_is_moved_to_the_existing_payment_clause_then_rejected_as_adverse(self) -> None:
        # 실측: "제31조 신설 — 지연 시 연 6% 이자" (우리가 지급자)
        f = _f("counsel_economic_04", "MEDIUM", "[경제] 지급 지연 시 이자·지연손해배상 규정 부재",
               display_path="제31조 신설", original_text="(해당 조항 없음 — 계약서에 신설 필요)",
               suggested_rewrite="각 당사자가 지급하여야 할 금액의 지급을 지연하는 경우 연 6%의 이자를 가산하여 지급한다.")
        rep = _audit([f])
        self.assertTrue(f["dedup_suppressed"])
        self.assertEqual(f["senior_audit_removed"], "REJECT_REDLINE_ADVERSE_TO_CLIENT")
        self.assertTrue(f["display_path"].startswith("제12조"), f["display_path"])
        self.assertTrue(rep["our_company_pays"])

    def test_cover_page_quote_is_grounded_to_its_real_clause(self) -> None:
        f = _f("ct_contract_amount_unsettled", "HIGH", "계약금액이 확정되지 않음",
               display_path="계약서 표지(갑지)", article_number=None,
               original_text="총 계약금액 : 금 ____________________원 □ VAT 포함 / □ VAT 별도 ② 위 계약금액은",
               suggested_rewrite="계약금액: 일금 ○○○원(부가가치세 별도) — 서명 전 확정 필수. 확정 전까지 지체상금 산정의 기준이 되는 잠정금액을 명시한다.")
        _audit([f])
        self.assertFalse(f.get("dedup_suppressed"), f.get("senior_audit_reason"))
        self.assertEqual(f["display_path"], "제8조 제1항")
        self.assertEqual(f["risk_tier"], "HIGH")

    def test_existing_article_in_path_is_kept(self) -> None:
        f = _f("CWC-07", "MEDIUM", "하자담보 기간 불명확", display_path="제13조",
               original_text="(해당 조항 없음 — 신설 필요)")
        _audit([f])
        self.assertEqual(f["display_path"], "제13조")
        self.assertEqual(f["article_number"], "13")
        self.assertIn("제13조 말미에 다음 문구 추가", f.get("location_instruction", ""))

    def test_empty_template_without_location_is_removed(self) -> None:
        f = _f("svc_delay_response", "LOW", "[권고] 일정 지연 대응 조항", problem="",
               display_path=None, original_text="")
        _audit([f])
        self.assertTrue(f.get("dedup_suppressed"))


class RedlineTest(unittest.TestCase):
    def test_template_party_noun_absent_from_contract_blocks_the_redline(self) -> None:
        # 실측: 제24조 제2항에 "위탁자는 … 중도 해지할 수 있다"
        f = _f("clr_termination_right_restricted", "MEDIUM", "제24조 제2항 [계약기간 대비 해지권 과도 제한]",
               display_path="제24조 제2항", article_number="24", original_text="협업자는 자신의 귀책 범위 내에서 책임을 부담한다.",
               suggested_rewrite="위탁자는 상당한 기간 전 서면 통지로 본 약정을 중도 해지할 수 있다.")
        _audit([f])
        self.assertTrue(f.get("dedup_suppressed"))

    def test_template_party_noun_is_mapped_to_the_contract_term(self) -> None:
        text = ('"고객"과 "매체사"는 다음과 같이 계약한다.\n제1조 (목적)\n"고객"은 광고료를 지급하고 "매체사"는 송출한다.\n'
                '제2조 (송출)\n"매체사"는 "고객"에게 송출 실적을 제출한다.\n')
        f = _f("ADM-01", "HIGH", "송출 실적 확인 수단 없음", display_path="제2조", article_number="2",
               original_text='"매체사"는 "고객"에게 송출 실적을 제출한다.',
               suggested_rewrite="매체사는 송출 실적 자료를 광고주에게 제출하고, 광고주는 미달분의 반환을 청구할 수 있다.")
        _audit([f], archetype="service_engagement", text=text)
        self.assertFalse(f.get("dedup_suppressed"))
        self.assertNotIn("광고주", f["suggested_rewrite"])
        self.assertIn("고객에게", f["suggested_rewrite"])
        self.assertIn("고객은", f["suggested_rewrite"])

    def test_descriptive_role_word_is_not_a_party_noun(self) -> None:
        f = _f("clr_fault_blind", "MEDIUM", "제12조 제4항 [판매취소 환수 — 귀책 구분 없음]",
               display_path="제12조 제4항", article_number="12", original_text="판매 로열티는 월별 정산하여 지급한다.",
               suggested_rewrite="다만 상품 공급자의 귀책사유로 취소된 경우에는 환수하지 아니한다.")
        _audit([f])
        self.assertFalse(f.get("dedup_suppressed"))

    def test_mention_or_negation_of_penalty_is_not_a_new_burden(self) -> None:
        f = _f("x", "MEDIUM", "제12조 제4항 정산", display_path="제12조 제4항", article_number="12",
               original_text="판매 로열티는 월별 정산한다.",
               suggested_rewrite="이 경우 정산 외에 위약금 등 추가 부담을 지지 아니한다.")
        _audit([f])
        self.assertFalse(f.get("dedup_suppressed"))


class MaterialityTest(unittest.TestCase):
    def test_domestic_jurisdiction_is_boilerplate_low(self) -> None:
        f = _f("KR-29-p2", "HIGH", "관할법원 특정", display_path="제29조 제2항", article_number="29",
               original_text="민사소송법상 관할법원을 제1심 전속 관할법원으로 한다.")
        _audit([f])
        self.assertEqual(f["risk_tier"], "LOW")
        self.assertTrue(f.get("boilerplate_low_priority"))

    def test_multinational_rule_on_domestic_contract_is_removed(self) -> None:
        f = _f("ACT-004", "MEDIUM", "다국가 거래 분쟁조항 점검", display_path="제29조 제2항", article_number="29",
               original_text="민사소송법상 관할법원을 제1심 전속 관할법원으로 한다.")
        _audit([f])
        self.assertTrue(f.get("dedup_suppressed"))

    def test_foreign_counterparty_keeps_jurisdiction_review(self) -> None:
        self.assertTrue(dispute_needs_review("Trendway Corp. Inc. 와 주식회사 퍼시스는 체결한다. 관할은 뉴욕 법원으로 한다."))
        self.assertFalse(dispute_needs_review(_text()))

    def test_severability_clause_does_not_disable_the_jurisdiction_cap(self) -> None:
        # 실측: 제30조 제2항 "무효 또는 집행 불가능한 것으로 판단되더라도"가 상한을 통째로 껐다.
        sev, changed, _ = calibrate_jurisdiction_finding_severity(
            "HIGH", "민사소송법상 관할법원을 제1심 전속 관할법원으로 한다.", _text(), "분쟁의 해결")
        self.assertEqual((sev, changed), ("LOW", True))

    def test_tax_invoice_timing_is_not_high(self) -> None:
        f = _f("counsel_KR-12-p4", "HIGH", "[세무] 세금계산서 발행 주체·시기 불명확",
               display_path="제12조 제4항", article_number="12", original_text="판매 로열티는 월별 정산한다.",
               high_severity_basis="counsel_agent[tax]: 가산세")
        _audit([f])
        # 2026-10-01 Triage 지시 7항 — 법무 finding 이 아니라 재경·세무 확인사항으로 옮긴다.
        self.assertEqual(f["risk_tier"], "LOW")
        self.assertTrue(f.get("finance_check"))
        self.assertEqual(f.get("triage"), "FINANCE_CHECK")

    def test_prepayment_guarantee_not_demanded_for_creative_collaboration(self) -> None:
        f = _f("svc_prepayment_guarantee", "LOW", "[권고] 선급금 보증 구조", display_path="제8조 제1항",
               article_number="8", original_text="총 계약금액 : 금 ___원")
        _audit([f], archetype="ip_license")
        self.assertTrue(f.get("dedup_suppressed"))

    def test_high_with_rule_basis_is_not_demoted_by_count(self) -> None:
        highs = [
            _f(f"H{i}", "HIGH", f"제{i}조 손해배상 책임 범위", display_path=f"제{i}조", article_number=str(i),
               original_text="손해를 배상한다.", high_severity_basis="declared:approval_required")
            for i in range(1, 9)
        ]
        _audit(highs, archetype="goods_supply", text="\n".join(f"제{i}조 (책임)\n손해를 배상한다." for i in range(1, 9)))
        self.assertEqual([h["risk_tier"] for h in highs], ["HIGH"] * 8)


class PackageTest(unittest.TestCase):
    def test_ip_findings_across_articles_become_one_package(self) -> None:
        a = _f("KR-10-p4", "HIGH", "[법률] 지식재산권 귀속 및 이용권 범위 불명확", display_path="제10조 제4항",
               article_number="10", original_text="협업자는 … 이용권을 허락한다.", suggested_rewrite="협업자는 … 이용권을 허락한다. 온라인 판매를 포함한다.")
        b = _f("eb_ip_no_derivative_right__KR-9-p3", "MEDIUM", "2차적저작물작성권의 포함 여부가 명시되지 않음",
               display_path="제9조 제3항", article_number="9", original_text="저작권은 협업자에게 귀속된다.")
        _audit([a, b])
        self.assertTrue(b["dedup_suppressed"])
        self.assertEqual(b["dedup_merged_into"], "KR-10-p4")
        self.assertEqual(a["sub_issues"][0]["display_path"], "제9조 제3항")
        self.assertIn("[통합된 하위 쟁점]", a["problem"])

    def test_distinct_liability_risks_in_different_articles_stay_separate(self) -> None:
        a = _f("L1", "HIGH", "무과실 하자 손해배상 책임", display_path="제22조", article_number="22", original_text="손해를 배상한다.")
        b = _f("L2", "HIGH", "계약금액 배수 손해배상", display_path="제24조", article_number="24", original_text="손해를 배상한다.")
        _audit([a, b])
        self.assertFalse(a.get("dedup_suppressed") or b.get("dedup_suppressed"))

    def test_duplicate_low_titles_collapse(self) -> None:
        lows = [_f(f"KR-{i}", "LOW", "정산식·차감사유·증빙 필수화", display_path=f"제{i}조", article_number=str(i),
                   original_text="정산한다.") for i in (8, 12, 16)]
        _audit(lows)
        # 2026-10-01 Triage 이후로는 정산 세부가 KEEP 으로 빠질 수도 있다 — 노출 항목이 1건 이하면 된다.
        self.assertLessEqual(
            sum(1 for c in lows if not c.get("dedup_suppressed") and not c.get("keep_as_is")), 1)


class RootCauseTest(unittest.TestCase):
    def test_ownership_retention_clause_does_not_trigger_pre_performance_chain(self) -> None:
        text = (
            "제3조 (자료)\n갑은 을에게 자료를 제공한다. 을은 검수 완료 후 결과물을 납품한다.\n"
            "제4조 (권리)\n제공자료에 관한 소유권은 갑에 귀속되며 자료 제공 자체가 을에게 해당 권리를 "
            "이전하는 것으로 해석되지 않는다.\n"
        )
        chains = {c["key"] for c in build_effect_risk_packages(text=text, our_labels=("갑",))}
        self.assertNotIn("pre_performance_recovery", chains)

    def test_license_archetype_has_no_pre_performance_chain(self) -> None:
        chains = {c["key"] for c in build_effect_risk_packages(text=_text(), archetype="ip_license")}
        self.assertNotIn("pre_performance_recovery", chains)

    def test_our_company_is_the_payer_in_hangul_day(self) -> None:
        self.assertTrue(our_company_pays(_text(), resolve_entities(_text(), entity="시디즈")))

    def test_brand_and_legal_entity_are_never_two_parties(self) -> None:
        res = resolve_entities(_text(), entity="시디즈")
        self.assertEqual(collapse_dual_party("시디즈 및 알로소의 사전 동의", res), "주식회사 시디즈(알로소)의 사전 동의")
        self.assertEqual(collapse_dual_party("알로소 법인이 지급한다", res), "주식회사 시디즈(알로소)가 지급한다")
        self.assertEqual(collapse_dual_party("알로소 및 기획·디렉팅사의 동의", res), "알로소 및 기획·디렉팅사의 동의")

    def test_composite_contract_type(self) -> None:
        comp = build_contract_composition(_text(), canonical_label="지식재산권 실시허락(라이선스) 계약", party_count=3)
        self.assertTrue(comp["is_composite"])
        self.assertEqual(comp["primary_contract_type"], "공적 지원사업 기반 3자 아트상품 개발·제작 및 협업계약")
        for el in ("창작·개발", "제작", "IP 이용허락", "전시·홍보", "상업판매", "로열티", "지원사업 정산"):
            self.assertIn(el, comp["secondary_contract_elements"])


class HangulDayPipelineAuditTest(unittest.TestCase):
    """AI 없이 전체 파이프라인 — 최종 출력이 지시 20항 점검을 통과하는가."""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.review.clause_level import build_clause_level_result
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService

        loader = RuleLoader()
        loader.load()
        logging.disable(logging.CRITICAL)
        try:
            b = build_clause_level_result(
                service=RuleQueryService(loader), entity="시디즈", contract_type="", text=_text(),
                filename="한글날.docx", answers={}, review_focus="알로소는 주식회사 시디즈의 브랜드입니다.",
                law_service=None, ai_provider=None, ai_model=None, ai_timeout_sec=None,
                ai_max_tokens=None, ai_temperature=None,
            )
        finally:
            logging.disable(logging.NOTSET)
        cls.meta, cls.results = b.meta, b.clause_results

    def _visible(self) -> list[dict]:
        return [c for c in self.results if not c.get("dedup_suppressed") and not c.get("keep_as_is")
                and str(c.get("risk_tier") or "").upper() in ("HIGH", "MEDIUM", "LOW")]

    def test_final_check_passes(self) -> None:
        audit = self.meta["senior_counsel_audit"]
        self.assertEqual(audit["final_check_failed"], [], audit["final_check"])

    def test_no_pre_performance_chain_or_multinational_rule(self) -> None:
        ids = [c["clause_id"] for c in self._visible()]
        self.assertFalse([i for i in ids if "pre_performance" in i], ids)
        self.assertFalse([c for c in self._visible() if "다국가" in str(c.get("detected_issue_list"))])

    def test_core_findings_carry_article_numbers(self) -> None:
        for c in self._visible():
            if str(c["risk_tier"]).upper() == "LOW" or c.get("is_entity_name_correction"):
                continue
            self.assertTrue(str(c.get("article_number") or "").strip(), c["clause_id"])
            self.assertNotRegex(str(c.get("display_path") or ""), r"신설|해당 조항 없음")

    def test_composite_type_in_canonical_state(self) -> None:
        cs = self.meta["canonical_state"]
        self.assertEqual(cs.get("primary_contract_type"), "공적 지원사업 기반 3자 아트상품 개발·제작 및 협업계약")
        self.assertIn("로열티", cs.get("secondary_contract_elements") or [])


if __name__ == "__main__":
    unittest.main()
