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

필수 필드: parties, our_party, counterparty, party_roles, contract_purpose,
primary_obligations, payment_flow, term, termination_structure,
liability_structure, indemnity_structure, third_party_liability,
unilateral_rights, survival_obligations, amendment_structure, key_deliverables.

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
) -> ContractLegalMap:
    is_nda = contract_type_code in _NDA_TYPE_CODES
    ai_enabled = bool(ai_provider and ai_model and ai_timeout_sec is not None and ai_max_tokens is not None and ai_temperature is not None)

    if not ai_enabled:
        return ContractLegalMap(
            fields=_regex_fallback(clauses=clauses, full_text=text, entity=entity, contract_type_code=contract_type_code),
            source="regex_fallback_no_ai",
            is_nda=is_nda,
        )

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
    return ContractLegalMap(fields=fields, source="ai", is_nda=is_nda)
