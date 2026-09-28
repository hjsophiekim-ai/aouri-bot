"""v19 — 임직원 비밀유지계약(Employee NDA) 사전질문·필수 검토항목 범용 보정 (2026-09-28).

실측(신규 입사자 비밀유지계약, California, Accounting Associate):

  사전질문   Q-EFF-payment-basis      "대가(금액·단가) 산정 근거" — 부가가치세·특수관계인
             Q-EFF-liability-exposure "최대 손해 규모" — 계약 대가 기준 배상 한도
             Q-FOCUS-privacy          "개인정보 제3자 제공·재위탁 절차"
                                      (담당자: '위탁이 아니라 내부 직원이 취급')
  수정본     0-2. 사용자 검토항목 답변 에 **다른 NDA 의 요청사항** 11건
             (Background IP, 범용 AI 학습 제한, 음성·수면·건강 정보, Foreground IP …)
  사용자요청 California 고용법 적법성 / SIDIZ America·Fursys America 양사 보호
             → 둘 다 "해당 조항 없음 / 사실관계 추가확인"
  파서       "No Effect on At-Will Employment" 의 'Will' 을 동사로 읽어 제9조 이후
             (준거법 포함 제10~13조)가 통째로 사라짐

고정하는 축
───────────
  1. canonical transaction model — employer/employee, 관할, 목적, 접근정보, 개인정보 구조
  2. Employee NDA whitelist 질문만, 이미 답이 있으면 묻지 않음
  3. 다른 거래유형 질문 금지(QUESTION_REJECTED_OUT_OF_SCOPE)
  4. 내부 직원 접근 ↔ 처리위탁 ↔ 제3자 제공 구분
  5. 사용자 요청을 mandatory issue 로 직접 답변(다른 generic 결과로 대체 금지)
  6. 계약 간 오염 hard gate(REVIEW_FAILED_QUESTION_CROSS_CONTRACT_CONTAMINATION)
  7. 필수 검토항목의 출처 구분 — 기술협업 NDA 항목이 다른 NDA 에 붙지 않음
  8. 수정본 DOCX 가 같은 결과를 싣는다(다운로드 경로가 이슈맵을 다시 만들지 않음)
  9. 골든 — 실제 PDF(있을 때만) / 교차 hold-out 2건(다른 법인·직무, 국문·대한민국법)
"""
from __future__ import annotations

import http.client
import json
import threading
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

from runtime.project_paths import CODE_REPO_ROOT
from runtime.questions.contract_question_agent import ContractQuestionPlan, _to_question
from runtime.questions.employee_nda_questions import (
    QUESTION_REJECTED_OUT_OF_SCOPE,
    QUESTION_REJECTED_PD_STRUCTURE_SETTLED,
    REVIEW_FAILED_QUESTION_CROSS_CONTRACT_CONTAMINATION,
    check_question_contamination,
    contamination_axes_for,
)
from runtime.questions.generator import generate_questions
from runtime.review.clause_extraction import extract_clauses
from runtime.review.employee_nda_model import (
    PD_EMPLOYEE_INTERNAL,
    PD_PROCESSOR,
    resolve_employee_nda_model,
)
from runtime.review.employee_nda_review import build_employee_nda_review
from runtime.review.mandatory_review_issues import derive_mandatory_review_issues

FIX = CODE_REPO_ROOT / "runtime" / "tests" / "fixtures"
NDA = "nda_confidentiality"

#: 실제 검증 대상 — 저장소에 두지 않는다. 있으면 골든으로 쓰고 없으면 건너뛴다.
GOLDEN_PDF = Path.home() / "Downloads" / "Fursys_America_Confidentiality_Agreement_Accounting_Associate.pdf"

CA_HR = (FIX / "employee_nda_ca_hr_generalist.txt").read_text(encoding="utf-8")
KR = (FIX / "employee_nda_kr_seoyakseo.txt").read_text(encoding="utf-8")

USER_REQ = (
    "1. 캘리포니아 법 / 노동법상 적법한지 검토해 주세요.\n"
    "2. 시디즈 아메리카(SIDIZ America)와 퍼시스 아메리카 양사의 기밀정보를 모두 보호할 수 있는지 확인해 주세요."
)
USER_ANSWER_INTERNAL = (
    "\n\n[사용자 확인 답변]\n- 개인정보 취급: 위탁이 아니라 내부 직원이 HR/재무 업무를 수행하며 개인정보를 취급한다"
)
CA_HR_REQ = "California 노동법상 적법한지, 퍼시스 아메리카 정보도 보호되는지 확인"

#: 지시 8항이 열거한 오염 키워드 — 원문 근거 없이 나오면 실패.
BANNED_QUESTION_WORDS = (
    "계약단가", "부가가치세", "특수관계인", "경영간섭", "판매정책",
    "공사대금", "검수", "준공", "광고매체", "위탁수수료",
)
#: 다른 NDA(기술협업)의 요청사항 — 직원 서약서의 필수 검토항목에 나오면 오염.
FOREIGN_NDA_ITEMS = (
    "Background IP", "범용 AI", "음성·수면·건강", "Foreground IP", "후속 계약과 본 계약",
)


def _golden_text() -> str | None:
    if not GOLDEN_PDF.exists():
        return None
    from runtime.review.text_extract import extract_text_from_file

    res = extract_text_from_file(GOLDEN_PDF)
    return str(getattr(res, "text", "") or "") or None


def _q_blob(qs) -> str:
    return "\n".join(f"{q.title}\n{q.description}" for q in qs)


def _ai_plan() -> ContractQuestionPlan:
    """AI 가 계약을 읽고 낸 질문을 흉내낸다 — 오염 질문 1건을 섞었다."""
    return ContractQuestionPlan(
        status="ai", contract_nature="고용계약 부수 비밀유지 약정", our_side="고용주",
        questions=[
            _to_question({"title": "이 직원이 퍼시스 아메리카와 시디즈 아메리카 양사의 정보에 모두 접근합니까?", "why": "x", "topic": "user_focus"}, 1),
            _to_question({"title": "시디즈 아메리카 정보는 퍼시스 아메리카가 위탁받아 처리하는 정보입니까?", "why": "x", "topic": "ip_ownership"}, 2),
            _to_question({"title": "직원이 처리하는 정보에 캘리포니아 소비자 개인정보(CCPA)가 포함됩니까?", "why": "x", "topic": "personal_data"}, 3),
            _to_question({"title": "계약단가 산정 근거와 부가가치세 처리는 어떻게 되나요?", "why": "특수관계인 거래", "topic": "payment_settlement"}, 4),
        ],
    )


# ══════════════════════════════════════════════════════════════════════════
# 1. canonical transaction model
# ══════════════════════════════════════════════════════════════════════════

class EmployeeNdaModelTest(unittest.TestCase):
    def test_hold_out_ca_different_employer_and_role(self) -> None:
        m = resolve_employee_nda_model(contract_text=CA_HR, user_description=CA_HR_REQ, contract_type_code=NDA)
        self.assertTrue(m.is_employee_nda and m.confident)
        self.assertEqual(m.relationship, "employer_employee")
        self.assertEqual(m.our_side, "employer")
        self.assertEqual(m.counterparty_role, "employee")
        self.assertEqual(m.employer_label, "SIDIZ America, Inc.")
        self.assertEqual(m.our_company, "시디즈 아메리카")
        self.assertEqual(m.governing_law, "California, USA")
        self.assertEqual(m.position, "HR Generalist")
        self.assertEqual(m.requested_affiliates, ("퍼시스 아메리카",))
        self.assertIn("payroll_hr_personal", m.information_types)

    def test_hold_out_korean_pledge(self) -> None:
        m = resolve_employee_nda_model(contract_text=KR, contract_type_code=NDA)
        self.assertTrue(m.is_employee_nda and m.confident)
        self.assertEqual(m.our_company, "일룸")
        self.assertEqual(m.jurisdiction_key, "kr")
        self.assertTrue(m.noncompete_present)

    def test_business_ndas_are_not_employee_ndas(self) -> None:
        # 사업자 간 NDA 도 "employees" 를 말한다 — 당사자로 정의될 때만 센다.
        for f in FIX.glob("*.txt"):
            if f.name.startswith("employee_nda_"):
                continue
            with self.subTest(fixture=f.name):
                m = resolve_employee_nda_model(contract_text=f.read_text(encoding="utf-8"))
                self.assertFalse(m.is_employee_nda)

    def test_canonical_type_is_not_overturned(self) -> None:
        m = resolve_employee_nda_model(contract_text=CA_HR, contract_type_code="dealer_agency")
        self.assertFalse(m.is_employee_nda)

    def test_personal_data_structure_user_answer_wins(self) -> None:
        m = resolve_employee_nda_model(
            contract_text=CA_HR, user_description="위탁이 아니라 내부 직원이 HR 업무를 수행한다",
            contract_type_code=NDA,
        )
        self.assertEqual((m.personal_data_structure, m.personal_data_basis), (PD_EMPLOYEE_INTERNAL, "user_answer"))
        m2 = resolve_employee_nda_model(
            contract_text=CA_HR, user_description="급여 정산은 외부 업체에 처리위탁 한다", contract_type_code=NDA,
        )
        self.assertEqual(m2.personal_data_structure, PD_PROCESSOR)


# ══════════════════════════════════════════════════════════════════════════
# 2~4. 사전질문
# ══════════════════════════════════════════════════════════════════════════

class EmployeeNdaQuestionTest(unittest.TestCase):
    def _qs(self, text: str, focus: str, *, plan=None, report=None):
        return generate_questions(
            "all", "all", [], contract_text=text, max_questions=5, review_focus=focus,
            contract_type_code=NDA, transaction_type="confidentiality_only",
            question_plan=plan, gate_report=report,
        )

    def test_only_whitelist_questions_and_no_contamination(self) -> None:
        for text, focus in ((CA_HR, CA_HR_REQ), (KR, "")):
            for plan in (None, _ai_plan()):
                with self.subTest(text=text[:20], plan=bool(plan)):
                    qs = self._qs(text, focus, plan=plan)
                    self.assertTrue(qs)
                    self.assertTrue(all(q.question_id.startswith("Q-ENDA-") for q in qs), [q.question_id for q in qs])
                    blob = _q_blob(qs)
                    for w in BANNED_QUESTION_WORDS:
                        self.assertNotIn(w, blob)

    def test_effect_questions_rejected_with_code(self) -> None:
        rep: dict = {}
        self._qs(CA_HR, CA_HR_REQ, report=rep)
        rejected = {r["question_id"]: r["code"] for r in rep["nda_question_policy"]["rejected"]}
        self.assertTrue(any(qid.startswith("Q-EFF-") for qid in rejected))
        self.assertIn(QUESTION_REJECTED_OUT_OF_SCOPE, set(rejected.values()))

    def test_ai_contaminated_question_rejected(self) -> None:
        rep: dict = {}
        self._qs(CA_HR, CA_HR_REQ, plan=_ai_plan(), report=rep)
        codes = {r["question_id"]: r["code"] for r in rep["nda_question_policy"]["rejected"]}
        self.assertEqual(codes.get("Q-AI-004-payment_settlement"), QUESTION_REJECTED_OUT_OF_SCOPE)

    def test_internal_access_suppresses_processor_questions(self) -> None:
        rep: dict = {}
        qs = self._qs(CA_HR, CA_HR_REQ + USER_ANSWER_INTERNAL, plan=_ai_plan(), report=rep)
        blob = _q_blob(qs)
        for w in ("재위탁", "처리위탁", "제3자에게 제공", "위탁받아"):
            self.assertNotIn(w, blob)
        codes = {r["code"] for r in rep["nda_question_policy"]["rejected"]}
        self.assertIn(QUESTION_REJECTED_PD_STRUCTURE_SETTLED, codes)

    def test_answered_facts_are_not_asked(self) -> None:
        # 반환·삭제 조항이 원문에 있고, 경업금지가 없는 캘리포니아 계약 — 묻지 않는다.
        ids = {q.question_id for q in self._qs(CA_HR, CA_HR_REQ)}
        self.assertNotIn("Q-ENDA-return-deletion", ids)
        self.assertNotIn("Q-ENDA-post-employment", ids)
        self.assertNotIn("Q-ENDA-hr-personal-data", ids)   # 정의에 급여·인사 정보가 있다
        self.assertIn("Q-ENDA-affiliate-access", ids)       # 요청했지만 실제 접근은 미확정

    def test_affiliate_question_uses_english_legal_name_in_english_contract(self) -> None:
        q = next(q for q in self._qs(CA_HR, CA_HR_REQ) if q.question_id == "Q-ENDA-affiliate-access")
        self.assertIn("Fursys America", q.title)

    def test_korean_noncompete_asks_consideration_not_work_location(self) -> None:
        ids = {q.question_id for q in self._qs(KR, "")}
        self.assertIn("Q-ENDA-noncompete-consideration", ids)
        self.assertNotIn("Q-ENDA-work-location", ids)

    def test_business_nda_keeps_its_questions_but_drops_contamination(self) -> None:
        text = (FIX / "nda_ai_sleep_collaboration.txt").read_text(encoding="utf-8")
        qs = self._qs(text, "")
        self.assertFalse(any(q.question_id.startswith("Q-ENDA-") for q in qs))
        for q in qs:
            self.assertEqual(contamination_axes_for(q, text), [], q.question_id)


class ContaminationGateTest(unittest.TestCase):
    def test_hard_gate_fails_when_contaminated_question_went_out(self) -> None:
        asked = [{"question_id": "Q-X", "title": "계약단가 산정 근거와 부가가치세는?", "description": ""}]
        rep = check_question_contamination(asked, contract_text=CA_HR, contract_type_code=NDA)
        self.assertEqual(rep["status"], REVIEW_FAILED_QUESTION_CROSS_CONTRACT_CONTAMINATION)

    def test_basis_in_contract_allows_the_question(self) -> None:
        body = CA_HR + "\nThe Company shall pay a signing bonus of $5,000 and all fees payable hereunder."
        asked = [{"question_id": "Q-X", "title": "대가(금액·단가)를 어떤 근거로 산정했나요?", "description": ""}]
        rep = check_question_contamination(asked, contract_text=body, contract_type_code=NDA)
        self.assertEqual(rep["status"], "")

    def test_non_nda_types_are_not_judged(self) -> None:
        asked = [{"question_id": "Q-X", "title": "계약단가 산정 근거는?", "description": ""}]
        rep = check_question_contamination(asked, contract_text="", contract_type_code="dealer_agency")
        self.assertEqual(rep["status"], "")


# ══════════════════════════════════════════════════════════════════════════
# 5·7. 필수 검토항목
# ══════════════════════════════════════════════════════════════════════════

class MandatoryIssueTest(unittest.TestCase):
    def test_user_requests_answered_directly_with_clauses(self) -> None:
        m = resolve_employee_nda_model(contract_text=CA_HR, user_description=CA_HR_REQ, contract_type_code=NDA)
        rev = build_employee_nda_review(m, contract_text=CA_HR, clauses=extract_clauses(CA_HR)[0], review_focus=CA_HR_REQ)
        users = {a["code"]: a for a in rev["mandatory_review_issues"] if a["source"] == "user_request"}
        law = users["enda_user_employment_law"]
        self.assertEqual(law["verdict"], "수정 필요")
        self.assertIn("18 U.S.C. §1833(b)", law["direct_answer"])    # 이 hold-out 에는 DTSA 고지가 없다
        self.assertIn("12964.5", law["direct_answer"])
        self.assertTrue(law["fix_clauses"])
        aff = users["enda_user_affiliate_protection"]
        self.assertEqual(aff["verdict"], "수정 필요")
        self.assertIn("Fursys America", aff["direct_answer"])
        self.assertTrue(any("third-party beneficiary" in c for c in aff["fix_clauses"]))

    def test_employee_catalog_has_no_foreign_nda_items(self) -> None:
        for text in (CA_HR, KR):
            m = resolve_employee_nda_model(contract_text=text, contract_type_code=NDA)
            rev = build_employee_nda_review(m, contract_text=text, clauses=extract_clauses(text)[0])
            titles = " ".join(a["title"] for a in rev["mandatory_review_issues"])
            for bad in FOREIGN_NDA_ITEMS:
                self.assertNotIn(bad, titles)

    def test_tech_items_need_tech_character_or_user_request(self) -> None:
        plain = (FIX / "nda_basic.txt").read_text(encoding="utf-8")
        codes = {i.code for i in derive_mandatory_review_issues(contract_type_code=NDA, contract_text=plain)}
        tech = (FIX / "nda_ai_sleep_collaboration.txt").read_text(encoding="utf-8")
        tech_codes = {i.code for i in derive_mandatory_review_issues(contract_type_code=NDA, contract_text=tech)}
        self.assertIn("ai_training_data_reuse", tech_codes)
        if "ai_training_data_reuse" in codes:
            self.fail("기술협업 신호가 없는 NDA 에 'AI 학습 제한' 이 기본 항목으로 붙었다")
        asked = {
            i.code: i.source for i in derive_mandatory_review_issues(
                contract_type_code=NDA, contract_text=plain, review_focus="AI 학습 데이터 재사용 제한 확인",
            )
        }
        self.assertEqual(asked.get("ai_training_data_reuse"), "user_request")


# ══════════════════════════════════════════════════════════════════════════
# 8·9. 골든 — 실제 PDF + 수정본 다운로드
# ══════════════════════════════════════════════════════════════════════════

class ClauseExtractionTest(unittest.TestCase):
    def test_hyphenated_will_is_not_a_verb(self) -> None:
        text = (
            "1. Definitions\nTerms used here have their ordinary meaning.\n"
            "2. No Effect on At-Will Employment\nThis Agreement does not alter at-will employment.\n"
            "3. Governing Law\nThis Agreement is governed by the laws of the State of California.\n"
        ) * 1
        ids = [c.clause_id for c in extract_clauses(text)[0]]
        self.assertEqual(ids, ["EN-1", "EN-2", "EN-3"])


@unittest.skipUnless(GOLDEN_PDF.exists(), "실제 검증 PDF 가 이 PC 에 없다")
class GoldenAcceptanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = _golden_text() or ""
        from runtime.review.clause_level import build_clause_level_result
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService

        loader = RuleLoader()
        loader.load()
        cls.service = RuleQueryService(loader)
        cls.bundle = build_clause_level_result(
            service=cls.service, entity="퍼시스", contract_type="all", text=cls.text,
            filename=GOLDEN_PDF.name, answers=None, review_focus=USER_REQ + USER_ANSWER_INTERNAL,
            law_service=None, ai_provider=None, ai_model=None, ai_timeout_sec=None,
            ai_max_tokens=None, ai_temperature=None, max_clause_law_items=0,
        )

    def test_canonical_model(self) -> None:
        cs = self.bundle.meta["canonical_state"]
        self.assertEqual(cs["contract_type"], NDA)
        self.assertIn("Employee NDA", cs["contract_type_label"])
        self.assertEqual(cs["party_label"], "Fursys America, Inc.")
        self.assertEqual(cs["counterparty_label"], "Employee")
        m = self.bundle.meta["employee_nda_model"]
        self.assertEqual(m["relationship"], "employer_employee")
        self.assertEqual(m["governing_law"], "California, USA")
        self.assertEqual(m["personal_data_structure"], PD_EMPLOYEE_INTERNAL)

    def test_questions(self) -> None:
        rep: dict = {}
        qs = generate_questions(
            "퍼시스", "all", [], contract_text=self.text, max_questions=5,
            review_focus=USER_REQ + USER_ANSWER_INTERNAL, contract_type_code=NDA,
            transaction_type="confidentiality_only", question_plan=_ai_plan(), gate_report=rep,
        )
        ids = [q.question_id for q in qs]
        self.assertEqual(ids, ["Q-ENDA-affiliate-access", "Q-ENDA-work-location"])
        blob = _q_blob(qs)
        for w in BANNED_QUESTION_WORDS + ("대리점", "재판매", "광고비", "재위탁", "처리위탁"):
            self.assertNotIn(w, blob)

    def test_mandatory_issues_include_user_requests(self) -> None:
        issues = self.bundle.meta["mandatory_review_issues"]
        users = {a["code"]: a for a in issues if a.get("source") == "user_request"}
        self.assertIn("enda_user_employment_law", users)
        self.assertIn("enda_user_affiliate_protection", users)
        self.assertEqual(users["enda_user_employment_law"]["verdict"], "수정 필요")   # SB 331 문구 누락
        self.assertIn("12964.5", users["enda_user_employment_law"]["direct_answer"])
        self.assertIn("SIDIZ America", users["enda_user_affiliate_protection"]["direct_answer"])
        titles = " ".join(a["title"] for a in issues)
        for bad in FOREIGN_NDA_ITEMS:
            self.assertNotIn(bad, titles)

    def test_user_coverage_is_direct_not_generic(self) -> None:
        cov = self.bundle.meta["user_review_coverage"]
        # 요청 2건 + 사전질문 답변으로 알려 온 '직원 내부 개인정보 취급'(v20 — 직접 답한다)
        self.assertEqual(len(cov), 3)
        self.assertTrue(any("내부 직원" in r["original_user_text"] for r in cov))
        for r in cov:
            self.assertEqual(r["answered_by"], "employee_nda_review")
            self.assertNotEqual(r["review_status"], "사실관계 추가확인")
            self.assertTrue(r["relevant_clause_paths"])

    def test_all_articles_extracted(self) -> None:
        ids = [c.clause_id for c in extract_clauses(self.text)[0]]
        self.assertEqual(ids, [f"EN-{i}" for i in range(1, 14)])


class RevisionDownloadTest(unittest.TestCase):
    """수정본 DOCX/PDF — 앱에서 누르는 것과 같은 HTTP 경로(hold-out 계약)."""

    @classmethod
    def setUpClass(cls) -> None:
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
        cls.doc = create_session(
            cls.service, entity="시디즈", contract_type="", filename="employee_confidentiality_hr.docx",
            extraction={}, text=CA_HR, classification={}, review_focus=CA_HR_REQ,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.thread.join(timeout=5)
        cls.httpd.server_close()

    def _post(self, path: str, payload: dict):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=300)
        conn.request(
            "POST", path, body=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp, body

    def test_session_questions_are_clean(self) -> None:
        blob = "\n".join(f"{q['title']}\n{q['description']}" for q in self.doc["questions"])
        for w in BANNED_QUESTION_WORDS:
            self.assertNotIn(w, blob)
        self.assertTrue(self.doc["question_gate"]["nda_question_policy"]["employee_mode"])

    def test_download_docx_has_only_this_contracts_items(self) -> None:
        resp, body = self._post(
            "/api/revision/download_docx",
            {"session_id": self.doc["session_id"], "rebuild": True, "ai_mode": "off"},
        )
        if resp.status != 200:
            self.fail(f"수정본(docx) 생성 실패 status={resp.status}: {body[:800]!r}")
        with zipfile.ZipFile(BytesIO(body)) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
        self.assertIn("0-2. 사용자 검토항목 답변", xml)
        self.assertIn("고용법(노동법)상 적법성", xml)
        self.assertIn("계약유형 기본 검토항목", xml)
        for bad in FOREIGN_NDA_ITEMS:
            self.assertNotIn(bad, xml)

    def test_download_pdf_succeeds(self) -> None:
        resp, body = self._post(
            "/api/revision/download_pdf",
            {"session_id": self.doc["session_id"], "rebuild": True, "ai_mode": "off"},
        )
        if resp.status != 200:
            self.fail(f"수정본(pdf) 생성 실패 status={resp.status}: {body[:800]!r}")
        self.assertTrue(body.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
