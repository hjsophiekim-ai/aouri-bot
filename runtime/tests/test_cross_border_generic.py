"""국제계약 범용성 회귀 — 기준 계약(원단 수입 매매)에만 맞춘 것이 아님을 성격이 다른 가상 계약 3종으로 고정한다.

1. 미국 회사와의 독점 판매점 계약 — 영문 단일, 뉴욕주법, 뉴욕 법원 전속관할(우리 = 판매점)
2. 중국 공급사와의 OEM 공급계약 — 국·영 병기, CIETAC 중재(중재지·중재인 수·언어 모두 지정), DDP, 선급금 30%(우리 = 구매자)
3. 유럽 회사의 상표 라이선스 — 로열티(원천징수 미정), 준거법 미기재, ICC 중재(우리 = 라이선시)

각 계약에서 크로스보더 공통 체크리스트가 맞게 작동하는지(있어야 할 지적, 없어야 할 오탐), 국내 전용 룰(소비자 대면
판매·딜러 렌탈·위탁판매·하도급법·대리점법)이 사업팀 전달본에 끼어들지 않는지 본다. fixture 는 모두 가상이다.
"""
from __future__ import annotations

import logging
import unittest
from pathlib import Path

from runtime.review.cross_border.engine import run_cross_border_review
from runtime.review.cross_border.evidence import verify_quote
from runtime.review.cross_border.perspective import resolve_perspective

FIX = Path(__file__).resolve().parent / "fixtures"

CASES = {
    "us_distribution": ("intl_us_exclusive_distribution.txt", "미국 공급사로부터 제품을 독점 수입해 판매하는 대리점 계약 검토 부탁드립니다."),
    "cn_oem": ("intl_cn_oem_supply.txt", "중국 공급사로부터 OEM 의자를 구매하는 계약입니다. 대금 지급과 하자 보증 검토 부탁드립니다."),
    "eu_license": ("intl_eu_trademark_license.txt", "독일 상표권자로부터 상표 사용권을 받는 라이선스 계약, 로열티 세금 검토"),
}
DOMESTIC_ONLY_WORDS = ("소비자 대면", "전자상거래법", "렌탈", "위탁판매", "하도급법", "대리점법")


def _text(key: str) -> str:
    return (FIX / CASES[key][0]).read_text(encoding="utf-8")


def _engine(key: str) -> tuple[dict, dict[str, dict]]:
    crs: list[dict] = []
    out = run_cross_border_review(text=_text(key), clause_results=crs, answers_text=CASES[key][1])
    return out, {c["clause_id"]: c for c in crs}


class EngineTest(unittest.TestCase):
    def test_types_and_perspective(self) -> None:
        exp = {"us_distribution": ("international_distribution", "distributor"),
               "cn_oem": ("international_sale_of_goods", "buyer"),
               "eu_license": ("international_license", "licensee")}
        for key, (itype, role) in exp.items():
            out, _f = _engine(key)
            self.assertEqual(out["international_type"], itype, key)
            self.assertEqual(out["perspective"].get("our_role"), role, key)

    def test_us_distribution(self) -> None:
        _out, f = _engine("us_distribution")
        court = f["xb_foreign_court_jurisdiction"]
        self.assertEqual((court["risk_tier"], court["display_path"]), ("MEDIUM", "Article 7.2"))
        self.assertIn("New York", court["problem"])
        # 뉴욕주법으로 확정된 준거법은 지적하지 않는다
        self.assertNotIn("xb_governing_law_missing", f)
        self.assertNotIn("xb_governing_law_undetermined", f)
        # 불가항력 조항이 있다
        self.assertNotIn("xb_force_majeure_missing", f)

    def test_cn_oem(self) -> None:
        _out, f = _engine("cn_oem")
        # 중재기관 하나·중재지·중재인 수·언어가 모두 있다 — 오탐 금지
        self.assertNotIn("xb_arbitration_pathological", f)
        # DDP 로 정해져 있다 — 인도 조건 미선택 아님
        self.assertNotIn("xb_incoterms_unselected", f)
        # 교체 의무가 있다 — 구제수단 지적 없음
        self.assertNotIn("xb_remedies_deduction_only", f)
        adv = f["xb_advance_and_delay_remedies"]
        self.assertEqual(adv["risk_tier"], "MEDIUM")
        self.assertIn("30%", adv["problem"])
        self.assertNotIn("지체상금 상한", adv["clause_title"])   # 지체상금 조항이 없는 계약
        # 영문 우선 조항은 서류 간 우선순위 조항이 아니다
        self.assertNotIn("xb_good_precedence", f)

    def test_eu_license(self) -> None:
        _out, f = _engine("eu_license")
        gl = f["xb_governing_law_missing"]
        self.assertEqual(gl["risk_tier"], "HIGH")
        wht = f["xb_withholding_tax_missing"]
        self.assertEqual(wht["risk_tier"], "MEDIUM")
        self.assertTrue(any("법인세법" in s["citation"] for s in wht["legal_grounding"]["statutes"]))
        # ICC·파리·단독 중재인·영어 — 중재조항은 정상
        self.assertNotIn("xb_arbitration_pathological", f)
        self.assertNotIn("xb_dispute_missing", f)

    def test_quotes_are_exact(self) -> None:
        for key in CASES:
            out, f = _engine(key)
            self.assertEqual(out["dropped_unverified"], [], key)
            t = _text(key)
            for c in f.values():
                for q in c.get("evidence_quotes") or []:
                    self.assertTrue(verify_quote(q, t), (key, c["clause_id"], q))

    def test_perspective_conflict_asks(self) -> None:
        p = resolve_perspective(text=_text("cn_oem"), request_text="중국 업체에 의자를 판매하고 원단도 구매하는 계약 검토")
        self.assertFalse(p["confirmed"])


class PipelineNoDomesticRulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from runtime.review.business_brief import brief_sections
        from runtime.review.clause_extraction import extract_clauses
        from runtime.review.clause_level import build_clause_level_result
        from runtime.review.delivery_docs import brief_from_meta
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService

        loader = RuleLoader()
        loader.load()
        cls.out: dict[str, tuple[dict, list[dict], str]] = {}
        logging.disable(logging.CRITICAL)
        try:
            for key, (name, focus) in CASES.items():
                t = (FIX / name).read_text(encoding="utf-8")
                b = build_clause_level_result(
                    service=RuleQueryService(loader), entity="", contract_type="", text=t, filename=name, answers={},
                    review_focus=focus, law_service=None, ai_provider=None, ai_model=None, ai_timeout_sec=None,
                    ai_max_tokens=None, ai_temperature=None,
                )
                br = brief_from_meta(clause_results=b.clause_results, meta=b.meta, clauses=extract_clauses(t)[0],
                                     contract_text=t, answers={})
                text = "\n".join(x for _h, rows in brief_sections(br) for _s, x in rows)
                cls.out[key] = (b.meta, b.clause_results, text)
        finally:
            logging.disable(logging.NOTSET)

    def test_cross_border_active_everywhere(self) -> None:
        for key, (meta, _crs, _t) in self.out.items():
            self.assertTrue(meta["cross_border"].get("active"), key)
            self.assertTrue(meta["canonical_state"]["international_type"].startswith("international_"), key)

    def test_no_domestic_only_rules_in_brief(self) -> None:
        for key, (_meta, _crs, text) in self.out.items():
            for w in DOMESTIC_ONLY_WORDS:
                self.assertNotIn(w, text, (key, w))

    def test_expected_items_reach_the_brief(self) -> None:
        self.assertIn("외국 법원", self.out["us_distribution"][2])
        self.assertIn("선급금", self.out["cn_oem"][2])
        self.assertIn("준거법", self.out["eu_license"][2])
        self.assertIn("원천징수", self.out["eu_license"][2])


if __name__ == "__main__":
    unittest.main()
