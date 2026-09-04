"""회귀검증(2026-09-02 지시 — 범용 사내변호사형 검토 엔진 고도화) — KOTRA
3자 컨설팅계약(Fursys/HRology/KOTRA) 실사례.

사용자 지적: Article 3.4의 일 10% 지체상금(cap 없음)을 놓침, Article 4.3의
Company의 Consultant 환급채무 보증을 충분히 강하게 평가하지 못함, Article
1.2의 KOTRA 광범위 면책 구조를 놓침, Article 6의 무제한 indemnity+attorney's
fees를 놓침, Article 8을 보다가 "준거법/관할 필요"를 HIGH로 잡았는데 바로
Article 9에 이미 준거법·중재가 있었음, California 현지 HR 서비스인데 한국
파견법/개인정보보호법을 자동으로 핵심 적용법률로 과대평가.

이를 KOTRA 전용 rule이 아니라 범용 구조로 고쳤다 — 이 테스트는 그 구조가
실제로 동작하는지, 문언 하드코딩이 아니라 계약 구조(legal effect/조항
경계/전체문서 재검색)로 확인한다:
  1. 영문 계약도 "Article N.M" 단위로 분리되는지(세그멘테이션 일반화)
  2. 금전 리스크 계산기가 영문 "N% ... per/each day" 패턴도 계산하는지
  3. 제3자 채무보증/상대방 광범위 자기책임면제/무제한 상호 indemnity가
     조항번호가 아니라 legal effect로 탐지되는지
  4. GLOBAL_CROSS_CLAUSE_VALIDATION이 이미 해결된 조항을 "부재"로 다시
     지적하는 finding을 억제하는지
  5. Contract Legal Map에 Transaction Map 필드가 포함됐는지

실제 AI 판단 품질(캘리포니아 현지 고용법 우선 판단 등, review_focus 조건부)은
이 세션에서 실제 AI(gpt-4.1)로 직접 검증했다(문서 참고) — 여기서는 AI 없이도
항상 동작해야 하는 결정론적 구조만 검증한다.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from runtime.review.clause_extraction import extract_clauses
from runtime.review.common_legal_risk import _apply_common_legal_risk_rules
from runtime.review.contract_legal_map import UNIVERSAL_FIELDS
from runtime.review.global_cross_clause_validation import apply_global_cross_clause_validation
from runtime.review.severity_reclassifier import demote_adequate_governing_law_dispute_clause

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "kotra_consulting_service_agreement.txt"


class EnglishSubParagraphSegmentationTest(unittest.TestCase):
    """영문 계약도 "Article N" 전체가 아니라 "N.M" 단락 단위로 분리되어야
    한다 — 그렇지 않으면 Article 3.4(지체상금)가 3.1~3.3과 한 덩어리로
    묶여 AI/규칙 엔진이 개별 리스크를 놓치기 쉽다(실사례로 확인)."""

    @classmethod
    def setUpClass(cls) -> None:
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        cls.chunks, cls.report = extract_clauses(text)
        cls.by_id = {c.clause_id: c for c in cls.chunks}

    def test_article_3_split_into_four_paragraphs(self) -> None:
        for pn in ("1", "2", "3", "4"):
            self.assertIn(f"EN-3.{pn}", self.by_id, f"Article 3.{pn}이 별도 세그먼트여야 한다")

    def test_article_3_4_isolated_and_contains_penalty_language(self) -> None:
        cr = self.by_id.get("EN-3.4")
        self.assertIsNotNone(cr)
        self.assertIn("10 %", cr.text)
        self.assertIn("each day of delay", cr.text)
        self.assertNotIn("necessary documents", cr.text, "3.3의 내용이 섞이면 안 된다")

    def test_article_4_split_into_four_paragraphs(self) -> None:
        for pn in ("1", "2", "3", "4"):
            self.assertIn(f"EN-4.{pn}", self.by_id, f"Article 4.{pn}이 별도 세그먼트여야 한다")

    def test_article_4_3_isolated_guarantee_clause(self) -> None:
        cr = self.by_id.get("EN-4.3")
        self.assertIsNotNone(cr)
        self.assertIn("guarantee", cr.text.lower())
        self.assertNotIn("ACH Transfer", cr.text, "4.4의 계좌정보가 섞이면 안 된다")

    def test_article_number_is_bare_digit_not_embedded_label(self) -> None:
        cr = self.by_id.get("EN-3.4")
        self.assertEqual(cr.article_number, "3.4")
        self.assertEqual(cr.display_path, "Article 3.4")


class KotraMonetaryRiskAndLegalEffectRulesTest(unittest.TestCase):
    """일 10% 지체상금·제3자 채무보증·상대방 광범위 자기책임면제·무제한
    상호 indemnity를 조항번호가 아니라 legal effect/문장구조로 탐지하는
    신규 Layer-1 규칙(영문 대응 포함)이 실제로 정확한 조항에 anchoring
    되는지 AI 없이(규칙 엔진만으로) 확인한다."""

    @classmethod
    def setUpClass(cls) -> None:
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        clauses, _ = extract_clauses(text)
        cls.clause_results: list[dict] = []
        _apply_common_legal_risk_rules(cls.clause_results, text, clauses)
        cls.by_id = {cr["clause_id"]: cr for cr in cls.clause_results}

    def test_late_penalty_rate_uncapped_on_article_3_4(self) -> None:
        cr = self.by_id.get("clr_late_penalty_rate_uncapped")
        self.assertIsNotNone(cr, "Article 3.4의 일 10% 지체상금(cap 없음)이 탐지되어야 한다")
        self.assertEqual(cr["display_path"], "Article 3.4")
        self.assertEqual(cr["risk_tier"], "HIGH")
        # 10%/day -> 10일 100%, 30일 300% 계산이 legal_business_reason에 반영돼야 한다
        self.assertIn("100", cr["legal_business_reason"])
        self.assertIn("300", cr["legal_business_reason"])
        # 2026-09-03 지시 회귀조건: cap만 추가하고 rate를 그대로 두는 비논리적
        # 수정안 금지 — 수정안(suggested_rewrite)에 "인하"(rate 조정)와
        # 상한(cap) 설정이 모두 포함되어야 한다.
        self.assertIn("인하", cr["suggested_rewrite"])
        self.assertTrue(any(k in cr["suggested_rewrite"] for k in ("상한", "한도", "초과할 수 없다")))
        # 2026-09-03 지시(요구 5) — "보다 낮은 요율로" 같은 추상적 표현이 아니라
        # 실제 협상 가능한 구체적 숫자(1일 0.1%)가 최선안에 포함되어야 한다.
        self.assertIn("0.1%", cr["suggested_rewrite"])
        self.assertNotIn("보다 낮은 요율로", cr["suggested_rewrite"])
        # rate+cap을 함께 판단하는 협상 사다리(negotiation_ladder)가 있어야 한다.
        ladder = cr.get("negotiation_ladder")
        self.assertTrue(ladder, "negotiation_ladder가 있어야 한다")
        self.assertIn("최선안", [t["label"] for t in ladder])

    def test_third_party_debt_guarantee_on_article_4_3(self) -> None:
        cr = self.by_id.get("clr_third_party_debt_guarantee")
        self.assertIsNotNone(cr, "Article 4.3의 Company의 Consultant 환급채무 보증이 탐지되어야 한다")
        self.assertEqual(cr["display_path"], "Article 4.3")
        self.assertEqual(cr["risk_tier"], "HIGH")
        self.assertEqual(cr.get("original_effect_tags"), ["third_party_debt_guarantee"])
        # 2026-09-03 지시: 협상 우선순위는 삭제가 1순위여야 한다.
        ladder = cr.get("negotiation_ladder")
        self.assertTrue(ladder, "negotiation_ladder가 있어야 한다")
        self.assertEqual(ladder[0]["priority"], 1)
        self.assertIn("삭제", ladder[0]["label"] + ladder[0]["action"])

    def test_conditional_funding_structure_unclear_detected(self) -> None:
        # Article 1.2(Hidden Champion Program 지원자격 유지조건)는 있으나
        # 중도탈락·clawback/환수·귀책사유별 반환주체·정책변경 대응이 계약상
        # 다뤄지지 않는다 — MEDIUM finding + additional_facts_needed로 남아야 한다.
        cr = self.by_id.get("clr_conditional_funding_unclear")
        self.assertIsNotNone(cr, "정부지원(KOTRA Hidden Champion Program) 조건부 자금 구조 불명확이 탐지되어야 한다")
        self.assertEqual(cr["risk_tier"], "MEDIUM")
        self.assertTrue(cr.get("additional_facts_needed"))

    def test_counterparty_broad_self_liability_shield_on_article_1_2(self) -> None:
        cr = self.by_id.get("clr_counterparty_broad_self_liability_shield")
        self.assertIsNotNone(cr, "Article 1.2의 KOTRA 광범위 자기책임면제+포괄면책이 탐지되어야 한다")
        self.assertEqual(cr["display_path"], "Article 1.2")
        self.assertEqual(cr["risk_tier"], "HIGH")

    def test_uncapped_mutual_indemnity_on_article_6(self) -> None:
        cr = self.by_id.get("clr_uncapped_mutual_indemnity_with_attorney_fees")
        self.assertIsNotNone(cr, "Article 6의 무제한 상호 indemnity+attorney's fees가 탐지되어야 한다")
        self.assertEqual(cr["display_path"], "Article 6")
        self.assertEqual(cr["risk_tier"], "MEDIUM")


class GlobalCrossClauseValidationTest(unittest.TestCase):
    """조항 하나만 보고 만들어진 "준거법/분쟁해결 조항이 없다"는 finding은
    Article 9에 이미 준거법·중재가 있으면 억제되어야 한다 — 실사례에서
    Article 8을 검토하며 이 오탐이 HIGH로 잡혔던 사고를 재현·검증."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = FIXTURE_PATH.read_text(encoding="utf-8")

    def test_missing_governing_law_claim_suppressed_when_article_9_has_it(self) -> None:
        cr = {
            "clause_id": "ai-fabricated-1",
            "clause_title": "Article 8 [준거법/관할 필요]",
            "rewrite_reason": "본 조항에 준거법과 분쟁해결(관할 법원 또는 중재) 조항이 명시되어 있지 않다.",
            "legal_business_reason": "",
            "dedup_suppressed": False,
        }
        clause_results = [cr]
        apply_global_cross_clause_validation(clause_results, self.text)
        self.assertTrue(cr["dedup_suppressed"])
        self.assertEqual(cr.get("global_cross_clause_suppressed_topic"), "governing_law")

    def test_recommendation_style_claim_also_suppressed(self) -> None:
        # 2026-09-03 지시(Article 8.2류 잔존 오탐) — "없다"고 단정하지 않고
        # 권고형으로 표현해도("준거법 조항을 추가할 것을 권고한다") 실질은
        # 같은 부재 주장이므로 억제되어야 한다.
        cr = {
            "clause_id": "ai-fabricated-2",
            "clause_title": "Article 8 [준거법/분쟁해결 보완]",
            "rewrite_reason": "본 조항에 준거법 조항을 추가할 것을 권고한다.",
            "legal_business_reason": "",
            "dedup_suppressed": False,
        }
        clause_results = [cr]
        apply_global_cross_clause_validation(clause_results, self.text)
        self.assertTrue(cr["dedup_suppressed"])

    def test_unrelated_finding_not_suppressed(self) -> None:
        cr = {
            "clause_id": "clr_late_penalty_rate_uncapped",
            "clause_title": "Article 3.4 [지체상금율 미계산·상한 부재]",
            "rewrite_reason": "지체일수 당 10%의 지체상금에 누계 상한이 없다.",
            "legal_business_reason": "10일 지연 시 100%에 달한다.",
            "dedup_suppressed": False,
        }
        clause_results = [cr]
        apply_global_cross_clause_validation(clause_results, self.text)
        self.assertFalse(cr["dedup_suppressed"], "무관한(cap 관련) finding까지 억제되면 안 된다")

    def test_claim_without_absence_marker_not_suppressed(self) -> None:
        # "준거법"을 언급하지만 "없다/미특정"류 부재 주장이 아닌 경우(예: 준거법이
        # 불리하다는 지적)까지 억제하면 안 된다.
        cr = {
            "clause_id": "ai-2",
            "clause_title": "Article 9 [준거법 불리]",
            "rewrite_reason": "준거법이 상대방 소재국법으로 지정되어 우리 회사에 불리하다.",
            "legal_business_reason": "",
            "dedup_suppressed": False,
        }
        clause_results = [cr]
        apply_global_cross_clause_validation(clause_results, self.text)
        self.assertFalse(cr["dedup_suppressed"])


class AdequateGoverningLawDisputeClauseDowngradeTest(unittest.TestCase):
    """Article 9.2(준거법: 대한민국법, 분쟁해결: 서울 중재)는 그 자체로 이미
    완결된 조항이다 — "다른 조항에 있다"가 아니라 "이 조항 자체가 이미
    충분하다"는 판단축(demote_adequate_governing_law_dispute_clause)이
    HIGH로 과대평가된 AI finding을 LOW로 강등하는지 확인한다."""

    def test_article_9_2_style_finding_demoted_to_low(self) -> None:
        # Article 9.1(준거법) + 9.2(중재) 원문을 모두 인용한 것으로 가정한
        # AI 생성 finding — absence claim은 없고 스타일 비판만 있다고 가정.
        article_9_text = (
            "This Agreement shall be governed and interpreted by the laws of "
            "[Republic of Korea]. In case of any dispute arising out of, or in "
            "connection with this Agreement, the parties shall take all "
            "necessary actions to settle amicably by negotiations between the "
            "parties. If a dispute is not settled amicably, it shall be "
            "finally settled by arbitration in [Seoul], in accordance with "
            "and governed by the laws of [Republic of Korea]."
        )
        new_sev, demoted = demote_adequate_governing_law_dispute_clause(
            severity="HIGH",
            clause_text=article_9_text,
            clause_title="Article 9.2 [준거법/분쟁해결 보완 필요]",
            rewrite_reason="분쟁해결 절차를 보다 명확히 정리할 필요가 있다.",
            legal_business_reason="",
        )
        self.assertTrue(demoted)
        self.assertEqual(new_sev, "LOW")

    def test_genuine_absence_claim_not_demoted(self) -> None:
        # 실제로 준거법/분쟁해결이 없다고 주장하는 finding은(원문에도 실제로
        # 없다면) 강등 대상이 아니다 — absence claim이 있으면 이 함수가 아니라
        # GLOBAL_CROSS_CLAUSE_VALIDATION의 영역이다.
        new_sev, demoted = demote_adequate_governing_law_dispute_clause(
            severity="HIGH",
            clause_text="이 조항에는 아무 내용도 없다.",
            clause_title="Article 8 [준거법/관할 필요]",
            rewrite_reason="본 조항에 준거법과 분쟁해결 조항이 명시되어 있지 않다.",
            legal_business_reason="",
        )
        self.assertFalse(demoted)
        self.assertEqual(new_sev, "HIGH")


class TransactionMapFieldsTest(unittest.TestCase):
    """Contract Legal Map(Layer 0)에 3자 이상 계약·조건부 자금·보증구조를
    구조화하는 Transaction Map 필드가 포함되어, 처음 보는 계약유형에서도
    개별 조항 검토 전에 "돈이 어디서 흐르고 누가 누구의 채무를 보증하는지"를
    먼저 파악하도록 요청하는지 확인한다."""

    def test_transaction_map_fields_present_in_universal_fields(self) -> None:
        for field in (
            "economic_beneficiary",
            "third_party_payer_or_guarantor",
            "conditional_funding_structure",
            "advance_payment_exists",
            "refund_or_clawback_obligation_holder",
            "guarantee_structure",
            "failure_loss_allocation",
            "termination_settlement_structure",
            "party_rights_obligations_matrix",
        ):
            self.assertIn(field, UNIVERSAL_FIELDS)


class FindingIdStabilityTest(unittest.TestCase):
    """UI와 DOCX가 동일 finding을 동일 ID로 가리키기 위한 안정적 finding_id
    (2026-09-03 지시, 요구 2) — 내용 기반 해시이므로 같은 입력에 대해
    여러 번 호출해도 값이 바뀌지 않아야 한다."""

    @classmethod
    def setUpClass(cls) -> None:
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        clauses, _ = extract_clauses(text)
        cls.clause_results: list[dict] = []
        _apply_common_legal_risk_rules(cls.clause_results, text, clauses)

    def test_every_finding_gets_a_stable_finding_id(self) -> None:
        from runtime.review.output_finalize import ensure_finding_ids
        ensure_finding_ids(self.clause_results)
        ids_first_pass = [cr.get("finding_id") for cr in self.clause_results]
        self.assertTrue(all(ids_first_pass), "모든 finding에 finding_id가 부여되어야 한다")
        self.assertEqual(len(ids_first_pass), len(set(ids_first_pass)), "finding_id는 서로 달라야 한다")
        # 이미 부여된 finding_id는 재호출해도 바뀌지 않는다(멱등).
        ensure_finding_ids(self.clause_results)
        ids_second_pass = [cr.get("finding_id") for cr in self.clause_results]
        self.assertEqual(ids_first_pass, ids_second_pass)


class MandatoryIssuesIdempotencyTest(unittest.TestCase):
    """UI 저장 시점과 DOCX 다운로드 시점 양쪽에서 inject_mandatory_issues가
    호출될 수 있으므로(요구 2), 같은 clause_results에 두 번 연속 호출해도
    중복 삽입되지 않아야 한다."""

    def test_calling_twice_does_not_duplicate(self) -> None:
        from runtime.review.mandatory_issues import inject_mandatory_issues
        text = "본 계약은 위탁판매 계약이며 용역수수료를 지급한다."
        first = inject_mandatory_issues(
            full_text=text, clause_results=[], contract_type_code="consignment_sales_agency",
        )
        second = inject_mandatory_issues(
            full_text=text, clause_results=list(first), contract_type_code="consignment_sales_agency",
        )
        self.assertEqual(len(first), len(second), "두 번째 호출이 항목을 중복 삽입하면 안 된다")
        mandatory_ids_first = sorted(str(cr.get("clause_id")) for cr in first if cr.get("is_mandatory"))
        mandatory_ids_second = sorted(str(cr.get("clause_id")) for cr in second if cr.get("is_mandatory"))
        self.assertEqual(mandatory_ids_first, mandatory_ids_second)


class IndemnifyingPartyUnclearTest(unittest.TestCase):
    """Article 1.2처럼 "shall be indemnified"만 있고 누가 indemnify하는지
    명시되지 않은 경우, Company가 부담한다고 단정하지 말고 그 불명확함
    자체를 finding으로 만들어야 한다(2026-09-03 지시, 요구 4)."""

    def test_passive_indemnify_without_named_obligor_flagged(self) -> None:
        from runtime.review.clause_extraction import extract_clauses as _extract
        text = (
            "Article 99 Miscellaneous Indemnification\n"
            "The Contractor shall be indemnified against any and all claims, "
            "damages, and expenses arising from the performance of this Agreement."
        )
        clauses, _ = _extract(text)
        results: list[dict] = []
        _apply_common_legal_risk_rules(results, text, clauses)
        cr = next((r for r in results if r.get("clause_id") == "clr_indemnifying_party_unclear"), None)
        self.assertIsNotNone(cr, "면책 의무 주체 불명확이 탐지되어야 한다")
        self.assertEqual(cr["risk_tier"], "MEDIUM")
        self.assertIn("고의 또는 과실", cr["suggested_rewrite"])

    def test_already_covered_by_specific_pattern_not_duplicated(self) -> None:
        # KOTRA Article 1.2는 이미 clr_counterparty_broad_self_liability_shield로
        # 잡히므로, 별도로 clr_indemnifying_party_unclear가 중복 생성되면 안 된다.
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        clauses, _ = extract_clauses(text)
        results: list[dict] = []
        _apply_common_legal_risk_rules(results, text, clauses)
        self.assertIsNone(
            next((r for r in results if r.get("clause_id") == "clr_indemnifying_party_unclear"), None),
            "이미 더 구체적인 패턴이 다루는 조항에 중복 finding이 생기면 안 된다",
        )


class SafeTruncateWordBoundaryTest(unittest.TestCase):
    """단어 중간 절단("Article" -> "icle", "Payment" -> "ayment") 방지
    (2026-09-03 지시, 요구 6)."""

    def test_does_not_cut_mid_word(self) -> None:
        from runtime.review.language_quality_gate import safe_truncate
        text = "KOTRA shall pay Consultant a total of USD $33,750 in accordance with the schedule."
        truncated = safe_truncate(text, 40)
        # "USD"/"$33,750" 같은 단어가 중간에서 잘리면 안 된다 — 잘린 결과의
        # 마지막 "단어"는 원문에 실제로 존재하는 완전한 토큰이어야 한다.
        last_word = truncated.rstrip("…").split()[-1]
        self.assertIn(last_word, text.split())

    def test_short_text_returned_unchanged(self) -> None:
        from runtime.review.language_quality_gate import safe_truncate
        self.assertEqual(safe_truncate("짧은 문장.", 100), "짧은 문장.")


class SeniorCounselExposureAndPriorityTest(unittest.TestCase):
    """Senior In-house Counsel 판단 레이어(2026-09-04 지시) — legal_risk와
    negotiation_priority를 분리해, KOTRA 계약의 실제 우선순위가 요구사항
    12번의 수용 기준대로 나오는지 확인한다:
      - Article 3.4(Consultant→KOTRA 지체상금): 우리 회사 직접 리스크가
        아니므로 MUST_FIX가 아니어야 한다.
      - Article 4.3(Company 보증책임): 최우선 MUST_FIX여야 한다.
      - Article 6(무제한 상호 indemnity): NEGOTIATE_IF_POSSIBLE + 3단계 사다리.
      - Article 3.4는 Article 4.3(보증조항)의 clause_id에 의존한다는 것이
        negotiation_priority_depends_on에 표시되어야 한다("4.3이 해결되면
        3.4의 협상우선순위를 낮출 수 있어야 한다"는 지시 반영).
    """

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.review.counterparty_role import classify_counterparty_role
        from runtime.review.exposure_classification import classify_exposure
        from runtime.review.negotiation_action import classify_negotiation_action

        text = FIXTURE_PATH.read_text(encoding="utf-8")
        clauses, _ = extract_clauses(text)
        cls.results: list[dict] = []
        _apply_common_legal_risk_rules(
            cls.results, text, clauses,
            our_party_aliases=["Fursys, Inc", "Company"],
        )
        role = classify_counterparty_role(text)
        cls.counterparty_role = role
        aliases = ["Fursys, Inc", "Company"]
        for cr in cls.results:
            if not cr.get("exposure_category"):
                cr["exposure_category"] = classify_exposure(str(cr.get("original_text") or ""), aliases)
            cr.update(classify_negotiation_action(cr, counterparty_role=role))

        # clause_level.py의 risk-cascade 연동(Phase 7)과 동일한 로직 —
        # 지체상금 finding이 보증 finding에 의존하도록 표시한다.
        guarantee = next((r for r in cls.results if r.get("clause_id") == "clr_third_party_debt_guarantee"), None)
        if guarantee is not None:
            for cr in cls.results:
                if cr.get("clause_id") != "clr_late_penalty_rate_uncapped":
                    continue
                if cr.get("business_exposure") == "counterparty_only" and cr.get("negotiation_priority") == "ACCEPT":
                    cr["negotiation_priority"] = "NEGOTIATE_IF_POSSIBLE(조건부)"
                    cr["negotiation_priority_depends_on"] = str(guarantee.get("clause_id") or "")
        cls.guarantee = guarantee
        cls.by_id = {cr["clause_id"]: cr for cr in cls.results}

    def test_counterparty_role_is_government_or_funding_agency(self) -> None:
        self.assertEqual(self.counterparty_role, "government_or_funding_agency")

    def test_article_3_4_exposure_is_counterparty_only(self) -> None:
        cr = self.by_id.get("clr_late_penalty_rate_uncapped")
        self.assertIsNotNone(cr)
        self.assertEqual(cr.get("business_exposure"), "counterparty_only")

    def test_article_3_4_not_must_fix(self) -> None:
        cr = self.by_id.get("clr_late_penalty_rate_uncapped")
        self.assertIsNotNone(cr)
        self.assertNotEqual(cr.get("negotiation_priority"), "MUST_FIX")

    def test_article_3_4_depends_on_article_4_3_guarantee(self) -> None:
        cr = self.by_id.get("clr_late_penalty_rate_uncapped")
        self.assertIsNotNone(self.guarantee, "Article 4.3 보증 finding이 있어야 이 연동을 검증할 수 있다")
        self.assertEqual(cr.get("negotiation_priority_depends_on"), self.guarantee.get("clause_id"))

    def test_article_4_3_guarantee_is_must_fix(self) -> None:
        self.assertIsNotNone(self.guarantee)
        self.assertEqual(self.guarantee.get("business_exposure"), "direct")
        self.assertEqual(self.guarantee.get("negotiation_priority"), "MUST_FIX")

    def test_article_6_mutual_indemnity_negotiate_if_possible_with_ladder(self) -> None:
        cr = self.by_id.get("clr_uncapped_mutual_indemnity_with_attorney_fees")
        self.assertIsNotNone(cr)
        self.assertEqual(cr.get("negotiation_priority"), "NEGOTIATE_IF_POSSIBLE")
        ladder = cr.get("negotiation_ladder")
        self.assertIsInstance(ladder, list)
        self.assertEqual(len(ladder), 3)

    def test_article_1_2_indemnifying_party_unclear_not_must_fix(self) -> None:
        cr = self.by_id.get("clr_indemnifying_party_unclear") or self.by_id.get("clr_counterparty_broad_self_liability_shield")
        self.assertIsNotNone(cr)
        self.assertNotEqual(cr.get("negotiation_priority"), "MUST_FIX")


class ForceMajeureSemanticMismatchTest(unittest.TestCase):
    """Force Majeure 조항에 SLA/지체상금류 문구를 섞으면 안 된다
    (2026-09-04 지시, 요구 6) — legal_effect_taxonomy에 force_majeure 태그가
    없어 effects_overlap()이 "원문 태그 없음=무조건 통과"로 잘못 판정하던
    구멍을 막았는지 확인한다."""

    def test_force_majeure_tag_detected(self) -> None:
        from runtime.review.legal_effect_taxonomy import infer_legal_effects
        text = "Article 7 Force Majeure. Neither party shall be liable for delay caused by force majeure events."
        self.assertIn("force_majeure", infer_legal_effects(text))

    def test_force_majeure_and_sla_penalty_do_not_overlap(self) -> None:
        from runtime.review.legal_effect_taxonomy import infer_legal_effects, effects_overlap
        original = "Article 7 Force Majeure. Neither party shall be liable for delay caused by force majeure events."
        contaminated_rewrite = "지체일수 당 대금의 1%에 해당하는 지체상금을 지급하여야 한다."
        self.assertFalse(effects_overlap(infer_legal_effects(original), infer_legal_effects(contaminated_rewrite)))


class GlobalCrossClauseFailureStatusTest(unittest.TestCase):
    """GLOBAL_CROSS_CLAUSE_VALIDATION 백스톱이 실제로 새로 억제한 finding이
    있으면 REVIEW_FAILED_GLOBAL_REASONING에 뭉뚱그리지 않고 전용 상태
    REVIEW_FAILED_GLOBAL_CROSS_CLAUSE로 분리 보고해야 한다(2026-09-04 지시,
    요구 5) — Article 8.2(Article 9에 이미 준거법·중재가 있는데 "부재"로
    지적하는) 잔존 사례를 합성해 백스톱이 실제로 억제하는 상황을 재현한다."""

    def test_backstop_suppression_sets_global_cross_clause_status(self) -> None:
        from runtime.review.self_check import run_self_check

        text = (
            "Article 8.2 Governing law and arbitration are not specified in this Agreement.\n"
            "Article 9 This Agreement shall be governed by the laws of the Republic of Korea, "
            "and any dispute shall be finally settled by arbitration in Seoul."
        )
        clause_results = [{
            "clause_id": "clr_governing_law_arbitration_absent",
            "article_number": "8.2",
            "display_path": "Article 8.2",
            "clause_topic": "governing_law",
            "original_text": "Governing law and arbitration are not specified in this Agreement.",
            "risk_tier": "HIGH",
            "severity": "HIGH",
            "suggested_rewrite": "준거법 및 중재 조항을 신설한다.",
            "rewrite_reason": "준거법·관할 조항이 없다.",
            "legal_business_reason": "분쟁 발생 시 준거법이 불명확하다.",
            "dedup_suppressed": False,
            "keep_as_is": False,
        }]
        report = run_self_check(
            clause_results=clause_results,
            full_text=text,
            contract_type_code="general",
            contract_class="general",
            our_role_bucket="",
            confidence=0.9,
        )
        self.assertEqual(report.get("review_status"), "REVIEW_FAILED_GLOBAL_CROSS_CLAUSE")


if __name__ == "__main__":
    unittest.main()
