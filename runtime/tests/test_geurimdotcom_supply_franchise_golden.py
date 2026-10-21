"""Golden — 일룸 ↔ ㈜아트앤라이프(그림닷컴) 물품공급거래계약 + [별첨] 프랜차이즈 가맹 (2026-10-13 긴급 보정).

fixture
    geurimdotcom_supply_franchise_contract.txt   Downloads/첨부1. 일룸_물품공급거래계약서_그림닷컴_260916.pdf 추출본
    geurimdotcom_supply_franchise_session.json   실제 세션의 요청문·사전질문·답변

수정 전(실측): 광고기간·매체 위치·송출·매체사·제공 콘텐츠 HIGH 3건(계약서에 없는 낱말), 건설 지위·광고 송출
사전질문, 갑=공급자/을=구매자 역할 뒤집힘, "장비 구매·설치 계약"(포**장비**), 별첨이 제27조 원문에 묶여 요청 B 가
"적정", 제16조 "수정 필요"와 KEEP 이 동시에, 가맹사업법 "적용 확실"·"㈜일룸(가맹본부)".

PASS 조건(지시 13항)
    광고계약 finding 0 · 매체사/송출/광고료 0 · 계약유형 = 물품공급 + 프랜차이즈 요소 · 제16조 실질 검토 ·
    별첨↔본문 충돌 검토 · 가맹사업법은 요건별 판단 · 역할 혼동 0 · 없는 조항 0 · 이전 계약 finding 재사용 0
"""
from __future__ import annotations

import json
import logging
import re
import unittest
from pathlib import Path

from runtime.review.clause_extraction import extract_clauses

FIX = Path(__file__).resolve().parent / "fixtures"
TEXT = (FIX / "geurimdotcom_supply_franchise_contract.txt").read_text(encoding="utf-8")
SESSION = json.loads((FIX / "geurimdotcom_supply_franchise_session.json").read_text(encoding="utf-8"))
BANNED = ("광고기간", "매체 위치", "송출", "광고료", "매체사", "콘텐츠", "크리에이터", "포트폴리오", "광고 소재", "노출 시간")


def _review_focus() -> str:
    """세션의 요청문 + 답변 블록(서버가 붙이는 형식 그대로 — 오분류된 질문 문구가 들어 있다)."""
    asked = {q["question_id"]: q["title"] for q in SESSION["questions"]}
    lines = [f"- {asked[k]}: {v}" for k, v in SESSION["answers"].items() if k in asked]
    return SESSION["review_focus"] + "\n\n[사용자 확인 답변]\n" + "\n".join(lines)


def _live(crs: list[dict]) -> list[dict]:
    return [c for c in crs if not c.get("dedup_suppressed") and not c.get("keep_as_is")
            and str(c.get("risk_tier")).upper() in ("HIGH", "MEDIUM")]


class ClassifierUnitTest(unittest.TestCase):
    def test_franchise_annex_advertising_line_is_not_an_ad_contract(self) -> None:
        from runtime.review.ad_transaction_model import AD_NOT_ADVERTISING, classify_ad_transaction_model
        m = classify_ad_transaction_model(contract_text=TEXT)
        self.assertEqual(m.model, AD_NOT_ADVERTISING)
        self.assertIsNone(m.canonical_contract_type or None)

    def test_user_saying_not_an_ad_contract_wins(self) -> None:
        from runtime.review.ad_transaction_model import AD_NOT_ADVERTISING, resolve_ad_transaction_model
        ad_text = "광고주는 광고물을 매체사에 전달하고 매체사는 송출한다. 광고료는 매월 지급한다. 송출 횟수는 별첨과 같다."
        m = resolve_ad_transaction_model(contract_text=ad_text, answers={"Q-ADM-001": "광고계약이 아님"})
        self.assertEqual((m.model, m.confident), (AD_NOT_ADVERTISING, True))

    def test_goods_contract_is_not_construction(self) -> None:
        from runtime.review.construction_transaction_model import classify_construction_transaction
        self.assertFalse(classify_construction_transaction(contract_text=TEXT).is_construction)

    def test_packing_cost_is_not_equipment(self) -> None:
        from runtime.review.contract_classifier import _classify_type_code
        self.assertEqual(_classify_type_code("물품공급계약서(그림)", TEXT, SESSION["filename"])[0], "purchase_supply")

    def test_receipt_clause_is_not_a_self_declaration(self) -> None:
        """제11조 제2항 "“갑”은 “을”이 … 납품한 경우 공급자에게 … 교부" 는 갑의 자기 선언이 아니다."""
        from runtime.review.party_label_binding import explicit_role_from_labels
        self.assertEqual(explicit_role_from_labels(TEXT, "갑", "을"), "buyer")

    def test_addendum_signature_and_annex_are_split_from_article_27(self) -> None:
        clauses, _ = extract_clauses(TEXT)
        by = {c.display_path: c for c in clauses}
        self.assertLess(len(by["제27조"].text), 300)
        self.assertNotIn("별 첨", by["제27조"].text)
        self.assertIn("[부칙]", by)
        self.assertIn("[별첨]", by)
        self.assertNotIn("대표자", by["[부칙]"].text)       # 서명란은 어느 조항에도 인용되지 않는다
        self.assertTrue(by["[별첨]"].text.startswith("[별 첨]"))

    def test_questions_have_no_ad_or_construction_template(self) -> None:
        from runtime.questions.generator import generate_questions
        qs = generate_questions(SESSION["entity"], SESSION["contract_type"], detected_rule_ids=[],
                                contract_text=TEXT, review_focus=SESSION["review_focus"], max_questions=7)
        ids = [q.question_id for q in qs]
        self.assertFalse([i for i in ids if i.startswith(("Q-ADM", "Q-CONST"))], ids)


class SourceGroundingUnitTest(unittest.TestCase):
    def test_finding_with_terms_absent_from_contract_is_removed(self) -> None:
        from runtime.review.source_grounding_gate import STATUS_CROSS_CASE, run_source_grounding_gate
        crs = [
            {"clause_id": "ADM-01", "risk_tier": "HIGH", "issue_title": "광고 급부(기간·매체 위치·수량) 불특정",
             "problem": "광고기간, 1일 송출 횟수가 확정되어 있지 않습니다."},
            {"clause_id": "KR-16", "risk_tier": "MEDIUM", "issue_title": "하자보증", "problem": "원화 대품 교환 불가"},
        ]
        rep = run_source_grounding_gate(contract_text=TEXT, review_focus=_review_focus(),
                                        answers=SESSION["answers"], clause_results=crs, meta={})
        self.assertTrue(crs[0]["dedup_suppressed"])
        self.assertEqual(rep["removed_findings"][0]["code"], STATUS_CROSS_CASE)
        self.assertFalse(crs[1].get("dedup_suppressed"))
        self.assertEqual(rep["status"], "")

    def test_same_domain_absence_recommendation_is_kept(self) -> None:
        """콘텐츠 제작계약에서 '2차적저작물작성권을 명시하라' 는 정상 권고다 — 낱말 하나가 없다고 지우지 않는다."""
        from runtime.review.source_grounding_gate import foreign_terms, allowed_source
        a = allowed_source(contract_text="을은 유튜브 콘텐츠를 제작하여 납품한다.")
        self.assertEqual(foreign_terms("포트폴리오 활용 범위를 정하십시오", a), [])

    def test_statute_reason_uses_contract_words_only(self) -> None:
        from runtime.review.statute_applicability_gate import assess_advertising_act
        d = assess_advertising_act(text=TEXT)
        self.assertNotIn("협찬", d.reason)
        self.assertIn("광고", d.reason)


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
                service=RuleQueryService(loader), entity=SESSION["entity"], contract_type=SESSION["contract_type"],
                text=TEXT, filename=SESSION["filename"], answers=SESSION["answers"], review_focus=_review_focus(),
                asked_questions=SESSION["questions"], law_service=None, ai_provider=None, ai_model=None,
                ai_timeout_sec=None, ai_max_tokens=None, ai_temperature=None,
            )
        finally:
            logging.disable(logging.NOTSET)
        cls.meta, cls.crs = b.meta, b.clause_results
        cls.live = _live(b.clause_results)
        cls.by = {c["clause_id"].split("__")[0]: c for c in cls.live}
        cls.clauses = extract_clauses(TEXT)[0]

    def test_no_ad_or_foreign_template_findings(self) -> None:
        blob = json.dumps([{k: c.get(k) for k in ("issue_title", "problem", "suggested_rewrite", "rewrite_reason")}
                           for c in self.live], ensure_ascii=False)
        self.assertFalse([w for w in BANNED if w in blob])
        self.assertFalse([c["clause_id"] for c in self.live if str(c["clause_id"]).startswith(("ADM-", "pkg_ip_chain"))])
        self.assertEqual((self.meta.get("ad_transaction_model") or {}).get("model"), "not_advertising")

    def test_contract_type_and_party_roles(self) -> None:
        cs = self.meta["canonical_state"]
        self.assertEqual(cs["contract_type"], "purchase_supply")
        comp = self.meta["contract_composition"]
        self.assertTrue(any("프랜차이즈" in e for e in comp["secondary_contract_elements"]))
        roles = {p["label"]: p["role"] for p in self.meta["party_map"]["parties"]}
        self.assertEqual(roles, {"갑": "구매자", "을": "공급자"})
        annex_roles = self.meta["annex_conflict_review"]["roles"]
        self.assertEqual(annex_roles["가맹본부"]["label"], "을")
        self.assertEqual(annex_roles["가맹점사업자"]["label"], "갑")
        self.assertEqual(cs.get("counterparty_legal_entity"), "㈜아트앤라이프")

    def test_article_16_substantive_artwork_review(self) -> None:
        f = self.by["uf_artwork_defect_warranty"]
        self.assertEqual(f["display_path"], "제16조")
        self.assertIn(f["risk_tier"], ("HIGH", "MEDIUM"))
        for must in ("원화", "자연스러운", "액자", "진품", "운송"):
            self.assertIn(must, f["problem"] + f["suggested_rewrite"])
        self.assertIn("공급가격 전액의 반환", f["suggested_rewrite"])
        self.assertNotIn("공사", f["suggested_rewrite"])          # 건설 서식 잔재 정리
        # 같은 조에 KEEP 이 함께 나가지 않는다.
        self.assertFalse([c for c in self.crs if c.get("keep_as_is") and c.get("article_number") == "16"])

    def test_annex_conflicts_mapped_clause_to_clause(self) -> None:
        rv = self.meta["annex_conflict_review"]
        rows = {r["axis"]: r for r in rv["rows"]}
        self.assertEqual(rows["반품/매입 · 계약종료 후 재고처리"]["status"], "충돌")
        self.assertEqual(rows["반품/매입 · 계약종료 후 재고처리"]["main_refs"], ["제13조 제3항"])
        self.assertIn("[별첨] 12. 2)", rows["반품/매입 · 계약종료 후 재고처리"]["annex_refs"])
        self.assertEqual(rows["대금 지급"]["status"], "충돌")
        self.assertEqual(rows["해지"]["status"], "충돌")
        self.assertEqual(rows["우선순위 조항"]["code"], "CONTRACT_APPENDIX_CONFLICT")
        for axis in ("당사자 역할", "대금/공급가격", "재고/초도물량", "하자/품질책임", "지식재산권", "브랜드 사용",
                     "광고/판촉", "독점/구입강제", "유효기간"):
            self.assertIn(axis, rows)
        self.assertEqual(self.by["ax_annex_precedence"]["risk_tier"], "HIGH")
        self.assertEqual(self.by["ax_annex_exit_inventory"]["risk_tier"], "HIGH")
        self.assertIn("“가맹본부”는 “을”을", self.by["ax_annex_precedence"]["suggested_rewrite"])

    def test_franchise_act_judged_by_requirements(self) -> None:
        rows = [r for r in self.meta["legal_applicability_review"] if "가맹사업" in r["statute"]]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["applicability"], "높음(확정 아님)")
        self.assertNotIn("확실", rows[0]["reasoning"])
        self.assertIn("차액가맹금", rows[0]["reasoning"])
        blob = json.dumps(self.meta["legal_applicability_review"], ensure_ascii=False)
        self.assertNotRegex(blob, r"일룸\s*\(\s*가맹본부")

    def test_both_user_requests_answered(self) -> None:
        tiers = {r["target"]: r for r in self.meta["user_focus_review"]}
        self.assertEqual(set(tiers), {"제16조", "[별첨]"})
        for t in tiers.values():
            self.assertEqual(t["verdict"], "수정 필요")
            self.assertFalse(t["missing"])
        self.assertEqual(tiers["[별첨]"]["tier"], "HIGH")
        cov = {r["normalized_issue"]: r for r in self.meta["user_review_coverage"]
               if r.get("source") == "user_focus_target"}
        annex = cov["[별첨] 지정 검토"]
        self.assertIn("CONTRACT_APPENDIX_CONFLICT", annex["conclusion"])
        self.assertIn("가맹사업법 실질 검토", annex["conclusion"])
        self.assertTrue(annex["proposed_clauses"])
        paths = {r["display_path"] for r in self.meta["mandatory_review_targets"]}
        self.assertEqual(paths, {"제16조", "[별첨]"})
        self.assertNotIn(self.meta.get("review_status"), ("REVIEW_FAILED_USER_FOCUS_DROPPED",
                                                          "CROSS_CASE_STATE_CONTAMINATION"))

    def test_every_live_finding_points_at_a_real_clause(self) -> None:
        real = {c.display_path for c in self.clauses}
        arts = {c.article_number for c in self.clauses if c.article_number}
        for c in self.live:
            p = str(c["display_path"])
            if p.startswith("["):
                self.assertTrue(any(p.startswith(r) for r in real if r.startswith("[")), p)
            else:
                m = re.match(r"제(\d+)조", p)
                self.assertTrue(m and m.group(1) in arts, p)
            # 조 제목 줄은 원문에서 괄호 안에 있으므로("제16조(하자보증 책임)") 본문 끝부분으로 대조한다.
            self.assertIn(re.sub(r"\s+", "", str(c.get("original_text") or ""))[-60:], re.sub(r"\s+", "", TEXT))

    def test_reset_state_recorded(self) -> None:
        st = self.meta["contract_review_state"]
        self.assertTrue(st["RESET_ALL_CONTRACT_CONTEXT"])
        self.assertEqual((st["prior_examples"], st["prior_golden_case"], st["prior_user_focus"]), ([], None, []))
        self.assertTrue(self.meta["source_grounding_gate"]["RESET_ALL_CONTRACT_CONTEXT"])


class DownloadDocxTest(unittest.TestCase):
    """수정본(DOCX) 경로 — 0절·0-3절이 지정 쟁점 판단을 그대로 싣는가(이 경로는 두 절을 다시 만든다)."""

    @classmethod
    def setUpClass(cls) -> None:
        import http.client
        import tempfile
        import threading

        from runtime.api.server import build_httpd
        from runtime.questions.storage import create_session, save_session
        from runtime.review.text_extract import extract_text_from_file
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService

        loader = RuleLoader()
        loader.load()
        svc = RuleQueryService(loader)
        httpd = build_httpd("127.0.0.1", 0, svc)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            doc = create_session(svc, entity=SESSION["entity"], contract_type=SESSION["contract_type"],
                                 filename=SESSION["filename"], extraction={}, text=TEXT, classification={})
            doc["questions"], doc["answers"] = SESSION["questions"], SESSION["answers"]
            doc.setdefault("input", {})["review_focus"] = _review_focus()
            save_session(doc)
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=300)
            conn.request("POST", "/api/revision/download_docx",
                         body=json.dumps({"session_id": doc["session_id"], "rebuild": True, "ai_mode": "off"}).encode(),
                         headers={"Content-Type": "application/json; charset=utf-8"})
            resp = conn.getresponse()
            cls.status, body = resp.status, resp.read()
            conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
        cls.text = ""
        if cls.status == 200:
            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as fh:
                fh.write(body)
            path = Path(fh.name)
            try:
                cls.text = extract_text_from_file(path).text
            finally:
                path.unlink(missing_ok=True)

    def test_download_and_sections(self) -> None:
        self.assertEqual(self.status, 200)
        self.assertIn("- 제16조: 검토완료 · 수정 필요 [MEDIUM]", self.text)
        self.assertIn("- [별첨]: 검토완료 · 수정 필요 [HIGH]", self.text)
        self.assertIn("CONTRACT_APPENDIX_CONFLICT", self.text)
        self.assertIn("상대방: ㈜아트앤라이프", self.text)
        self.assertIn("프랜차이즈 가맹 요소", self.text)
        self.assertFalse([w for w in BANNED + ("일룸(가맹본부)", "와/과", "“갑”가") if w in self.text])


if __name__ == "__main__":
    unittest.main()
