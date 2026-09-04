"""Contract Legal Map — Layer 0 (Document/Contract Understanding).

변호사형 전체계약 판단 지시 (2026-09-01): 개별 조항 검토를 시작하기 전에,
계약 전체를 한 번 읽고 당사자·거래구조·의무구조·해지구조·책임구조 등을
구조화된 JSON으로 먼저 확정한다. 이 결과가 이후 모든 조항별 검토(Layer 1
공통 법률효과 분석, Layer 2 유형별 분석)의 공통 컨텍스트로 주입된다.

AI가 있으면 실제로 AI를 호출해 이 구조를 채운다(한 계약당 1회 호출 —
조항 단위로 반복 호출하지 않음). AI가 없으면(ai_provider=None) 기존
contract_overview.py의 regex 기반 4필드만으로 채워지는 축소판을 반환한다
— "AI 없이도 Layer 1 공통 검토는 항상 실행되어야 한다"는 요구사항 때문에
이 축소판도 하위 필드가 전부 None/빈 값일 뿐 dict 자체는 항상 반환한다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from runtime.ai.enhance import _try_json
from runtime.ai.http_openai_compatible_provider import build_messages
from runtime.ai.provider import AIProvider, AIRequest
from runtime.review.clause_extraction import ClauseChunk
from runtime.review.contract_overview import build_contract_overview

logger = logging.getLogger(__name__)

# 모든 계약에 공통 적용되는 필드 — 처음 보는 contract_type이어도 항상 요청한다.
UNIVERSAL_FIELDS: tuple[str, ...] = (
    "parties",
    "our_party",
    "counterparty",
    "party_roles",
    "contract_purpose",
    "primary_obligations",
    "payment_flow",
    "term",
    "termination_structure",
    "liability_structure",
    "indemnity_structure",
    "third_party_liability",
    "unilateral_rights",
    "survival_obligations",
    "amendment_structure",
    "key_deliverables",
    # 우리 회사가 이 계약의 핵심 급부를 "제공하는 쪽(provider)"인지 "받는
    # 쪽(recipient)"인지 — 기존 rule 기반 classifier/party_role.py가 처음
    # 보는 계약유형(라이선스/임대차/투자계약 등)에서 방향을 반대로 판정하는
    # 사례가 hold-out 검증에서 발견되어, 이 축만큼은 Layer 0(AI)이 확신할
    # 때 우선하는 source of truth가 되도록 별도 필드로 분리했다
    # (runtime/review/legal_map_role_override.py가 실제 override를 적용).
    "our_role_direction",
    "our_role_direction_confidence",
    # ── Transaction Map 필드 (2026-09-02 지시 — 범용 사내변호사형 검토
    # 고도화, KOTRA 3자 컨설팅계약 실사례) — 처음 보는 계약유형에서도 "돈이
    # 어디서 흐르고 누가 누구의 책임을 떠안는지"를 조항 검토 전에 먼저
    # 구조화한다. 3자 이상 계약을 2자 계약처럼 단순화하지 않도록 party_
    # rights_obligations_matrix를 별도로 요청한다.
    "economic_beneficiary",
    "third_party_payer_or_guarantor",
    "conditional_funding_structure",
    "advance_payment_exists",
    "refund_or_clawback_obligation_holder",
    "guarantee_structure",
    "failure_loss_allocation",
    "termination_settlement_structure",
    "party_rights_obligations_matrix",
    # ── 판매/위탁판매/대리판매/중개 거래구조 필드(2026-09-04 지시 — 그림닷컴
    # 판매지원 용역계약 실사례) — "판매지원 용역"이라는 계약 제목만 보고
    # 판매자·소유권을 추정하지 않기 위해, 최종 소비자와의 매매관계에서
    # 누가 무엇을 소유·판매·수령·책임지는지를 별도로 구조화한다. POS/결제
    # 단말기 명의자를 곧바로 판매자로 단정해서는 안 된다(위탁매매 구조에서는
    # 매장이 결제를 대행할 뿐 실제 판매자가 다를 수 있음).
    "seller",
    "owner_of_goods",
    "payment_recipient",
    "revenue_recipient",
    "intermediary",
    "sales_support_provider",
    "inventory_risk_holder",
    "consumer_liability_holder",
    "refund_liability",
    "ip_authenticity_liability",
    "existing_related_contract",
    "dependency_on_existing_contract",
)

# NDA류 계약일 때만 추가로 요청하는 확장 필드.
NDA_EXTENSION_FIELDS: tuple[str, ...] = (
    "mutual_or_one_way",
    "provider_receiver_roles",
    "confidential_information_scope",
    "permitted_use",
    "disclosure_rules",
    "standard_of_care",
    "return_destruction",
    "confidentiality_survival",
)

_NDA_TYPE_CODES = frozenset({"nda_confidentiality"})

_SYSTEM_PROMPT = """당신은 계약서 전체를 처음부터 끝까지 읽고 구조를 파악하는
사내변호사입니다. 개별 조항을 검토하기 전에, 이 계약이 전체적으로 어떤
거래인지, 당사자들의 실제 지위가 무엇인지, 대금·해지·책임·존속 구조가
어떻게 되어 있는지를 먼저 요약합니다.

반드시 아래 JSON 객체 하나만 반환하십시오(설명 문장 금지, 마크다운 코드
펜스 금지). 각 값은 원문에 근거해 한국어로 간결하게 서술하고, 원문에 없는
내용을 지어내지 마십시오 — 확인할 수 없으면 null을 반환하십시오.

입력에 "confirmed_transaction_facts"가 있으면, 이는 사용자가 사전질문에
직접 답변해 이미 확정한 사실관계입니다. 해당 필드(예: seller, owner_of_goods,
payment_recipient, revenue_recipient)는 원문에 명시되어 있지 않더라도
"null"이나 "미확인"으로 되돌리지 말고 그 값을 그대로 채우며, 관련된 다른
필드(예: consumer_liability_holder, party_roles)의 서술도 이 확정된
사실관계와 일관되게 작성하십시오.

필수 필드: parties, our_party, counterparty, party_roles, contract_purpose,
primary_obligations, payment_flow, term, termination_structure,
liability_structure, indemnity_structure, third_party_liability,
unilateral_rights, survival_obligations, amendment_structure, key_deliverables,
our_role_direction, our_role_direction_confidence, economic_beneficiary,
third_party_payer_or_guarantor, conditional_funding_structure,
advance_payment_exists, refund_or_clawback_obligation_holder,
guarantee_structure, failure_loss_allocation, termination_settlement_structure,
party_rights_obligations_matrix, seller, owner_of_goods, payment_recipient,
revenue_recipient, intermediary, sales_support_provider, inventory_risk_holder,
consumer_liability_holder, refund_liability, ip_authenticity_liability,
existing_related_contract, dependency_on_existing_contract.

아래 9개 필드는 "Transaction Map"입니다 — 돈이 실제로 어디서 흐르고, 누가
누구의 책임을 떠안는지를 조항 하나하나를 보기 전에 먼저 파악하는 것이
목적이므로, 계약이 몇 당사자든, 처음 보는 계약유형이든 반드시 채우십시오:
- economic_beneficiary: 이 계약의 급부(서비스·재화 등)로 실제 경제적
  이익을 얻는 당사자는 누구인가(대금을 지급하는 당사자와 다를 수 있음 —
  예: 제3자가 비용을 대고 다른 당사자가 서비스를 받는 구조).
- third_party_payer_or_guarantor: 계약당사자가 아닌 제3자, 또는 당사자 중
  하나가 다른 당사자를 위해 대금을 지급·보증·지원하는 구조인지, 있다면
  누가 누구를 위해 그렇게 하는지.
- conditional_funding_structure: 정부지원금·보조금·투자금·보험금 등 특정
  조건(자격 유지, 별도 참여계약 이행 등)이 충족되어야만 지급되는 조건부
  자금이 있는지, 조건은 무엇인지, 조건 미충족 시 어떻게 되는지.
- advance_payment_exists: 선급금(계약 이행 전 또는 이행 중 결과물 완성
  전에 지급되는 대금)이 있는지, 있다면 규모와 지급 시점.
- refund_or_clawback_obligation_holder: 선급금·지원금 등을 반환해야 하는
  사유가 발생했을 때, 그 반환채무를 누가 부담하는지(급부를 제공하지 못한
  당사자인지, 아니면 그 당사자를 위해 다른 당사자가 보증하는지).
- guarantee_structure: 한 당사자의 채무(반환·이행 등)를 다른 당사자가
  보증·연대책임지는 구조가 있는지, 있다면 누가 누구의 어떤 채무를
  보증하는지 구체적으로 서술.
- failure_loss_allocation: 핵심 급부(서비스·재화 등)의 이행이 실패했을 때,
  그로 인한 경제적 손실이 최종적으로 어느 당사자에게 귀속되는지 — 이행
  실패의 원인 제공자와 손실 부담자가 다를 수 있음에 주의.
  - termination_settlement_structure: 계약 종료(만료·중도해지 불문) 시
  미정산 대금, 기지급금의 환급, clawback(사후 회수) 등이 어떻게
  처리되는지.
- party_rights_obligations_matrix: 당사자가 3인 이상인 계약에서는 절대로
  2자 계약처럼 단순화하지 말고, 각 당사자별로 "제공하는 것/받는 것/지급
  의무/보증 의무/실패 시 책임"을 짧게 표로 서술(문자열로, 예:
  "A: 대금지급 조건부 / B: 서비스 제공 및 실패시 반환의무 / C: A를 대신해
  B의 반환채무 보증"). 당사자가 2인이면 간단히 "2자 계약, matrix 불필요"로
  답해도 됩니다.

아래 12개 필드는 판매·위탁판매·대리판매·중개·판매지원 성격의 계약에서
"최종 소비자와의 매매관계"를 구조화합니다(그림닷컴 판매지원 용역계약
실사례 — "판매지원 용역계약"이라는 제목만 보고 판매자·소유권을 추정했다가
실제로는 다른 당사자가 매입 후 재판매하는 구조였던 사고를 계기로 추가):
- seller: 최종 고객과의 매매계약상 실제 판매자(매도인)는 누구인가.
- owner_of_goods: 판매 전 상품의 소유권자는 누구이며 언제 고객에게 이전되는가.
- payment_recipient: 고객으로부터 대금을 실제로 수령하는 당사자는 누구인가 —
  **매장 POS/결제 단말기의 명의자를 곧바로 판매자·수령자로 단정하지 마십시오.**
  위탁매매 구조에서는 매장이 결제를 대행할 뿐 실제 판매자·매출귀속 주체가
  다를 수 있습니다.
- revenue_recipient: 판매대금이 누구의 매출로 인식(회계상 귀속)되는가.
- intermediary: 순수 중개자(매매계약 당사자가 아니며 수수료만 받는 자)가
  있다면 누구인가.
- sales_support_provider: 매매계약 당사자는 아니지만 상담·전시·결제처리
  등 판매를 지원하는 용역 제공자가 있다면 누구인가.
- inventory_risk_holder: 재고·분실·파손 위험을 부담하는 당사자는 누구인가.
- consumer_liability_holder: 배송·하자·반품·환불 등 소비자 클레임에 대한
  책임 주체는 누구인가.
- refund_liability: 판매 취소·환불 발생 시 그 비용/수수료 반환 의무를
  귀책사유에 따라 어떻게 배분하는지(구분이 없다면 그렇게 명시).
- ip_authenticity_liability: 상품(특히 작품·창작물)의 진위·품질·저작권/IP
  침해에 대한 책임 주체는 누구인가.
- existing_related_contract: 이 계약과 경제적으로 연결된 기존 거래계약
  (예: 별도의 대리점/위탁판매 운영계약)이 있는지, 있다면 그 계약명/당사자.
- dependency_on_existing_contract: "별도 계약"이라는 형식만으로 독립적
  거래라고 단정하지 말고, 당사자 동일성·동일 매장 사용·계약기간 연동·
  기존 계약 종료 시 함께 종료되는지 등 실질적 경제적 종속 관계가 있는지.

our_role_direction은 반드시 아래 세 값 중 하나만 사용하십시오(다른 표현 금지):
- "provider": 우리 회사(our_party)가 이 계약의 핵심 급부(재화, 용역, 자금,
  사용권, 공간, 기술 등 무엇이든)를 상대방에게 제공/공급/대여/제조/부여하는
  쪽이며, 상대방이 그 대가(대금·사용료·임차료 등)를 우리에게 지급하는 구조.
- "recipient": 반대로 우리 회사가 그 핵심 급부를 상대방으로부터 받거나
  구매·임차·사용하며, 우리가 그 대가를 상대방에게 지급하는 구조.
- "mutual_or_neutral": 방향성이 없는 계약(비밀유지계약 등 상호형)이거나,
  자금 흐름과 급부 방향이 다자간이라 단일 축으로 판단할 근거가 부족한 경우.
our_role_direction_confidence는 "high"(원문에 대금 지급 방향·급부 제공 방향이
명확히 서술됨) / "medium" / "low"(추정에 가까움) 중 하나. 확신이 없으면
절대 "high"를 쓰지 마십시오 — 이 필드는 다른 자동 분류기 결과를 덮어쓰는 데
쓰이므로, 근거가 약하면 "medium"/"low"로 낮추는 것이 "high"로 잘못 답하는
것보다 안전합니다.

이 계약이 비밀유지계약(NDA)류라면 다음 필드도 함께 채우십시오(NDA가 아니면
전부 null): mutual_or_one_way(상호형인지 일방형인지), provider_receiver_roles
(정보 제공자/수신자가 고정인지 정보별로 바뀌는지), confidential_information_scope,
permitted_use, disclosure_rules, standard_of_care, return_destruction,
confidentiality_survival.

party_roles는 우리 회사(our_party로 지정된 회사)가 이 계약에서 실제로 어떤
법적 지위(예: 공급자/구매자/수신자/제공자 등)인지를 명시하고, 정보·거래
방향에 따라 지위가 바뀌는 구조라면 그렇게 명시하십시오. 확정할 수 없는데
방향성 있는 role(공급자/구매자 등)을 임의로 추정하지 말고, 근거가 부족하면
"확인 필요"라고 쓰십시오."""


@dataclass(frozen=True)
class ContractLegalMap:
    fields: dict[str, Any]
    source: str  # "ai" | "regex_fallback_no_ai" | "ai_call_failed_fallback"
    is_nda: bool

    def to_dict(self) -> dict[str, Any]:
        return {**self.fields, "_legal_map_source": self.source, "_is_nda": self.is_nda}


def _regex_fallback(*, clauses: list[ClauseChunk] | None, full_text: str, entity: str, contract_type_code: str) -> dict[str, Any]:
    overview = build_contract_overview(clauses=clauses or [], full_text=full_text)
    fields: dict[str, Any] = {k: None for k in UNIVERSAL_FIELDS}
    fields["contract_purpose"] = overview.purpose
    fields["term"] = overview.contract_term
    fields["payment_flow"] = overview.payment_structure
    fields["our_party"] = entity or None
    if contract_type_code in _NDA_TYPE_CODES:
        for k in NDA_EXTENSION_FIELDS:
            fields[k] = None
    return fields


def build_contract_legal_map(
    *,
    ai_provider: AIProvider | None,
    ai_model: str | None,
    ai_timeout_sec: float | None,
    ai_max_tokens: int | None,
    ai_temperature: float | None,
    entity: str,
    contract_type: str,
    contract_type_code: str,
    text: str,
    clauses: list[ClauseChunk] | None,
    answers: dict[str, Any] | None = None,
) -> ContractLegalMap:
    is_nda = contract_type_code in _NDA_TYPE_CODES
    ai_enabled = bool(ai_provider and ai_model and ai_timeout_sec is not None and ai_max_tokens is not None and ai_temperature is not None)

    if not ai_enabled:
        return ContractLegalMap(
            fields=_regex_fallback(clauses=clauses, full_text=text, entity=entity, contract_type_code=contract_type_code),
            source="regex_fallback_no_ai",
            is_nda=is_nda,
        )

    # [canonical_transaction_facts, 2026-09-04 지시] — 사용자가 사전질문에
    # 이미 답변한 판매자/소유자 등 사실관계가 있으면, Layer-0 AI 호출부터
    # 이를 확정된 값으로 전제하도록 명시한다 — AI가 원문에 없다는 이유로
    # 스스로 "미확인"이라 적거나 다른 당사자로 추정하는 것을 막는다. 이후
    # `apply_transaction_structure_answers()`가 이 필드를 어떤 경우에도
    # 사용자 답변으로 최종 덮어쓰지만, 그 전 단계인 AI의 다른 필드 추론
    # (예: 거래구조 설명)도 이 사실과 일관되도록 미리 전달한다.
    from runtime.review.canonical_transaction_facts import (
        build_ai_fact_directive,
        build_canonical_transaction_facts_from_answers,
    )
    _fact_directive = build_ai_fact_directive(build_canonical_transaction_facts_from_answers(answers)) if answers else ""

    user_payload = {
        "entity": entity,
        "contract_type": contract_type,
        "contract_type_code": contract_type_code,
        "is_nda_hint": is_nda,
        # 전체 계약 텍스트를 통째로 보낸다 — 조항별 호출과 달리 이 호출은
        # 계약당 단 1회이므로 비용 영향이 제한적이다. 과도하게 긴 계약은
        # 앞부분(당사자/목적/정의) + 뒷부분(서명/부속서)이 구조 파악에
        # 가장 중요하므로 앞 12000자로 자른다.
        "contract_text": (text or "")[:12000],
        "confirmed_transaction_facts": _fact_directive or None,
    }
    import json as _json
    user = _json.dumps(user_payload, ensure_ascii=False)
    req = AIRequest(
        model=ai_model,
        messages=build_messages(_SYSTEM_PROMPT, user),
        temperature=float(ai_temperature),
        max_tokens=int(ai_max_tokens),
        timeout_sec=float(ai_timeout_sec),
    )
    try:
        resp = ai_provider.complete(req)
        obj = _try_json(resp.content)
    except Exception as exc:
        logger.warning("contract_legal_map AI call failed, falling back to regex: %s", exc)
        return ContractLegalMap(
            fields=_regex_fallback(clauses=clauses, full_text=text, entity=entity, contract_type_code=contract_type_code),
            source="ai_call_failed_fallback",
            is_nda=is_nda,
        )
    if not isinstance(obj, dict):
        logger.warning("contract_legal_map AI response was not a JSON object, falling back to regex")
        return ContractLegalMap(
            fields=_regex_fallback(clauses=clauses, full_text=text, entity=entity, contract_type_code=contract_type_code),
            source="ai_call_failed_fallback",
            is_nda=is_nda,
        )

    expected = list(UNIVERSAL_FIELDS) + (list(NDA_EXTENSION_FIELDS) if is_nda else [])
    fields = {k: obj.get(k) for k in expected}
    # regex fallback 값(계약목적/기간/대금구조)을 AI가 null로 남긴 필드의
    # 최소 안전망으로 보강 — AI가 놓친 경우에도 완전히 비어있지 않게 한다.
    regex_fields = _regex_fallback(clauses=clauses, full_text=text, entity=entity, contract_type_code=contract_type_code)
    for k in ("contract_purpose", "term", "payment_flow"):
        if not fields.get(k) and regex_fields.get(k):
            fields[k] = regex_fields[k]
    # our_role_direction/confidence는 rule-based classifier/party_role 결과를
    # 덮어쓰는 데 쓰이는 필드이므로, 지정된 enum 값이 아니면 무조건 버린다
    # (환각으로 인한 임의 override를 원천 차단).
    if fields.get("our_role_direction") not in ("provider", "recipient", "mutual_or_neutral"):
        fields["our_role_direction"] = None
    if fields.get("our_role_direction_confidence") not in ("high", "medium", "low"):
        fields["our_role_direction_confidence"] = None
    return ContractLegalMap(fields=fields, source="ai", is_nda=is_nda)
