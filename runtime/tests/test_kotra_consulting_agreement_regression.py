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

    def test_third_party_debt_guarantee_on_article_4_3(self) -> None:
        cr = self.by_id.get("clr_third_party_debt_guarantee")
        self.assertIsNotNone(cr, "Article 4.3의 Company의 Consultant 환급채무 보증이 탐지되어야 한다")
        self.assertEqual(cr["display_path"], "Article 4.3")
        self.assertEqual(cr["risk_tier"], "HIGH")
        self.assertEqual(cr.get("original_effect_tags"), ["third_party_debt_guarantee"])

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


if __name__ == "__main__":
    unittest.main()
