"""Canonical Contract Type / Party Role — 하나의 진실만 남긴다
(2026-09-09 지시 1항).

계약유형과 우리 회사의 지위는 검토의 모든 단계가 참조하는 전제다. 유형이
틀리면 적용할 체크리스트가 틀리고, 지위가 뒤집히면 위험배분 매트릭스가
좌우로 뒤집혀 "상대방 부담"과 "우리 부담"이 서로 바뀐다. 그래서 이 두 값은
**여러 곳에서 각자 판단하면 안 된다**.

이 엔진에는 판단 주체가 둘 있다:

    rule classifier   급부·대금·완료조건·위험이전 구조를 문형으로 채점
                      (contract_type_resolution.resolve_contract_type)
    AI 분석           Contract Legal Map 의 our_role_direction / 유형 서술

둘이 다른 답을 내면 어느 하나가 틀렸다는 뜻이고, 그 상태로 진행하면 결과가
조용히 틀린다. 이 모듈은 두 판단을 맞춰 보고, 어긋나면 정상 완료를 막는다.

제목은 근거로 쓰지 않는다. "용역계약서"라는 제목 아래 도급 구조가 들어 있고
"업무협약"이라는 제목 아래 위탁판매가 들어 있는 것이 실무다. 판단은 급부·
대금·완료조건·위험이전 구조로 한다 — 그 채점은 rule classifier 가 한다.

설계 — **하드코딩 금지**. 특정 계약명·회사명을 쓰지 않는다.
"""
from __future__ import annotations

import re
from typing import Any

REVIEW_FAILED_CANONICAL_TYPE_CONFLICT = "REVIEW_FAILED_CANONICAL_TYPE_CONFLICT"
REVIEW_FAILED_CANONICAL_ROLE_CONFLICT = "REVIEW_FAILED_CANONICAL_ROLE_CONFLICT"

ROLE_PROVIDER = "provider"
ROLE_RECIPIENT = "recipient"

ROLE_LABELS = {
    ROLE_PROVIDER: "급부 제공자 (일을 해주고 대가를 받는 쪽)",
    ROLE_RECIPIENT: "급부 수령자 (대가를 지급하고 일을 받는 쪽)",
}

#: AI 가 서술한 지위를 두 방향 중 하나로 정규화한다. AI 는 자유서술로 답하므로
#: ("수급인", "공급자", "Contractor", "용역 제공") 여러 표현이 온다.
_RX_PROVIDER = re.compile(
    r"수급인|시공(?:사|자)|공급(?:자|업자|사)|제조(?:자|사)|매도인|수탁|대리점|"
    r"판매점|용역\s*(?:제공|수행)|provider|contractor|supplier|seller|vendor|"
    r"licensor|제공자|정보\s*제공",
    re.IGNORECASE,
)
_RX_RECIPIENT = re.compile(
    r"도급인|발주(?:자|처)|주문자|구매(?:자|사)|매수인|위탁자|임대인|"
    r"employer|owner|buyer|purchaser|client|licensee|수령자|정보\s*수령",
    re.IGNORECASE,
)


def normalize_role(value: str) -> str:
    """자유서술 지위를 provider / recipient 로 정규화한다. 못 가리면 ""."""
    text = str(value or "")
    if not text.strip():
        return ""
    low = text.strip().lower()
    if low in (ROLE_PROVIDER, ROLE_RECIPIENT):
        return low
    provider = _RX_PROVIDER.search(text)
    recipient = _RX_RECIPIENT.search(text)
    if provider and not recipient:
        return ROLE_PROVIDER
    if recipient and not provider:
        return ROLE_RECIPIENT
    if provider and recipient:
        # 둘 다 언급되면 먼저 나온 쪽을 우리 지위로 본다 — 서술은 보통
        # "우리 회사는 수급인, 상대방은 도급인" 순으로 온다.
        return ROLE_PROVIDER if provider.start() < recipient.start() else ROLE_RECIPIENT
    return ""


def resolve_canonical_identity(
    *,
    rule_type_code: str,
    rule_confidence: float | None,
    rule_uncertain: bool,
    ai_type_text: str = "",
    ai_role_text: str = "",
    rule_role: str = "",
    declared_type_code: str = "",
) -> dict[str, Any]:
    """계약유형·당사자 지위의 canonical 값을 확정하고 충돌을 보고한다.

    canonical 값은 rule classifier 의 결과다 — 급부·대금·완료조건·위험이전
    구조를 실제로 채점한 쪽이기 때문이다. AI 서술은 **검증용**으로 쓴다.
    """
    from runtime.review.contract_type_resolution import TYPE_LABELS

    canonical_type = str(rule_type_code or "")
    canonical_role = normalize_role(rule_role) or normalize_role(ai_role_text)

    conflicts: list[dict[str, Any]] = []

    # ── 유형 충돌 ────────────────────────────────────────────────────────────
    # AI 가 서술한 유형을 코드로 되돌릴 수는 없으므로, canonical 유형의 라벨이
    # AI 서술에 전혀 등장하지 않고 **다른** 유형 라벨이 등장하면 충돌로 본다.
    ai_type = str(ai_type_text or "")
    if canonical_type and ai_type.strip():
        own_label = str(TYPE_LABELS.get(canonical_type) or "")
        mentions_own = bool(own_label) and own_label in ai_type
        other_labels = [
            (code, label) for code, label in TYPE_LABELS.items()
            if code != canonical_type and label and label in ai_type
        ]
        if not mentions_own and other_labels:
            conflicts.append({
                "kind": "contract_type",
                "status": REVIEW_FAILED_CANONICAL_TYPE_CONFLICT,
                "canonical": canonical_type,
                "canonical_label": own_label,
                "other": [c for c, _ in other_labels],
                "other_labels": [l for _, l in other_labels],
                "detail": (
                    f"구조 채점은 '{own_label}'로 판정했는데 AI 분석은 "
                    f"'{', '.join(l for _, l in other_labels)}'로 서술했습니다. "
                    f"유형이 다르면 적용할 체크리스트 자체가 달라집니다."
                ),
            })

    if declared_type_code and canonical_type and declared_type_code != canonical_type:
        conflicts.append({
            "kind": "declared_type",
            "status": REVIEW_FAILED_CANONICAL_TYPE_CONFLICT,
            "canonical": canonical_type,
            "canonical_label": str(TYPE_LABELS.get(canonical_type) or ""),
            "other": [declared_type_code],
            "other_labels": [str(TYPE_LABELS.get(declared_type_code) or "")],
            "detail": (
                "계약서가 스스로 밝힌 유형과 구조 채점 결과가 다릅니다. "
                "제목이 아니라 급부·대금·완료조건·위험이전 구조를 기준으로 "
                "다시 확인해야 합니다."
            ),
        })

    # ── 지위 충돌 ────────────────────────────────────────────────────────────
    rule_norm = normalize_role(rule_role)
    ai_norm = normalize_role(ai_role_text)
    if rule_norm and ai_norm and rule_norm != ai_norm:
        conflicts.append({
            "kind": "party_role",
            "status": REVIEW_FAILED_CANONICAL_ROLE_CONFLICT,
            "canonical": rule_norm,
            "canonical_label": ROLE_LABELS.get(rule_norm, rule_norm),
            "other": [ai_norm],
            "other_labels": [ROLE_LABELS.get(ai_norm, ai_norm)],
            "detail": (
                f"구조 채점은 우리 회사를 '{ROLE_LABELS.get(rule_norm)}'로, "
                f"AI 분석은 '{ROLE_LABELS.get(ai_norm)}'로 보았습니다. 지위가 "
                f"뒤집히면 위험배분이 좌우로 반대가 됩니다."
            ),
        })

    blocking = [c for c in conflicts if c.get("status")]
    return {
        "contract_type_code": canonical_type,
        "contract_type_label": str(TYPE_LABELS.get(canonical_type) or ""),
        "our_role_direction": canonical_role,
        "our_role_label": ROLE_LABELS.get(canonical_role, ""),
        "source": "rule_classifier",
        "rule_confidence": rule_confidence,
        "rule_uncertain": bool(rule_uncertain),
        "conflicts": conflicts,
        "conflict_count": len(conflicts),
        "review_status": str(blocking[0]["status"]) if blocking else "",
        "detail": str(blocking[0]["detail"]) if blocking else "",
    }
