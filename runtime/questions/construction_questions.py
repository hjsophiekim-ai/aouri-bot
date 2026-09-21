"""건설·인테리어 공사계약의 지위별 사전질문 묶음.

2026-09-21 지시 3항 —
  "계약유형을 확정한 뒤 해당 유형에서 실제 판단에 필요한 질문만 하세요.
   건설공사 수급인 계약의 기본 질문: 공사대금 미회수 / 설계변경·추가공사 /
   공기연장·지체상금 / 검수·준공 / 지급유보·상계 / 하자·보증 / 유치권 포기 /
   재하도급 / 타 공종 간섭 / 안전·산재 / 중도해지."
  "건설공사에서 IP 가 부수 조항에 불과하면 '저작물을 어느 매체·기간·지역에서
   활용하는가' 같은 IP 중심 필수질문을 생성하지 마세요."

무엇이 문제였나
─────────────
실측(인테리어 2차 본계약, 2026-09-21). 담당자는 "퍼시스가 발주처로부터
인테리어 공사를 도급받아 진행", "유치권포기각서에 대한 내용도 요청" 이라고
적었는데, 나간 사전질문 5개는 이랬다.

    Q-EFF-ip-scope            이 계약으로 취득하는 지식재산을 앞으로 어디까지
                              활용할 계획인가요? (매체·기간·지역·재가공)
    Q-EFF-liability-exposure  최대 손해 규모는?
    Q-EFF-subcontract-plan    **상대방이** 이 업무의 일부를 제3자에게 맡길
                              예정인가요?
    Q-EFF-delivery-acceptance 검수·인수의 합격 기준은?
    Q-FOCUS-other             추가로 확인할 사실관계가 있나요?

담당자는 "지식재산을 취득하지 않습니다" 라고 답해야 했고, 재하도급 질문은
방향이 거꾸로였다(재하도급을 하는 쪽은 우리다). 원인은 건설계약 전용 질문
묶음이 **아예 없어서**, 거래 원형에서 기계적으로 만들어지는 일반 질문
(`effect_questions`)이 그 자리를 채웠기 때문이다.

설계
────
· 지위가 확정된 경우에만 낸다. 확정 전에는 지위 질문(Q-CONST-ROLE-001)이
  먼저다 — 지위를 모르면 어떤 질문이 필요한지도 정해지지 않는다.
· 계약 문언에 그 위험이 실제로 있을 때만 묻는다. 유치권 포기 문언이 없는
  계약에 "포기각서를 요구받았습니까" 를 묻지 않는다.
· 담당자가 검토요청에 이미 쓴 내용은 다시 묻지 않는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from runtime.questions.model import Question, QuestionOption

#: 이 묶음이 만드는 질문의 id 접두사. 질문-모델 정합성 게이트가 이것으로
#: "건설 계약에 건설 질문이 나갔는가" 를 확인한다.
QUESTION_ID_PREFIX = "Q-CONST-"

#: 건설공사 계약에서 **성립하지 않는** 일반 질문. 지시 3항이 명시적으로 든
#: IP 중심 질문이 여기 해당한다 — 공사도급에서 설계 결과물의 귀속은 부수
#: 조항이고, 우리가 취득해서 활용할 지식재산이 아니다.
INCOMPATIBLE_QUESTION_IDS: tuple[str, ...] = (
    "Q-EFF-ip-scope",
    "Q-EFF-ip-ownership",
    "Q-EFF-license-scope",
)


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


@dataclass(frozen=True)
class ConstructionQuestion:
    question_id: str
    title: str
    description: str
    topic: str
    #: 계약 문언에 이 위험이 있을 때만 묻는다. None 이면 항상 묻는다.
    trigger: re.Pattern[str] | None = None
    options: tuple[tuple[str, str], ...] = ()
    required: bool = False


#: 수급인(+재하도급인) — 지시 3항이 열거한 순서 그대로.
CONTRACTOR_QUESTIONS: tuple[ConstructionQuestion, ...] = (
    ConstructionQuestion(
        question_id="Q-CONST-payment-recovery",
        title="이 발주처로부터 공사대금을 받는 데 우려되는 점이 있나요?",
        description=(
            "과거 지급 지연·유보 경험, 발주처의 자금 사정, 상위 계약(시행사·"
            "금융)에 대금이 연동되는지를 알려 주시면 대금 회수 사슬(준공검사→"
            "기성확정→지급유보→상계→잔금)을 그 사정에 맞춰 검토합니다."
        ),
        topic="payment_recovery",
        required=True,
    ),
    ConstructionQuestion(
        question_id="Q-CONST-change-order",
        title="설계변경·추가공사가 발생할 가능성이 있나요? 있다면 어떤 부분인가요?",
        description=(
            "추가공사 대금 분쟁의 대부분은 '지시는 구두로, 청구는 준공 후에' "
            "이루어져 발생합니다. 예상되는 변경 항목을 알려 주시면 계약금액 "
            "조정 절차와 단가 기준을 그 항목 기준으로 봅니다."
        ),
        topic="change_order",
        required=True,
    ),
    ConstructionQuestion(
        question_id="Q-CONST-schedule",
        title="공사기간을 지키는 데 우려되는 요인이 있나요? (선행공정 지연, 착수일 통지 등)",
        description=(
            "공기연장 사유를 계약에 넣어 두지 않으면 남의 귀책으로 늦어져도 "
            "지체상금을 우리가 부담합니다. 실제 예상되는 지연 요인을 알려 주십시오."
        ),
        topic="schedule",
    ),
    ConstructionQuestion(
        question_id="Q-CONST-acceptance",
        title="준공검사·인수인계는 실무적으로 어떻게 진행하기로 했나요?",
        description=(
            "검사 기한, 합격 간주 여부, 사용승인 취득과의 연동 여부에 따라 "
            "잔금 지급 시점이 달라집니다."
        ),
        topic="acceptance",
    ),
    ConstructionQuestion(
        question_id="Q-CONST-withholding",
        title="발주처가 대금의 일부를 유보하거나 다른 채권과 상계할 것으로 예상되나요?",
        description=(
            "유보 사유와 한도가 제한되지 않으면 다툼이 있다는 주장만으로 대금 "
            "전액이 묶일 수 있습니다."
        ),
        topic="withholding",
        trigger=_rx(r"유보|상계|공제|차감"),
    ),
    ConstructionQuestion(
        question_id="Q-CONST-guarantee",
        title="이행보증·하자보수보증의 발급 한도와 비용 부담은 확인되었나요?",
        description=(
            "보증 요구가 과다하면 그 자체가 자금 부담이고, 보증기관 한도를 "
            "넘으면 계약 이행 자체가 막힙니다."
        ),
        topic="guarantee",
        trigger=_rx(r"보증|보험증권|하자보수"),
    ),
    ConstructionQuestion(
        question_id="Q-CONST-lien-waiver",
        title="유치권 포기각서 제출을 요구받았나요? 요구받았다면 언제·어느 대금의 조건인가요?",
        description=(
            "유치권은 공사대금을 받지 못했을 때 남는 마지막 채권보전 수단입니다. "
            "무조건 포기하면 대금 미지급 시 현장을 점유할 근거가 사라집니다."
        ),
        topic="lien_waiver",
        trigger=_rx(r"유치권|포기각서|불행사"),
        required=True,
    ),
    ConstructionQuestion(
        question_id="Q-CONST-subcontract",
        title="우리가 어느 공종을 재하도급할 예정인가요?",
        description=(
            "재하도급을 하면 우리 회사가 원사업자가 되어 하도급법이 **재하도급 "
            "계약에** 적용됩니다. 원도급 계약과는 적용 관계가 다르므로 구분해 "
            "검토합니다."
        ),
        topic="subcontract",
        trigger=_rx(r"하도급|재하도급|제3자"),
    ),
    ConstructionQuestion(
        question_id="Q-CONST-interface",
        title="같은 현장에서 다른 공종(건축·소방·클린룸 등)이 함께 진행되나요?",
        description=(
            "공구 인수 지연과 타 공종 간섭은 우리 귀책이 아닌데도 공기 지연과 "
            "복구 비용으로 돌아옵니다. 병행 공종이 있으면 경계와 책임 분담을 "
            "함께 봅니다."
        ),
        topic="interface",
        trigger=_rx(r"분리\s*발주|타\s*공종|공구\s*인수|병행|간섭"),
    ),
    ConstructionQuestion(
        question_id="Q-CONST-safety",
        title="현장 안전·보건 관리 주체와 산재 발생 시 책임 분담은 어떻게 정리되어 있나요?",
        description=(
            "중대재해처벌법상 의무는 계약으로 면제되지 않습니다. 도급인 관리영역의 "
            "사고까지 우리가 떠안는 구조인지 확인합니다."
        ),
        topic="safety",
        trigger=_rx(r"안전|산재|재해|중대재해|산업안전"),
    ),
    ConstructionQuestion(
        question_id="Q-CONST-termination",
        title="공사가 중도에 해지될 가능성이 있나요? 있다면 기성 정산은 어떻게 하기로 했나요?",
        description=(
            "발주처가 사유 없이 해지할 수 있고 기성·투입비 정산이 보장되지 않으면, "
            "이미 투입한 공사원가를 회수하지 못합니다."
        ),
        topic="termination",
        trigger=_rx(r"해지|해제|중지|중단"),
    ),
)

#: 도급인 — 우리가 발주하는 쪽일 때. 방향이 반대다.
OWNER_QUESTIONS: tuple[ConstructionQuestion, ...] = (
    ConstructionQuestion(
        question_id="Q-CONST-owner-schedule",
        title="공기 지연이 우리 사업 일정(입주·개점·사용승인)에 어떤 영향을 주나요?",
        description="지체상금 수준과 공정관리 의무의 강도를 그 영향에 맞춰 봅니다.",
        topic="schedule",
        required=True,
    ),
    ConstructionQuestion(
        question_id="Q-CONST-owner-quality",
        title="준공검사·하자보수는 누가 어떤 기준으로 확인하나요?",
        description="검사 기준과 하자담보 기간·보증금이 확보되어 있는지 봅니다.",
        topic="acceptance",
    ),
    ConstructionQuestion(
        question_id="Q-CONST-owner-safety",
        title="현장 안전관리와 사고 발생 시 책임 분담은 어떻게 정리되어 있나요?",
        description="발주자로서 부담하는 법정 의무와 계약상 분담을 함께 봅니다.",
        topic="safety",
    ),
    ConstructionQuestion(
        question_id="Q-CONST-owner-subcontract",
        title="수급인의 재하도급을 어디까지 허용할 계획인가요?",
        description="일괄하도급 금지와 사전 승인 절차가 필요한지 판단합니다.",
        topic="subcontract",
        trigger=_rx(r"하도급|재하도급"),
    ),
)


def _already_covered(q: ConstructionQuestion, answered_text: str) -> bool:
    """담당자가 검토요청·기존 답변에서 이미 말한 주제인가."""
    if not answered_text:
        return False
    keywords = {
        "payment_recovery": ("대금", "미수", "지급 지연"),
        "change_order": ("설계변경", "추가공사", "변경"),
        "schedule": ("공기", "공사기간", "지연"),
        "acceptance": ("준공", "검수", "검사"),
        "withholding": ("유보", "상계", "공제"),
        "guarantee": ("보증", "보험"),
        "lien_waiver": ("유치권", "포기각서"),
        "subcontract": ("재하도급", "하도급"),
        "interface": ("타 공종", "분리발주", "공구"),
        "safety": ("안전", "산재", "중대재해"),
        "termination": ("해지", "해제"),
    }.get(q.topic, ())
    return any(k in answered_text for k in keywords)


def build_construction_questions(
    *,
    model: Any,
    contract_text: str,
    answered_topics: str = "",
    max_questions: int = 7,
) -> list[Question]:
    """지위에 맞는 건설 사전질문. 지위가 확정되지 않았으면 빈 목록."""
    if not getattr(model, "is_construction", False):
        return []
    if not getattr(model, "construction_confident", False):
        return []
    if not getattr(model, "is_settled", False):
        return []

    pack = OWNER_QUESTIONS if getattr(model, "is_owner_side", False) else CONTRACTOR_QUESTIONS
    body = str(contract_text or "")
    answered = str(answered_topics or "")

    out: list[Question] = []
    for q in pack:
        if q.trigger is not None and not q.trigger.search(body):
            continue
        if not q.required and _already_covered(q, answered):
            continue
        out.append(
            Question(
                question_id=q.question_id,
                title=q.title,
                description=q.description,
                answer_type="text" if not q.options else "single_choice",
                required=q.required,
                options=[QuestionOption(v, l) for v, l in q.options],
                tags=[f"topic:{q.topic}", "pack:construction"],
                related_rule_ids=[],
            )
        )
        if len(out) >= max_questions:
            break
    return out
