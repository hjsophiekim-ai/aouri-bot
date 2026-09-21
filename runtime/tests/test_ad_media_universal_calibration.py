"""광고계약 범용 보정 — Transaction Model 우선 + 집행형 검토 안정화 (2026-09-16).

지시 —
  "광고계약을 '광고' 라는 큰 범주만 보고 콘텐츠 제작형 규칙까지 함께
   활성화하지 말 것. 실제 거래모델을 먼저 확정한 뒤 그 유형에 맞는 질문과
   finding 만 생성할 것."

v11(2026-09-15)이 거래모델 판정 자체는 세웠는데, **그 판정이 계약유형으로
이어지지 않아** 리포트가 두 개의 계약을 말하고 있었다.

    거래모델         ad_media_placement (확신)    "상대방은 송출만 한다"
    canonical 유형   advertising_content_production
    리포트 상단      "제품 광고 콘텐츠 제작 대행 계약"
    최종 자가점검    contract_type — blocking 실패("계약유형 미확정")
    contract_class   project_installation  → 설치·시운전·산업안전 법령 검색

여기서 고정하는 것은 그 연결이다 — 거래모델이 확정되면 **그것이 계약유형이고**,
질문·finding·rewrite·UI·DOCX 가 전부 그 하나의 값 위에 선다(지시 1항).

이 파일이 고정하는 축
────────────────────
  1. 거래모델 → canonical 계약유형 (단일 확정 지점)
  2. 집행형에서 제작계약용 질문 금지 + 지시가 열거한 항목 전부 질문
  3. 계약유형과 finding 불일치 차단
  4. 계약에 없는 산출물·의무를 기정사실로 말하지 않기
  6. 세무·회계·특수관계인은 재경 확인사항으로 분리(HIGH/MEDIUM 금지)
  7. 우리에게 유리한 권리(환불·연장·상대방 배상·송출의무·실적 확인) KEEP
  9. Final Consistency Gate 6축
 10. 수정본 DOCX/PDF 다운로드가 실제로 나온다(앱과 같은 HTTP 경로)
"""
from __future__ import annotations

import http.client
import json
import threading
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

from runtime.questions.ad_media_questions import (
    AD_MEDIA_PREFIX,
    MEDIA_PLACEMENT_QUESTIONS,
    QUESTION_PRIORITY,
    apply_ad_media_question_policy,
    is_production_only_question,
)
from runtime.questions.model import Question
from runtime.review.ad_transaction_model import (
    AD_MEDIA_PLACEMENT,
    AD_MEDIA_PLACEMENT_TYPE_CODE,
    classify_ad_transaction_model,
    is_production_only_finding,
    resolve_ad_transaction_model,
)

FIXTURE = Path(__file__).parent / "fixtures" / "ad_media_placement_contract.txt"
MEDIA = FIXTURE.read_text(encoding="utf-8")
USER_MEDIA = "엘레베이터 내 미디어 광고 집행을 위탁하기 위한 계약서입니다."
PRODUCTION = (
    "광고 콘텐츠 제작 대행 계약서\n"
    "제1조 을은 갑의 제품 광고 영상 콘텐츠 제작을 위탁받아 수행한다.\n"
    "제2조 을은 시안을 제출하고 갑의 검수를 받아 결과물을 납품한다.\n"
    "제3조 결과물의 저작재산권은 갑에게 양도된다. 을은 저작인격권을 행사하지 아니한다.\n"
    "제4조 을은 촬영 원본과 편집 파일을 인도한다. 제작 대금은 납품 검수 후 지급한다.\n"
)
USER_PRODUCTION = "제품 광고 영상 콘텐츠 제작을 대행사에 맡기는 계약입니다."


def _q(qid: str, title: str, desc: str = "") -> Question:
    return Question(
        question_id=qid, title=title, description=desc, answer_type="text",
        required=False, options=[], tags=[], related_rule_ids=[],
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. 거래모델이 canonical 계약유형을 정한다
# ═══════════════════════════════════════════════════════════════════════════

class CanonicalTransactionModelTest(unittest.TestCase):
    def test_media_placement_settles_a_canonical_type(self) -> None:
        m = resolve_ad_transaction_model(
            contract_text=MEDIA, user_description=USER_MEDIA,
        )
        self.assertEqual(m.model, AD_MEDIA_PLACEMENT)
        self.assertTrue(m.is_settled)
        self.assertEqual(m.canonical_contract_type, AD_MEDIA_PLACEMENT_TYPE_CODE)

    def test_unsure_model_settles_nothing(self) -> None:
        """확신하지 못하면 유형을 덮어쓰지 않는다 — 모르는 것을 정하지 않는다."""
        m = classify_ad_transaction_model(
            contract_text=MEDIA, user_description=USER_PRODUCTION,
        )
        self.assertFalse(m.confident)
        self.assertEqual(m.canonical_contract_type, "")
        self.assertFalse(m.is_settled)

    def test_production_contract_keeps_production_type(self) -> None:
        m = resolve_ad_transaction_model(
            contract_text=PRODUCTION, user_description=USER_PRODUCTION,
        )
        self.assertEqual(m.canonical_contract_type, "advertising_content_production")

    def test_answers_can_flip_the_model(self) -> None:
        """답변은 사용자 설명에 더해진다 — 검토 시점 판정이 질문 시점을 덮는다."""
        m = resolve_ad_transaction_model(
            contract_text=MEDIA,
            user_description="",
            answers={"Q-1": "상대방이 광고 영상 콘텐츠 제작도 함께 맡습니다."},
        )
        self.assertFalse(m.is_media_placement, m.to_dict())

    def test_question_wording_is_not_taken_as_user_description(self) -> None:
        """질문 템플릿의 낱말을 사용자 설명으로 승계하지 않는다(지시 4항)."""
        m = resolve_ad_transaction_model(
            contract_text=MEDIA,
            user_description=USER_MEDIA,
            answers=[{
                "question_id": "Q-EFF-ip-scope",
                "question": "결과물을 2차 활용할 계획인가요? 콘텐츠 제작 범위는?",
                "answer": "해당 없음",
            }],
        )
        self.assertEqual(m.model, AD_MEDIA_PLACEMENT, m.to_dict())

    def test_classifier_uses_the_transaction_model(self) -> None:
        """'시안'·'이미지' 같은 낱말 하나로 제작형이 되지 않는다."""
        from runtime.review.contract_classifier import classify_contract_detailed

        profile = classify_contract_detailed(
            entity="가나상사", contract_type="광고", text=MEDIA,
        )
        self.assertEqual(profile.contract_type, AD_MEDIA_PLACEMENT_TYPE_CODE)
        self.assertNotIn("제작", profile.our_legal_role)


class CrossContractHoldoutTest(unittest.TestCase):
    """fixture 한 건에 맞춘 판정이 아닌지 — 다른 계약서로 교차 확인한다.

    v8 이후 원칙: 유형별 룰팩을 더하는 대신 판단 축을 세우고, 그 축이
    **처음 보는 계약**에서도 서는지 hold-out 으로 확인한다.
    """

    BUS_WRAP = (
        "시내버스 외부광고 게재계약서\n"
        "제1조 (목적) 을은 갑이 제공하는 광고물을 을이 운행하는 시내버스 외부에 부착·게재한다.\n"
        "제2조 (광고기간) 광고기간은 2026. 3. 1.부터 6개월로 한다.\n"
        "제3조 (광고물) 갑은 광고 게재 개시 7일 전까지 광고 디자인 시안과 출력물을 을에게 전달한다. "
        "광고물의 제작비용은 갑이 부담한다.\n"
        "제4조 (광고료) 갑은 매월 말일 광고료를 지급한다. 연체 시 을은 게재를 즉시 중단할 수 있다.\n"
        "제5조 (게재 중단) 차량 정비·사고 등으로 게재가 불가능한 경우 을은 해당 기간만큼 연장한다.\n"
        "제6조 (책임) 광고 내용의 위법성에 대한 모든 법적 책임은 갑이 부담하며 을을 면책한다.\n"
    )
    INFLUENCER = (
        "인플루언서 광고 콘텐츠 제작 및 게시 계약서\n"
        "제1조 을(크리에이터)은 갑의 제품에 관한 광고 영상 콘텐츠를 직접 기획·촬영·편집하여 제작한다.\n"
        "제2조 을은 시안을 제출하고 갑의 검수를 거쳐 결과물을 납품한다.\n"
        "제3조 결과물의 저작재산권은 갑에게 양도되며, 을은 저작인격권을 행사하지 아니한다.\n"
        "제4조 을은 제작에 사용한 제3자 소재(음원·폰트·스톡 이미지)의 이용허락을 확보한다.\n"
        "제5조 을은 제작한 콘텐츠를 자신의 채널에 30일간 게시한다.\n"
        "제6조 제작 대금은 납품 검수 완료 후 30일 이내에 지급한다.\n"
    )
    HYBRID = (
        "디지털 광고 통합 대행 계약서\n"
        "제1조 을은 갑의 광고 콘텐츠를 제작하고, 제작한 콘텐츠를 온·오프라인 매체에 집행한다.\n"
        "제2조 을은 시안 제작, 촬영, 편집을 수행하고 갑의 검수를 받는다.\n"
        "제3조 을은 매체 위치와 수량, 송출 횟수를 갑과 협의하여 정하고 광고를 송출한다.\n"
        "제4조 제작물의 저작재산권 귀속은 별도로 정한다. 산출물은 갑에게 인도한다.\n"
        "제5조 을은 월별 송출 실적과 노출 횟수를 갑에게 보고한다. 광고기간 중 민원 발생 시 협의한다.\n"
        "제6조 제작 대금과 매체 집행 광고료는 구분하여 청구한다.\n"
    )
    NOT_AD = (
        "사무용 가구 공급계약서\n"
        "제1조 을은 갑에게 사무용 의자 200개를 납품한다.\n"
        "제2조 을은 본 계약의 체결 사실을 광고에 사용할 수 없다.\n"
        "제3조 납품 검수 후 대금을 지급한다.\n"
    )

    def _resolve(self, text: str, desc: str):
        return resolve_ad_transaction_model(contract_text=text, user_description=desc)

    def test_a_different_media_contract_is_still_media_placement(self) -> None:
        m = self._resolve(self.BUS_WRAP, "버스 외부광고 게재를 위탁하는 계약입니다.")
        self.assertEqual(m.canonical_contract_type, AD_MEDIA_PLACEMENT_TYPE_CODE)

    def test_creator_contract_is_production_not_placement(self) -> None:
        """매체 어휘(게시·채널)가 있어도 만드는 쪽이 상대방이면 제작형이다."""
        m = self._resolve(self.INFLUENCER, "인플루언서에게 광고 영상 제작을 맡기는 계약입니다.")
        self.assertEqual(m.canonical_contract_type, "advertising_content_production")

    def test_hybrid_keeps_production_topics_on(self) -> None:
        """제작 + 집행이면 아무것도 끄지 않는다."""
        m = self._resolve(self.HYBRID, "콘텐츠 제작과 매체 집행을 함께 맡기는 계약입니다.")
        self.assertTrue(m.counterparty_produces_content)
        self.assertFalse(m.is_media_placement)

    def test_a_passing_mention_of_advertising_settles_nothing(self) -> None:
        """'광고에 사용할 수 없다' 한 줄로 광고계약이 되지 않는다."""
        m = self._resolve(self.NOT_AD, "사무용 가구를 구매하는 계약입니다.")
        self.assertFalse(m.is_settled)
        self.assertEqual(m.canonical_contract_type, "")

    def test_classifier_agrees_on_every_holdout(self) -> None:
        from runtime.review.contract_classifier import classify_contract_detailed

        for text, expected in (
            (self.BUS_WRAP, AD_MEDIA_PLACEMENT_TYPE_CODE),
            (self.INFLUENCER, "advertising_content_production"),
            (self.NOT_AD, "purchase_supply"),
        ):
            profile = classify_contract_detailed(entity="퍼시스", contract_type="", text=text)
            self.assertEqual(profile.contract_type, expected, text[:30])


# ═══════════════════════════════════════════════════════════════════════════
# 2. 집행형 사전질문
# ═══════════════════════════════════════════════════════════════════════════

class MediaPlacementQuestionPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = resolve_ad_transaction_model(
            contract_text=MEDIA, user_description=USER_MEDIA,
        )

    def test_banned_questions_are_suppressed(self) -> None:
        """지시 2항이 열거한 다섯 가지."""
        for title in (
            "결과물을 2차 활용할 계획이 있나요?",
            "저작물을 어느 매체·기간·지역에서 사용할 계획인가요?",
            "2차적저작물작성권을 확보해야 하나요?",
            "저작인격권 불행사 확약을 받나요?",
            "창작자로부터 chain of title 을 확보했나요?",
        ):
            self.assertTrue(is_production_only_question(_q("Q-X", title)), title)

    def test_every_instructed_topic_is_actually_asked(self) -> None:
        """상한 때문에 우선순위 질문이 잘리지 않는다."""
        report = apply_ad_media_question_policy([], self.model, max_questions=7)
        asked = [q.question_id for q in report["questions"]]
        self.assertEqual(
            sorted(asked), sorted(q.question_id for q in MEDIA_PLACEMENT_QUESTIONS),
            "지시가 우선하라고 한 질문이 상한에 잘렸다",
        )

    def test_priority_order_matches_the_instruction(self) -> None:
        report = apply_ad_media_question_policy([], self.model, max_questions=7)
        asked = [q.question_id for q in report["questions"]]
        self.assertEqual(asked[: len(QUESTION_PRIORITY)], list(QUESTION_PRIORITY))

    def test_user_focus_question_comes_first(self) -> None:
        focus = _q("Q-FOCUS-other", "추가로 확인이 필요한 사실관계가 있나요?")
        report = apply_ad_media_question_policy([focus], self.model, max_questions=7)
        self.assertEqual(report["questions"][0].question_id, "Q-FOCUS-other")

    def test_generic_questions_do_not_crowd_out_the_priority_set(self) -> None:
        generic = [_q(f"Q-EFF-{i}", f"일반 질문 {i}") for i in range(6)]
        report = apply_ad_media_question_policy(generic, self.model, max_questions=7)
        asked = {q.question_id for q in report["questions"]}
        for q in MEDIA_PLACEMENT_QUESTIONS:
            self.assertIn(q.question_id, asked, q.question_id)

    def test_production_contract_is_untouched(self) -> None:
        model = resolve_ad_transaction_model(
            contract_text=PRODUCTION, user_description=USER_PRODUCTION,
        )
        ip_q = _q("Q-EFF-ip-scope", "이 계약으로 취득하는 지식재산을 어디까지 활용하나요?")
        report = apply_ad_media_question_policy([ip_q], model)
        self.assertFalse(report["applied"])
        self.assertIn("Q-EFF-ip-scope", {q.question_id for q in report["questions"]})


# ═══════════════════════════════════════════════════════════════════════════
# 4. 계약에 없는 산출물·의무를 만들어내지 않는다
# ═══════════════════════════════════════════════════════════════════════════

class FabricatedArtifactGateTest(unittest.TestCase):
    def setUp(self) -> None:
        from runtime.review.fabricated_artifact_gate import (
            enforce_no_fabricated_artifacts,
            find_fabricated_artifacts,
        )
        self.enforce = enforce_no_fabricated_artifacts
        self.find = find_fabricated_artifacts

    def test_nonexistent_report_is_caught(self) -> None:
        hits = self.find(
            finding_text="제4조가 정한 성적서 제출 기한이 지나치게 짧습니다.",
            contract_text=MEDIA,
        )
        self.assertIn("성적서", hits)

    def test_nonexistent_deliverable_copyright_is_caught(self) -> None:
        hits = self.find(
            finding_text="결과물의 저작권이 매체사에게 귀속되어 있어 불리합니다.",
            contract_text=MEDIA,
        )
        self.assertTrue(hits, "계약에 없는 결과물 저작권을 기정사실로 말했다")

    def test_pointing_out_an_absence_is_allowed(self) -> None:
        """없는 것을 없다고 말하는 것은 정확히 해야 할 일이다."""
        self.assertEqual(
            self.find(
                finding_text="송출 실적에 관한 성적서·증빙 제출 의무가 없습니다.",
                contract_text=MEDIA,
            ),
            [],
        )

    def test_proposing_a_new_obligation_is_allowed(self) -> None:
        self.assertEqual(
            self.find(
                finding_text="제3자 소재 라이선스 확보 의무를 신설하여야 합니다.",
                contract_text=MEDIA,
            ),
            [],
        )

    def test_existing_terms_are_not_touched(self) -> None:
        contract = "제1조 을은 시험성적서를 갑에게 제출한다. 검수 후 대금을 지급한다."
        self.assertEqual(
            self.find(
                finding_text="성적서 제출 기한이 정해져 있지 않아 검수가 지연됩니다.",
                contract_text=contract,
            ),
            [],
        )

    def test_enforcement_removes_and_records(self) -> None:
        results = [
            {"clause_id": "X", "issue_title": "성적서 제출 기한이 짧습니다",
             "problem": "제4조의 성적서 제출 기한은 3일입니다."},
            {"clause_id": "ADM-02", "issue_title": "미송출 구제가 연장뿐",
             "problem": "환불 선택권이 없습니다."},
        ]
        report = self.enforce(results, contract_text=MEDIA)
        self.assertEqual([c["clause_id"] for c in results], ["ADM-02"])
        self.assertEqual(len(report["removed"]), 1)
        self.assertTrue(report["status"])


# ═══════════════════════════════════════════════════════════════════════════
# 6. 세무·회계·특수관계인은 재경 확인사항
# ═══════════════════════════════════════════════════════════════════════════

class FinanceConfirmationSplitTest(unittest.TestCase):
    def setUp(self) -> None:
        from runtime.review.internal_control_split import (
            is_finance_confirmation_topic,
            split_internal_controls,
        )
        self.is_topic = is_finance_confirmation_topic
        self.split = split_internal_controls

    def test_related_party_check_is_a_finance_topic(self) -> None:
        self.assertTrue(self.is_topic("상대방이 특수관계인에 해당하는지 확인이 필요합니다."))

    def test_tax_treatment_is_a_finance_topic(self) -> None:
        self.assertTrue(self.is_topic("광고비의 손금 산입 시기와 세무조정이 문제될 수 있습니다."))

    def test_payment_terms_stay_a_contract_issue(self) -> None:
        """세금계산서 발행 시기는 대금 지급조건과 얽힌 계약 조항이다."""
        self.assertFalse(
            self.is_topic("매체사가 세금계산서를 발행하여 청구하도록 되어 있어 "
                          "선지급 구조입니다.")
        )

    def test_finance_topic_is_demoted_out_of_high(self) -> None:
        results = [{
            "clause_id": "TAX-1", "risk_tier": "HIGH", "severity": "HIGH",
            "issue_title": "특수관계인 해당 여부 확인 필요",
            "problem": "특수관계인에 해당하면 부당행위계산 부인이 문제될 수 있습니다.",
        }]
        moved = self.split(results)
        self.assertEqual(results[0]["risk_tier"], "LOW")
        self.assertTrue(results[0]["finance_confirmation_item"])
        self.assertEqual([m["clause_id"] for m in moved], ["TAX-1"])

    def test_contract_findings_are_untouched(self) -> None:
        results = [{
            "clause_id": "ADM-03", "risk_tier": "HIGH", "severity": "HIGH",
            "issue_title": "중도해지 시 할인액 소급 청구에 상한이 없음",
            "problem": "표준가로 재산정해 차액을 청구합니다.",
        }]
        self.split(results)
        self.assertEqual(results[0]["risk_tier"], "HIGH")


# ═══════════════════════════════════════════════════════════════════════════
# 7. 우리에게 유리한 권리는 KEEP
# ═══════════════════════════════════════════════════════════════════════════

class OurFavorableAdRightsTest(unittest.TestCase):
    def setUp(self) -> None:
        from runtime.review.accept_keep import softens_counterparty_burden
        self.softens = softens_counterparty_burden

    def test_refund_right_is_protected(self) -> None:
        original = ('"매체사"는 미 방영 시간 만큼 계약한 월 광고금액을 일할 계산하여 '
                    '"고객"에게 반환한다.')
        weakened = "매체사와 고객은 쌍방 협의하여 반환 여부와 금액을 정한다."
        self.assertTrue(self.softens(original, weakened, our_labels=("고객",)))

    def test_extension_right_is_protected(self) -> None:
        original = '"매체사"의 과실로 광고가 미 방영될 경우 해당 시간만큼 연장하여 광고를 방영하여야 한다.'
        weakened = "매체사의 고의 또는 중대한 과실이 있는 경우에 한하여 연장한다."
        self.assertTrue(self.softens(original, weakened, our_labels=("고객",)))

    def test_performance_report_duty_is_protected(self) -> None:
        original = "매체사는 매월 송출 실적을 고객에게 제출한다."
        weakened = "매체사는 고객이 요청하는 경우 쌍방 협의하여 실적을 제공할 수 있다."
        self.assertTrue(self.softens(original, weakened, our_labels=("고객",)))

    def test_strengthening_our_right_is_not_blocked(self) -> None:
        """환불권을 **더하는** 수정은 약화가 아니다."""
        original = '"매체사"의 과실로 광고가 미 방영될 경우 해당 시간만큼 연장하여 방영하여야 한다.'
        stronger = (
            '"매체사"의 과실로 광고가 미 방영된 경우 "고객"은 기간 연장, 대체 매체 송출, '
            '해당 금액의 환불 중 하나를 선택할 수 있다.'
        )
        self.assertFalse(self.softens(original, stronger, our_labels=("고객",)))


# ═══════════════════════════════════════════════════════════════════════════
# 3·9. 파이프라인 — 유형·질문·finding 이 하나로 선다
# ═══════════════════════════════════════════════════════════════════════════

class MediaPlacementPipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from runtime.questions.generator import generate_questions
        from runtime.questions.model import question_to_dict
        from runtime.review.clause_level import build_clause_level_result
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService

        loader = RuleLoader()
        loader.load()
        cls.questions = generate_questions(
            entity="가나상사", contract_type="광고", detected_rule_ids=None,
            contract_text=MEDIA, review_focus=USER_MEDIA,
            contract_type_code=AD_MEDIA_PLACEMENT_TYPE_CODE,
        )
        cls.bundle = build_clause_level_result(
            service=RuleQueryService(loader),
            entity="가나상사", contract_type="광고", text=MEDIA,
            filename="ad_media_placement_contract.txt",
            answers=None, review_focus=USER_MEDIA,
            asked_questions=[question_to_dict(q) for q in cls.questions],
            law_service=None, ai_provider=None, ai_model="", ai_timeout_sec=60.0,
            ai_max_tokens=2000, ai_temperature=0.1,
        )
        cls.meta = cls.bundle.meta

    # ── 1항: 하나의 값 ──────────────────────────────────────────────────────
    def test_canonical_type_equals_the_transaction_model(self) -> None:
        for key in ("canonical_state", "legal_state"):
            self.assertEqual(
                str((self.meta.get(key) or {}).get("contract_type")),
                AD_MEDIA_PLACEMENT_TYPE_CODE,
                key,
            )

    def test_report_header_says_media_placement(self) -> None:
        """UI·DOCX·PDF 가 공유하는 섹션 1 이 같은 값을 말한다."""
        from runtime.review.report_header import build_section1_rows

        ff = self.meta.get("final_findings") or {}
        rows = build_section1_rows(
            entity="가나상사", contract_type="광고",
            contract_type_code=AD_MEDIA_PLACEMENT_TYPE_CODE,
            filename="ad.txt",
            detailed_contract_profile=self.meta.get("detailed_contract_profile"),
            high_issues=ff.get("high_issues") or [],
            medium_issues=ff.get("medium_issues") or [],
            canonical_state=self.meta.get("canonical_state"),
        )
        text = "\n".join(r.text for r in rows)
        self.assertIn("광고매체 집행 계약", text)
        self.assertNotIn("제작 대행", text)

    def test_local_class_does_not_fall_back_to_installation(self) -> None:
        """집행형인데 설치·시운전 계열로 분류되면 그 유형의 법령·체크리스트가 따라온다."""
        self.assertEqual(self.meta.get("contract_class"), "general")

    # ── 3항: 유형과 finding 불일치 ─────────────────────────────────────────
    def test_no_production_finding_survives_anywhere(self) -> None:
        offenders: list[str] = []
        for cr in self.bundle.clause_results:
            if not isinstance(cr, dict) or cr.get("dedup_suppressed"):
                continue
            blob = "\n".join(
                str(cr.get(k) or "")
                for k in ("issue_title", "problem", "suggested_rewrite")
            )
            if is_production_only_finding(blob):
                offenders.append(str(cr.get("clause_id")))
        self.assertEqual(offenders, [], "집행형인데 제작계약용 논점이 남았다")

    def test_media_placement_axes_are_in_the_output(self) -> None:
        ff = self.meta.get("final_findings") or {}
        ids = {
            str(i.get("clause_id"))
            for bucket in ("high_issues", "medium_issues")
            for i in (ff.get(bucket) or []) if isinstance(i, dict)
        }
        self.assertTrue(
            {x for x in ids if x.startswith("ADM-")},
            "집행형 검토 항목이 최종 결과에 하나도 없다",
        )

    def test_supplied_content_liability_survives(self) -> None:
        """지시 5항 — 우리가 제공한 콘텐츠의 책임 범위는 집행형의 진짜 논점이다."""
        ff = self.meta.get("final_findings") or {}
        ids = {
            str(i.get("clause_id"))
            for bucket in ("high_issues", "medium_issues")
            for i in (ff.get(bucket) or []) if isinstance(i, dict)
        }
        self.assertIn("ADM-05", ids)

    # ── 8항: 완성 문구 ──────────────────────────────────────────────────────
    def test_every_high_medium_has_insertable_text(self) -> None:
        from runtime.review.rewrite_completeness import is_descriptive_only

        ff = self.meta.get("final_findings") or {}
        bad: list[str] = []
        for bucket in ("high_issues", "medium_issues"):
            for i in (ff.get(bucket) or []):
                if not isinstance(i, dict):
                    continue
                proposal = str(
                    i.get("proposed_revision") or i.get("suggested_rewrite") or ""
                )
                if not proposal.strip() or is_descriptive_only(proposal):
                    bad.append(str(i.get("clause_id")))
        self.assertEqual(bad, [], "그대로 붙여넣을 수 있는 완성 문구가 없다")

    # ── 9항: Final Consistency Gate ────────────────────────────────────────
    def test_final_consistency_gate_passes_all_six_axes(self) -> None:
        gate = self.meta.get("ad_final_consistency_gate") or {}
        self.assertTrue(gate.get("applied"), "게이트가 돌지 않았다")
        self.assertEqual(
            [c["key"] for c in gate["checks"]],
            [
                "model_consistent", "questions_fit_model", "findings_fit_model",
                "no_fabricated_facts", "problem_and_rewrite_align",
                "no_type_uncertain_contradiction",
            ],
        )
        self.assertEqual(gate.get("failed"), [], gate.get("detail"))

    def test_type_uncertain_does_not_coexist_with_a_settled_type(self) -> None:
        status = str(self.meta.get("review_status") or "")
        self.assertNotIn("TYPE_UNCERTAIN", status)
        blocking = (self.meta.get("final_lawyer_self_check") or {}).get("blocking_failed") or []
        self.assertNotIn("contract_type", blocking)

    def test_review_completes_normally(self) -> None:
        self.assertFalse(
            str(self.meta.get("review_status") or ""),
            self.meta.get("review_status_detail"),
        )

    # ── 6항: 재경 확인사항이 HIGH/MEDIUM 을 차지하지 않는다 ────────────────
    def test_no_finance_topic_in_high_or_medium(self) -> None:
        from runtime.review.internal_control_split import is_finance_confirmation_topic

        ff = self.meta.get("final_findings") or {}
        bad: list[str] = []
        for bucket in ("high_issues", "medium_issues"):
            for i in (ff.get(bucket) or []):
                if not isinstance(i, dict):
                    continue
                blob = f"{i.get('issue_title') or ''}\n{i.get('problem') or ''}"
                if is_finance_confirmation_topic(blob):
                    bad.append(str(i.get("clause_id")))
        self.assertEqual(bad, [], "재경·세무 확인사항이 계약 리스크 등급을 차지했다")


class ConsistencyGateDetectsDriftTest(unittest.TestCase):
    """게이트가 실제로 잡는지 — 통과만 확인하면 꺼져 있어도 알 수 없다."""

    def setUp(self) -> None:
        from runtime.review.ad_final_consistency_gate import run_ad_final_consistency_gate
        self.run = run_ad_final_consistency_gate
        self.model = resolve_ad_transaction_model(
            contract_text=MEDIA, user_description=USER_MEDIA,
        )
        self.meta = {
            "canonical_state": {"contract_type": AD_MEDIA_PLACEMENT_TYPE_CODE},
            "final_findings": {"high_issues": [], "medium_issues": []},
        }

    def test_catches_a_type_that_drifted(self) -> None:
        self.meta["canonical_state"] = {"contract_type": "advertising_content_production"}
        report = self.run(model=self.model, meta=self.meta, clause_results=[])
        self.assertIn("model_consistent", report["failed"])
        self.assertTrue(report["status"])

    def test_catches_a_production_question(self) -> None:
        report = self.run(
            model=self.model, meta=self.meta, clause_results=[],
            questions=[{"question_id": "Q-EFF-ip-scope",
                        "title": "취득하는 지식재산을 어디까지 활용하나요?"}],
        )
        self.assertIn("questions_fit_model", report["failed"])

    def test_catches_a_production_finding_in_final_output(self) -> None:
        self.meta["final_findings"] = {
            "high_issues": [{
                "clause_id": "pkg_ip_chain_of_title",
                "issue_title": "창작자 → 2차적저작물작성권 → 저작인격권",
                "problem": "창작자로부터의 권리 확약이 없습니다.",
            }],
        }
        report = self.run(model=self.model, meta=self.meta, clause_results=[])
        self.assertIn("findings_fit_model", report["failed"])

    def test_catches_a_fabricated_fact(self) -> None:
        self.meta["fabricated_artifact_gate"] = {
            "removed": [{"clause_id": "X", "artifacts": ["성적서"]}],
        }
        report = self.run(model=self.model, meta=self.meta, clause_results=[])
        self.assertIn("no_fabricated_facts", report["failed"])

    def test_catches_the_type_uncertain_contradiction(self) -> None:
        self.meta["review_status"] = "REVIEW_FAILED_CONTRACT_TYPE_UNCERTAIN"
        report = self.run(model=self.model, meta=self.meta, clause_results=[])
        self.assertIn("no_type_uncertain_contradiction", report["failed"])

    def test_does_nothing_for_production_contracts(self) -> None:
        model = resolve_ad_transaction_model(
            contract_text=PRODUCTION, user_description=USER_PRODUCTION,
        )
        report = self.run(model=model, meta={}, clause_results=[])
        self.assertFalse(report["applied"])
        self.assertEqual(report["failed"], [])


# ═══════════════════════════════════════════════════════════════════════════
# 10. 수정본 다운로드 — 앱에서 누르는 것과 같은 HTTP 경로
# ═══════════════════════════════════════════════════════════════════════════

class AdMediaRevisionDownloadTest(unittest.TestCase):
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
        doc = create_session(
            cls.service,
            entity="가나상사",
            contract_type="",
            filename="디지털사이니지_광고계약서.docx",
            extraction={},
            text=MEDIA,
            classification={},
            review_focus=USER_MEDIA,
        )
        cls.session_id = doc["session_id"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.thread.join(timeout=5)
        cls.httpd.server_close()

    def _post(self, path: str, payload: dict):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=300)
        conn.request(
            "POST", path,
            body=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp, body

    def test_download_docx_succeeds(self) -> None:
        resp, body = self._post(
            "/api/revision/download_docx",
            {"session_id": self.session_id, "rebuild": True, "ai_mode": "off"},
        )
        if resp.status != 200:
            self.fail(f"수정본(docx) 생성 실패 status={resp.status}: {body[:800]!r}")
        self.assertGreater(len(body), 1000)
        with zipfile.ZipFile(BytesIO(body)) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
        self.assertIn("광고매체 집행 계약", xml)
        for banned in ("2차적저작물", "저작인격권", "chain of title"):
            self.assertNotIn(banned, xml, banned)

    def test_download_pdf_succeeds(self) -> None:
        resp, body = self._post(
            "/api/revision/download_pdf",
            {"session_id": self.session_id, "rebuild": True, "ai_mode": "off"},
        )
        if resp.status != 200:
            self.fail(f"수정본(pdf) 생성 실패 status={resp.status}: {body[:800]!r}")
        self.assertTrue(body.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
