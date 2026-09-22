"""Legal Map 의 "미기재" 판정을 계약 원문으로 확인한다.

2026-09-21 4차 지시 3항 —
  "비밀유지기간, 외부 협력업체, Background IP, Foreground IP, 개인정보
   처리경계가 실제 계약에 있으면 Legal Map 에서 절대 '미기재' 로 표시하지
   마세요. Legal Map 과 조항별 검토결과가 모순되면
   REVIEW_FAILED_LEGAL_MAP_CONTRADICTION."

왜 비어 있었나
────────────
Legal Map 은 AI 가 채운다. AI 를 쓰지 않거나 호출이 실패하면 정규식
fallback 이 도는데, 그것이 채우는 축은 사실상 `contract_purpose` 하나다.
그 상태로 완결성 게이트를 돌리면 계약에 **실재하는** 축까지 전부 미기재가
된다. 실측(상호 NDA 수정안, 2026-09-21):

    missing_blocking = 우리 회사의 지위, 핵심 급부, 대가 지급 구조,
                       검수/인도/준공 조건, 지식재산/자료 귀속

지식재산 귀속은 제9조에, 우리 지위는 canonical_state 에 이미 있다. 대가
지급·검수는 NDA 에 **없는 것이 정상**이다(그 축은 유형 게이트가 따로
걸러야 한다). 셋 다 성격이 다른데 한 줄로 "미기재" 가 됐다.

이 모듈이 하는 일
──────────────
Map 필드가 비어 있어도 (1) 이미 확정된 canonical 값이 있거나 (2) 계약
원문이 그 축을 규정하고 있으면 **채워진 것으로 본다**. 무엇을 근거로
채웠는지 함께 남긴다 — 조용히 채우면 나중에 그 값이 어디서 왔는지 알 수
없다.

새로 판단하지 않는다. 이미 있는 것을 못 본 것을 고칠 뿐이다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

REVIEW_FAILED_LEGAL_MAP_CONTRADICTION = "REVIEW_FAILED_LEGAL_MAP_CONTRADICTION"


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


#: 축 → 계약 원문에서 그 축이 규정되어 있음을 보여주는 문형.
#: 낱말 하나가 아니라 **규정하는 문장**을 찾는다 — "비밀"이라는 낱말이
#: 있다고 비밀유지 구조가 정해진 것은 아니다.
AXIS_TEXT_EVIDENCE: dict[str, re.Pattern[str]] = {
    "primary_obligations": _rx(
        r"비밀유지의무[^.\n]{0,60}(?:부담|적용|이행)"
        r"|비밀정보를[^.\n]{0,40}(?:사용|제공|공개)하[^.\n]{0,30}아니"
        r"|목적을?\s*위해서만[^.\n]{0,30}사용"
    ),
    "ip_and_data_ownership": _rx(
        r"(?:지식재산권?|권리)[^.\n]{0,60}귀속"
        r"|(?:체결\s*전부터|이전부터)\s*보유[^.\n]{0,80}귀속"
        r"|양도, 허락 또는 부여한 것으로 보지"
    ),
    "term": _rx(
        r"비밀유지의무는[^.\n]{0,60}(?:\d+\s*년|영업비밀)"
        r"|효력이\s*발생한다|계약\s*기간[^.\n]{0,40}(?:년|개월|까지)"
    ),
    "liability_structure": _rx(
        r"손해를?\s*배상|배상\s*범위[^.\n]{0,60}(?:직접손해|한정|제외)"
        r"|책임을\s*부담한다"
    ),
    "indemnity_structure": _rx(
        r"간접손해|특별손해|결과손해|일실이익|배상\s*범위"
    ),
    "termination_structure": _rx(
        r"(?:계약이?|협력이?)\s*(?:종료|해지|해제)[^.\n]{0,60}(?:경우|때)"
        r"|반환\s*또는\s*폐기"
    ),
    "third_party_liability": _rx(
        r"제3자[^.\n]{0,80}(?:제공|공개|참여)"
        r"|협력업체[^.\n]{0,60}(?:제공|부과)"
    ),
    "confidential_information_scope": _rx(
        r"[\"'“”]?비밀정보[\"'“”]?(?:란|이란)[^.\n]{0,80}의미한다"
        r"|비밀정보에는[^.\n]{0,80}포함"
    ),
    "return_destruction": _rx(
        r"반환\s*(?:또는|및)\s*폐기|폐기하여야|폐기\s*확인서"
    ),
    "confidentiality_survival": _rx(
        r"종료되더라도[^.\n]{0,60}(?:계속|존속)"
        r"|영업비밀성을\s*유지하는\s*동안"
    ),
    "applicable_statutes": _rx(
        r"준거법|대한민국\s*법률을\s*적용|관련\s*법령을\s*준수"
    ),
    "acceptance_and_completion": _rx(
        r"검수|준공|인수인계|합격[^.\n]{0,40}(?:본다|간주)"
    ),
    "payment_flow": _rx(
        r"대금[^.\n]{0,30}지급|기성|계약금액|지급기한|지급한다"
    ),
    "risk_transfer_point": _rx(r"위험(?:은|이)?\s*[^.\n]{0,30}이전|인도\s*시"),
}

#: 축 → canonical_state 에서 그 값을 들고 있는 속성.
AXIS_CANONICAL_SOURCE: dict[str, str] = {
    "our_role_direction": "party_role_direction",
    "counterparty": "counterparty_role",
    "contract_purpose": "contract_type_label",
}


@dataclass
class GroundingReport:
    """원문·확정값으로 채운 축과 그 근거."""

    grounded: dict[str, str] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    #: Map 은 미기재라고 했는데 조항별 검토는 그 조항을 다루고 있는 축.
    contradictions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def status(self) -> str:
        return REVIEW_FAILED_LEGAL_MAP_CONTRADICTION if self.contradictions else ""

    @property
    def detail(self) -> str:
        if not self.contradictions:
            return ""
        names = ", ".join(c["label"] for c in self.contradictions[:4])
        return (
            f"Legal Map 이 '미기재' 로 둔 축을 계약 원문에서 확인해 채웠습니다 "
            f"— {names}."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "grounded": dict(self.grounded),
            "sources": dict(self.sources),
            "contradictions": list(self.contradictions),
        }


def ground_legal_map(
    fields: dict[str, Any] | None,
    *,
    contract_text: str,
    canonical_state: Any = None,
    axis_labels: dict[str, str] | None = None,
) -> GroundingReport:
    """비어 있는 축을 확정값·원문으로 채운다. 제자리에서 `fields` 를 고친다."""
    from runtime.review.legal_map_gate import _is_filled

    report = GroundingReport()
    if fields is None:
        return report
    labels = axis_labels or {}
    body = str(contract_text or "")

    for axis, attr in AXIS_CANONICAL_SOURCE.items():
        if _is_filled(fields.get(axis)):
            continue
        value = str(getattr(canonical_state, attr, "") or "") if canonical_state else ""
        if not value:
            continue
        fields[axis] = value
        report.grounded[axis] = value
        report.sources[axis] = "canonical_state"
        report.contradictions.append({
            "axis": axis, "label": labels.get(axis, axis),
            "evidence": value, "source": "canonical_state",
        })

    for axis, pattern in AXIS_TEXT_EVIDENCE.items():
        if _is_filled(fields.get(axis)):
            continue
        m = pattern.search(body)
        if m is None:
            continue
        evidence = re.sub(r"\s+", " ", m.group(0)).strip()[:160]
        fields[axis] = f"[원문 확인] {evidence}"
        report.grounded[axis] = evidence
        report.sources[axis] = "contract_text"
        report.contradictions.append({
            "axis": axis, "label": labels.get(axis, axis),
            "evidence": evidence, "source": "contract_text",
        })
    return report
