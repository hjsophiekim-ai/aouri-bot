"""Golden Acceptance — 서울대 산학협력단 연구계약 (2026-10-06 범용 보정: 조항 정확성 / 불필요 이슈 제거).

fixture
    snu_research_contract.txt          퍼시스 ↔ 서울대학교 산학협력단 연구계약서(별지 제1호 서식, PDF 추출본)
    snu_research_contract_session.json 실제 세션의 검토 요청문·사전질문·답변

실측(수정 전 아우리봇):
    - 같은 계약이 legal_state "라이선스", 구조 판정 "NDA", 범위 정책 "자문/용역" 으로 동시에 불림
    - 제9조 제3항 둘째 줄 "(15)일 전에" 를 호 번호로 읽어 제9조 제2항·제3항 원문이 통째로 사라짐
      → IP 논점이 제2조(정의)·제9조 제1항(유형적 재산)에 붙음
    - 제10조 광고 "금지" 문장 하나로 표시광고법 "일부 적용"
    - 제6조 MUST(중요도 점수 0) · 2차적저작물 SHOULD · 제13조 해지 요건을 좁히는(우리 해지권 축소) 수정안
    - IP 조항에 위탁자/수탁자 용역 템플릿(제3자 침해 보증)이 붙음
    - 배경 문장("~진행하고자 함")·머리말("요청사항")·일반 의뢰가 각각 검토 쟁점이 되어 "적정" 답변
    - "지식재산권이 퍼시스에게 있으니 승인 없이 쓰겠다" 는 답변의 틀린 전제를 짚지 않음

담당 사내변호사 기준 답(이 테스트의 PASS 조건):
    MUST FIX  ① 성과물 제출·대금 연계(제5조 제1항 + 제6조·제13조 제3항)
              ② 연구성과 귀속·활용(제9조 제2항 + 제9조 제3항·제10조)
              ③ 일방적 방어·면책(제12조 제2항)
    SHOULD    없음 — 나머지는 DROP(2차적저작물·비밀유지 예외·존속조항 등)
    사업부 확인  제5조 제4항 금액 미확정 인터뷰 용역비
"""
from __future__ import annotations

import json
import logging
import re
import unittest
from pathlib import Path

from runtime.review.answer_intent_review import answer_lines
from runtime.review.clause_effect import ARCHETYPE_LICENSE, ARCHETYPE_RESEARCH, build_effect_profile
from runtime.review.clause_extraction import extract_clauses
from runtime.review.contract_type_resolution import resolve_contract_type
from runtime.review.research_model import resolve_research_model
from runtime.review.senior_counsel_audit import _narrows_our_remedy
from runtime.review.statute_applicability_gate import assess_advertising_act
from runtime.review.user_review_request import separate_context

FIX = Path(__file__).resolve().parent / "fixtures"
TEXT = (FIX / "snu_research_contract.txt").read_text(encoding="utf-8")
SESSION = json.loads((FIX / "snu_research_contract_session.json").read_text(encoding="utf-8"))

_FOREIGN_TEMPLATE = re.compile(r"위탁자|수탁자|라이선서|라이선시|2차적저작물|\[○\]|\[수정 제안")


def _live(crs: list[dict]) -> list[dict]:
    return [c for c in crs if not c.get("dedup_suppressed") and not c.get("keep_as_is")
            and str(c.get("risk_tier")).upper() in ("HIGH", "MEDIUM")]


class ParserGroundingTest(unittest.TestCase):
    """지시 2항 — 실제 조항이 있는데 사라지거나 다른 조·항·호로 읽히면 안 된다."""

    def test_article_9_paragraphs_survive_quantity_blank(self) -> None:
        by_path = {c.display_path: c.text for c in extract_clauses(TEXT)[0]}
        self.assertIn("제9조 제2항", by_path)
        self.assertIn("제9조 제3항", by_path)
        self.assertIn("공동\n소유로 한다", by_path["제9조 제2항"])
        self.assertIn("별도의 실시계약을 체결한다", by_path["제9조 제2항"])
        self.assertIn("(15)일 전에", by_path["제9조 제3항"])
        self.assertFalse([p for p in by_path if re.search(r"제9조 제\d항 \d+호", p)])

    def test_quantity_blanks_are_not_items(self) -> None:
        by_path = {c.display_path for c in extract_clauses(TEXT)[0]}
        self.assertIn("제13조 제3항", by_path)
        self.assertFalse([p for p in by_path if re.search(r"(?:4|15|30)호$", p)], by_path)


class ContractTypeTest(unittest.TestCase):
    """지시 1항 — 제목·정의조항 어휘가 아니라 목적·역할·급부·대금·핵심권리로 유형을 정한다."""

    def test_transaction_model(self) -> None:
        m = resolve_research_model(contract_text=TEXT, entity="퍼시스")
        self.assertTrue(m.confident)
        self.assertEqual((m.sponsor_label, m.performer_label, m.our_side), ("(주)퍼시스", "학교", "sponsor"))
        self.assertEqual(m.ip_regime, "joint")
        self.assertTrue(m.separate_license_required)
        self.assertEqual((m.final_payment_date, m.report_due), ("2027-02-28", "2027-03-31"))
        self.assertFalse(m.payment_linked_to_report)

    def test_not_license_nor_nda(self) -> None:
        self.assertEqual(resolve_contract_type(TEXT).contract_type_code, "research_collaboration")
        prof = build_effect_profile(text=TEXT, clauses=extract_clauses(TEXT)[0])
        self.assertEqual(prof.archetype, ARCHETYPE_RESEARCH)

    def test_ip_vocabulary_alone_is_not_a_license(self) -> None:
        body = re.sub(r"연\s*구\s*계\s*약\s*서", "계약서", TEXT)  # 표제를 지워도
        prof = build_effect_profile(text=body, clauses=extract_clauses(body)[0])
        self.assertNotEqual(prof.archetype, ARCHETYPE_LICENSE)

    def test_other_contracts_are_not_research(self) -> None:
        for name in ("wired_online_supply_draft.txt", "hangul_day_100th_alloso_3party_contract.txt",
                     "interior_works_prime_contractor.txt", "webzen_nda.txt"):
            t = (FIX / name).read_text(encoding="utf-8")
            self.assertFalse(resolve_research_model(contract_text=t).confident, name)


class StatuteContaminationTest(unittest.TestCase):
    """지시 7항 — 광고를 **금지**하는 문장은 표시·광고 행위가 아니다."""

    def test_ad_prohibition_is_not_advertising(self) -> None:
        self.assertEqual(assess_advertising_act(text=TEXT).conclusion, "비적용")

    def test_planned_advertising_still_applies(self) -> None:
        d = assess_advertising_act(text="을은 갑의 제품을 SNS에 광고하고 협찬 사실을 표시한다.")
        self.assertNotEqual(d.conclusion, "비적용")


class AdverseRedlineTest(unittest.TestCase):
    """지시 10항 — 상대방 위반을 사유로 한 우리 해지 요건을 좁히는 수정안은 REJECT."""

    ORIGINAL = "\"학교”가 본 계약을 위반하여 원활한 연구수행이 극히 곤란하다고 판단될 경우"
    PROPOSAL = ("“(주)퍼시스”는 \"학교\"가 본 계약의 주요 의무(연구수행, 연구보고서 제출 등)를 위반하여 그로 인해 연구의 "
                "목적 달성이 현저히 곤란하다고 객관적으로 인정되는 경우, 30일간의 시정 요구에도 불구하고 시정되지 "
                "아니하면 본 계약을 해지할 수 있다.")

    def test_narrowing_our_termination_right_is_adverse(self) -> None:
        self.assertTrue(_narrows_our_remedy(self.PROPOSAL, self.ORIGINAL, ["(주)퍼시스", "퍼시스"]))

    def test_narrowing_counterparty_right_against_us_is_fine(self) -> None:
        orig = "“(주)퍼시스”가 본 계약을 위반하여 원활한 연구수행이 극히 곤란하다고 판단될 경우"
        self.assertFalse(_narrows_our_remedy("“(주)퍼시스”가 주요 의무를 현저히 위반한 경우", orig, ["퍼시스"]))


class SemanticMismatchTest(unittest.TestCase):
    """지시 3항 — 양 당사자 불가항력 면책(제15조)을 '일방 면책'으로 읽지 않는다(AI 경로 실측)."""

    def test_one_sided_finding_on_mutual_clause_is_mismatch(self) -> None:
        from runtime.review.senior_counsel_audit import _one_sided_on_mutual_clause

        art15 = next(c.text for c in extract_clauses(TEXT)[0] if c.display_path == "제15조")
        t = {"detected_issue_list": [{"issue_title": "일방 면책/일방 배상(후보) 탐지"}]}
        self.assertTrue(_one_sided_on_mutual_clause({**t, "original_text": art15}))
        art12 = next(c.text for c in extract_clauses(TEXT)[0] if c.display_path == "제12조 제2항")
        self.assertFalse(_one_sided_on_mutual_clause({**t, "original_text": art12}))


class UserRequestTest(unittest.TestCase):
    """지시 4·12항 — 배경·머리말·일반 의뢰는 쟁점이 아니고, 답변 속 의도에는 직접 답한다."""

    def test_background_and_generic_request_are_context(self) -> None:
        kept, context = separate_context(SESSION["review_focus_base"])
        self.assertEqual(kept, "")
        self.assertEqual(len(context), 3)

    def test_specific_asks_are_kept(self) -> None:
        for t in ("지체상금 조항 검토 요청", "제7조 관할 확인 바랍니다", "해외 진출을 추진 중임. 관할이 불리한지 봐주세요",
                  "① 최저가 보장 관련 귀책 구분(제7조)\n② 버틀랩 정산 주체 문제(제7조 8항)"):
            self.assertTrue(separate_context(t)[0], t)

    def test_answer_block_is_read(self) -> None:
        self.assertEqual(len(answer_lines(SESSION["review_focus"])), 5)


class PipelineGoldenTest(unittest.TestCase):
    """AI 없이 전체 파이프라인."""

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
                service=RuleQueryService(loader), entity="퍼시스", contract_type=SESSION["contract_type"],
                text=TEXT, filename="서울대 산학협력단 연구계약서.pdf", answers=SESSION["answers"],
                review_focus=SESSION["review_focus"], asked_questions=SESSION["questions"], law_service=None,
                ai_provider=None, ai_model=None, ai_timeout_sec=None, ai_max_tokens=None, ai_temperature=None,
            )
        finally:
            logging.disable(logging.NOTSET)
        cls.meta, cls.crs = b.meta, b.clause_results
        cls.live = _live(b.clause_results)

    def test_one_contract_type_everywhere(self) -> None:
        m = self.meta
        self.assertEqual(m["legal_state"]["contract_type"], "research_collaboration")
        self.assertEqual(m["canonical_state"]["contract_type"], "research_collaboration")
        self.assertEqual(m["canonical_identity"]["contract_type_code"], "research_collaboration")
        self.assertEqual(m["contract_type_resolution"]["contract_type_code"], "research_collaboration")
        self.assertIn("산학협력 연구용역", m["contract_composition"]["canonical_label"])
        self.assertNotIn("라이선스", m["canonical_state"]["contract_type_label"])
        self.assertEqual(m["canonical_state"]["party_role"], "research_sponsor")
        self.assertEqual(m["legal_state"]["our_role_direction"], "recipient")

    def test_exactly_three_must_fix_on_exact_clauses(self) -> None:
        got = sorted((c["clause_id"].split("__")[0], c["display_path"], c["risk_tier"]) for c in self.live)
        self.assertEqual(got, [
            ("clr_one_sided_client_indemnity", "제12조 제2항", "HIGH"),
            ("tx_deliverable_payment_package", "제5조 제1항", "HIGH"),
            ("tx_research_ip_package", "제9조 제2항", "HIGH"),
        ])
        tri = self.meta["senior_counsel_audit"]["triage"]
        self.assertEqual(len(tri["MUST_FIX"]), 3)
        self.assertEqual(tri["SHOULD_FIX"], [])

    def test_packages_name_their_linked_clauses(self) -> None:
        pay = next(c for c in self.live if c["clause_id"].startswith("tx_deliverable"))
        self.assertEqual(pay["related_clause_paths"], ["제5조 제1항", "제6조", "제13조 제3항"])
        self.assertIn("2027. 2. 28.", pay["problem"])
        self.assertIn("2027. 3. 31.", pay["problem"])
        ip = next(c for c in self.live if c["clause_id"].startswith("tx_research_ip"))
        for p in ("제9조 제2항", "제9조 제3항", "제10조"):
            self.assertIn(p, ip["related_clause_paths"])
        self.assertIn("제10조는", ip["problem"])

    def test_redlines_are_insertable_and_ours(self) -> None:
        for c in self.live:
            sr = str(c.get("suggested_rewrite") or "")
            orig = str(c.get("original_text") or "")
            self.assertTrue(sr.strip(), c["clause_id"])
            self.assertNotEqual(re.sub(r"\s+", "", sr), re.sub(r"\s+", "", orig), c["clause_id"])
            self.assertFalse(_FOREIGN_TEMPLATE.search(sr), (c["clause_id"], sr[-200:]))
            self.assertTrue(sr.rstrip().endswith("."), c["clause_id"])
            self.assertIn("“(주)퍼시스”", sr)
        ip = next(c for c in self.live if c["clause_id"].startswith("tx_research_ip"))
        self.assertNotIn("별도의 실시계약을 체결한다", ip["suggested_rewrite"])
        self.assertIn("무상으로 실시", ip["suggested_rewrite"])

    def test_noise_is_dropped_not_shown(self) -> None:
        drop = {r["clause_id"].split("__")[0] for r in self.meta["senior_counsel_audit"]["triage"]["DROP"]}
        self.assertIn("eb_ip_no_derivative_right", drop)
        for c in self.live:
            self.assertNotRegex(str(c.get("issue_title") or "") + str(c.get("problem") or ""), r"2차적저작물|표시광고법")

    def test_business_check_kept_out_of_body(self) -> None:
        row = next(c for c in self.crs if str(c["clause_id"]).startswith("tx_open_cost"))
        self.assertEqual(row["display_path"], "제5조 제4항")
        self.assertFalse(row.get("dedup_suppressed"))
        self.assertEqual(str(row["risk_tier"]).upper(), "LOW")

    def test_user_answers_are_answered_directly(self) -> None:
        cov = self.meta["user_review_coverage"]
        self.assertFalse([r for r in cov if r.get("source") == "explicit_user_request"], cov)
        by_topic = {r["topic"]: r for r in cov if r.get("source") == "user_answer_intent"}
        self.assertEqual(by_topic["payment_on_deliverable"]["review_status"], "수정 필요")
        self.assertIn("tx_deliverable_payment_package__KR-5-p1", by_topic["payment_on_deliverable"]["matched_finding_ids"])
        free = by_topic["result_free_use"]
        self.assertEqual(free["review_status"], "수정 필요")
        self.assertIn("전제", free["conclusion"])
        self.assertIn("공동소유", free["conclusion"])
        self.assertIn("제10조", free["conclusion"])
        self.assertEqual(by_topic["subcontracting"]["review_status"], "사업부 결정 필요")

    def test_answer_and_body_agree(self) -> None:
        """지시 4항 — 요청 답변이 가리키는 finding 은 본문에 살아 있는 MUST FIX 다."""
        live_ids = {c["clause_id"] for c in self.live}
        for r in self.meta["user_review_coverage"]:
            for fid in r.get("matched_finding_ids") or []:
                self.assertIn(fid, live_ids, r.get("topic"))

    def test_statutes_and_gates(self) -> None:
        ad = next(d for d in self.meta["statute_applicability_gate"]["decisions"] if d["statute"] == "표시광고법")
        self.assertEqual(ad["conclusion"], "비적용")
        failed = [c["key"] for c in self.meta["final_counsel_gate"]["checks"] if not c["ok"]]
        self.assertEqual(failed, [])
        self.assertEqual(self.meta["senior_counsel_audit"]["final_check_failed"], [])


class RevisionDownloadTest(unittest.TestCase):
    """'수정본 생성하기' 와 같은 HTTP 경로 — 게이트가 정당하게 통과해야 한다(다운로드 경로 보호 지시)."""

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
        doc = create_session(
            cls.service, entity="퍼시스", contract_type=SESSION["contract_type"],
            filename="서울대 산학협력단 연구계약서.pdf", extraction={}, text=TEXT, classification={},
        )
        cls.session_id = doc["session_id"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.thread.join(timeout=5)
        cls.httpd.server_close()

    def _post(self, path: str) -> tuple[int, bytes]:
        import http.client

        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=180)
        conn.request("POST", path, body=json.dumps(
            {"session_id": self.session_id, "rebuild": True, "ai_mode": "off"}).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"})
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp.status, body

    def test_docx_and_pdf(self) -> None:
        import zipfile
        from io import BytesIO

        status, body = self._post("/api/revision/download_docx")
        self.assertEqual(status, 200, body[:600])
        with zipfile.ZipFile(BytesIO(body)) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        self.assertIn("무상으로 실시", xml)
        self.assertIn("잔금의 지급을 거절할 수 있다", xml)
        self.assertNotIn("수탁자", xml)
        status, body = self._post("/api/revision/download_pdf")
        self.assertEqual(status, 200, body[:600])
        self.assertTrue(body.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
