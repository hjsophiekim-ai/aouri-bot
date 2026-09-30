"""사전 질문 관련성 회귀테스트 — 한글날 제품개발·협업 계약 (2026-09-30).

실측: 파일 업로드로 한글날 아트상품 개발·제작 협업 계약을 올리자
"최종 고객과의 매매계약상 판매자는 누구인가요?", "재고 소유권", "매출 귀속",
"POS 결제 명의" 같은 **위탁매매 계약용** 질문 5개가 나갔다. 매장도 고객 대금
수령도 위탁판매도 없는 계약이다.

원인은 세 겹이었다.
  1. 업로드 경로(`storage.create_session`)만 AI 질문 계획과 거래 원형 게이트
     없이 질문을 만들었다 — 키워드 탐지 하나가 질문을 정했다.
  2. 탐지기가 "반품"(로열티 산정에서 빼는 반품분)과 "판매실적"(로열티 산정
     기준) 두 낱말로 위탁매매 구조라고 판정했다. 자기 제품을 파는 회사의
     계약에도 늘 나오는 낱말이다.
  3. 거래 원형이 "물품 공급·매매"로 읽혀 원형 게이트도 위탁매매 질문을
     통과시켰다 — 시제품 납품 조항 수가 IP 조항 수보다 많았기 때문이다.
"""
from __future__ import annotations

import logging
import re
import unittest
from pathlib import Path

from runtime.questions.contract_question_agent import ContractQuestionPlan
from runtime.questions.model import Question
from runtime.review.clause_effect import ARCHETYPE_LICENSE, build_effect_profile
from runtime.review.clause_extraction import extract_clauses
from runtime.review.transaction_structure_signals import detect_sales_transaction_ambiguity

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "hangul_day_100th_alloso_3party_contract.txt"

#: 위탁매매 계약에서나 성립하는 질문의 표지.
RX_CONSIGNMENT_QUESTION = re.compile(r"판매자는\s*누구|재고|POS|결제\s*명의|매출로\s*인식|위탁판매자|판매지원\s*용역자")


def _text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


class DetectorTest(unittest.TestCase):
    def test_hangul_day_contract_is_not_a_consignment_structure(self) -> None:
        self.assertFalse(detect_sales_transaction_ambiguity(_text()))

    def test_own_product_sales_with_royalty_is_not_ambiguous(self) -> None:
        text = (
            "제10조 (로열티)\n① 갑은 제품의 판매실적에 따라 을에게 로열티를 지급한다.\n"
            "② 반품된 수량은 로열티 산정에서 제외한다.\n③ 갑은 소비자에게 판매한 대금을 매월 정산한다.\n"
        )
        self.assertFalse(detect_sales_transaction_ambiguity(text))

    def test_fee_prohibition_mentioning_brokerage_is_not_a_signal(self) -> None:
        text = (
            "기획사는 협업자로부터 중개수수료를 받지 않는다. 갑은 제품의 판매실적에 따라 로열티를 지급하고 "
            "반품분은 제외한다. 소비자 결제는 갑의 명의로 한다."
        )
        self.assertFalse(detect_sales_transaction_ambiguity(text))

    def test_real_consignment_structure_is_still_detected(self) -> None:
        text = (
            "제3조 (위탁판매)\n을은 갑의 작품을 매장에 진열하여 고객에게 판매하고, 갑은 을에게 판매수수료를 지급한다.\n"
            "고객의 결제는 을의 POS 단말로 한다.\n"
        )
        self.assertTrue(detect_sales_transaction_ambiguity(text))


class ArchetypeTest(unittest.TestCase):
    def test_royalty_development_contract_is_a_license_not_goods_supply(self) -> None:
        t = _text()
        profile = build_effect_profile(text=t, clauses=extract_clauses(t)[0])
        self.assertEqual(profile.archetype, ARCHETYPE_LICENSE, profile.to_dict())


class UploadSessionQuestionTest(unittest.TestCase):
    """파일 업로드 경로(`create_session`) — 테스트에서는 실제 AI 호출이 막혀 있어
    AI 계획이 없는 결정론적 경로를 탄다. 그래도 위탁매매 질문이 나가면 안 된다."""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService

        loader = RuleLoader()
        loader.load()
        cls.service = RuleQueryService(loader)

    def _session(self, **kw):
        from runtime.questions.storage import create_session

        logging.disable(logging.CRITICAL)
        try:
            return create_session(
                self.service, entity="시디즈", contract_type="", filename="한글날_제품개발계약.docx",
                extraction={}, text=_text(), classification={}, **kw,
            )
        finally:
            logging.disable(logging.NOTSET)

    def test_no_consignment_questions_without_ai_plan(self) -> None:
        doc = self._session()
        titles = [str(q.get("title") or "") for q in doc["questions"]]
        ids = [str(q.get("question_id") or "") for q in doc["questions"]]
        self.assertFalse([i for i in ids if i.startswith("Q-TXN-")], titles)
        self.assertFalse([t for t in titles if RX_CONSIGNMENT_QUESTION.search(t)], titles)

    def test_ai_plan_questions_lead_on_upload(self) -> None:
        plan = ContractQuestionPlan(
            status="ai",
            contract_nature="복합(도급+라이선스)",
            our_side="시디즈(알로소)는 제품화·판매 주체",
            questions=[Question(
                question_id="Q-AI-001-payment_settlement",
                title="로열티 지급 시 부가가치세 포함 여부는 어떻게 정했나요?",
                description="세금계산서 발행 주체가 달라집니다.",
                answer_type="text", required=True, options=[],
                tags=["topic:payment_settlement", "source:contract_question_agent"],
                related_rule_ids=[],
            )],
        )
        doc = self._session(question_plan=plan)
        self.assertEqual(doc["questions"][0]["question_id"], "Q-AI-001-payment_settlement")


if __name__ == "__main__":
    unittest.main()
