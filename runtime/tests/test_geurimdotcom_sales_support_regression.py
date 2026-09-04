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

    def test_explicit_user_answer_overrides_ai_inferred_value(self) -> None:
        # 2026-09-04 지시 — "explicit user answer > AI inference": 사용자가
        # 사전질문에 명시적으로 답변하면, AI/rule이 먼저 채워둔 값이라도
        # 그 답변으로 덮어써야 한다. 계약서만으로 확정할 수 없는 거래실질을
        # 사용자가 보충한 사실이므로 어떤 추정보다 신뢰도가 높다.
        fields = {"seller": "AI가 이미 판단한 값(오추정)"}
        apply_transaction_structure_answers(fields, {"Q-TXN-001-seller": "(주)일룸"})
        self.assertEqual(fields["seller"], "(주)일룸")


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


class GeurimdotcomUserAnswersAppliedEndToEndTest(unittest.TestCase):
    """사전질문 답변 미반영 근본 수정(2026-09-04 지시) — 사용자가 이미
    판매자=일룸/소유자=일룸/매출귀속=일룸/대금수령=일룸/대리점=판매지원
    이라고 답변했으면, 그 사실관계가 Contract Legal Map·소비자책임
    finding·self_check 전체에 동일하게 반영되어야 한다. "고객 계약 당사자:
    미확인"/"[실제 판매자/소유자]" 같은 결과가 나오면 회귀다."""

    _ANSWERS = {
        "Q-TXN-001-seller": "(주)일룸",
        "Q-TXN-002-owner": "(주)일룸 — 일룸이 상품을 매입한 후 재판매",
        "Q-TXN-003-revenue": "(주)일룸 매출로 인식",
        "Q-TXN-004-payment-collection": "매장 POS로 결제되나 위탁매매 구조로 (주)일룸 명의로 결제됨",
        "Q-TXN-008-relationship-type": "sales_support_service",
    }

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.review.clause_level import build_clause_level_result
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService

        text = FIXTURE_PATH.read_text(encoding="utf-8")
        loader = RuleLoader()
        loader.load()
        service = RuleQueryService(loader)
        cls.bundle = build_clause_level_result(
            service=service, entity="퍼시스", contract_type="영업지원 용역계약",
            text=text, filename="geurimdotcom.pdf",
            answers=dict(cls._ANSWERS), review_focus=None, law_service=None,
            ai_provider=None, ai_model=None, ai_timeout_sec=None, ai_max_tokens=None, ai_temperature=None,
        )

    def test_canonical_transaction_facts_resolved_to_illoom(self) -> None:
        facts = self.bundle.meta.get("canonical_transaction_facts") or {}
        self.assertIn("일룸", facts.get("seller") or "")
        self.assertIn("일룸", facts.get("owner_of_goods") or "")
        self.assertIn("일룸", facts.get("revenue_recipient") or "")
        self.assertIn("일룸", facts.get("payment_recipient") or "")
        self.assertTrue(facts.get("sales_support_provider"), "판매지원 역할 답변이 필드에 반영되어야 한다")
        self.assertTrue(facts.get("resale_structure"), "판매자=소유자=일룸이면 재판매 구조로 판정되어야 한다")

    def test_consumer_liability_finding_uses_resolved_seller_not_placeholder(self) -> None:
        crs = [cr for cr in self.bundle.clause_results if isinstance(cr, dict)]
        cr = next((c for c in crs if c.get("clause_id") == "clr_missing_consumer_product_liability_allocation"), None)
        self.assertIsNotNone(cr, "소비자책임 finding이 있어야 한다")
        rewrite = str(cr.get("suggested_rewrite") or "")
        self.assertNotIn("[실제 판매자/소유자]", rewrite)
        self.assertIn("일룸", rewrite)

    def test_self_check_not_blocked_by_unresolved_placeholder_gate(self) -> None:
        self_check = self.bundle.meta.get("self_check") or {}
        self.assertNotEqual(self_check.get("review_status"), "REVIEW_FAILED_USER_FACTS_NOT_APPLIED")
        resolved = set(self_check.get("resolved_mandatory_fact_fields") or [])
        self.assertEqual(resolved, {"seller", "owner_of_goods", "payment_recipient", "revenue_recipient"})
        self.assertTrue(self_check.get("user_facts_applied_ok"))
        self.assertEqual(self_check.get("unresolved_fact_placeholders"), [])


class TransactionFactsExplicitAnswerOverridesAiInferenceTest(unittest.TestCase):
    """우선순위(요청 3): explicit user answer > AI inference — 사용자가
    명확히 답한 사실을 rule/AI가 이미 채워둔 값이 덮어써서는 안 된다."""

    def test_user_answer_overrides_prefilled_wrong_value(self) -> None:
        fields = {"seller": "잘못 추정된 값", "owner_of_goods": None}
        apply_transaction_structure_answers(fields, {"Q-TXN-001-seller": "(주)일룸"})
        self.assertEqual(fields["seller"], "(주)일룸")


class QuestionSessionDocumentScopingTest(unittest.TestCase):
    """질문 answer state는 document-scoped(요청 7) — 새로 업로드한 문서의
    세션은 이전 세션의 답변을 자동 승계하지 않는다."""

    def test_new_session_starts_with_no_inherited_answers(self) -> None:
        from runtime.questions.storage import create_text_session, save_answers

        text_a = FIXTURE_PATH.read_text(encoding="utf-8")
        doc_a = create_text_session(entity="퍼시스", contract_type="", filename="a.txt", text=text_a, review_focus=None)
        save_answers(doc_a["session_id"], {"Q-TXN-001-seller": "(주)일룸"})

        doc_b = create_text_session(entity="퍼시스", contract_type="", filename="b.txt", text="전혀 다른 계약서 본문.", review_focus=None)
        self.assertNotEqual(doc_a["session_id"], doc_b["session_id"])
        self.assertFalse(doc_b.get("answers"), "새 문서 세션은 이전 세션의 답변을 승계하면 안 된다")


class GeurimdotcomGoldenAnswerApplicabilityTest(unittest.TestCase):
    """대리점법 적용성 판단 보정(2026-09-04 지시, 그림닷컴 Golden Answer) —
    기존 대리점(위탁판매)관계가 있고 이번 계약이 동일 매장·인력·POS 또는
    계약기간·해지 연동으로 그 관계와 경제적·운영상 연계되어 있으면,
    상대방이 자기 명의로 재판매하지 않는다는 이유만으로 대리점법 적용을
    "낮음"으로 방치하면 안 된다(적용 가능성 있음/MEDIUM 이상). 반대로
    하도급법은 단순 판매지원 업무만으로 MEDIUM 이상 자동 승격되면 안
    된다(낮음/LOW 확정). 조항번호·회사명·상품명을 하드코딩하지 않는
    구조 신호 기반 판단이 실제로 이 실사례에서 정답을 내는지 확인한다."""

    _ANSWERS = {
        "Q-TXN-001-seller": "(주)일룸",
        "Q-TXN-002-owner": "(주)일룸 - 일룸이 그림을 매입하여 재판매",
        "Q-TXN-003-revenue": "(주)일룸 매출로 인식",
        "Q-TXN-004-payment-collection": "매장 POS로 결제되나 위탁매매 구조로 (주)일룸 명의로 결제됨",
        "Q-TXN-008-relationship-type": "sales_support_service",
        "Q-TXN-009-existing-contract-link": "기존 위탁판매(운영) 계약과 계약기간·해지가 연동됨",
    }

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.review.clause_level import build_clause_level_result
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService

        text = FIXTURE_PATH.read_text(encoding="utf-8")
        loader = RuleLoader()
        loader.load()
        service = RuleQueryService(loader)
        cls.bundle = build_clause_level_result(
            service=service, entity="퍼시스", contract_type="영업지원 용역계약",
            text=text, filename="geurimdotcom.pdf",
            answers=dict(cls._ANSWERS), review_focus=None, law_service=None,
            ai_provider=None, ai_model=None, ai_timeout_sec=None, ai_max_tokens=None, ai_temperature=None,
        )
        cls.lar_by_statute = {
            str(r.get("statute")): r
            for r in (cls.bundle.meta.get("legal_applicability_review") or [])
            if isinstance(r, dict)
        }

    def test_dealer_act_applicability_not_low(self) -> None:
        dealer = self.lar_by_statute.get("대리점법")
        self.assertIsNotNone(dealer, "위탁판매/대리점 성격 계약에서 대리점법은 항상 검토 대상이어야 한다")
        self.assertNotIn(dealer.get("risk_level"), ("LOW",), "대리점법을 낮음으로 방치하면 안 된다")
        self.assertNotEqual(dealer.get("applicability"), "낮음")
        self.assertEqual(dealer.get("applicability"), "있음(추가 확인 필요)")
        self.assertEqual(dealer.get("risk_level"), "MEDIUM")

    def test_subcontract_act_capped_at_low(self) -> None:
        subcontract = self.lar_by_statute.get("하도급법")
        self.assertIsNotNone(subcontract)
        self.assertEqual(subcontract.get("risk_level"), "LOW", "단순 판매지원만으로 하도급법이 MEDIUM 이상으로 승격되면 안 된다")
        self.assertEqual(subcontract.get("applicability"), "낮음")

    def test_self_check_ok(self) -> None:
        self_check = self.bundle.meta.get("self_check") or {}
        self.assertEqual(self_check.get("review_status"), "OK")

    def test_system_guaranteed_statutes_do_not_trigger_missing_scope_failure(self) -> None:
        # 대리점법/하도급법을 시스템이 항상 검토 대상에 포함시키더라도,
        # 이는 사용자가 직접 요청한 것이 아니므로 AI 미가동 stub만 남아도
        # REVIEW_FAILED_USER_LEGAL_SCOPE_MISSING을 유발하면 안 된다.
        self.assertIsNone(self.bundle.meta.get("review_status"))
        self.assertNotIn("대리점법", self.bundle.meta.get("user_cited_statutes") or [])
        self.assertNotIn("하도급법", self.bundle.meta.get("user_cited_statutes") or [])

    def test_canonical_facts_still_resolved_to_illoom(self) -> None:
        facts = self.bundle.meta.get("canonical_transaction_facts") or {}
        self.assertIn("일룸", facts.get("seller") or "")
        self.assertIn("일룸", facts.get("owner_of_goods") or "")

    def test_unilateral_interpretation_finding_stays_high_not_capped_by_jurisdiction_calibration(self) -> None:
        # 관할 자체는 원칙적으로 HIGH 금지이지만, 이 계약의 핵심 문제는
        # 관할이 아니라 일방적 해석권이다 — clr_unilateral_interpretation_
        # and_forum은 is_common_legal_risk=True라 jurisdiction_risk_
        # calibration의 대상이 아니며, HIGH로 유지되어야 한다.
        crs = [cr for cr in self.bundle.clause_results if isinstance(cr, dict)]
        cr = next((c for c in crs if c.get("clause_id") == "clr_unilateral_interpretation_and_forum"), None)
        self.assertIsNotNone(cr)
        self.assertEqual(cr.get("risk_tier"), "HIGH")
        self.assertTrue(cr.get("is_common_legal_risk"))


if __name__ == "__main__":
    unittest.main()
