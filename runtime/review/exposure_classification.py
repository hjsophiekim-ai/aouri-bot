"""Exposure 분류 — "법적으로 문제인가"와 "우리 회사가 실제로 부담하는가"를
분리한다(2026-09-04 지시, Senior In-house Counsel 판단 레이어).

KOTRA 3자 컨설팅계약 Article 3.4("Consultant가 KOTRA에 부담하는 지체상금")가
전형적인 사례다 — 조항 자체는 실재하는 법률 리스크이지만, 그 채무자가
우리 회사(Company)가 아니라 상대방(Consultant)이므로 우리 회사의 직접
리스크로 HIGH를 매길 근거가 없다. 반대로 같은 계약의 Article 4.3(Company의
보증책임)은 채무자가 상대방이라도 우리 회사가 보증을 서므로 진짜 리스크다.

이 모듈은 계약유형이나 조항번호가 아니라, 조항 문장 안에서 의무자(주어)가
누구인지를 우리 당사자 라벨(party_role.py의 our_label — "갑"/"을"/
"Company" 등)과 대조해 판정한다.
"""
from __future__ import annotations

import re
from typing import Any

# 조항 안에서 "누가 의무를 부담하는가"를 규정하는 문장 구조 — 한국어/영어
# 공통. 그룹 1이 의무자(주어)다.
#
# 한국어 문장에서 "-는" 어미(예: "해당하는", "정한", "지체하는")가 주격
# 조사 "는"과 겹쳐, 동사 어간을 주어로 잘못 포착하는 문제가 있었다(예:
# "…해당하는 금액을 지체상금으로 "갑"에게 지급하여야 한다"에서 "해당하"가
# 주어로 오탐되어 실제 의무자를 놓침 — 2026-09-04, 웹젠 계약 회귀테스트로
# 확인). 국문 계약은 당사자를 지칭할 때 거의 항상 따옴표로 묶은 라벨
# ("갑"/"을"/회사명)을 쓰므로, 따옴표로 감싼 주어만 인정해 이 오탐을
# 막는다 — 따옴표 없는 주어는 아예 포착하지 않고 "판단 불가"로 남겨
# indirect_operational(보수적 기본값)로 처리되도록 한다.
_RX_OBLIGOR_KO = re.compile(
    r"[\"'“]([가-힣A-Za-z]{1,20})[\"'”]\s*(?:은|는|이|가)\s*[\S ]{0,40}"
    r"(?:책임(?:이|을)?\s*(?:있다|진다|부담한다)|배상(?:할\s*책임이\s*있다|한다)"
    r"|지급(?:하여야|해야)\s*한다|반환(?:하여야|해야)\s*한다|부담한다)",
)
_RX_OBLIGOR_EN = re.compile(
    r"\b([A-Z][A-Za-z]{1,20})\s+shall\s+(?:be\s+responsible|pay|bear|indemnify|refund|return|guarantee)",
)

# 같은 조항 안에 "우리 쪽이 상대방의 채무를 보증/연대/대위"한다는 신호가
# 있으면 counterparty_only가 아니라 contingent로 격상한다 —
# common_legal_risk.py의 clr_third_party_debt_guarantee와 동일한 문장구조
# 신호를 재사용한다(모듈 간 순환 참조를 피하기 위해 패턴만 복제).
_RX_GUARANTEE_SIGNAL = re.compile(
    r"guarantee(?:s)?\s+that\b|(?:갑|우리\s*회사|당사)(?:이|가|는).{0,20}(?:연대하여?|직접)?\s*(?:보증|책임)",
    re.IGNORECASE | re.DOTALL,
)

def _label_matches(subject: str, our_party_aliases: list[str]) -> bool | None:
    """subject(조항에서 찾은 의무자 명칭)가 우리 당사자를 가리키는 라벨
    중 하나와 같은지 판단한다. 우리 라벨과도 다르고 아무 정보도 없으면
    None이 아니라 False로 본다 — 문장에 명시적으로 등장하는 의무자
    명칭(예: "Consultant", "KOTRA")은 우리 라벨이 아닌 이상 다른 당사자로
    보는 것이 안전하다(우리 라벨을 모르는 경우에만 호출하지 않는다 —
    상위에서 aliases가 비어있으면 이 함수 자체를 부르지 않음)."""
    s = subject.strip().lower()
    for alias in our_party_aliases:
        if not alias:
            continue
        if s == alias.strip().lower():
            return True
    return False


def classify_exposure(clause_text: str, our_party_aliases: list[str] | None, our_role_bucket: str = "") -> str:
    """조항 텍스트에서 우리 회사의 exposure 유형을 판정한다.

    반환값: "direct" | "contingent" | "counterparty_only" | "indirect_operational"

    - direct: 조항의 의무자가 명확히 우리 당사자(our_label)다.
    - counterparty_only: 의무자가 명확히 상대방/제3자이고, 우리 쪽이 그
      채무를 보증·연대하는 문구가 없다 — 우리 회사의 직접 리스크가 아니다.
    - contingent: 의무자는 상대방/제3자이지만, 우리 쪽이 보증·연대하는
      문구가 같은 조항에 있다 — 조건부로 우리 리스크가 된다.
    - indirect_operational: 의무자를 문장구조로 특정할 수 없다(보수적 기본값
      — 임의로 낮추지 않는다).
    """
    t = clause_text or ""
    aliases = [a for a in (our_party_aliases or []) if a and a.strip()]
    if not t.strip() or not aliases:
        return "indirect_operational"

    has_guarantee_signal = bool(_RX_GUARANTEE_SIGNAL.search(t))

    subjects: list[str] = []
    for m in _RX_OBLIGOR_KO.finditer(t):
        subjects.append(m.group(1))
    for m in _RX_OBLIGOR_EN.finditer(t):
        subjects.append(m.group(1))

    if not subjects:
        return "contingent" if has_guarantee_signal else "indirect_operational"

    match_results = [_label_matches(s, aliases) for s in subjects]
    if any(r is True for r in match_results):
        return "direct"
    return "contingent" if has_guarantee_signal else "counterparty_only"
