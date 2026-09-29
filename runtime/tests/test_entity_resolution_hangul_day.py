"""Entity Resolution Golden Test — 한글날 제정 100주년 3자 협업 계약 (2026-09-30).

계약서 서두·서명란에 "주식회사 알로소"라고 적혀 있다. 알로소는 주식회사
시디즈의 **브랜드**이지 법인이 아니다(담당자 확정 사실). 권리·의무의 귀속
주체는 주식회사 시디즈다.

PASS 조건 (지시 8항)
  · "주식회사 알로소"를 독립 법인으로 인식하지 않는다
  · legal entity = 주식회사 시디즈, brand = 알로소, 우리 회사 = 주식회사 시디즈
  · 계약당사자 표기 오류를 REVIEW_FAILED_LEGAL_ENTITY_MISMATCH 로 검출한다
  · 서두·서명란의 "주식회사 알로소"를 각각 수정 필요로 표시한다
  · finding 에서 시디즈와 알로소를 서로 다른 당사자로 다루지 않는다

실측으로 잡힌 함정도 함께 고정한다.
  1. 파서가 서명란을 마지막 조항(제30조 ③)에 붙이면 그 조항 글자에
     "주식회사 알로소"가 들어가, 글자가 같은 서두 줄을 "이미 다뤘다"고 보고
     서두 오기를 놓쳤다.
  2. "브랜드만 한 줄" 규칙이 조문 안의 "① 알로소"(정의된 약칭의 소제목)를
     당사자란으로 읽어 제3조를 고치려 했다.
  3. 서술 정규화가 정정 finding 의 설명까지 고쳐 "주식회사 시디즈(알로소)는
     주식회사 시디즈의 브랜드"가 됐다.
"""
from __future__ import annotations

import logging
import re
import unittest
from pathlib import Path

from runtime.review.delivery_gate import REMEDIABLE_STATUSES
from runtime.review.entity_name_correction import (
    build_name_correction_findings,
    find_name_hits,
    split_party_regions,
)
from runtime.review.entity_resolution import (
    STATUS_LEGAL_ENTITY_MISMATCH,
    normalize_findings,
    normalize_party_narrative,
    parse_user_brand_facts,
    resolve_entities,
)
from runtime.review.report_header import build_section1_rows

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "hangul_day_100th_alloso_3party_contract.txt"
USER_FACT = "알로소는 주식회사 시디즈의 브랜드입니다."

#: 법인으로서의 알로소 — 어떤 출력에도 권리·의무 주체로 나오면 안 된다.
RX_ALLOSO_AS_COMPANY = re.compile(r"주식회사\s*알로소|㈜\s*알로소|알로소\s*주식회사|알로소\s*법인")


def _text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


class HangulDayResolutionTest(unittest.TestCase):
    """파이프라인 없이 Entity Resolution 단계만."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.res = resolve_entities(_text(), entity="시디즈", review_focus=USER_FACT)

    def _alloso_party(self):
        return next(p for p in self.res.parties if p.written_name == "주식회사 알로소")

    def test_brand_is_not_an_independent_legal_entity(self) -> None:
        p = self._alloso_party()
        self.assertEqual(p.legal_entity_name, "주식회사 시디즈")
        self.assertEqual(p.brand_name, "알로소")
        self.assertEqual(p.signing_entity, "주식회사 시디즈")
        self.assertTrue(p.affiliated)
        for q in self.res.parties:
            self.assertNotRegex(q.legal_entity_name, RX_ALLOSO_AS_COMPANY)
            self.assertNotRegex(q.signing_entity, RX_ALLOSO_AS_COMPANY)

    def test_role_and_alias_are_kept_separately(self) -> None:
        p = self._alloso_party()
        self.assertEqual(p.label, "알로소")
        self.assertEqual(p.role_in_contract, "브랜드·제품 제작 및 판매 주체")
        self.assertIn("알로소", self.res.defined_brand_aliases)

    def test_our_company_is_the_legal_entity(self) -> None:
        our = self.res.our_company
        self.assertIsNotNone(our)
        self.assertEqual(our.legal_entity_name, "주식회사 시디즈")
        self.assertEqual(our.brand_name, "알로소")
        self.assertEqual(self.res.our_company_display(), "주식회사 시디즈 (브랜드: 알로소)")

    def test_sidiz_and_alloso_are_one_party(self) -> None:
        sidiz = [p for p in self.res.parties if p.legal_entity_name == "주식회사 시디즈"]
        self.assertEqual(len(sidiz), 1)
        self.assertFalse(any(p.legal_entity_name == "알로소" for p in self.res.parties))

    def test_other_parties_are_not_touched(self) -> None:
        vt = next(p for p in self.res.parties if p.label == "기획·디렉팅사")
        self.assertEqual(vt.legal_entity_name, "주식회사 베리띵즈")
        self.assertFalse(vt.affiliated)
        self.assertFalse(vt.is_our_company)

    def test_mismatch_in_preamble_and_signature(self) -> None:
        self.assertEqual(self.res.status, STATUS_LEGAL_ENTITY_MISMATCH)
        locs = {(m.location, m.code) for m in self.res.mismatches}
        self.assertIn(("서두(당사자 표시)", "BRAND_AS_LEGAL_ENTITY"), locs)
        self.assertIn(("서명란", "BRAND_AS_LEGAL_ENTITY"), locs)
        for m in self.res.mismatches:
            self.assertEqual(m.correct, "주식회사 시디즈")

    def test_user_fact_is_recorded(self) -> None:
        facts = {f.brand: (f.legal_name_ko, f.source) for f in self.res.user_brands}
        self.assertEqual(facts.get("알로소"), ("주식회사 시디즈", "user"))

    def test_registry_alone_resolves_the_same_way(self) -> None:
        res = resolve_entities(_text(), entity="시디즈")
        self.assertEqual(res.status, STATUS_LEGAL_ENTITY_MISMATCH)
        self.assertEqual(res.our_company.legal_entity_name, "주식회사 시디즈")


class HangulDayCorrectionFindingTest(unittest.TestCase):
    def test_preamble_and_signature_are_found_even_when_signature_joins_last_clause(self) -> None:
        text = _text()
        # 파서가 서명란을 마지막 조항에 붙인 상황을 그대로 재현한다(함정 1).
        _, sig = split_party_regions(text)
        last_clause = {"clause_id": "KR-30-p3", "text": "③ 부속합의서 등은 본 계약의 일부를 구성한다.\n" + text[sig:]}
        fixes = build_name_correction_findings([last_clause], full_text=text, entity="시디즈")
        places = [f["display_path"] for f in fixes]
        self.assertIn("전문(당사자 표시)", places)
        self.assertIn("서명란·말미", places)
        self.assertFalse(any(f["clause_id"] == "ENTITY_NAME__KR-30-p3" for f in fixes), places)

    def test_role_subheading_in_article_body_is_not_a_party_line(self) -> None:
        clause = {"clause_id": "KR-3-p1", "text": "알로소\n알로소는 본 프로젝트의 브랜드 및 제품 사업 주체로서 다음 업무를 담당한다."}
        fixes = build_name_correction_findings([clause], full_text=_text(), entity="시디즈")
        self.assertFalse(any("KR-3" in f["clause_id"] for f in fixes))
        # 서두·서명란에서는 브랜드만 한 줄도 오기다.
        self.assertTrue(find_name_hits("알로소"))
        self.assertFalse(find_name_hits("알로소", bare_lines=False))


class NarrativeNormalizationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.res = resolve_entities(_text(), entity="시디즈", review_focus=USER_FACT)

    def test_obligation_subject_is_the_legal_entity(self) -> None:
        self.assertEqual(
            normalize_party_narrative("알로소가 손해배상 책임을 부담한다.", self.res),
            "주식회사 시디즈(알로소)가 손해배상 책임을 부담한다.",
        )
        self.assertEqual(
            normalize_party_narrative("로열티 지급 주체는 알로소이며, 알로소는 매월 정산한다.", self.res),
            "로열티 지급 주체는 알로소이며, 주식회사 시디즈(알로소)는 매월 정산한다.",
        )

    def test_quoted_contract_text_is_left_alone(self) -> None:
        s = "원문 “알로소가 협업자에게 직접 지급한다”는 지급 주체를 특정한다."
        self.assertEqual(normalize_party_narrative(s, self.res), s)

    def test_brand_fact_sentence_is_left_alone(self) -> None:
        s = "알로소는 주식회사 시디즈의 브랜드이며 법인이 아닙니다."
        self.assertEqual(normalize_party_narrative(s, self.res), s)

    def test_correction_findings_are_not_rewritten(self) -> None:
        crs = [
            {"clause_id": "ENTITY_NAME__party_block_a", "is_entity_name_correction": True,
             "problem": "'주식회사 알로소'는 틀린 표현입니다. 알로소는 주식회사 시디즈의 브랜드입니다."},
            {"clause_id": "KR-12", "worst_case_scenario": "알로소가 로열티를 지급하지 않으면 분쟁이 생긴다."},
        ]
        before = crs[0]["problem"]
        touched = normalize_findings(crs, self.res)
        self.assertEqual(crs[0]["problem"], before)
        self.assertEqual(touched, ["KR-12"])
        self.assertTrue(crs[1]["worst_case_scenario"].startswith("주식회사 시디즈(알로소)가"))

    def test_particle_follows_the_legal_name(self) -> None:
        res = resolve_entities("주식회사 데스커(이하 \"갑\")\n제1조 (목적)\n데스커는 대금을 지급한다.", entity="일룸")
        self.assertEqual(normalize_party_narrative("데스커는 대금을 지급한다.", res),
                         "주식회사 일룸(데스커)은 대금을 지급한다.")


class GeneralMismatchTest(unittest.TestCase):
    """한글날 계약 밖의 불일치 유형 — 지시 3항."""

    def test_preamble_and_signature_names_differ(self) -> None:
        text = (
            "주식회사 시디즈(이하 \"갑\")와 주식회사 한빛목재(이하 \"을\")는 다음과 같이 체결한다.\n"
            "제1조 (목적)\n을은 갑에게 목재를 공급한다.\n" + "제2조 (기타)\n성실히 이행한다.\n" * 5
            + "서명\n갑: 주식회사 시디즈 대표이사 (인)\n을: 주식회사 한빛산업 대표이사 (인)\n"
        )
        res = resolve_entities(text, entity="시디즈")
        codes = [m.code for m in res.mismatches]
        self.assertIn("PREAMBLE_SIGNATURE_MISMATCH", codes)
        self.assertTrue(any("주식회사 한빛산업" in m.written for m in res.mismatches))

    def test_preamble_without_corporate_marker_is_not_a_mismatch(self) -> None:
        # 실측(인테리어 공사도급): 서두는 "한빛로보틱스(이하 “도급인”)", 서명란은
        # "주식회사 한빛로보틱스" — 같은 법인이다. 불일치로 잡으면 원문 모순 같은
        # 더 무거운 상태를 가렸다.
        text = (
            "「주식회사 퍼시스」(이하 \"수급인\")와\n한빛로보틱스(이하 \"도급인\")가 체결한다.\n"
            "제1조 (목적)\n수급인은 공사를 완성한다.\n" + "제2조 (기타)\n성실히 이행한다.\n" * 5
            + "2026년 09월 10일\n상 호 주식회사 한빛로보틱스\n상 호 주식회사 퍼시스\n"
        )
        res = resolve_entities(text, entity="주식회사 퍼시스")
        self.assertEqual([m.to_dict() for m in res.mismatches], [])
        owner = next(p for p in res.parties if p.label == "도급인")
        self.assertEqual(owner.signing_entity, "주식회사 한빛로보틱스")

    def test_group_name_as_party(self) -> None:
        text = "퍼시스그룹(이하 \"갑\")과 주식회사 한빛목재(이하 \"을\")는 체결한다.\n제1조 (목적)\n을은 공급한다.\n"
        res = resolve_entities(text, entity="퍼시스")
        self.assertIn("GROUP_NAME_AS_PARTY", [m.code for m in res.mismatches])
        self.assertEqual(res.parties[0].legal_entity_name, "주식회사 퍼시스")

    def test_non_party_affiliate_used_as_obligor(self) -> None:
        text = (
            "주식회사 시디즈(이하 \"갑\")와 주식회사 한빛목재(이하 \"을\")는 체결한다.\n"
            "제1조 (대금)\n일룸은 을에게 대금을 지급한다.\n"
        )
        res = resolve_entities(text, entity="시디즈")
        self.assertIn("NON_PARTY_AFFILIATE_AS_PARTY", [m.code for m in res.mismatches])

    def test_clean_contract_has_no_mismatch(self) -> None:
        text = (
            "주식회사 시디즈(브랜드명: 알로소, 이하 \"알로소\")와 주식회사 한빛목재(이하 \"을\")는 체결한다.\n"
            "제1조 (목적)\n알로소는 을에게 대금을 지급한다.\n" + "제2조 (기타)\n성실히 이행한다.\n" * 5
            + "서명\n주식회사 시디즈 대표이사 (인)\n주식회사 한빛목재 대표이사 (인)\n"
        )
        res = resolve_entities(text, entity="시디즈")
        self.assertEqual(res.mismatches, [])
        self.assertEqual(res.status, "")
        self.assertEqual(res.our_company.legal_entity_name, "주식회사 시디즈")

    def test_user_fact_for_unregistered_brand_wins(self) -> None:
        facts = parse_user_brand_facts("베리굿은 주식회사 베리띵즈의 브랜드입니다")
        self.assertEqual([(f.brand, f.legal_name_ko) for f in facts], [("베리굿", "주식회사 베리띵즈")])
        text = "주식회사 시디즈(이하 \"갑\")와 주식회사 베리굿(이하 \"을\")는 체결한다.\n제1조 (목적)\n을은 공급한다.\n"
        res = resolve_entities(text, entity="시디즈", review_focus="베리굿은 주식회사 베리띵즈의 브랜드입니다")
        other = next(p for p in res.parties if p.label == "을")
        self.assertEqual(other.legal_entity_name, "주식회사 베리띵즈")
        self.assertEqual(other.brand_name, "베리굿")
        self.assertIn("BRAND_AS_LEGAL_ENTITY", [m.code for m in res.mismatches])

    def test_mismatch_status_does_not_block_delivery(self) -> None:
        # 정정 문안이 함께 나가므로 제거·기록 후 전달한다(다운로드 409 금지).
        self.assertIn(STATUS_LEGAL_ENTITY_MISMATCH, REMEDIABLE_STATUSES)


class HangulDayPipelineGoldenTest(unittest.TestCase):
    """실제 파이프라인(AI 없이) — 지시 8항 PASS 조건."""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.review.clause_level import build_clause_level_result
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService

        loader = RuleLoader()
        loader.load()
        logging.disable(logging.CRITICAL)
        try:
            res = build_clause_level_result(
                service=RuleQueryService(loader), entity="시디즈", contract_type="", text=_text(),
                filename="한글날 제정 100주년 아트상품 협업 계약서.docx", answers={},
                review_focus=USER_FACT, law_service=None, ai_provider=None, ai_model=None,
                ai_timeout_sec=None, ai_max_tokens=None, ai_temperature=None,
            )
        finally:
            logging.disable(logging.NOTSET)
        cls.results = res.clause_results
        cls.meta = res.meta

    def _fixes(self) -> list[dict]:
        return [c for c in self.results if c.get("is_entity_name_correction")]

    def test_status_flags_the_entity_mismatch(self) -> None:
        er = self.meta["entity_resolution"]
        self.assertEqual(er["status"], STATUS_LEGAL_ENTITY_MISMATCH)
        self.assertTrue(any(m["written"] == "주식회사 알로소" for m in er["mismatches"]))
        self.assertEqual(self.meta.get("review_status"), STATUS_LEGAL_ENTITY_MISMATCH)
        self.assertIn("주식회사 알로소", self.meta.get("review_status_detail", ""))

    def test_correction_rewrites_count_as_complete(self) -> None:
        # 당사자란 한 줄 정정은 규범 어미가 없어도 완성 문구다.
        for f in self._fixes():
            self.assertFalse(f.get("incomplete_rewrite"), f["clause_id"])

    def test_meta_records_the_resolution(self) -> None:
        er = self.meta["entity_resolution"]
        self.assertEqual(er["our_company"], {"legal_entity_name": "주식회사 시디즈", "brand_name": "알로소"})
        alloso = next(p for p in er["parties"] if p["written_name"] == "주식회사 알로소")
        self.assertEqual(alloso["legal_entity_name"], "주식회사 시디즈")
        self.assertEqual(alloso["brand_name"], "알로소")
        self.assertTrue(alloso["is_our_company"])

    def test_preamble_and_signature_each_need_correction(self) -> None:
        fixes = self._fixes()
        places = sorted(f["display_path"] for f in fixes)
        self.assertEqual(places, ["서명란·말미", "전문(당사자 표시)"], [f["clause_id"] for f in fixes])
        for f in fixes:
            self.assertEqual(f["risk_tier"], "MEDIUM")
            self.assertFalse(f.get("dedup_suppressed"), f["clause_id"])
            self.assertFalse(f.get("keep_as_is"), f["clause_id"])
            self.assertEqual(f["original_text"], "주식회사 알로소")
            self.assertIn("주식회사 시디즈", f["suggested_rewrite"])

    def test_preamble_keeps_the_brand_as_a_defined_name(self) -> None:
        pre = next(f for f in self._fixes() if f["display_path"] == "전문(당사자 표시)")
        self.assertIn("주식회사 시디즈(브랜드명: 알로소)", pre["suggested_rewrite"])

    def test_article_body_alias_is_not_corrected(self) -> None:
        # 본문의 "알로소"는 서두에서 정의된 약칭이다 — 조문 수정 대상이 아니다.
        self.assertFalse(any(re.search(r"KR-\d", f["clause_id"]) for f in self._fixes()))

    def test_no_output_treats_alloso_as_a_company(self) -> None:
        narrative = (
            "problem", "rewrite_reason", "legal_business_reason", "negotiation_position",
            "negotiation_strategy", "worst_case_scenario", "suggested_rewrite", "recommendation_text",
        )
        for cr in self.results:
            if cr.get("dedup_suppressed"):
                continue
            for key in narrative:
                v = cr.get(key)
                if not isinstance(v, str):
                    continue
                if cr.get("is_entity_name_correction"):
                    # 정정 finding 은 틀린 표현을 인용해 설명한다 — 인용 밖과
                    # 수정문안([추가 권고] 뒤)에는 없어야 한다.
                    if key in ("suggested_rewrite", "recommendation_text"):
                        v = v.split("[추가 권고]")[-1]
                    else:
                        v = re.sub(r"'[^']*'", "", v)
                self.assertNotRegex(v, RX_ALLOSO_AS_COMPANY, f"{cr.get('clause_id')}.{key}")

    def test_correction_explanation_is_not_garbled(self) -> None:
        for f in self._fixes():
            self.assertNotIn("주식회사 시디즈(알로소)는 주식회사 시디즈의 브랜드", f["problem"])

    def test_report_header_names_the_legal_entity(self) -> None:
        cs = self.meta.get("canonical_state") or {}
        self.assertEqual(cs.get("our_legal_entity"), "주식회사 시디즈")
        rows = build_section1_rows(
            entity="시디즈", contract_type="", contract_type_code="", filename="한글날.docx",
            detailed_contract_profile={}, high_issues=[], medium_issues=[], canonical_state=cs,
        )
        texts = [r.text for r in rows]
        self.assertIn("우리 회사: 주식회사 시디즈 (브랜드: 알로소)", texts)


if __name__ == "__main__":
    unittest.main()
