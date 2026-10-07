"""법조문 grounding 회귀테스트 (2026-10-01 지시) — 한글날 아트상품 협업계약 Golden Test 포함.

실측: 실제 AI 검토에서 legal_basis 가 "저작권법, 민법" 이었고, 그대로 "법적/실무상 이유:
저작권법, 민법 / 지식재산권 분쟁 발생 시 …" 로 보고서에 실렸다. 같은 검토에서
"2차적저작물작성권 포함 여부" 가 제9조 제3항(실물 소유권과 저작권은 별개)에 붙었다.

Golden (지시 14항)
  A. 기존 저작물/기법 이용 — 제10조 제1항·제4항, 저작권법 제46조(+제22조), 제45조는 양도일 때만
  B. 갤러리·에이전시 권한 — 제20조 제1항~제3항, 민법 제114조·제130조·제390조, 저작권법 제46조
  C. 실물 소유권 — 제9조, 저작권과 구분, 2차적저작물작성권 문제로 오인 금지
"""
from __future__ import annotations

import logging
import re
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

from runtime.review.clause_extraction import extract_clauses
from runtime.review.entity_resolution import resolve_entities
from runtime.review.senior_counsel_audit import run_senior_counsel_audit
from runtime.review.statute_grounding import (
    audit_cited_statutes,
    detect_relations,
    statutes_for,
    strip_law_mentions,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "hangul_day_100th_alloso_3party_contract.txt"


def _text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def _cites(cr: dict) -> list[str]:
    return [s["citation"] for s in (cr.get("legal_grounding") or {}).get("statutes") or []]


class RelationTest(unittest.TestCase):
    def test_license_structure_does_not_get_assignment_article(self) -> None:
        cr = {"detected_issue_list": [{"issue_title": "지식재산권 이용권 범위 불명확"}],
              "original_text": "협업자는 … 제작·복제·생산·판매·유통하는 데 필요한 이용권을 허락한다."}
        rels = detect_relations(cr)
        self.assertIn("ip_license", rels)
        self.assertNotIn("ip_assignment", rels)
        cites = [s.citation for s in statutes_for(rels)]
        self.assertIn("저작권법 제46조 제2항", cites)
        self.assertFalse([c for c in cites if "제45조" in c])

    def test_assignment_with_derivative_gets_article_45_2(self) -> None:
        cr = {"detected_issue_list": [{"issue_title": "저작재산권 양도 범위에 2차적저작물작성권 누락"}],
              "original_text": "을은 결과물에 대한 저작재산권 일체를 갑에게 양도한다."}
        cites = [s.citation for s in statutes_for(detect_relations(cr))]
        self.assertIn("저작권법 제45조 제2항", cites)
        self.assertIn("저작권법 제22조", cites)

    def test_consequence_words_do_not_create_relations(self) -> None:
        # "손해배상"은 IP 쟁점의 결과로 언급됐을 뿐 — 민법 제390조를 붙이지 않는다.
        cr = {"detected_issue_list": [{"issue_title": "[법률] 이용권 범위 불명확 시 분쟁 위험"}],
              "problem": "다툼이 생기면 판매 중단, 손해배상, 저작권 침해 소송 등이 발생할 수 있다."}
        self.assertNotIn("damages", detect_relations(cr))
        # 계약금액 공란의 "지체상금·보증금 연동"도 위약금·보증 관계가 아니다.
        cr2 = {"detected_issue_list": [{"issue_title": "계약금액이 확정되지 않음"}],
               "problem": "계약금액이 '공란' 상태다. 지체상금·보증금·손해배상 상한이 모두 계약금액에 연동된다."}
        self.assertEqual(detect_relations(cr2), [])

    def test_physical_ownership_is_not_a_derivative_issue(self) -> None:
        cr = {"detected_issue_list": [{"issue_title": "실물 소유권 귀속 주체가 선택되지 않음"}],
              "problem": "원본 실물의 귀속이 정해지지 않았다. 변형 이용과는 별개다."}
        rels = detect_relations(cr)
        self.assertIn("physical_ownership", rels)
        self.assertNotIn("derivative", rels)
        cites = [s.citation for s in statutes_for(rels)]
        self.assertIn("저작권법 제35조 제1항", cites)
        self.assertIn("민법 제211조", cites)
        self.assertNotIn("저작권법 제22조", cites)


class CitationAuditTest(unittest.TestCase):
    def test_name_only_citations_are_removed(self) -> None:
        kept, removed = audit_cited_statutes("저작권법, 민법 / 지식재산권 분쟁 시 손실", ["ip_license"])
        self.assertEqual(kept, [])
        self.assertTrue(any("법률명만" in r["reason"] for r in removed))

    def test_mismatched_article_is_removed(self) -> None:
        kept, removed = audit_cited_statutes("저작권법 제45조에 따라 양도된다", ["ip_license"])
        self.assertEqual(kept, [])
        self.assertIn("저작권법 제45조", removed[0]["citation"])

    def test_unknown_article_is_not_trusted(self) -> None:
        kept, removed = audit_cited_statutes("민법 제999조 위반", ["damages"])
        self.assertEqual(kept, [])
        self.assertTrue(removed)

    def test_valid_article_is_kept(self) -> None:
        kept, _ = audit_cited_statutes("저작권법 제46조 제2항: 허락 범위", ["ip_license"])
        self.assertEqual([s.citation for s in kept], ["저작권법 제46조 제2항"])

    def test_business_reason_loses_bare_law_names(self) -> None:
        self.assertEqual(
            strip_law_mentions("저작권법, 민법 / 지식재산권 분쟁 발생 시 제품 판매 중단 우려"),
            "지식재산권 분쟁 발생 시 제품 판매 중단 우려",
        )
        self.assertEqual(strip_law_mentions("소득세법, 법인세법 / 세금계산서 오류 시 가산세"), "세금계산서 오류 시 가산세")


class AuditGroundingTest(unittest.TestCase):
    """실제 AI 결과의 모양 그대로 — 감사가 조항·조문·이유를 분리해 싣는가."""

    def _run(self, findings: list[dict]) -> dict:
        t = _text()
        return run_senior_counsel_audit(
            findings, text=t, clauses=extract_clauses(t)[0],
            entity_resolution=resolve_entities(t, entity="시디즈"), archetype="ip_license",
        )

    def test_ai_finding_with_bare_law_names_gets_real_articles(self) -> None:
        f = {
            "clause_id": "KR-10-p4", "risk_tier": "HIGH", "severity": "HIGH",
            "display_path": "제10조 제4항", "article_number": "10", "paragraph_number": "4",
            "detected_issue_list": [{"issue_title": "[법률] 지식재산권 귀속 및 이용권 범위 불명확 시 분쟁 위험"}],
            "original_text": "협업자는 제13조에서 정한 판매기간 동안 알로소가 최종 승인된 작품 및 디자인을 제품으로 제작·복제·생산·판매·유통하는 데 필요한 이용권을 허락한다.",
            "problem": "이용권 범위, 2차적 저작물 작성권, 온라인·해외 판매 등에서 다툼이 생기면 판매 중단·손해배상이 발생할 수 있다.",
            "legal_business_reason": "저작권법, 민법 / 지식재산권 분쟁 발생 시 제품 판매 중단, 손해배상 등 직접적 영업 손실이 크기 때문.",
            "suggested_rewrite": "협업자는 … 이용권(2차적저작물 작성·이용 포함)을 허락한다.",
            "high_severity_basis": "counsel_agent[legal]",
        }
        rep = self._run([f])
        g = f["legal_grounding"]
        self.assertEqual(g["contract_clauses"], ["제10조 제1항", "제10조 제4항"])  # Golden A
        self.assertEqual(_cites(f), ["저작권법 제46조 제2항", "저작권법 제22조"])
        self.assertNotIn("저작권법, 민법", f["legal_business_reason"])
        self.assertTrue(g["legal_reason"].startswith("이 조항은 저작재산권 양도가 아니라 이용허락"))
        self.assertIn("판매 중단", g["business_reason"])
        self.assertIn("REVIEW_FAILED_STATUTE_GROUNDING", rep["codes"])

    def test_derivative_issue_on_physical_ownership_clause_moves_to_license_clause(self) -> None:
        f = {
            "clause_id": "eb_ip_no_derivative_right__KR-9-p3", "risk_tier": "MEDIUM", "severity": "MEDIUM",
            "display_path": "제9조 제3항", "article_number": "9", "paragraph_number": "3",
            "clause_title": "실물 소유권", "clause_effects": ["ip_license"],
            "detected_issue_list": [{"issue_title": "2차적저작물작성권의 포함 여부가 명시되지 않음"}],
            "original_text": "실물 소유권과 저작권 및 저작재산권은 별개의 권리로 한다.",
            "problem": "2차적저작물작성권 포함 여부가 없다.",
            "suggested_rewrite": "실물 소유권과 저작권 및 저작재산권은 별개의 권리로 한다. 2차적저작물작성권을 포함한다.",
        }
        self._run([f])
        self.assertEqual(f["display_path"], "제10조 제4항")
        self.assertIn("이용권을 허락한다", f["suggested_rewrite"])
        self.assertIn("저작권법 제22조", _cites(f))


class HangulDayStatuteGoldenTest(unittest.TestCase):
    """AI 없이 전체 파이프라인 + DOCX — 지시 14항 A·B·C."""

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
        ff = cls.meta["final_findings"]
        cls.core = ff["high_issues"] + ff["medium_issues"]

    def _by_title(self, pattern: str) -> dict:
        hit = [i for i in self.core if re.search(pattern, i["issue_title"])]
        self.assertTrue(hit, [i["issue_title"] for i in self.core])
        return hit[0]

    def test_a_ip_license_package(self) -> None:
        f = self._by_title(r"2차적저작물")
        g = f["legal_grounding"]
        self.assertEqual(f["display_path"], "제10조 제4항")
        self.assertIn("제10조 제1항", g["contract_clauses"])
        self.assertIn("제10조 제4항", g["contract_clauses"])
        cites = _cites(f)
        self.assertIn("저작권법 제46조 제2항", cites)
        self.assertIn("저작권법 제22조", cites)
        self.assertFalse([c for c in cites if "제45조" in c])

    def test_b_agent_authority(self) -> None:
        # 2026-10-01 Triage 지시 17항(팀원 판단): 권한 확인·보증·하자 책임이 이미 제20조에
        # 있으므로 KEEP. 법률관계(대리)와 조문은 KEEP 판정의 근거로 그대로 싣는다.
        keep = [c for c in self.results if c.get("keep_as_is") and c.get("triage") == "KEEP"
                and str(c.get("clause_id", "")).startswith("ac_agent_authority")]
        self.assertEqual(len(keep), 1)
        f = keep[0]
        g = f["legal_grounding"]
        self.assertEqual(g["contract_clauses"], ["제20조 제1항~제3항"])
        cites = _cites(f)
        for c in ("민법 제114조 제1항", "민법 제130조", "민법 제390조", "저작권법 제46조 제2항"):
            self.assertIn(c, cites)
        self.assertFalse([i for i in self.core if "권한" in i["issue_title"] and "에이전시" in i["issue_title"]])

    def test_c_physical_ownership(self) -> None:
        f = self._by_title(r"실물 소유권")
        g = f["legal_grounding"]
        self.assertEqual(f["display_path"], "제9조 제1항")
        cites = _cites(f)
        self.assertIn("저작권법 제35조 제1항", cites)
        self.assertIn("민법 제211조", cites)
        self.assertNotIn("저작권법 제22조", cites)
        self.assertIn("별개의 권리", g["legal_reason"])
        self.assertIn("알로소에게 귀속한다", f["proposed_revision"])

    def test_every_core_finding_is_grounded(self) -> None:
        for f in self.core:
            g = f.get("legal_grounding") or {}
            self.assertTrue(g.get("contract_clauses"), f["clause_id"])
            self.assertTrue(g.get("statutes") or g.get("statute_note"), f["clause_id"])
            self.assertNotRegex(" ".join(g.get("contract_clauses")), r"신설|관련 조항|해당 조항 없음")
            self.assertNotRegex(f.get("legal_business_reason") or "", r"^(?:저작권법|민법)\s*[,/]")

    def test_docx_prints_articles_and_separates_reasons(self) -> None:
        from runtime.review.legal_review_docx import build_legal_review_docx

        ff = self.meta["final_findings"]
        data = build_legal_review_docx(
            entity="시디즈", contract_type="", filename="한글날.docx", clause_results=self.results,
            canonical_state=self.meta.get("canonical_state"),
            top_risks_filtered=ff["top_risks"], high_issues_filtered=ff["high_issues"],
            medium_issues_filtered=ff["medium_issues"],
        )
        with zipfile.ZipFile(BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        for needle in ("[기존 관련조항] 제20조 제1항~제3항", "[관련 법령] 민법 제130조(무권대리)",
                       "[관련 법령] 저작권법 제35조 제1항", "[법률상 이유]", "[실무상 이유]"):
            self.assertIn(needle, xml)


if __name__ == "__main__":
    unittest.main()
