"""판매/위탁판매/대리판매/중개/판매지원 계약의 핵심 거래구조 확인 질문.

범용 사내변호사형 검토 엔진 전면 보정(2026-09-04 지시) — 계약 문언만으로
법적 책임 주체(판매자/소유권/매출귀속/대금수령/재고위험/소비자책임/IP·진위
책임/기존계약연계)가 확정되지 않으면, 계약유형별 체크리스트를 돌리기 전에
반드시 먼저 물어야 하는 사실관계 8종을 우선순위 순서로 정의한다.

핵심 원칙: POS/결제 단말기 명의자를 곧바로 판매자로 추정하지 않는다 —
"위탁매매" 구조에서는 매장이 결제를 대행하지만 실제 판매자·소유자는 다른
당사자일 수 있다(그림닷컴 판매지원 계약 실사례로 확인).
"""
from __future__ import annotations

from runtime.questions.model import Question, QuestionOption

_TEXT = "text"

TRANSACTION_STRUCTURE_QUESTIONS: list[Question] = [
    Question(
        question_id="Q-TXN-001-seller",
        title="최종 고객과의 매매계약상 판매자는 누구인가요?",
        description="계약서 문언(위탁판매/대리판매/판매지원 등 제목)이 아니라, 실제로 고객에게 물건을 파는 법적 당사자가 누구인지 확인합니다.",
        answer_type=_TEXT,
        required=True,
        options=[],
        tags=["topic:transaction_structure", "priority:1", "reason_code:seller_identity"],
        related_rule_ids=[],
    ),
    Question(
        question_id="Q-TXN-002-owner",
        title="상품(재고)의 소유권은 판매 전 누구에게 있으며, 언제 고객에게 이전되나요?",
        description="위탁판매(소유권이 공급자에게 남아있음)인지, 매입 후 재판매(소유권이 이미 판매자에게 이전됨)인지에 따라 재고 위험·회계처리·법적 책임이 달라집니다.",
        answer_type=_TEXT,
        required=True,
        options=[],
        tags=["topic:transaction_structure", "priority:2", "reason_code:ownership_of_goods"],
        related_rule_ids=[],
    ),
    Question(
        question_id="Q-TXN-003-revenue",
        title="판매대금은 누구의 매출로 인식(귀속)되나요?",
        description="POS/결제 명의자와 매출 귀속 주체가 다를 수 있습니다(위탁매매 구조 등).",
        answer_type=_TEXT,
        required=True,
        options=[],
        tags=["topic:transaction_structure", "priority:3", "reason_code:revenue_attribution"],
        related_rule_ids=[],
    ),
    Question(
        question_id="Q-TXN-004-payment-collection",
        title="고객으로부터 대금을 실제로 수령하는 주체와 그 정산 방식은 무엇인가요? (POS/결제 명의자를 그대로 판매자로 단정하지 마세요)",
        description="매장 POS로 결제를 대행하더라도 그 명의가 실제 판매자와 다를 수 있습니다 — 결제 명의와 정산 흐름을 구체적으로 확인합니다.",
        answer_type=_TEXT,
        required=True,
        options=[],
        tags=["topic:transaction_structure", "priority:4", "reason_code:payment_recipient"],
        related_rule_ids=[],
    ),
    Question(
        question_id="Q-TXN-005-inventory-risk",
        title="재고·분실·파손 위험은 누가 부담하나요?",
        description="상품이 매장에 진열/보관되는 동안 발생하는 분실·파손 리스크의 부담 주체를 확인합니다.",
        answer_type=_TEXT,
        required=False,
        options=[],
        tags=["topic:transaction_structure", "priority:5", "reason_code:inventory_risk"],
        related_rule_ids=[],
    ),
    Question(
        question_id="Q-TXN-006-consumer-liability",
        title="배송·하자·반품·환불 등 소비자 관련 책임은 누구에게 있나요?",
        description="소비자 클레임 발생 시 실제 대응·배상 주체를 확인합니다 — 전자상거래법/소비자보호법 적용과 직결됩니다.",
        answer_type=_TEXT,
        required=False,
        options=[],
        tags=["topic:transaction_structure", "priority:6", "reason_code:consumer_liability"],
        related_rule_ids=[],
    ),
    Question(
        question_id="Q-TXN-007-ip-authenticity",
        title="상품의 진위·품질·저작권/IP 관련 책임은 누구에게 있나요?",
        description="작품·창작물 판매의 경우 진위·저작권 침해 클레임에 대한 책임 주체를 확인합니다.",
        answer_type=_TEXT,
        required=False,
        options=[],
        tags=["topic:transaction_structure", "priority:7", "reason_code:ip_authenticity_liability"],
        related_rule_ids=[],
    ),
    Question(
        question_id="Q-TXN-008-relationship-type",
        title="상대방(또는 우리 회사)은 단순 판매지원 용역자인가요, 매매계약 당사자(판매자)인가요, 위탁판매자인가요, 중개자인가요?",
        description="계약 제목(예: '판매지원 용역계약')과 실제 법적 지위가 다를 수 있습니다.",
        answer_type="single_choice",
        required=True,
        options=[
            QuestionOption("sales_support_service", "단순 판매지원 용역자(매매계약 당사자 아님)"),
            QuestionOption("seller_party", "매매계약 당사자(판매자)"),
            QuestionOption("consignment_seller", "위탁판매자(소유권은 공급자에게 있음)"),
            QuestionOption("intermediary", "중개자"),
            QuestionOption("unknown", "미상"),
        ],
        tags=["topic:transaction_structure", "priority:8", "reason_code:relationship_type"],
        related_rule_ids=[],
    ),
    Question(
        question_id="Q-TXN-009-existing-contract-link",
        title="이 계약은 기존 거래계약(예: 대리점/위탁판매 운영계약)과 완전히 별도의 독립된 계약인가요, 경제적으로 연계되어 있나요?",
        description="별도 계약이라는 형식만으로 독립적 거래라고 단정하지 않습니다 — 당사자 동일·동일 매장·기존 계약 종료 시 함께 종료 등 경제적 연결성을 확인합니다.",
        answer_type=_TEXT,
        required=True,
        options=[],
        tags=["topic:transaction_structure", "priority:9", "reason_code:existing_contract_dependency"],
        related_rule_ids=[],
    ),
]


def build_transaction_structure_questions() -> list[Question]:
    return list(TRANSACTION_STRUCTURE_QUESTIONS)
