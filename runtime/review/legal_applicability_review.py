"""Mandatory Legal Applicability Review — 사용자가 특정 법률의 적용 여부를
직접 물어보면(review_focus에 법률명이 등장하면), 그 법률에 대한 독립적인
분석을 rule hit 여부와 무관하게 반드시 산출한다(2026-09-02 지시).

기존 rule 엔진은 "이 조항이 문제다"라는 개별 finding만 만든다 — 사용자가
"이 계약이 하도급법에 문제가 되지 않는지 판단해달라"처럼 특정 법률의
적용 가능성 자체를 물어봤을 때, 관련 finding이 0건이라는 이유로 그 질문에
대한 답 자체가 사라지면 안 된다. 이 모듈은 그 답을 항상 만든다 — AI가
없으면 "확인 필요" stub이라도 반환하고(원인 없는 "확인 불가"), 절대
조용히 생략하지 않는다.

거래실질 우선 원칙(2026-09-02 지시 4~6): 하도급법/공정거래법/건설산업
기본법은 키워드 존재 여부가 아니라 실제 거래구조(기성품 구매 vs 사양별
주문제작, 단순 소개 vs 실제 시공수행 등)를 먼저 분석한 뒤 적용 가능성을
판단하도록 프롬프트에 명시한다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from runtime.ai.enhance import _try_json
from runtime.ai.http_openai_compatible_provider import build_messages
from runtime.ai.provider import AIProvider, AIRequest

logger = logging.getLogger(__name__)

# 법률명 별칭 사전 — review_focus 자유 텍스트에서 법률명을 탐지하는 데
# 쓴다. 계약유형·회사명과 무관한 범용 사전(2026-09-02 원칙 준수).
_KNOWN_STATUTES: dict[str, list[str]] = {
    "하도급법": ["하도급법", "하도급거래공정화에관한법률", "하도급거래 공정화에 관한 법률", "하도급거래의 공정화에 관한 법률"],
    "공정거래법": ["공정거래법", "독점규제및공정거래에관한법률", "독점규제 및 공정거래에 관한 법률"],
    "건설산업기본법": ["건설산업기본법"],
    "대리점법": ["대리점법", "대리점거래의공정화에관한법률", "대리점거래의 공정화에 관한 법률"],
    "가맹사업법": ["가맹사업법", "가맹사업거래의공정화에관한법률", "가맹사업거래의 공정화에 관한 법률"],
    "표시광고법": ["표시광고법", "표시·광고의 공정화에 관한 법률", "표시광고의 공정화에 관한 법률"],
    "개인정보보호법": ["개인정보보호법", "개인정보 보호법"],
}

# 통계적으로 자주 문의되는 3개 법률에 대해서는, 사용자가 요구한 "거래실질
# 우선" 분석 프레임을 프롬프트에 구체적으로 명시한다 — 단순 키워드 매칭이
# 아니라 사실관계를 먼저 구분하도록 강제한다.
_STATUTE_SPECIFIC_GUIDANCE: dict[str, str] = {
    "하도급법": (
        "하도급법 적용 여부는 다음 사실관계를 먼저 구분한 뒤 판단하십시오: "
        "(1) 기성품을 단순히 구매하는 거래인지, 아니면 특정 사양·규격에 따라 "
        "주문·제작을 위탁하는 거래인지(제조위탁 가능성), (2) 설계 업무 자체를 "
        "위탁하는지(용역위탁 가능성), (3) 실제 시공 행위를 위탁하는지(건설위탁 "
        "가능성), (4) 원사업자·수급사업자에 해당하려면 필요한 당사자 규모(중소기업자 "
        "여부)가 확인되는지. 이 중 어느 것에도 해당하지 않고 단순 소개·연계에 "
        "그친다면 하도급법 적용 가능성은 낮습니다. 사실관계가 불명확하면 "
        "'적용 가능성 있음(추가 확인 필요)'로 판단하고 확인이 필요한 사실관계를 "
        "구체적으로 나열하십시오 — 결론을 단정하지 마십시오."
    ),
    "공정거래법": (
        "공정거래법 적용 여부는 다음 legal effect가 실제로 존재하는지, 그리고 "
        "그 각각이 거래상 지위 남용에 해당하는지를 종합적으로 판단하십시오(단순히 "
        "'최소구매 의무가 있다'는 사실 하나만으로 위반을 단정하지 마십시오): "
        "minimum_purchase_commitment(연간 최소발주 등), exclusivity(배타적 거래"
        "요구), non_circumvention(직접거래 제한), direct_dealing_restriction, "
        "penalty_for_bypass(우회거래 위약벌), platform_dependency(플랫폼 의존 "
        "구조), rebate_or_support_payment(리베이트·지원금). 종합 판단 시 거래상 "
        "지위(누가 우위인지), 시장에서의 대안 선택가능성, 제한기간, 제한대상의 "
        "범위, 위약 수준의 과도함, 경제적 효과를 함께 고려하십시오."
    ),
    "건설산업기본법": (
        "건설산업기본법 적용 여부는 상대방이 (1) 직접 시공행위를 수행하는지, "
        "(2) 시공사를 단순히 소개·조율하는 데 그치는지, (3) 공사를 도급받아 "
        "수행하는지, (4) 건설업 등록이 필요한 업무 범위인지를 구분한 뒤 "
        "판단하십시오. 계약서상 '시공 연계·조율' 문언만으로는 직접 시공으로 "
        "단정할 수 없습니다 — 사실관계가 불명확하면 직접 시공 여부·건설업 등록"
        "보유 여부를 확인 필요 사실관계로 명시하고 결론을 단정하지 마십시오."
    ),
}


def detect_user_cited_statutes(review_focus: str | None) -> list[str]:
    """review_focus 자유 텍스트에서 사용자가 명시적으로 언급한 법률명을
    찾는다. 이 목록에 있는 법률은 rule hit 여부와 무관하게 반드시 독립
    분석 결과를 가져야 한다."""
    text = (review_focus or "")
    found: list[str] = []
    for canonical_name, aliases in _KNOWN_STATUTES.items():
        if any(alias in text for alias in aliases):
            found.append(canonical_name)
    return found


@dataclass(frozen=True)
class StatuteApplicabilityResult:
    statute: str
    applicability: str  # "높음" | "있음(추가 확인 필요)" | "낮음" | "확인 필요"
    reasoning: str
    additional_facts_needed: list[str]
    related_clauses: list[str]
    risk_level: str  # "HIGH" | "MEDIUM" | "LOW" | "확인 필요"
    source: str  # "ai" | "stub_no_ai" | "ai_call_failed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "statute": self.statute,
            "applicability": self.applicability,
            "reasoning": self.reasoning,
            "additional_facts_needed": list(self.additional_facts_needed),
            "related_clauses": list(self.related_clauses),
            "risk_level": self.risk_level,
            "source": self.source,
        }


def _stub_result(statute: str, source: str) -> StatuteApplicabilityResult:
    return StatuteApplicabilityResult(
        statute=statute,
        applicability="확인 필요",
        reasoning="AI 분석을 실행하지 못해 자동 판단이 없습니다 — 법무팀이 직접 검토해야 합니다.",
        additional_facts_needed=["AI 분석 재실행 필요"],
        related_clauses=[],
        risk_level="확인 필요",
        source=source,
    )


_SYSTEM_PROMPT_TEMPLATE = """당신은 특정 법률의 적용 가능성을 판단하는 사내변호사입니다.
사용자가 아래에 나열된 법률 각각에 대해 이 계약에 적용될 수 있는지 물었습니다.
각 법률마다 키워드가 있는지가 아니라 실제 거래의 실질(무엇을 누구에게 위탁/
공급/판매하는지, 당사자의 실제 역할)을 먼저 분석한 뒤 판단하십시오. 사실관계가
불명확하면 결론을 단정하지 말고 "적용 가능성 있음(추가 확인 필요)"로 답하고
확인이 필요한 사실관계를 구체적으로 나열하십시오 — 근거 없이 위반을 단정하는
것이 근거 없이 안전하다고 단정하는 것보다 더 위험합니다.

반드시 아래 JSON 배열 하나만 반환하십시오(설명 문장 금지, 마크다운 코드펜스 금지):
[
  {{
    "statute": "법률명(요청된 이름 그대로)",
    "applicability": "높음" | "있음(추가 확인 필요)" | "낮음",
    "reasoning": "거래실질 분석에 근거한 판단 이유 (2~4문장)",
    "additional_facts_needed": ["확인이 필요한 구체적 사실관계", ...] (없으면 빈 배열),
    "related_clauses": ["제N조" 형태로 관련 조항 표시, ...] (없으면 빈 배열),
    "risk_level": "HIGH" | "MEDIUM" | "LOW"
  }},
  ...
]

각 법률에 대한 구체적 판단 프레임:
{guidance_blocks}

요청된 법률 목록: {statute_list}"""


def build_mandatory_legal_applicability_review(
    *,
    statutes: list[str],
    contract_legal_map: dict[str, Any] | None,
    text: str,
    entity: str,
    ai_provider: AIProvider | None,
    ai_model: str | None,
    ai_timeout_sec: float | None,
    ai_max_tokens: int | None,
    ai_temperature: float | None,
) -> list[StatuteApplicabilityResult]:
    """statutes에 있는 모든 법률에 대해 독립적인 적용성 분석 결과를
    반환한다 — AI가 없거나 호출이 실패해도 각 법률마다 최소한 "확인 필요"
    stub을 반환해, 어떤 법률도 조용히 결과 없이 사라지지 않는다."""
    if not statutes:
        return []

    ai_enabled = bool(ai_provider and ai_model and ai_timeout_sec is not None and ai_max_tokens is not None and ai_temperature is not None)
    if not ai_enabled:
        return [_stub_result(s, "stub_no_ai") for s in statutes]

    guidance_blocks = "\n".join(
        f"- {s}: {_STATUTE_SPECIFIC_GUIDANCE.get(s, '일반적인 법률 적용 요건(주체·행위·목적물)을 계약 내용에 비추어 판단하십시오.')}"
        for s in statutes
    )
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(guidance_blocks=guidance_blocks, statute_list=", ".join(statutes))

    lm = contract_legal_map or {}
    lm_summary = {k: v for k, v in lm.items() if not k.startswith("_") and v}
    import json as _json
    user_payload = {
        "entity": entity,
        "contract_legal_map": lm_summary,
        "contract_text": (text or "")[:14000],
    }
    user = _json.dumps(user_payload, ensure_ascii=False)

    req = AIRequest(
        model=ai_model,
        messages=build_messages(system_prompt, user),
        temperature=float(ai_temperature),
        max_tokens=int(ai_max_tokens),
        timeout_sec=float(ai_timeout_sec),
    )
    try:
        resp = ai_provider.complete(req)
        obj = _try_json(resp.content)
    except Exception as exc:
        logger.warning("legal_applicability_review AI call failed: %s", exc)
        return [_stub_result(s, "ai_call_failed") for s in statutes]

    if not isinstance(obj, list):
        logger.warning("legal_applicability_review AI response was not a JSON array")
        return [_stub_result(s, "ai_call_failed") for s in statutes]

    by_statute: dict[str, dict[str, Any]] = {}
    for item in obj:
        if isinstance(item, dict) and isinstance(item.get("statute"), str):
            by_statute[item["statute"].strip()] = item

    results: list[StatuteApplicabilityResult] = []
    for s in statutes:
        item = by_statute.get(s)
        if item is None:
            # AI가 이 법률을 응답에서 빠뜨린 경우 — 조용히 생략하지 않고
            # stub으로라도 채운다.
            results.append(_stub_result(s, "ai_call_failed"))
            continue
        applicability = str(item.get("applicability") or "").strip()
        if applicability not in ("높음", "있음(추가 확인 필요)", "낮음"):
            applicability = "있음(추가 확인 필요)"
        risk_level = str(item.get("risk_level") or "").strip().upper()
        if risk_level not in ("HIGH", "MEDIUM", "LOW"):
            risk_level = "MEDIUM"
        additional_facts = item.get("additional_facts_needed")
        related_clauses = item.get("related_clauses")
        results.append(StatuteApplicabilityResult(
            statute=s,
            applicability=applicability,
            reasoning=str(item.get("reasoning") or "").strip() or "판단 근거가 제공되지 않았습니다.",
            additional_facts_needed=[str(x) for x in additional_facts if isinstance(x, str)] if isinstance(additional_facts, list) else [],
            related_clauses=[str(x) for x in related_clauses if isinstance(x, str)] if isinstance(related_clauses, list) else [],
            risk_level=risk_level,
            source="ai",
        ))
    return results
