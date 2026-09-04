"""회귀검증(2026-09-04 지시 — 범용 사내변호사형 계약검토 엔진 전면 보정) —
판교점_그림닷컴_영업지원_용역계약서 실사례.

사용자 지적: 그림닷컴 판매지원 용역계약 검토가 HIGH 0 / MEDIUM 0으로
끝났고(실제로는 기존 위탁판매계약과의 경제적 연계, 판매수수료 환수,
소비자책임 불명확 등 실질적 리스크가 있었음), UI에는 이 계약과 무관한
svc_delay_response(납기 지연 대응 조항)가 노출됐다.

이를 그림닷컴 전용 rule이 아니라 범용 구조로 고쳤다 — 이 테스트는 그
구조가 실제로 동작하는지 확인한다:
  1. 판매/위탁판매/대리판매/중개 계약에서 거래구조 확인 질문이 최우선으로
     생성되는지(contract_class 분류 결과와 무관하게)
  2. 사용자가 실제로 답변한 사실관계(판매자=일룸, 소유권=일룸, POS는
     일룸 명의 위탁매매)가 Contract Legal Map 필드에 반영되는지
  3. 5개 신규 결정론적 Layer-1 rule이 실제 조항 텍스트에서 올바른
     severity로 탐지되는지
  4. svc_delay_response가 더 이상 오탐하지 않는지
  5. self_check 결과 HIGH+MEDIUM > 0이고 REVIEW_FAILED_LIKELY_FALSE_NEGATIVE가
     아닌지
"""
from __future__ import annotations

import unittest
from pathlib import Path

from runtime.questions.generator import generate_questions
from runtime.review.clause_extraction import extract_clauses
from runtime.review.clause_level import _SVC_CHECKLIST_ITEMS
from runtime.review.common_legal_risk import _apply_common_legal_risk_rules
from runtime.review.transaction_structure_answers import apply_transaction_structure_answers
from runtime.review.transaction_structure_signals import detect_sales_transaction_ambiguity

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "geurimdotcom_sales_support_agreement.txt"


class TransactionStructureAmbiguityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = FIXTURE_PATH.read_text(encoding="utf-8")

    def test_ambiguity_detected(self) -> None:
        self.assertTrue(detect_sales_transaction_ambiguity(self.text))

    def test_priority_questions_lead_regardless_of_review_focus_keywords(self) -> None:
        # 사용자가 review_focus에 "불이익" 계열 키워드를 먼저 썼더라도, 거래구조
        # 확인 질문이 여전히 최우선으로 노출돼야 한다(2026-09-04 지시 핵심).
        qs = generate_questions(
            "퍼시스", "영업지원 용역계약", detected_rule_ids=[], contract_text=self.text,
            review_focus="불이익 제공 관련 문제가 있는지 봐주세요", max_questions=7,
        )
        ids = [q.question_id for q in qs]
        self.assertTrue(ids[0].startswith("Q-TXN-"), f"거래구조 질문이 최우선이어야 한다: {ids}")
        self.assertIn("Q-TXN-001-seller", ids)
        self.assertIn("Q-TXN-002-owner", ids)

    def test_required_questions_survive_truncation(self) -> None:
        qs = generate_questions(
            "퍼시스", "영업지원 용역계약", detected_rule_ids=[], contract_text=self.text, max_questions=5,
        )
        required_ids = {q.question_id for q in qs if q.required}
        self.assertIn("Q-TXN-001-seller", required_ids)
        self.assertIn("Q-TXN-002-owner", required_ids)


class TransactionStructureAnswersTest(unittest.TestCase):
    def test_real_user_answers_populate_contract_legal_map_fields(self) -> None:
        fields = {
            "seller": None, "owner_of_goods": None, "payment_recipient": None,
            "sales_support_provider": None,
        }
        answers = {
            "Q-TXN-001-seller": "(주)일룸",
            "Q-TXN-002-owner": "(주)일룸 — 일룸이 그림을 매입하여 재판매",
            "Q-TXN-004-payment-collection": "데스커 판교점 POS로 결제되나 위탁매매 구조로 일룸 명의로 결제됨",
            "Q-TXN-008-relationship-type": "sales_support_service",
        }
        apply_transaction_structure_answers(fields, answers)
        self.assertEqual(fields["seller"], "(주)일룸")
        self.assertIn("일룸", fields["owner_of_goods"])
        self.assertIn("일룸", fields["payment_recipient"])
        self.assertEqual(fields["sales_support_provider"], "단순 판매지원 용역자(매매계약 당사자 아님)")

    def test_does_not_overwrite_existing_values(self) -> None:
        fields = {"seller": "AI가 이미 판단한 값"}
        apply_transaction_structure_answers(fields, {"Q-TXN-001-seller": "다른 값"})
        self.assertEqual(fields["seller"], "AI가 이미 판단한 값")


class SalesTransactionRulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        clauses, _ = extract_clauses(text)
        cls.clause_results: list[dict] = []
        _apply_common_legal_risk_rules(cls.clause_results, text, clauses)
        cls.by_id = {cr["clause_id"]: cr for cr in cls.clause_results}

    def test_linked_contract_dependency_detected_as_high(self) -> None:
        cr = self.by_id.get("clr_linked_contract_dependency_no_voluntary_clause")
        self.assertIsNotNone(cr, "기존 위탁판매계약과의 경제적 연계 + 자율성 조항 부재가 탐지되어야 한다")
        self.assertEqual(cr["risk_tier"], "HIGH")

    def test_fault_blind_commission_clawback_detected(self) -> None:
        cr = self.by_id.get("clr_fault_blind_commission_clawback")
        self.assertIsNotNone(cr, "귀책사유 구분 없는 판매취소 수수료 환수가 탐지되어야 한다")
        self.assertEqual(cr["risk_tier"], "MEDIUM")

    def test_unbounded_scope_expansion_detected(self) -> None:
        cr = self.by_id.get("clr_unbounded_scope_expansion")
        self.assertIsNotNone(cr, "\"기타 판매 관련 요청사항 지원\" 무제한 확장형 업무범위가 탐지되어야 한다")
        self.assertEqual(cr["risk_tier"], "MEDIUM")

    def test_unilateral_interpretation_and_forum_detected_as_high(self) -> None:
        cr = self.by_id.get("clr_unilateral_interpretation_and_forum")
        self.assertIsNotNone(cr, "일방적 해석권 + 일방 소재지 전속관할이 탐지되어야 한다")
        self.assertEqual(cr["risk_tier"], "HIGH")

    def test_missing_consumer_product_liability_detected(self) -> None:
        cr = self.by_id.get("clr_missing_consumer_product_liability_allocation")
        self.assertIsNotNone(cr, "소비자 대면 판매 구조인데 배송/하자/환불/진위/IP 책임 배분이 없다는 finding이 있어야 한다")
        self.assertEqual(cr["risk_tier"], "MEDIUM")

    def test_at_least_one_high_and_findings_are_not_zero(self) -> None:
        high_count = sum(1 for cr in self.clause_results if cr.get("risk_tier") == "HIGH")
        total = len(self.clause_results)
        self.assertGreaterEqual(high_count, 1)
        self.assertGreaterEqual(total, 3)


class SvcDelayResponseFalsePositiveTest(unittest.TestCase):
    def test_trigger_no_longer_matches_generic_contract_term_language(self) -> None:
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        item = next(i for i in _SVC_CHECKLIST_ITEMS if i["id"] == "svc_delay_response")
        self.assertFalse(
            item["trigger"].search(text),
            "\"2. 약정 기간\" 같은 일반 계약기간 문구만으로 트리거되면 안 된다",
        )

    def test_trigger_still_matches_genuine_delivery_deadline_language(self) -> None:
        # 정밀화된 trigger가 실제로 의도한 "산출물 납기" 리스크는 여전히 잡아야 한다.
        text = "수탁자는 납기일까지 결과물을 제출하여야 한다."
        item = next(i for i in _SVC_CHECKLIST_ITEMS if i["id"] == "svc_delay_response")
        self.assertTrue(item["trigger"].search(text))


class GeurimdotcomFullPipelineSelfCheckTest(unittest.TestCase):
    """AI 없이(ai_provider=None) 전체 파이프라인을 실제 픽스처로 돌려
    HIGH/MEDIUM이 0건이 아니고 REVIEW_FAILED_LIKELY_FALSE_NEGATIVE가
    더 이상 아닌지 end-to-end로 확인한다."""

    def test_full_pipeline_no_longer_false_negative(self) -> None:
        from runtime.review.clause_level import build_clause_level_result
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService

        text = FIXTURE_PATH.read_text(encoding="utf-8")
        loader = RuleLoader()
        loader.load()
        service = RuleQueryService(loader)
        bundle = build_clause_level_result(
            service=service, entity="퍼시스", contract_type="영업지원 용역계약",
            text=text, filename="geurimdotcom.pdf",
            answers=None, review_focus=None, law_service=None,
            ai_provider=None, ai_model=None, ai_timeout_sec=None, ai_max_tokens=None, ai_temperature=None,
        )
        final_findings = bundle.meta.get("final_findings", {})
        high_count = int(final_findings.get("high_count") or 0)
        medium_count = int(final_findings.get("medium_count") or 0)
        self.assertGreater(high_count + medium_count, 0, "실제 리스크가 있는 계약인데 HIGH+MEDIUM이 0건이면 안 된다")
        # 회귀 방지 — 신규 5개 rule이 전부 hallucination_guard의 3개 지점
        # (self_check 백스톱/clause_level 조기 가드/output_filter Gate 4)을
        # 무사히 통과해 정확한 개수로 살아남는지 정밀하게 확인한다.
        self.assertEqual(high_count, 2, "clr_linked_contract_dependency + clr_unilateral_interpretation_and_forum 2건")
        self.assertEqual(medium_count, 3, "clr_fault_blind_commission_clawback + clr_unbounded_scope_expansion + clr_missing_consumer_product_liability 3건")
        self_check = bundle.meta.get("self_check") or {}
        self.assertNotEqual(self_check.get("review_status"), "REVIEW_FAILED_LIKELY_FALSE_NEGATIVE")
        self.assertEqual(self_check.get("review_status"), "OK")
        # 내 5개 신규 rule 자신은 scope_violations_stripped에 하나도 나타나면
        # 안 된다 — 나타나는 다른 항목(예: 이 계약과 무관한 checklist 항목의
        # 별개 dev-phrase 오탐)은 이 회귀 테스트의 범위가 아니다.
        _mine = {
            "clr_linked_contract_dependency_no_voluntary_clause", "clr_fault_blind_commission_clawback",
            "clr_unbounded_scope_expansion", "clr_unilateral_interpretation_and_forum",
            "clr_missing_consumer_product_liability_allocation",
        }
        _stripped_ids = {str(v.get("clause_id")) for v in (self_check.get("scope_violations_stripped") or [])}
        self.assertEqual(_stripped_ids & _mine, set(), f"신규 rule이 hallucination guard에 걸리면 안 된다: {_stripped_ids & _mine}")


class CommonLegalRiskHallucinationGuardExemptionTest(unittest.TestCase):
    """실제 진단 중 발견한 버그(2026-09-04) — common_legal_risk.py의 결정론적
    rule이 원문에 실제로 등장하는 "위탁판매"/"용역수수료" 같은 어휘를,
    contract_type_code 오분류(예: advisory) 하나만으로 hallucination_guard의
    "wrong context" 오탐으로 걸러내던 사고. 3개 지점(output_filter.py의
    is_valid_issue Gate 4가 최종 발견 지점) 전부에서 is_common_legal_risk=True
    finding은 예외 처리되어야 한다."""

    def test_is_valid_issue_exempts_common_legal_risk_from_wrong_context_guard(self) -> None:
        from runtime.review.output_filter import ReviewIssue, is_valid_issue
        issue = ReviewIssue(
            clause_id="clr_test_rule",
            clause_title="테스트",
            severity="MEDIUM",
            approval_required=False,
            issue_title="테스트 이슈",
            original_text="원문",
            problem="위탁판매 관련 문제",
            legal_business_reason="용역수수료 산정 관련 실무상 이유",
            proposed_revision="위탁판매 및 용역수수료 정산 방식을 명확히 한다.",
            negotiation_position="",
            confidence=0.8,
            is_common_legal_risk=True,
        )
        # contract_type_code가 advisory 계열이 아니어도(예: 오분류) 통과해야 한다.
        self.assertTrue(is_valid_issue(issue, contract_type_code="store_operation_outsourcing"))

    def test_non_common_legal_risk_still_guarded(self) -> None:
        # is_common_legal_risk=False(일반 AI/체크리스트 finding)는 기존처럼
        # 계약유형별 금지문구 가드가 그대로 적용되어야 한다 — 예외를 너무
        # 넓게 풀어서 원래 가드 목적(잘못된 계약유형 boilerplate 차단)을
        # 무력화하면 안 된다.
        from runtime.review.output_filter import ReviewIssue, is_valid_issue
        issue = ReviewIssue(
            clause_id="ai_generic_finding",
            clause_title="테스트",
            severity="MEDIUM",
            approval_required=False,
            issue_title="테스트 이슈",
            original_text="원문",
            problem="문제",
            legal_business_reason="사유",
            proposed_revision="렌탈 물류시설 관련 조항을 수정한다.",
            negotiation_position="",
            confidence=0.8,
            is_common_legal_risk=False,
        )
        self.assertFalse(is_valid_issue(issue, contract_type_code="store_operation_outsourcing"))


class MandatoryIssuesNeverDowngradesTest(unittest.TestCase):
    """실제 진단 중 발견한 버그(2026-09-04) — inject_mandatory_issues()의
    "기존 clause_result 업그레이드" 로직이 이름과 달리 severity를 낮추는
    방향으로도 덮어썼다. clr_unilateral_interpretation_and_forum(HIGH,
    "해석상 이의...관할 법원" 원문 인용)의 원문 발췌가 우연히 어떤 MI-*
    필수이슈의 트리거 패턴과 겹쳐, 아무 관련 없는 MEDIUM으로 조용히
    강등되는 사고가 재현됐다 — 재발 방지 테스트."""

    def test_does_not_downgrade_higher_severity_common_legal_risk_finding(self) -> None:
        from runtime.review.mandatory_issues import inject_mandatory_issues
        # 그림닷컴 실사례의 실제 원문 인용을 그대로 사용해 재현한다.
        original_text = (
            "본 약정서 문구 해석상 이의가 발생했을 때는 \"갑\"의 해석에 따르며 소송은 \"갑\"의 본점 소재지 관할\n"
            "법원으로 한다."
        )
        clause_results = [{
            "clause_id": "clr_unilateral_interpretation_and_forum",
            "original_text": original_text,
            "risk_tier": "HIGH",
            "severity": "HIGH",
            "is_common_legal_risk": True,
            "dedup_suppressed": False,
            "keep_as_is": False,
        }]
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        result = inject_mandatory_issues(
            full_text=text, clause_results=clause_results, contract_type_code="store_operation_outsourcing",
        )
        mine = next(cr for cr in result if cr.get("clause_id") == "clr_unilateral_interpretation_and_forum")
        self.assertEqual(mine["risk_tier"], "HIGH", "is_common_legal_risk finding은 mandatory issue 텍스트 매치로 강등되면 안 된다")
        self.assertEqual(mine["severity"], "HIGH")

    def test_never_downgrades_even_non_common_legal_risk_findings(self) -> None:
        # is_common_legal_risk가 아니어도(일반 AI/rule-engine finding) "업그레이드"
        # 로직이 severity를 낮추는 방향으로 동작하면 안 된다 — 이름 그대로
        # upgrade만 허용한다.
        from runtime.review.mandatory_issues import inject_mandatory_issues
        clause_results = [{
            "clause_id": "some_other_finding",
            "original_text": "위탁판매 대금수금의 책임이 대리점에게 있다.",
            "risk_tier": "HIGH",
            "severity": "HIGH",
            "is_common_legal_risk": False,
            "dedup_suppressed": False,
            "keep_as_is": False,
        }]
        text = "본 계약은 위탁판매 계약이며 용역수수료를 지급한다. 대금수금의 책임이 대리점에게 있다."
        result = inject_mandatory_issues(
            full_text=text, clause_results=clause_results, contract_type_code="consignment_sales_agency",
        )
        mine = next(cr for cr in result if cr.get("clause_id") == "some_other_finding")
        self.assertNotEqual(mine["risk_tier"], "LOW")


if __name__ == "__main__":
    unittest.main()
