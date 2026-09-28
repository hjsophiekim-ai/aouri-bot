"""v20 — Employee NDA: 기존 보호조항 KEEP + 실질 공백만 최소수정 (2026-09-28 2차 지시).

실측(신규 입사자 비밀유지계약, California, AI 사용 검토):

    지위   supplier / buyer                       (AI Legal Map override)
    HIGH   Art.5  "임금·근로조건 논의권 명확화"      → 제안문구 = 원문 (c)  (no-op)
    HIGH   counsel "경업금지 해석 위험 차단"         → 제8·11조에 이미 직업선택 자유 문구
    HIGH   Art.6  DTSA 고지                          → §1833(b) 네 요소 이미 충족
    HIGH   counsel 가처분 반복                        → 제10조에 이미 있음
    MED    Art.8  "영구 비밀유지 무효 위험"           → 비밀인 동안 + 일반 지식 허용 이미 있음
    없음   계열사(SIDIZ America) 보호 공백, Gov. Code §12964.5 문구 누락 finding

고정하는 축
───────────
  1. 사용자/직원 지위 고정 — 공급자·구매자로 덮이지 않음, 바뀌면 REVIEW_FAILED_PARTY_ROLE_MISMATCH
  2. 다른 계약유형 축·지위의 finding 제거
  3. 기존 보호조항 → KEEP_EXISTING_CLAUSE
  4. 원문과 같은 제안 → REVIEW_FAILED_NO_OP_REDLINE 기록 후 KEEP
  5·6. 요청별 직접 답변 — 관련조항·현재 효과·법률 판단·결론, 계열사는 정의조항 중심
  7·8. 직원 개인정보 — 내부 접근, 계약 층위와 법률 층위(NEEDS_FACT_CHECK) 구분
  10. DTSA 는 존재가 아니라 네 요소 충족으로 판단
  11. 존속기간 — 영업비밀/일반 비밀정보/일반 지식 세 범주
  12·16. HIGH 는 실질 공백에만, 추가문안은 빠진 문장만
"""
from __future__ import annotations

import unittest

from runtime.questions.generator import generate_questions
from runtime.review.checklists.employee_nda import (
    KEEP_EXISTING_CLAUSE,
    REVIEW_FAILED_NO_OP_REDLINE,
    REVIEW_FAILED_PARTY_ROLE_MISMATCH,
    apply_employee_nda_final_gate,
    check_party_roles,
    dtsa_elements,
    employee_nda_protections,
    is_no_op_redline,
    run_employee_nda_checklist,
)
from runtime.review.clause_extraction import extract_clauses
from runtime.review.employee_nda_model import resolve_employee_nda_model
from runtime.review.employee_nda_review import (
    NEEDS_FACT_CHECK,
    build_employee_nda_review,
    detect_user_requests,
)
from runtime.tests.test_v19_employee_nda_questions import (
    CA_HR,
    CA_HR_REQ,
    GOLDEN_PDF,
    KR,
    NDA,
    USER_ANSWER_INTERNAL,
    _golden_text,
)

#: 사업부 요청 메모 모양(글머리표 ●) — 합성. 배경 서술과 요청이 섞여 있다.
MEMO = (
    "비밀유지협약서.\n\n"
    "●대상자: 신규 입사자 (Accounting Associate)\n"
    "●담당업무: SIDIZ America 및 Fursys America 양사 회계·재무 업무\n"
    "●신청 배경: 업무 특성상 재무·회계, 직원 급여·인사 정보에 접근 불가피\n"
    "●요청사항: 미국 캘리포니아주 관련 법령 및 노동법상 적법성 여부 검토\n"
    "●추가사항: SIDIZ America 및 Fursys America 양사의 기밀정보를 포괄적으로 보호하는 데 법적 문제 여부 검토\n"
    "*법무팀 검토 의견 반영 후 최종 NDA 확정 및 입사자 서명 진행"
)
MEMO_ANSWER = (
    "\n\n[사용자 확인 답변]\n- 개인정보를 제3자에게 제공하거나 재위탁하는 절차가 있나요?: "
    "위탁은 아니고, 회사 직원이 내부 인사, 재무관련 업무를 하다보니 개인의 개인정보를 취급하는 업무를 하게 될 예정입니다."
)


def _model(text: str, focus: str = ""):
    return resolve_employee_nda_model(contract_text=text, user_description=focus, contract_type_code=NDA)


def _ai_like(clause_id: str, *, title: str, original: str, rewrite: str, tier: str = "HIGH", reason: str = "") -> dict:
    return {
        "clause_id": clause_id, "issue_title": title, "original_text": original,
        "suggested_rewrite": rewrite, "risk_tier": tier, "severity": tier,
        "rewrite_reason": reason or title, "problem": reason or title,
        "high_risk": tier == "HIGH", "must_fix": tier == "HIGH", "display_kind": "redline",
    }


# ══════════════════════════════════════════════════════════════════════════
# 4. no-op redline
# ══════════════════════════════════════════════════════════════════════════

class NoOpRedlineTest(unittest.TestCase):
    ORIG = (
        "Nothing in this Agreement prevents Employee from: (a) making a disclosure required by law, court order, "
        "or valid subpoena; (c) exercising rights under Section 7 of the National Labor Relations Act or "
        "California Labor Code Sections 232 and 232.5, including the right to discuss Employee's own wages, "
        "hours, and working conditions."
    )

    def test_ellipsis_copy_of_original_is_no_op(self) -> None:
        rw = (
            "Nothing in this Agreement prevents Employee from: ... (c) exercising rights under Section 7 of the "
            "National Labor Relations Act or California Labor Code Sections 232 and 232.5, including the right to "
            "discuss Employee's own wages, hours, and working conditions."
        )
        self.assertTrue(is_no_op_redline(self.ORIG, rw))

    def test_real_addition_is_not_no_op(self) -> None:
        rw = self.ORIG + " Nothing in this Agreement prevents Employee from discussing unlawful acts in the workplace."
        self.assertFalse(is_no_op_redline(self.ORIG, rw))


# ══════════════════════════════════════════════════════════════════════════
# 2·3·4. 최종 감사 게이트
# ══════════════════════════════════════════════════════════════════════════

@unittest.skipUnless(GOLDEN_PDF.exists(), "실제 검증 PDF 가 이 PC 에 없다")
class GoldenGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = _golden_text() or ""
        cls.clauses = extract_clauses(cls.text)[0]
        cls.model = _model(cls.text, MEMO + MEMO_ANSWER)

    def test_existing_protections_recognised(self) -> None:
        prot = employee_nda_protections(self.model, contract_text=self.text, clauses=self.clauses)
        for key in ("employee_freedom", "dtsa_notice", "wage_discussion", "whistleblower",
                    "required_disclosure", "injunctive_relief", "return_deletion", "duration"):
            self.assertIn(key, prot)

    def test_dtsa_is_judged_by_elements(self) -> None:
        el = dtsa_elements(self.text)
        self.assertTrue(all(el.values()), el)

    def test_gate_keeps_existing_and_no_op_and_removes_foreign(self) -> None:
        a5 = next(c for c in self.clauses if "Permitted Disclosures" in (c.title or ""))
        results = [
            _ai_like("EN-5", title="직원의 임금·근로조건 논의 권리 제한 금지 명확화 필요",
                     original=a5.text, rewrite="Nothing in this Agreement prevents Employee from: ... (c) exercising "
                     "rights under Section 7 of the National Labor Relations Act or California Labor Code Sections 232 "
                     "and 232.5, including the right to discuss Employee's own wages, hours, and working conditions."),
            _ai_like("counsel_legal_02", title="경업금지(직업선택 제한)로 해석될 위험 차단 필요",
                     original="(원문)", rewrite="Employee may accept employment with any other employer."),
            _ai_like("counsel_EN-10", title="가처분 등 형평법상 구제 명시", original="(원문)",
                     rewrite="The Company may seek injunctive relief."),
            _ai_like("EN-8", title="영구적 비밀유지 의무의 합리적 제한 필요", tier="MEDIUM",
                     original="(원문)", rewrite="Obligations survive for three years."),
            _ai_like("x-tax", title="부가가치세·특수관계인 거래 검토", original="(원문)", rewrite="VAT clause"),
            _ai_like("x-role", title="공급업자의 하자담보 책임", original="(원문)", rewrite="warranty"),
        ]
        results += run_employee_nda_checklist(self.model, contract_text=self.text, clauses=self.clauses)
        rep = apply_employee_nda_final_gate(results, model=self.model, contract_text=self.text, clauses=self.clauses)
        by_id = {r["clause_id"]: r for r in results}
        self.assertEqual(by_id["EN-5"]["keep_code"], REVIEW_FAILED_NO_OP_REDLINE)
        for cid in ("counsel_legal_02", "counsel_EN-10", "EN-8"):
            self.assertEqual(by_id[cid]["keep_code"], KEEP_EXISTING_CLAUSE, cid)
            self.assertEqual(by_id[cid]["risk_tier"], "LOW")
        self.assertNotIn("x-tax", by_id)
        self.assertNotIn("x-role", by_id)
        self.assertEqual(len(rep["removed"]), 2)

    def test_checklist_only_real_gaps_minimal(self) -> None:
        items = {i["clause_id"]: i for i in run_employee_nda_checklist(
            self.model, contract_text=self.text, clauses=self.clauses, review_focus=MEMO + MEMO_ANSWER,
        )}
        self.assertEqual(set(items), {"ENDA-AFFILIATE", "ENDA-CARVEOUT", "ENDA-EMPLOYEE-DATA"})
        self.assertEqual(items["ENDA-AFFILIATE"]["risk_tier"], "HIGH")
        self.assertEqual(items["ENDA-AFFILIATE"]["display_path"], "Article 1")
        self.assertIn("SIDIZ America", items["ENDA-AFFILIATE"]["suggested_rewrite"])
        # 기존 carve-out 은 그대로 두고 빠진 §12964.5 문장만 추가한다.
        carve = items["ENDA-CARVEOUT"]
        self.assertEqual(carve["display_path"], "Article 5")
        self.assertIn("unlawful acts in the workplace", carve["suggested_rewrite"])
        for kept in ("Defend Trade Secrets", "Section 7", "1102.5"):
            self.assertNotIn(kept, carve["suggested_rewrite"])
        self.assertEqual(items["ENDA-EMPLOYEE-DATA"]["risk_tier"], "MEDIUM")
        # 원문에 있는 것은 다시 넣지 않는다.
        self.assertNotIn("need to know", items["ENDA-EMPLOYEE-DATA"]["suggested_rewrite"].lower())

    def test_requests_answered_directly_in_four_parts(self) -> None:
        rev = build_employee_nda_review(
            self.model, contract_text=self.text, clauses=self.clauses, review_focus=MEMO + MEMO_ANSWER,
        )
        users = {a["code"]: a for a in rev["mandatory_review_issues"] if a["source"] == "user_request"}
        self.assertEqual(set(users), {
            "enda_user_employment_law", "enda_user_affiliate_protection", "enda_user_employee_privacy",
        })
        for a in users.values():
            for k in ("relevant_clauses", "current_effect", "legal_judgment", "conclusion"):
                self.assertTrue(a["parts"][k], (a["code"], k))
        law = users["enda_user_employment_law"]["direct_answer"]
        for piece in ("DTSA", "경업금지", "존속기간", "12964.5"):
            self.assertIn(piece, law)
        aff = users["enda_user_affiliate_protection"]
        self.assertIn("'Company'", aff["parts"]["current_effect"])
        self.assertIn("Article 1", aff["parts"]["relevant_clauses"])
        priv = users["enda_user_employee_privacy"]
        self.assertIn("employee internal access", priv["direct_answer"])
        self.assertIn(NEEDS_FACT_CHECK, priv["direct_answer"])
        self.assertTrue(priv["fact_checks"])


# ══════════════════════════════════════════════════════════════════════════
# 교차 hold-out — 다른 법인·직무 / 국문
# ══════════════════════════════════════════════════════════════════════════

class HoldOutChecklistTest(unittest.TestCase):
    def test_ca_hr_missing_dtsa_is_high_and_duration_split(self) -> None:
        m = _model(CA_HR, CA_HR_REQ)
        items = {i["clause_id"]: i for i in run_employee_nda_checklist(
            m, contract_text=CA_HR, clauses=extract_clauses(CA_HR)[0], review_focus=CA_HR_REQ,
        )}
        self.assertEqual(items["ENDA-CARVEOUT"]["risk_tier"], "HIGH")
        self.assertIn("Defend Trade Secrets Act", items["ENDA-CARVEOUT"]["suggested_rewrite"])
        # 비밀인 동안 존속은 있으나 일반 지식·경험 허용이 없다 → 범주 구분 보완(MEDIUM)
        self.assertEqual(items["ENDA-DURATION"]["risk_tier"], "MEDIUM")
        self.assertIn("general knowledge", items["ENDA-DURATION"]["suggested_rewrite"])
        self.assertNotIn("ENDA-NONCOMPETE", items)

    def test_partial_dtsa_notice_asks_only_missing_element(self) -> None:
        text = CA_HR.replace(
            "7. Governing Law",
            "6A. Notice\nUnder the Defend Trade Secrets Act, Employee is immune for disclosure in confidence to a "
            "federal, state, or local government official or to an attorney, or in a filing made under seal.\n\n7. Governing Law",
        )
        el = dtsa_elements(text)
        self.assertTrue(el["present"] and not el["retaliation_lawsuit"])
        items = {i["clause_id"]: i for i in run_employee_nda_checklist(
            _model(text), contract_text=text, clauses=extract_clauses(text)[0],
        )}
        self.assertIn("retaliation", items["ENDA-CARVEOUT"]["suggested_rewrite"])

    def test_california_noncompete_is_high(self) -> None:
        text = CA_HR.replace(
            "7. Governing Law",
            "6B. Non-Competition\nFor one year after employment ends, Employee shall not engage in any business "
            "that competes with the Company.\n\n7. Governing Law",
        )
        items = {i["clause_id"]: i for i in run_employee_nda_checklist(
            _model(text), contract_text=text, clauses=extract_clauses(text)[0],
        )}
        self.assertEqual(items["ENDA-NONCOMPETE"]["risk_tier"], "HIGH")

    def test_korean_pledge_gets_no_english_drafting(self) -> None:
        items = run_employee_nda_checklist(_model(KR), contract_text=KR, clauses=extract_clauses(KR)[0])
        for i in items:
            self.assertNotRegex(i["suggested_rewrite"], r"[A-Za-z]{12,}")


# ══════════════════════════════════════════════════════════════════════════
# 1. 지위 · 5. 요청 인식 · 사전질문
# ══════════════════════════════════════════════════════════════════════════

class RoleAndRequestTest(unittest.TestCase):
    def test_party_role_mismatch_is_reported(self) -> None:
        m = _model(CA_HR)
        self.assertEqual(check_party_roles({"party_role": "employer", "counterparty_role": "employee"}, m)["status"], "")
        self.assertEqual(
            check_party_roles({"party_role": "supplier", "counterparty_role": "buyer"}, m)["status"],
            REVIEW_FAILED_PARTY_ROLE_MISMATCH,
        )

    def test_memo_bullets_separate_requests_from_background(self) -> None:
        m = _model(CA_HR, MEMO + MEMO_ANSWER)
        reqs = {r["code"]: r["text"] for r in detect_user_requests(m, MEMO + MEMO_ANSWER)}
        self.assertIn("노동법상 적법성", reqs["enda_user_employment_law"])
        self.assertIn("포괄적으로 보호", reqs["enda_user_affiliate_protection"])   # 담당업무 줄이 아니라 요청 줄
        self.assertIn("내부 인사", reqs["enda_user_employee_privacy"])
        for t in reqs.values():
            self.assertIn(t, MEMO + MEMO_ANSWER)   # 담당자가 실제로 쓴 문장만

    def test_memo_answers_affiliate_access_question(self) -> None:
        qs = generate_questions(
            "all", "all", [], contract_text=CA_HR, max_questions=5, review_focus=MEMO, contract_type_code=NDA,
        )
        self.assertNotIn("Q-ENDA-affiliate-access", {q.question_id for q in qs})


@unittest.skipUnless(GOLDEN_PDF.exists(), "실제 검증 PDF 가 이 PC 에 없다")
class GoldenPipelineTest(unittest.TestCase):
    """골든 — 검토 파이프라인 전체(AI 미사용)."""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.review.clause_level import build_clause_level_result
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService

        loader = RuleLoader()
        loader.load()
        cls.bundle = build_clause_level_result(
            service=RuleQueryService(loader), entity="퍼시스", contract_type="all", text=_golden_text() or "",
            filename=GOLDEN_PDF.name, answers=None, review_focus=MEMO + MEMO_ANSWER,
            law_service=None, ai_provider=None, ai_model=None, ai_timeout_sec=None,
            ai_max_tokens=None, ai_temperature=None, max_clause_law_items=0,
        )

    def test_roles_and_status(self) -> None:
        cs = self.bundle.meta["canonical_state"]
        self.assertEqual((cs["party_role"], cs["counterparty_role"]), ("employer", "employee"))
        self.assertEqual(self.bundle.meta["legal_map_role_override"].get("skipped"), "employee_nda_model")
        self.assertIn(self.bundle.meta.get("review_status") or "", ("", None))

    def test_high_only_on_real_gaps(self) -> None:
        live = [c for c in self.bundle.clause_results if str(c.get("risk_tier")).upper() in ("HIGH", "MEDIUM")]
        ids = {c["clause_id"] for c in live}
        self.assertEqual(ids, {"ENDA-AFFILIATE", "ENDA-CARVEOUT", "ENDA-EMPLOYEE-DATA"})
        blob = " ".join(str(c.get("issue_title") or "") + str(c.get("problem") or "") for c in self.bundle.clause_results)
        for bad in ("공급업자", "수탁자", "하도급", "대리점", "부가가치세"):
            self.assertNotIn(bad, blob)

    def test_coverage_has_only_requests(self) -> None:
        cov = self.bundle.meta["user_review_coverage"]
        self.assertEqual({r["answered_by"] for r in cov}, {"employee_nda_review"})
        self.assertEqual(len(cov), 3)


if __name__ == "__main__":
    unittest.main()
