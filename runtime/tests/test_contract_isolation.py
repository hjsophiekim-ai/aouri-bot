"""Cross-Case Hallucination 차단 · Party/Role Reset · Clause Provenance (2026-10-07 지시).

현재 계약 Golden — 시디즈 ↔ ㈜비디앤에스 브랜디드 콘텐츠 제작 계약(fixture: branded_content_contract.txt):
    갑 = 주식회사 시디즈 = 광고주 / 을 = ㈜비디앤에스 = 제작사 / 크리에이터 = 을 측 비당사자 / 당사자 수 = 2.

실측(수정 전): 서두가 시디즈를 “갑”·“광고주” 로 두 번 정의 → 약칭 3개를 당사자 3으로 세어
"3자 브랜디드 콘텐츠 제작계약". 신설 제안 제14조 ⑤~⑦ 이 "관련 계약조항" 에 원문처럼 섞임.
하도급법 비적용 확정 후에도 적용성 표·Legal Map 에 남음(AI 최초 의견 MEDIUM).
"""
from __future__ import annotations

import json
import logging
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

from runtime.review.clause_extraction import extract_clauses
from runtime.review.clause_index import build_clause_index
from runtime.review.contract_isolation import (
    SOURCE_ORIGINAL,
    SOURCE_PROPOSED,
    STATUS_PARTY_COUNT,
    apply_clause_provenance,
    build_party_map,
    classify_path,
    compress_proposed,
    fix_party_count,
    party_count_mentions,
    provenance_violations,
    role_mismatches,
    run_contract_isolation_gate,
)
from runtime.review.entity_resolution import resolve_entities

FIX = Path(__file__).resolve().parent / "fixtures"
TEXT = (FIX / "branded_content_contract.txt").read_text(encoding="utf-8")
SESSION = json.loads((FIX / "branded_content_contract_session.json").read_text(encoding="utf-8"))


def _run(fixture: str, *, entity: str, contract_type: str = "", session: dict | None = None):
    from runtime.review.clause_level import build_clause_level_result
    from runtime.rules.loader import RuleLoader
    from runtime.services.query_service import RuleQueryService

    loader = RuleLoader()
    loader.load()
    logging.disable(logging.CRITICAL)
    try:
        s = session or {}
        return build_clause_level_result(
            service=RuleQueryService(loader), entity=entity, contract_type=contract_type,
            text=(FIX / fixture).read_text(encoding="utf-8"), filename=fixture,
            answers=s.get("answers"), review_focus=s.get("review_focus"), asked_questions=s.get("questions"),
            law_service=None, ai_provider=None, ai_model=None, ai_timeout_sec=None, ai_max_tokens=None,
            ai_temperature=None,
        )
    finally:
        logging.disable(logging.NOTSET)


def _run_branded():
    return _run("branded_content_contract.txt", entity="시디즈", contract_type=SESSION["contract_type"],
                session=SESSION)


def _blob(b) -> str:
    return json.dumps({"meta": b.meta, "crs": b.clause_results, "summary": b.review.get("executive_summary")},
                      ensure_ascii=False, default=str)


class LegalPartyCountTest(unittest.TestCase):
    """지시 2항 — 당사자 수는 서두·정의·서명란 대조로만. 별칭·비서명 이해관계자는 세지 않는다."""

    def test_branded_is_two_party(self) -> None:
        res = resolve_entities(TEXT, entity="시디즈")
        self.assertEqual(res.legal_party_count, 2)
        self.assertEqual([p.label for p in res.legal_parties], ["갑", "을"])
        by = {p.label: p for p in res.parties}
        self.assertEqual(by["광고주"].alias_of, "갑")

    def test_other_contracts_keep_their_count(self) -> None:
        for fx, n in [("hangul_day_100th_alloso_3party_contract.txt", 3), ("snu_research_contract.txt", 2),
                      ("barter_content_furniture.txt", 2), ("geurimdotcom_sales_support_agreement.txt", 2),
                      ("fiti_testing_service_agreement.txt", 2), ("construction_works_contract.txt", 2)]:
            with self.subTest(fx=fx):
                res = resolve_entities((FIX / fx).read_text(encoding="utf-8"), entity="퍼시스")
                self.assertEqual(res.legal_party_count, n)

    def test_registry_match_alone_is_not_alias(self) -> None:
        """㈜일룸(갑)·퍼시스데스커드림센터(을) — registry 가 같은 법인으로 읽어도 이름이 다르면 다른 당사자."""
        res = resolve_entities((FIX / "geurimdotcom_sales_support_agreement.txt").read_text(encoding="utf-8"),
                               entity="일룸")
        self.assertFalse(any(p.alias_of for p in res.parties))


class PartyMapTest(unittest.TestCase):
    """지시 3항 — 갑=시디즈=광고주, 을=비디앤에스=제작사, 크리에이터=을 측 비당사자."""

    def setUp(self) -> None:
        self.pm = build_party_map(resolve_entities(TEXT, entity="시디즈"), TEXT, "advertising_content_production")

    def test_canonical_map(self) -> None:
        d = {p.label: p for p in self.pm.parties}
        self.assertEqual(self.pm.count, 2)
        self.assertEqual((d["갑"].legal_entity, d["갑"].role, d["갑"].is_our_company), ("주식회사 시디즈", "광고주", True))
        self.assertEqual((d["을"].legal_entity, d["을"].role), ("㈜비디앤에스", "제작사"))
        creator = [s for s in self.pm.non_party_stakeholders if s["name"] == "크리에이터"]
        self.assertEqual(creator[0]["side"], "을")

    def test_role_label_swap_detected_and_fixed(self) -> None:
        self.assertEqual(role_mismatches("광고주(을)의 귀책사유", self.pm), [("광고주(을)", "광고주(갑)")])
        self.assertEqual(role_mismatches("“을”(광고주)", self.pm), [("“을”(광고주)", "“갑”(광고주)")])
        self.assertEqual(role_mismatches("갑(비디앤에스)", self.pm), [("갑(비디앤에스)", "을(비디앤에스)")])
        self.assertEqual(role_mismatches("광고주(갑)·계약을(광고주)", self.pm), [])

    def test_party_count_wording(self) -> None:
        self.assertEqual(party_count_mentions("3자 브랜디드 콘텐츠 계약", 2), ["3자"])
        self.assertEqual(fix_party_count("3자 브랜디드 콘텐츠 제작계약", 2), "브랜디드 콘텐츠 제작계약")
        self.assertEqual(fix_party_count("3자 간 협업 구조", 2), "당사자 간 협업 구조")
        for ok in ("제3자 권리 침해", "제 3자에게 제공", "제삼자 소재", "3자에게 제공하는 계약"):
            self.assertEqual(party_count_mentions(ok, 2), [], ok)
        self.assertEqual(party_count_mentions("3자 협업계약", 3), [])


class ClauseProvenanceTest(unittest.TestCase):
    """지시 6·7항 — 원문 조항과 신설 제안을 섞지 않는다."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.index = build_clause_index(TEXT, extract_clauses(TEXT)[0])

    def test_classify(self) -> None:
        self.assertEqual(classify_path("제14조 제3항", self.index), SOURCE_ORIGINAL)
        self.assertEqual(classify_path("제13조 제3·4항", self.index), SOURCE_ORIGINAL)
        self.assertEqual(classify_path("제14조 제2항~제4항", self.index), SOURCE_ORIGINAL)
        self.assertEqual(classify_path("제14조 제1항 3호", self.index), SOURCE_ORIGINAL)
        self.assertEqual(classify_path("제14조 ⑤(같은 조 말미)", self.index), SOURCE_PROPOSED)
        self.assertEqual(classify_path("제14조 제6항", self.index), SOURCE_PROPOSED)
        self.assertEqual(classify_path("제30조", self.index), SOURCE_PROPOSED)

    def test_proposed_moves_out_of_related_list(self) -> None:
        cr = {"clause_id": "X", "risk_tier": "HIGH", "display_path": "제14조 제3항",
              "related_clause_paths": ["제14조 제3항", "제14조 ⑤(같은 조 말미)", "제14조 ⑥(같은 조 말미)",
                                       "제14조 ⑦(같은 조 말미)", "제13조 제4항"],
              "legal_grounding": {"contract_clauses": ["제13조 제4항", "제14조 ⑤(같은 조 말미)"]},
              "package_linked_edits": [{"display_path": "제14조 ⑤(같은 조 말미)", "text": "⑤ …"},
                                       {"display_path": "제14조 제2항", "text": "…"}]}
        apply_clause_provenance([cr], self.index)
        self.assertEqual(cr["related_clause_paths"], ["제14조 제3항", "제13조 제4항"])
        self.assertEqual(cr["legal_grounding"]["contract_clauses"], ["제13조 제4항"])
        self.assertEqual(cr["legal_grounding"]["proposed_clauses"], ["제14조 제5~7항"])
        self.assertEqual([(e["display_path"], e["source"]) for e in cr["package_linked_edits"]],
                         [("제14조 제5항(신설)", SOURCE_PROPOSED), ("제14조 제2항", SOURCE_ORIGINAL)])
        self.assertTrue(all(r["source"] in (SOURCE_ORIGINAL, SOURCE_PROPOSED) for r in cr["clause_references"]))
        self.assertEqual(provenance_violations([cr], self.index), [])

    def test_compress(self) -> None:
        self.assertEqual(compress_proposed(["제14조 제5항(신설)", "제14조 제6항(신설)", "제14조 제7항(신설)"]),
                         ["제14조 제5~7항"])


class GateUnitTest(unittest.TestCase):
    """AI 가 만든 오염(“광고주(을)”·“3자 계약”·하도급법 MEDIUM)을 출력 직전에 고치고 기록한다."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.index = build_clause_index(TEXT, extract_clauses(TEXT)[0])
        cls.res = resolve_entities(TEXT, entity="시디즈")

    def _meta(self) -> dict:
        return {
            "canonical_state": {"contract_type": "advertising_content_production",
                                "contract_type_label": "제품 광고 콘텐츠 제작 대행 계약",
                                "primary_contract_type": "3자 브랜디드 콘텐츠 제작계약"},
            "contract_composition": {"primary_contract_type": "3자 브랜디드 콘텐츠 제작계약",
                                     "canonical_label": "제품 광고 콘텐츠 제작 대행 계약"},
            "applicable_law_state": {"statuses": {"하도급법": "NOT_APPLIES", "표시광고법": "APPLIES"}},
            "legal_applicability_review": [
                {"statute": "하도급거래 공정화에 관한 법률", "applicability": "낮음", "risk_level": "MEDIUM",
                 "source": "ai_self_identified", "canonical_status": "NOT_APPLIES"},
                {"statute": "표시·광고의 공정화에 관한 법률", "risk_level": "LOW", "source": "ai_self_identified"},
            ],
            "contract_legal_map": {"applicable_statutes": "저작권법(이용), 하도급거래 공정화에 관한 법률(하도급 가능성), 민법"},
        }

    def test_contamination_is_fixed_and_recorded(self) -> None:
        meta = self._meta()
        crs = [{"clause_id": "A", "risk_tier": "HIGH", "display_path": "제14조 제3항",
                "problem": "광고주(을)의 귀책사유만 규정한 3자 브랜디드 콘텐츠 계약 구조",
                "original_text": "“을”은 “광고주”에 대한 서면 통지로써",
                "related_clause_paths": ["제14조 제3항", "제14조 ⑤(같은 조 말미)"],
                "legal_grounding": {"contract_clauses": ["제14조 ⑤(같은 조 말미)"],
                                    "statutes": [{"citation": "하도급법 제2조"}, {"citation": "민법 제398조"}]}}]
        rep = run_contract_isolation_gate(text=TEXT, meta=meta, clause_results=crs, review={},
                                          entity_resolution=self.res, clause_index=self.index,
                                          focus_paths=["제6조 제2항", "제7조 제3항", "제14조"])
        self.assertEqual(rep["status"], "", rep["residual"])
        self.assertEqual(crs[0]["problem"], "광고주(갑)의 귀책사유만 규정한 브랜디드 콘텐츠 계약 구조")
        self.assertEqual(crs[0]["original_text"], "“을”은 “광고주”에 대한 서면 통지로써")  # 원문은 건드리지 않는다
        self.assertEqual(meta["contract_composition"]["primary_contract_type"], "브랜디드 콘텐츠 제작계약")
        self.assertEqual([r["statute"] for r in meta["legal_applicability_review"]],
                         ["표시·광고의 공정화에 관한 법률"])
        self.assertNotIn("하도급", meta["contract_legal_map"]["applicable_statutes"])
        self.assertEqual([s["citation"] for s in crs[0]["legal_grounding"]["statutes"]], ["민법 제398조"])
        self.assertEqual(crs[0]["legal_grounding"]["proposed_clauses"], ["제14조 제5항"])
        self.assertTrue(rep["contract_state"]["RESET_PREVIOUS_CONTRACT_STATE"])
        self.assertEqual(rep["contract_state"]["party_count"], 2)

    def test_party_from_another_contract_fails(self) -> None:
        """현재 문서에 없는 법인이 당사자로 남으면 다른 계약에서 온 값이다 — 출력 금지."""
        fake = SimpleNamespace(
            parties=[SimpleNamespace(label="갑", alias_of="", legal_entity_name="주식회사 베리띵즈",
                                     written_name="주식회사 베리띵즈", is_our_company=False),
                     SimpleNamespace(label="을", alias_of="", legal_entity_name="㈜비디앤에스",
                                     written_name="㈜비디앤에스", is_our_company=False)],
            brand_map=lambda: {},
        )
        fake.legal_parties = fake.parties
        rep = run_contract_isolation_gate(text=TEXT, meta=self._meta(), clause_results=[], review={},
                                          entity_resolution=fake, clause_index=self.index)
        self.assertEqual(rep["status"], STATUS_PARTY_COUNT)


class BrandedGoldenAcceptanceTest(unittest.TestCase):
    """지시 10항 PASS 조건 — 실제 파이프라인(AI off)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.b = _run_branded()
        cls.meta, cls.crs = cls.b.meta, cls.b.clause_results
        cls.blob = _blob(cls.b)

    def test_party_count_and_map(self) -> None:
        self.assertEqual(self.meta["party_map"]["party_count"], 2)
        self.assertEqual(self.meta["contract_review_state"]["party_count"], 2)
        roles = {p["label"]: (p["legal_entity"], p["role"]) for p in self.meta["party_map"]["parties"]}
        self.assertEqual(roles, {"갑": ("주식회사 시디즈", "광고주"), "을": ("㈜비디앤에스", "제작사")})
        self.assertNotIn("3자 브랜디드", self.blob)
        self.assertNotIn("3자", self.meta["contract_composition"]["primary_contract_type"])
        self.assertIsNone(re.search(r"광고주\s*\(\s*[“\"]?을", self.blob))

    def test_gate_passes_with_no_residual(self) -> None:
        gate = self.meta["contract_isolation_gate"]
        self.assertEqual(gate["status"], "")
        self.assertFalse(any(gate["residual"].values()), gate["residual"])
        self.assertTrue(self.meta["contract_review_state"]["RESET_PREVIOUS_CONTRACT_STATE"])

    def test_no_subcontract_act_overrating(self) -> None:
        self.assertEqual(self.meta["applicable_law_state"]["statuses"]["하도급법"], "NOT_APPLIES")
        for row in self.meta.get("legal_applicability_review") or []:
            if "하도급" in str(row.get("statute")):
                self.assertNotIn(str(row.get("risk_level")).upper(), ("HIGH", "MEDIUM"))
        for c in self.crs:
            if str(c.get("risk_tier")).upper() in ("HIGH", "MEDIUM") and not c.get("dedup_suppressed"):
                cites = [s.get("citation") for s in (c.get("legal_grounding") or {}).get("statutes") or []]
                self.assertFalse(any("하도급" in str(x) for x in cites), c["clause_id"])

    def test_new_paragraphs_only_as_proposal(self) -> None:
        f14 = next(c for c in self.crs if c["clause_id"].startswith("lr_remedy_stacking"))
        self.assertFalse(any(re.search(r"제14조\s*(?:제\s*[5-7]\s*항|[⑤⑥⑦])", p)
                             for p in f14["related_clause_paths"] + f14["legal_grounding"]["contract_clauses"]))
        self.assertEqual(f14["legal_grounding"]["proposed_clauses"], ["제14조 제5~7항"])
        new = [e for e in f14["package_linked_edits"] if e.get("source") == SOURCE_PROPOSED]
        self.assertEqual([e["display_path"] for e in new], ["제14조 제5항(신설)", "제14조 제6항(신설)", "제14조 제7항(신설)"])
        row = next(r for r in self.meta["user_review_coverage"] if r.get("issue_id") == "user_focus_제14조")
        self.assertFalse(any("말미" in p or "⑤" in p for p in row["relevant_clause_paths"]))
        self.assertEqual(row["proposed_clause_paths"], ["제14조 제5~7항"])

    def test_report_lines_split_existing_and_new(self) -> None:
        from runtime.review.legal_review_docx import grounding_lines, linked_edit_heading
        from runtime.review.output_filter import build_final_findings

        ff = build_final_findings(self.crs, contract_type_code="advertising_content_production", include_low=False)
        issue = next(i for i in ff["high_issues"] if i["clause_id"].startswith("lr_remedy_stacking"))
        from runtime.review.legal_review_docx import _review_issue_from_dict as _issue_from_dict
        lines = dict(grounding_lines(_issue_from_dict(issue)))
        self.assertNotIn("관련 계약조항", lines)
        self.assertNotIn("⑤", lines["기존 관련조항"])
        self.assertEqual(lines["신설 제안"], "제14조 제5~7항")
        heads = [linked_edit_heading(e) for e in issue["linked_edits"]]
        self.assertIn("[신설 제안] 제14조 제5항(신설)", heads)
        self.assertIn("[기존 조항 수정] 제14조 제2항", heads)

    def test_user_requests_remain_mandatory_and_implemented(self) -> None:
        targets = [t["display_path"] for t in self.meta["mandatory_review_targets"]]
        self.assertEqual(targets, ["제6조 제2항", "제7조 제3항", "제14조"])
        impl = self.meta["user_request_implementation"]
        self.assertEqual(len(impl), 3)
        self.assertTrue(all(not r["missing"] for r in impl), impl)
        self.assertTrue(all(r["tier"] in ("HIGH", "MEDIUM") for r in self.meta["user_focus_review"]))


class CrossCaseIsolationTest(unittest.TestCase):
    """지시 1·4항 — 3자 협업계약을 먼저 검토한 같은 프로세스에서도 결과가 처음과 같다."""

    def test_previous_three_party_contract_does_not_leak(self) -> None:
        def sig(b) -> str:
            m = b.meta
            live = sorted((c["clause_id"], str(c.get("risk_tier")), str(c.get("suggested_rewrite") or ""))
                          for c in b.clause_results if not c.get("dedup_suppressed"))
            return json.dumps({"cs": m.get("canonical_state"), "comp": m.get("contract_composition"),
                               "pm": m.get("party_map"), "laws": m.get("applicable_law_state"), "live": live},
                              ensure_ascii=False, default=str, sort_keys=True)

        fresh = sig(_run_branded())
        prior = _run("hangul_day_100th_alloso_3party_contract.txt", entity="알로소")
        self.assertEqual(prior.meta["party_map"]["party_count"], 3)
        after = sig(_run_branded())
        self.assertEqual(fresh, after)
        self.assertNotIn("3자", json.loads(after)["comp"]["primary_contract_type"])


if __name__ == "__main__":
    unittest.main()
