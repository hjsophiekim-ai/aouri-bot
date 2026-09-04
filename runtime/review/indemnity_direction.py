"""Indemnity/면책 조항의 책임 방향 구조화.

범용 사내변호사형 검토 고도화(2026-09-03 지시) — "indemnify"/"면책"이라는
단어가 있다고 곧바로 HIGH로 올리지 말고, 먼저 "누가 -> 누구에게 -> 누구의
행위로 발생한 -> 어떤 손해를 부담하는가"를 구조화해야 한다는 요구.

`common_legal_risk.py`의 기존 3개 indemnity 관련 rule(제3자 채무보증/상대방
광범위 자기책임면제/무제한 상호 indemnity)은 이미 문장 구조로 방향을
구분해 severity를 설계해 두었으므로, 이 모듈은 그 severity 판단을
대체하지 않는다 — finding에 부착할 구조화된 메타데이터(`indemnity_direction`)
만 만든다. 표시(DOCX/self-check)에서 "책임 방향"을 한눈에 보여주기 위함이다.
"""
from __future__ import annotations

import re
from typing import Any

_RX_HAS_CAP = re.compile(
    r"상한|한도|최대|초과할?\s*수\s*없다|\bcap\b|\bmaximum\b|shall\s+not\s+exceed|not\s+to\s+exceed",
    re.IGNORECASE,
)

# 이미 common_legal_risk.py에 정의된 3개 패턴과 동일한 문장구조 — 여기서는
# severity 판단이 아니라 "누가->누구에게->누구의 행위로->무엇을" 구조만 뽑는다.
_RX_THIRD_PARTY_DEBT_GUARANTEE = re.compile(
    r"guarantee(?:s)?\s+that\b.{0,120}?(?:return|repay|refund).{0,150}?"
    r"(?:otherwise|failing\s+which).{0,80}?(?:directly\s+responsible|liable)"
    r"|(?:을|상대방)(?:이|가).{0,20}(?:반환|환불|상환)하지\s*(?:아니|않)하는?\s*경우.{0,60}"
    r"(?:갑|우리\s*회사|당사)(?:이|가|는).{0,20}(?:연대하여?|직접)?\s*(?:보증|책임)",
    re.IGNORECASE | re.DOTALL,
)
_RX_COUNTERPARTY_SELF_LIABILITY_SHIELD = re.compile(
    r"shall\s+bear\s+no\s+legal\s+liability.{0,80}?except.{0,120}?shall\s+be\s+indemnified\s+against\s+all\s+claims"
    r"|(?:갑|을|상대방)(?:은|는).{0,20}(?:본\s*계약과?\s*관련하여)?\s*(?:일체의?|아무런?)\s*법적\s*책임을?\s*지지\s*(?:아니|않)"
    r"[^.\n]{0,60}(?:모든|일체의)\s*(?:청구|손해|비용)(?:에\s*대하여)?\s*(?:면책|배상)",
    re.IGNORECASE | re.DOTALL,
)
_RX_MUTUAL_UNCAPPED_INDEMNITY = re.compile(
    r"indemnify\s+the\s+other\s+part(?:y|ies)\s+against\s+all\s+claims,?\s*damages,?\s*losses,?\s*(?:and\s+)?expenses"
    r"|모든\s*청구\s*[,·]\s*손해\s*[,·]\s*비용.{0,40}(?:변호사\s*보수|소송비용)[^.\n]{0,60}(?:배상|면책)",
    re.IGNORECASE | re.DOTALL,
)
_RX_GENERIC_INDEMNITY = re.compile(
    r"indemnif(?:y|ication)|hold\s+harmless|면책|배상\s*책임",
    re.IGNORECASE,
)

# [요구 4, 2026-09-03 지시] — 수동태 "shall be indemnified"/"면책된다"류
# 문구가 "누가" 그 면책을 제공하는지(의무 주체) 명시하지 않는 경우를 감지.
# 40자 이내에 "by [주체]"가 없으면 주체가 특정되지 않은 것으로 본다.
_RX_PASSIVE_INDEMNIFIED_NO_OBLIGOR = re.compile(
    r"shall\s+be\s+indemnified(?:\s+and\s+held\s+harmless)?(?:\s+against|\s+for)?(?!.{0,40}\bby\s+\w)"
    r"|(?:은|는|이|가)\s*면책(?:되며|되고|된다|받는다|받을\s*수\s*있다)(?!.{0,20}(?:이|가)\s*(?:부담|이행|제공))",
    re.IGNORECASE | re.DOTALL,
)


def has_unclear_indemnifying_party(clause_text: str) -> bool:
    """수동태로 "면책된다/shall be indemnified"라고만 되어 있고 누가 그
    면책을 제공하는지(의무 주체)가 조항 자체에 명시되지 않은 경우를 감지한다.

    이미 더 구체적인 3개 방향성 패턴(제3자 채무보증/상대방 자기책임면제/
    상호 indemnity) 중 하나에 해당하는 조항은 그쪽이 이미 이 이슈를
    (직접 지목하지는 않더라도) 자신의 방향성 판단 안에서 다루고 있으므로
    중복 지적하지 않는다 — 그 3개 패턴에 전혀 해당하지 않는 나머지 일반
    indemnity 문구만 이 함수의 대상이다.
    """
    t = clause_text or ""
    if not t:
        return False
    if (
        _RX_THIRD_PARTY_DEBT_GUARANTEE.search(t)
        or _RX_COUNTERPARTY_SELF_LIABILITY_SHIELD.search(t)
        or _RX_MUTUAL_UNCAPPED_INDEMNITY.search(t)
    ):
        return False
    return bool(_RX_PASSIVE_INDEMNIFIED_NO_OBLIGOR.search(t))


def classify_indemnity_direction(clause_text: str) -> dict[str, Any] | None:
    """clause_text에서 indemnity/면책 구조를 찾아 방향을 구조화한다.

    반환: {"indemnifier", "indemnitee", "fault_source", "damage_type",
    "has_cap"} 또는 indemnity 관련 문구가 전혀 없으면 None.

    fault_source:
      - "counterparty_own": 상대방 자신의 채무(반환 등)를 우리가 보증
      - "third_party_shifted_to_us": 상대방 자신은 면책되고 우리가 포괄적으로 부담
      - "mutual": 상호(대칭) 조항 — 각자 자신의 귀책사유에 대해 상대방에게 배상
      - "unclear": indemnity 문구는 있으나 방향을 문장 구조만으로 특정할 수 없음
    """
    t = clause_text or ""
    if not t:
        return None
    has_cap = bool(_RX_HAS_CAP.search(t))

    if _RX_THIRD_PARTY_DEBT_GUARANTEE.search(t):
        return {
            "indemnifier": "우리 회사",
            "indemnitee": "지급기관 또는 채권자",
            "fault_source": "counterparty_own",
            "damage_type": "상대방 자신의 채무(반환·상환 등) 불이행",
            "has_cap": has_cap,
        }
    if _RX_COUNTERPARTY_SELF_LIABILITY_SHIELD.search(t):
        return {
            "indemnifier": "우리 회사(또는 제3의 수행기관)",
            "indemnitee": "상대방",
            "fault_source": "third_party_shifted_to_us",
            "damage_type": "용역과 관련해 발생하는 모든 청구·손해·비용",
            "has_cap": has_cap,
        }
    if _RX_MUTUAL_UNCAPPED_INDEMNITY.search(t):
        return {
            "indemnifier": "각 당사자(상호)",
            "indemnitee": "상대방",
            "fault_source": "mutual",
            "damage_type": "모든 청구·손해·비용(변호사 보수 포함)",
            "has_cap": has_cap,
        }
    if _RX_GENERIC_INDEMNITY.search(t):
        return {
            "indemnifier": "확인 필요",
            "indemnitee": "확인 필요",
            "fault_source": "unclear",
            "damage_type": "확인 필요",
            "has_cap": has_cap,
        }
    return None


def is_indemnifying_party_unclear(direction: dict[str, Any] | None) -> bool:
    """`classify_indemnity_direction()`의 결과가 방향을 특정하지 못한
    경우(의무 주체를 조항 문장구조만으로 확정할 수 없음)인지 여부."""
    return bool(direction) and direction.get("fault_source") == "unclear"


def summarize_indemnity_direction(direction: dict[str, Any] | None) -> str | None:
    """DOCX/UI에 표시할 한 줄 요약."""
    if not direction:
        return None
    fault_label = {
        "counterparty_own": "상대방 자신의 채무를 우리가 대신 보증",
        "third_party_shifted_to_us": "상대방 자신의 귀책까지 우리가 부담",
        "mutual": "상호 대칭적 귀책 배상",
        "unclear": "귀책 방향 확인 필요",
    }.get(str(direction.get("fault_source") or ""), "귀책 방향 확인 필요")
    cap_label = "cap 있음" if direction.get("has_cap") else "cap 없음"
    return (
        f"책임 방향: {direction.get('indemnifier')} → {direction.get('indemnitee')} "
        f"({fault_label}, {cap_label})"
    )
