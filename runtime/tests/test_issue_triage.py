"""Issue Triage 회귀테스트 (2026-10-01 지시) — MUST/SHOULD/KEEP/FINANCE_CHECK/DROP.

Golden Benchmark(지시 17항, 팀원 판단 — 한글날 3자 아트상품 협업계약)
    아티스트 권한보증 → KEEP          하자/A/S 책임경계 → KEEP
    대금/로열티 구조 → 대부분 KEEP     선급금 보증보험 → DROP
    관할 → DROP/LOW                   Background IP → SHOULD FIX
    실물 소유권 → SHOULD/MUST FIX      지원사업 상위기준 → SHOULD FIX
    일반 세무 디테일 → FINANCE CHECK
"""
from __future__ import annotations

import logging
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

from runtime.review.clause_extraction import extract_clauses
from runtime.review.entity_resolution import resolve_entities
from runtime.review.issue_triage import (
    DROP, FINANCE_CHECK, KEEP, MUST_FIX, SHOULD_FIX, materiality, triage_one,
)
from runtime.review.senior_counsel_audit import run_senior_counsel_audit

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "hangul_day_100th_alloso_3party_contract.txt"


def _text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def _f(cid: str, tier: str, title: str, **kw) -> dict:
    d = {"clause_id": cid, "risk_tier": tier, "severity": tier,
         "detected_issue_list": [{"issue_title": title}], "problem": kw.pop("problem", "문제")}
    d.update(kw)
    return d


def _audit(findings: list[dict]) -> dict:
    t = _text()
    return run_senior_counsel_audit(
        findings, text=t, clauses=extract_clauses(t)[0],
        entity_resolution=resolve_entities(t, entity="시디즈"), archetype="ip_license",
    )


class TriageUnitTest(unittest.TestCase):
    def test_tax_detail_is_finance_check(self) -> None:
        f = _f("counsel_tax", "MEDIUM", "[세무] 세금계산서 발행 시기 불명확", is_counsel_agent=True,
               display_path="제12조 제4항", article_number="12", original_text="월별 정산하여 다음 달 말일까지 지급한다.")
        _audit([f])
        self.assertEqual(f["triage"], FINANCE_CHECK)
        self.assertEqual(f["risk_tier"], "LOW")

    def test_domestic_jurisdiction_is_dropped(self) -> None:
        f = _f("KR-29-p2", "MEDIUM", "관할법원 특정", display_path="제29조 제2항", article_number="29",
               original_text="민사소송법상 관할법원을 제1심 전속 관할법원으로 한다.")
        _audit([f])
        self.assertNotIn(f.get("triage"), (MUST_FIX, SHOULD_FIX))

    def test_existing_authority_warranty_is_keep(self) -> None:
        # 실측(AI): "[법률] 아티스트 권한·보증 불충분에 따른 제3자 권리침해 위험" HIGH
        f = _f("counsel_legal_03", "HIGH", "[법률] 아티스트 권한·보증 불충분에 따른 제3자 권리침해 위험",
               is_counsel_agent=True, display_path="제20조 제1항", article_number="20", paragraph_number="1",
               original_text="협업자는 참여 아티스트로부터 본 계약 체결 및 이행에 필요한 적법한 권한을 위임받았음을 확인한다.",
               suggested_rewrite="협업자는 … 보증한다.")
        _audit([f])
        self.assertEqual(f["triage"], KEEP)
        self.assertTrue(f["keep_as_is"])

    def test_concrete_settlement_detail_is_keep(self) -> None:
        f = _f("counsel_econ", "HIGH", "[경제] 반복 제작비·실비 정산 기준·증빙 불명확", is_counsel_agent=True,
               display_path="제12조 제2항", article_number="12", original_text="반복 제작비는 월별 정산한다.",
               suggested_rewrite="… 증빙을 첨부한다.")
        _audit([f])
        self.assertEqual(f["triage"], KEEP)

    def test_blank_amount_stays_must_fix(self) -> None:
        f = _f("ct_contract_amount_unsettled", "HIGH", "계약금액이 확정되지 않음 — 연동된 금전 노출 전부가 미확정",
               display_path="제8조 제1항", article_number="8", original_text="총 계약금액 : 금 ___원",
               suggested_rewrite="계약금액: 일금 ○○○원(부가가치세 별도) — 서명 전 확정 필수.")
        _audit([f])
        self.assertEqual(f["triage"], MUST_FIX)
        self.assertEqual(f["risk_tier"], "HIGH")

    def test_generated_high_with_modest_score_becomes_should(self) -> None:
        f = _f("counsel_ip", "HIGH", "[법률] 지식재산권 이용권 범위 불명확", is_counsel_agent=True,
               display_path="제10조 제4항", article_number="10", paragraph_number="4",
               original_text="협업자는 판매기간 동안 알로소가 … 판매·유통하는 데 필요한 이용권을 허락한다.",
               suggested_rewrite="협업자는 … 이용권(2차적저작물 작성·이용 포함)을 허락한다.")
        _audit([f])
        self.assertEqual(f["triage"], SHOULD_FIX)
        self.assertEqual(f["risk_tier"], "MEDIUM")

    def test_rule_high_is_not_demoted_by_score(self) -> None:
        # 규칙이 원문으로 확인한 HIGH(골든 답안)는 점수로 내리지 않는다.
        label, _, _ = triage_one(
            _f("clr_fault_blind", "HIGH", "무과실 하자 책임"), axis="defect", relations=[],
            contract_text="", article_text="",
        )
        self.assertEqual(label, MUST_FIX)

    def test_ai_entity_finding_is_dropped_when_name_corrections_exist(self) -> None:
        ai = _f("counsel_entity", "HIGH", "[법률] 계약 당사자 표기 오류로 인한 권리·의무 주체 불명확",
                is_counsel_agent=True, display_path="제30조 제3항", article_number="30",
                original_text="본 계약과 관련하여 별도로 작성하고", suggested_rewrite="…")
        fix = _f("ENTITY_NAME__party_block_a", "MEDIUM", "계약 당사자 법인명 오기 — 전문(당사자 표시)",
                 is_entity_name_correction=True, display_path="전문(당사자 표시)", original_text="주식회사 알로소",
                 suggested_rewrite="주식회사 시디즈(브랜드명: 알로소)")
        _audit([ai, fix])
        self.assertTrue(ai["dedup_suppressed"])
        self.assertFalse(fix.get("dedup_suppressed"))

    def test_materiality_axes(self) -> None:
        s = materiality(_f("x", "MEDIUM", "실물 소유권 귀속 주체가 선택되지 않음"), "ip", ["physical_ownership"])
        self.assertEqual(sum(s.values()) >= 5, True, s)
        s2 = materiality(_f("y", "MEDIUM", "정산식·차감사유·증빙 필수화"), "payment", [])
        self.assertLessEqual(sum(s2.values()), 4, s2)


class HangulDayBenchmarkTest(unittest.TestCase):
    """AI 없이 전체 파이프라인 — 팀원 판단과 같은 선별이 나오는가(지시 17항)."""

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
        cls.triage = cls.meta["senior_counsel_audit"]["triage"]

    def _titles(self, label: str) -> list[str]:
        return [r["title"] for r in self.triage[label]]

    def test_artist_authority_is_keep(self) -> None:
        self.assertTrue([t for t in self._titles(KEEP) if "권한" in t], self._titles(KEEP))

    def test_should_fix_set(self) -> None:
        should = " | ".join(self._titles(SHOULD_FIX))
        self.assertIn("실물 소유권", should)          # 실물 소유권 → SHOULD
        self.assertIn("상위 지원사업 협약", should)    # 지원사업 상위기준 → SHOULD
        self.assertIn("2차적저작물", should)          # Background IP·이용권 → SHOULD

    def test_must_fix_is_small_and_core(self) -> None:
        must = self._titles(MUST_FIX)
        self.assertLessEqual(len(must), 3, must)
        self.assertTrue(any("계약금액" in t for t in must), must)

    def test_no_boilerplate_or_prepayment_in_core(self) -> None:
        core = " | ".join(self._titles(MUST_FIX) + self._titles(SHOULD_FIX))
        for bad in ("관할", "준거법", "선급금", "보증보험", "세금계산서"):
            self.assertNotIn(bad, core)

    def test_report_has_keep_section(self) -> None:
        from runtime.review.legal_review_docx import build_legal_review_docx

        ff = self.meta["final_findings"]
        finance = _f("fin", "LOW", "[세무] 세금계산서 발행 시기", finance_check=True,
                     display_path="제12조 제4항", problem="공급시기에 맞춘 세금계산서 발행 주체 확인")
        data = build_legal_review_docx(
            entity="시디즈", contract_type="", filename="한글날.docx", clause_results=self.results + [finance],
            canonical_state=self.meta.get("canonical_state"), top_risks_filtered=ff["top_risks"],
            high_issues_filtered=ff["high_issues"], medium_issues_filtered=ff["medium_issues"],
        )
        with zipfile.ZipFile(BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        self.assertIn("현행 유지(KEEP) 판단", xml)
        self.assertIn("[KEEP] 제20조 제1항", xml)
        self.assertIn("재경·세무 확인사항", xml)


if __name__ == "__main__":
    unittest.main()
