"""Golden Acceptance — 시디즈 ↔ ㈜비디앤에스 브랜디드 콘텐츠 제작 계약 (2026-10-07 긴급 보정).

fixture
    branded_content_contract.txt          계약 원문(Downloads/브랜디드 콘텐츠 제작 계약서.docx 추출본, 동일)
    branded_content_contract_session.json 실제 세션의 요청문·사전질문·답변

사업부 지정 검토사항: 제6조 제2항 / 제7조 제3항 / 제14조.

실측(수정 전): 제14조 전부 DROP(필수 검토항목은 HIGH 로 표시) · 제13조 책임한도 비대칭이 "사업부 결정" 재경 확인 ·
손해배상 체크리스트가 제14조 원문을 인용하면서 제9조 제1항에 붙음 · HIGH 0건 · 요청 답변은 다른 finding 의 제목 ·
갑(시디즈)을 우리 회사로 인식하지 못함(“[시디즈]” 대괄호 표기, 광고주·콘텐츠·본 계약이 ㈜비디앤에스로 읽힘).

PASS 조건(사용자 지시)
    - 제6조 제2항: 갑 귀책범위 중심 검토(자동 HIGH 금지)
    - 제7조 제3항: 경쟁사 제한은 좁고 실무적으로
    - 제14조: 반드시 최종 finding — 50% 위약벌 + 모든 손해 + 삭제 + 잔여대금 = 책임 중첩
    - 제13조 책임한도 비대칭 = 법무 핵심이슈
    - 제9조를 손해배상 조항으로 매핑하지 않음
    - HIGH 0건으로 끝나지 않음, 같은 쟁점 LOW/MEDIUM/HIGH 모순 0건
"""
from __future__ import annotations

import json
import logging
import re
import unittest
from pathlib import Path

from runtime.review.clause_extraction import extract_clauses
from runtime.review.entity_resolution import resolve_entities
from runtime.review.user_focus_review import (
    FocusTarget, extract_targets, risk_state_conflicts, verify_focus,
)
from runtime.review.user_review_request import separate_context

FIX = Path(__file__).resolve().parent / "fixtures"
TEXT = (FIX / "branded_content_contract.txt").read_text(encoding="utf-8")
SESSION = json.loads((FIX / "branded_content_contract_session.json").read_text(encoding="utf-8"))


def _live(crs: list[dict]) -> list[dict]:
    return [c for c in crs if not c.get("dedup_suppressed") and not c.get("keep_as_is")
            and str(c.get("risk_tier")).upper() in ("HIGH", "MEDIUM")]


class EntityAndRequestTest(unittest.TestCase):
    def test_bracketed_party_is_our_company(self) -> None:
        res = resolve_entities(TEXT, entity="시디즈")
        by = {p.label: p for p in res.parties}
        self.assertTrue(by["갑"].is_our_company)
        self.assertEqual(by["갑"].legal_entity_name, "주식회사 시디즈")
        self.assertEqual(by["광고주"].legal_entity_name, "주식회사 시디즈")
        self.assertEqual(by["을"].legal_entity_name, "㈜비디앤에스")
        self.assertNotIn("콘텐츠", by)
        self.assertNotIn("본 계약", by)

    def test_cited_items_are_the_requests(self) -> None:
        kept, context = separate_context(SESSION["review_focus"].split("[사용자 확인 답변]")[0])
        self.assertEqual(len([ln for ln in kept.splitlines() if ln.strip()]), 3)
        self.assertEqual([t.path for t in extract_targets(SESSION["review_focus"])],
                         ["제6조 제2항", "제7조 제3항", "제14조"])


class FocusGateUnitTest(unittest.TestCase):
    """지시 1·2항 — 지정 조항에 답이 없으면 실패, 위험도가 화면마다 다르면 실패."""

    def test_missing_target_is_reported(self) -> None:
        res = verify_focus([FocusTarget(path="제7조 제3항", article="7", paragraph="3", request="제7조 제3항")],
                           [], extract_clauses(TEXT)[0])
        self.assertIn("최종 판단", res[0].missing)
        self.assertIn("위험도", res[0].missing)

    def test_risk_state_conflict_is_detected(self) -> None:
        crs = [{"clause_id": "X", "risk_tier": "LOW"}]
        ff = {"medium_issues": [{"clause_id": "X"}]}
        self.assertTrue(risk_state_conflicts(crs, ff, [], []))


class PipelineGoldenTest(unittest.TestCase):
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
                service=RuleQueryService(loader), entity=SESSION.get("entity") or "시디즈",
                contract_type=SESSION["contract_type"], text=TEXT, filename="브랜디드 콘텐츠 제작 계약서.docx",
                answers=SESSION["answers"], review_focus=SESSION["review_focus"],
                asked_questions=SESSION["questions"], law_service=None, ai_provider=None, ai_model=None,
                ai_timeout_sec=None, ai_max_tokens=None, ai_temperature=None,
            )
        finally:
            logging.disable(logging.NOTSET)
        cls.meta, cls.crs = b.meta, b.clause_results
        cls.live = _live(b.clause_results)
        cls.by = {c["clause_id"].split("__")[0]: c for c in cls.live}

    def test_core_findings_and_counts(self) -> None:
        got = sorted((c["clause_id"].split("__")[0], c["display_path"], c["risk_tier"]) for c in self.live)
        self.assertEqual(got, [
            ("lr_asymmetric_liability", "제13조 제1항", "HIGH"),
            ("lr_content_use_rights", "제10조 제1항", "HIGH"),
            ("lr_remedy_stacking", "제14조 제3항", "HIGH"),
            ("uf_non_exclusivity", "제7조 제3항", "MEDIUM"),
            ("uf_supplied_material_warranty", "제6조 제2항", "MEDIUM"),
        ])

    def test_article_14_stacking(self) -> None:
        f = self.by["lr_remedy_stacking"]
        self.assertEqual(f["legal_effect_code"], "REMEDY_STACKING_RISK")
        self.assertEqual(len(f["semantic_checks"]), 8)
        self.assertFalse([c for c in f["semantic_checks"] if c["ok"]])
        self.assertIn("손해배상액의 예정", f["suggested_rewrite"])
        self.assertNotIn("이와 별도로", f["suggested_rewrite"])
        linked = {e["display_path"]: e["text"] for e in f["package_linked_edits"]}
        self.assertIn("제13조 제4항", linked)                       # 같은 사유 이중 위약벌
        self.assertIn("객관적으로", linked["제14조 제1항 3호"])
        self.assertNotIn("즉시", linked["제14조 제2항"])
        self.assertIn("제3항에 따른 금액으로 한정", linked["제14조 제4항"])
        recip = next(t for p, t in linked.items() if "⑤" in p)
        self.assertIn("기 지급받은 제작료 전액을 반환", recip)

    def test_asymmetric_liability_is_legal_core(self) -> None:
        f = self.by["lr_asymmetric_liability"]
        self.assertEqual(f["legal_effect_code"], "LEGAL_RISK_ASYMMETRIC_LIABILITY")
        self.assertEqual(f["triage"], "MUST_FIX")
        self.assertIn("각 당사자의 손해배상금액", f["suggested_rewrite"])
        fin = [r["clause_id"] for r in self.meta["senior_counsel_audit"]["triage"]["FINANCE_CHECK"]]
        self.assertFalse([cid for cid in fin if "13" in cid])

    def test_article_9_is_not_a_damages_clause(self) -> None:
        for c in self.live:
            if c.get("article_number") == "9":
                self.assertNotRegex(str(c.get("issue_title") or "") + str(c.get("problem") or ""), r"손해\s*배상")
        cp = next(c for c in self.crs if c["clause_id"] == "CP-007")
        self.assertTrue(cp["display_path"].startswith("제14조"), cp["display_path"])

    def test_focus_answers_first_and_consistent(self) -> None:
        cov = self.meta["user_review_coverage"]
        self.assertEqual([r["source"] for r in cov[:3]], ["user_focus_target"] * 3)
        tiers = {r["target"]: r for r in self.meta["user_focus_review"]}
        self.assertEqual(tiers["제14조"]["tier"], "HIGH")
        self.assertEqual(tiers["제6조 제2항"]["tier"], "MEDIUM")
        self.assertEqual(tiers["제7조 제3항"]["tier"], "MEDIUM")
        self.assertFalse([r for r in self.meta["user_focus_review"] if r["missing"]])
        for m in self.meta["mandatory_review_targets"]:
            self.assertEqual(m["severity"], tiers[m["display_path"]]["tier"])
        self.assertEqual(self.meta["risk_state_conflicts"], [])
        self.assertNotIn(str(self.meta.get("review_status") or ""),
                         ("REVIEW_FAILED_USER_FOCUS_DROPPED", "REVIEW_FAILED_RISK_STATE_CONFLICT"))

    def test_cited_clause_judgements(self) -> None:
        w = self.by["uf_supplied_material_warranty"]
        self.assertIn("통상적", w["problem"])
        self.assertIn("귀책사유가 함께 원인", w["suggested_rewrite"])
        n = self.by["uf_non_exclusivity"]
        self.assertIn("3개월", n["suggested_rewrite"])
        self.assertIn("“광고주”", n["suggested_rewrite"])
        self.assertNotIn("“시디즈”", n["suggested_rewrite"])

    def test_redlines_edit_existing_clauses(self) -> None:
        for c in self.live:
            sr = str(c["suggested_rewrite"])
            self.assertTrue(sr.rstrip().endswith("."), c["clause_id"])
            self.assertNotRegex(sr + c["display_path"], r"신설|\[\s*\]|\[○\]|위탁자|수탁자")

    def test_one_type_everywhere(self) -> None:
        m = self.meta
        codes = {m["legal_state"]["contract_type"], m["canonical_state"]["contract_type"],
                 m["canonical_identity"]["contract_type_code"], m["contract_type_resolution"]["contract_type_code"]}
        self.assertEqual(codes, {"advertising_content_production"})

    def test_answer_intents(self) -> None:
        by = {r.get("topic"): r for r in self.meta["user_review_coverage"]}
        self.assertEqual(by["content_reuse"]["review_status"], "수정 필요")
        self.assertEqual(by["subcontracting"]["review_status"], "적정")
        self.assertIn("제7조 제2항", by["subcontracting"]["conclusion"])
        self.assertNotIn("인터뷰", by["subcontracting"]["conclusion"])


class RevisionDownloadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import threading

        from runtime.api.server import build_httpd
        from runtime.questions.storage import create_session
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService

        loader = RuleLoader()
        loader.load()
        cls.service = RuleQueryService(loader)
        cls.httpd = build_httpd("127.0.0.1", 0, cls.service)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        doc = create_session(cls.service, entity="시디즈", contract_type=SESSION["contract_type"],
                             filename="브랜디드 콘텐츠 제작 계약서.docx", extraction={}, text=TEXT, classification={})
        cls.session_id = doc["session_id"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.thread.join(timeout=5)
        cls.httpd.server_close()

    def test_docx_and_pdf(self) -> None:
        import http.client

        for fmt in ("docx", "pdf"):
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=180)
            conn.request("POST", f"/api/revision/download_{fmt}", body=json.dumps(
                {"session_id": self.session_id, "rebuild": True, "ai_mode": "off"}).encode("utf-8"),
                headers={"Content-Type": "application/json; charset=utf-8"})
            resp = conn.getresponse()
            body = resp.read()
            conn.close()
            self.assertEqual(resp.status, 200, (fmt, body[:600]))


if __name__ == "__main__":
    unittest.main()
