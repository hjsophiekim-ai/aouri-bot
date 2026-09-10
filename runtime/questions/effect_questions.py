"""법률효과 기반 **기본 사전질문** — 계약유형 질문세트가 없어도 항상 나온다.

2026-09-10 아키텍처 지시 항목 4 — "사전 질문은 (a) 현재 계약의 법률효과를
판단하는 데 꼭 필요한 사실, (b) 사용자가 이미 설명하지 않은 사실만 물어볼 것.
유형별 canned question 금지."

canned question 을 범위 게이트(`question_scope`)로 막고 나니, 그 게이트를
통과하는 질문세트가 없는 계약(라이선스·대물교환·공사도급)에서 질문이 0건이
됐다. 잘못된 질문보다는 낫지만, 물어야 할 것을 못 묻는 것도 같은 실패다.

그래서 질문도 finding 과 같은 방식으로 만든다 — **조항의 법률효과**에서
직접. 배상 한도가 있는 계약이면 노출 규모를 물어야 하고, 개인정보가 오가는
계약이면 동의 징구 주체를 물어야 한다. 그 계약이 어느 유형이든.

각 질문은 두 조건을 모두 만족해야 만들어진다.

  1. 그 법률효과가 이 계약에 **실재**한다(effect_counts 에 잡혔다).
  2. 그 답을 계약 문언에서 **찾을 수 없다**(계약 전체를 검색해 확인).

두 번째 조건이 "계약서에 이미 답이 있는 것은 묻지 않는다"를 보장한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from runtime.questions.model import Question
from runtime.review.clause_effect import (
    ARCHETYPE_BARTER,
    EFFECT_CHANGE,
    EFFECT_CONFIDENTIALITY,
    EFFECT_DELIVERY,
    EFFECT_IP,
    EFFECT_LIABILITY,
    EFFECT_OWNERSHIP,
    EFFECT_PAYMENT,
    EFFECT_PRIVACY,
    EFFECT_SUBCONTRACT,
    EFFECT_TERMINATION,
    ContractEffectProfile,
)


@dataclass(frozen=True)
class EffectQuestion:
    question_id: str
    effect: str
    title: str
    why: str
    #: 계약 전체에 이 패턴이 있으면 이미 답이 있는 것이므로 묻지 않는다.
    answered_if: re.Pattern[str] | None = None


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


EFFECT_QUESTIONS: tuple[EffectQuestion, ...] = (
    EffectQuestion(
        question_id="Q-EFF-ip-scope",
        effect=EFFECT_IP,
        title="이 계약으로 취득하는 지식재산을 앞으로 어디까지 활용할 계획인가요? (매체·기간·지역·재가공 포함 여부)",
        why="활용 계획이 계약상 허락 범위를 넘으면 추가 대가를 요구받거나 사용을 중단해야 합니다. 2차적저작물작성권 명시 필요 여부가 이 답에 달려 있습니다.",
        answered_if=_rx(r"기간·지역|매체(?:를|의)?\s*(?:불문|제한\s*없)|2차적저작물(?:작성권)?"),
    ),
    EffectQuestion(
        question_id="Q-EFF-payment-basis",
        effect=EFFECT_PAYMENT,
        title="대가(금액·단가)를 어떤 근거로 산정했나요? 산정 근거 자료가 있나요?",
        why="산정 근거가 없으면 세무상 시가 적정성(부가가치세법 제29조)과 특수관계인 거래 판단에서 다툼이 생기고, 분쟁 시 대가의 합리성을 입증하기 어렵습니다.",
        answered_if=_rx(r"산정\s*(?:기준|근거)|견적서에\s*따라|단가표|시가에\s*근거"),
    ),
    EffectQuestion(
        question_id="Q-EFF-liability-exposure",
        effect=EFFECT_LIABILITY,
        title="이 거래에서 실제로 발생할 수 있는 최대 손해 규모는 어느 정도인가요?",
        why="배상 한도를 계약 대가 기준으로 제안할지, 별도 금액으로 제안할지가 이 답에 따라 달라집니다. 한도 없이 두면 대가를 크게 넘는 청구에 노출됩니다.",
        answered_if=_rx(r"배상\s*(?:총액|한도|상한)|책임\s*(?:한도|상한)|limitation\s+of\s+liability"),
    ),
    EffectQuestion(
        question_id="Q-EFF-privacy-consent",
        effect=EFFECT_PRIVACY,
        title="개인정보(초상·연락처 등)의 동의는 누가, 어떤 항목으로 받나요?",
        why="동의 징구 주체가 개인정보처리자가 되어 수집·이용 목적·보유기간·제3자 제공 동의를 갖출 의무를 집니다. 주체가 정해지지 않으면 양측 모두 미이행 상태가 됩니다.",
        answered_if=_rx(r"동의(?:서)?를?\s*(?:징구|받아|확보)|보유기간|수집·?\s*이용\s*목적"),
    ),
    EffectQuestion(
        question_id="Q-EFF-subcontract-plan",
        effect=EFFECT_SUBCONTRACT,
        title="상대방이 이 업무의 일부를 제3자에게 맡길 예정인가요? 예정이라면 어느 부분인가요?",
        why="실제 재위탁이 있으면 그 제3자가 이행 주체가 되고 비밀정보·개인정보가 흘러갑니다. 동의권과 사용자책임 조항의 필요 수준이 이 답에 달려 있습니다.",
        answered_if=_rx(r"사전\s*(?:서면)?\s*동의를?\s*(?:받아|얻어)|재위탁(?:을)?\s*(?:금지|할\s*수\s*없)"),
    ),
    EffectQuestion(
        question_id="Q-EFF-termination-recovery",
        effect=EFFECT_TERMINATION,
        title="상대방이 이행하지 않아 계약이 종료되면, 이미 제공한 것을 실제로 회수할 수 있나요?",
        why="회수가 현실적으로 어렵다면 반환청구 조항만으로는 부족하고 보증·담보 또는 단계적 이행 구조가 필요합니다.",
        answered_if=_rx(r"반환(?:하여야|한다|청구)|원상\s*회복|보증(?:보험|증권)|담보를?\s*제공"),
    ),
    EffectQuestion(
        question_id="Q-EFF-delivery-acceptance",
        effect=EFFECT_DELIVERY,
        title="검수·인수의 합격 기준을 실무적으로 어떻게 정하기로 했나요?",
        why="기준이 없으면 검수권이 사실상 자의적 거절권으로 작동해 대금 지급과 납기 책임이 동시에 불안정해집니다.",
        answered_if=_rx(r"검수\s*기준|합격\s*기준|사양(?:서)?에\s*따라|acceptance\s+criteria"),
    ),
    EffectQuestion(
        question_id="Q-EFF-ownership-risk",
        effect=EFFECT_OWNERSHIP,
        title="목적물의 운송·보관 중 사고 위험은 어느 쪽이 부보(보험)하나요?",
        why="소유권·위험 이전 시점과 보험 부보 주체가 어긋나면 사고 시 어느 쪽도 보상을 받지 못하는 공백이 생깁니다.",
        answered_if=_rx(r"보험(?:에)?\s*가입|부보|위험(?:은|이).{0,30}부담"),
    ),
    EffectQuestion(
        question_id="Q-EFF-confidentiality-scope",
        effect=EFFECT_CONFIDENTIALITY,
        title="상대방에게 제공할 정보의 범위가 정해졌나요? 우리가 이미 보유한 정보와 겹치나요?",
        why="기보유 정보·독자 개발 정보가 비밀유지 대상에 함께 묶이면, 우리 자체 사업 활동이 의무 위반으로 주장될 수 있습니다.",
        answered_if=_rx(r"이미\s*(?:알고|보유)|독자적으로\s*개발|공지(?:의|된)|independently\s+developed"),
    ),
    EffectQuestion(
        question_id="Q-EFF-change-order",
        effect=EFFECT_CHANGE,
        title="업무 범위의 추가·변경이 예상되나요? 예상된다면 대가는 어떻게 조정하기로 했나요?",
        why="조정 절차가 없으면 추가 업무를 수행하고도 대가를 청구할 근거가 없고, 동시에 원래 납기 지연의 책임만 남습니다.",
        answered_if=_rx(r"변경.{0,30}(?:대가|비용|기간).{0,20}(?:조정|합의)|추가.{0,20}대가"),
    ),
)

#: 대물교환(무현금) 구조에서만 물어야 하는 사실.
BARTER_QUESTIONS: tuple[EffectQuestion, ...] = (
    EffectQuestion(
        question_id="Q-EFF-barter-valuation",
        effect=EFFECT_PAYMENT,
        title="교환하는 급부의 가액을 어떤 기준으로 동일하게 산정했나요? (소비자가·시가·견적 등)",
        why="교환거래의 과세표준은 공급한 재화·용역의 시가입니다(부가가치세법 제29조). 소비자가 기준이 시가와 다르면 부가가치세·법인세 추징 위험이 생기고, 특수관계인 거래라면 부당행위계산 부인까지 이어질 수 있습니다.",
        answered_if=_rx(r"시가에\s*근거|시가로\s*한다|감정평가|산정\s*근거를?\s*첨부"),
    ),
    EffectQuestion(
        question_id="Q-EFF-barter-invoice-timing",
        effect=EFFECT_PAYMENT,
        title="양측 세금계산서의 발행 시기를 서로 맞추기로 합의했나요?",
        why="공급시기가 어긋나면 한쪽이 먼저 발행하고 다른 쪽이 늦게 발행해 가산세·매입세액 불공제 문제가 생깁니다.",
        answered_if=_rx(r"발행\s*시기|같은\s*날|동일한\s*날|공급시기"),
    ),
)


def build_effect_questions(
    *,
    profile: ContractEffectProfile,
    contract_text: str,
    answered_topics: str = "",
    max_questions: int = 5,
) -> list[Question]:
    """계약의 법률효과에서 직접 사전질문을 만든다.

    `answered_topics` 는 사용자가 이미 설명한 내용(검토요청·기존 답변)이다.
    그 안에 답이 있으면 묻지 않는다(지시 항목 4의 (b) 조건).
    """
    body = str(contract_text or "")
    already = str(answered_topics or "")
    candidates: list[EffectQuestion] = []

    if profile.archetype == ARCHETYPE_BARTER or profile.is_non_monetary:
        candidates.extend(BARTER_QUESTIONS)
    candidates.extend(EFFECT_QUESTIONS)

    out: list[Question] = []
    for eq in candidates:
        if not profile.has(eq.effect):
            continue
        if eq.answered_if is not None and eq.answered_if.search(body):
            continue
        if eq.answered_if is not None and already and eq.answered_if.search(already):
            continue
        out.append(
            Question(
                question_id=eq.question_id,
                title=eq.title,
                description=eq.why,
                answer_type="text",
                required=False,
                options=[],
                tags=[
                    f"topic:{eq.effect}",
                    "source:effect_questions",
                    f"archetype:{profile.archetype}",
                ],
                related_rule_ids=[],
            )
        )
        if len(out) >= max_questions:
            break
    return out
