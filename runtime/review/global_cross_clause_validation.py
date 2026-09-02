"""GLOBAL_CROSS_CLAUSE_VALIDATION (2026-09-02 지시 — 범용 사내변호사형 검토).

한 조항만 보고 만들어진 "이 조항에는 준거법/분쟁해결 조항이 없다"류 finding은,
같은 계약서의 *다른* 조항에 그 내용이 이미 있으면 오탐이다 — 실제 KOTRA 3자
컨설팅계약에서 Article 8(비밀유지)을 검토하며 "준거법/관할 필요"를 HIGH로
잡았는데, 바로 다음 Article 9에 준거법(대한민국법)과 서울 중재 조항이 이미
있었던 사고가 이 클래스의 전형이다.

원인은 조항 단위(또는 AI의 단일 clause 호출) 검토가 문서 전체를 보지 못하는
구조적 한계이므로, 특정 계약이나 특정 조항번호를 하드코딩하는 대신 "이
finding이 정말 X가 없다고 주장하는가?"와 "실제로 계약 전체에 X가 있는가?"를
일반화된 두 단계로 분리해 검증한다:

  local clause issue -> entire contract search -> already addressed elsewhere?

이미 해결되어 있으면 finding을 제거(dedup_suppressed)한다.
"""
from __future__ import annotations

import re
from typing import Any

# "X가 없다"류 주장 어휘 — 한국어/영어 공통. 특정 조항 번호나 계약유형을
# 언급하지 않는, 순수 "부재 주장" 신호만 모은다.
_ABSENCE_CLAIM_MARKERS = re.compile(
    r"없다|부재|누락|명시되어\s*있지\s*않|규정되어\s*있지\s*않|정해져\s*있지\s*않|규정하고\s*있지\s*않"
    r"|미특정|미설정|특정되지\s*않|설정되지\s*않|불명확"
    r"|\bmissing\b|\babsent\b|does\s+not\s+specify|not\s+specified|no\s+provision|\blacks?\b"
    r"|\bunspecified\b|\bunclear\b",
    re.IGNORECASE,
)

# 계약 전반에 걸쳐 반복적으로 "국지적으로는 없어 보이지만 실제로는 다른
# 조항에 있는" 구조적 topic들. 각 topic은 (해당 topic을 "없다"고 주장하는
# finding을 식별하는 키워드, 계약 전체에서 실제로 그 topic이 존재하는지
# 확인하는 패턴) 쌍으로 정의한다 — 특정 계약의 조항번호에 의존하지 않는다.
_TOPIC_CLAIM_KEYWORDS: dict[str, re.Pattern[str]] = {
    "governing_law": re.compile(r"준거법|governing\s+law", re.IGNORECASE),
    "dispute_resolution": re.compile(
        r"관할\s*법원|중재|분쟁\s*해결\s*(?:조항|절차|방법)?|arbitration|dispute\s+resolution|jurisdiction\s+clause",
        re.IGNORECASE,
    ),
    "liability_cap": re.compile(r"책임\s*상한|배상\s*한도|liability\s+cap|limitation\s+of\s+liability", re.IGNORECASE),
    "notice_procedure": re.compile(r"통지\s*(?:방법|절차)|notice\s+(?:provision|procedure|clause)", re.IGNORECASE),
}

_TOPIC_PRESENCE_PATTERNS: dict[str, re.Pattern[str]] = {
    "governing_law": re.compile(
        r"준거법[은는이가]?\s*[\S ]{0,20}(?:법|법률)(?:으로|을|를)?\s*한다"
        r"|governed\s+and\s+interpreted\s+by\s+the\s+laws?\s+of"
        r"|governed\s+by\s+the\s+laws?\s+of"
        r"|이\s*계약(?:서)?은\s*[\S ]{0,20}법(?:을|에)\s*따(?:라|른다)",
        re.IGNORECASE,
    ),
    "dispute_resolution": re.compile(
        r"중재(?:에\s*의하여|로)\s*(?:최종\s*)?해결"
        r"|관할\s*법원(?:은|으로)\s*[\S ]{0,20}(?:로|으로)\s*한다"
        r"|settled\s+by\s+arbitration|final(?:ly)?\s+settled\s+by\s+arbitration"
        r"|exclusive\s+jurisdiction",
        re.IGNORECASE,
    ),
    "liability_cap": re.compile(
        r"책임(?:의\s*)?(?:총액은|상한은|은)\s*[\S ]{0,20}(?:을|를)\s*한도로"
        r"|liability\s+shall\s+not\s+exceed|aggregate\s+liability.{0,30}(?:cap|limit)",
        re.IGNORECASE,
    ),
    "notice_procedure": re.compile(
        r"통지는\s*[\S ]{0,20}(?:방법|주소)(?:으로|에)\s*(?:한다|송부)"
        r"|notice(?:s)?\s+(?:shall|must)\s+be\s+(?:given|sent|delivered)",
        re.IGNORECASE,
    ),
}


def _finding_haystack(cr: dict[str, Any]) -> str:
    return " ".join(
        str(cr.get(k) or "")
        for k in ("clause_title", "rewrite_reason", "legal_business_reason", "suggested_direction")
    )


def apply_global_cross_clause_validation(
    clause_results: list[dict[str, Any]],
    full_text: str,
) -> None:
    """In place: for every finding that claims a structural topic (governing
    law, dispute resolution, liability cap, notice procedure) is missing —
    checked only against that finding's OWN clause-scoped text (its title/
    rewrite_reason/legal_business_reason), never against a neighboring
    clause — search the ENTIRE contract text for evidence the topic is
    actually addressed elsewhere. If found, suppress the finding
    (dedup_suppressed) instead of letting it reach the DOCX as a false
    "missing clause" positive.

    Only ever suppresses — never invents or upgrades a finding, and only
    ever acts on a finding that already explicitly claims something is
    absent (checked via `_ABSENCE_CLAIM_MARKERS`), so a finding that merely
    *mentions* governing law for an unrelated reason (e.g. "the governing
    law clause designates a foreign forum, which is unfavorable") is left
    untouched.
    """
    text = full_text or ""
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if bool(cr.get("dedup_suppressed")) or bool(cr.get("keep_as_is")):
            continue
        haystack = _finding_haystack(cr)
        if not haystack.strip() or not _ABSENCE_CLAIM_MARKERS.search(haystack):
            continue
        for topic, claim_pat in _TOPIC_CLAIM_KEYWORDS.items():
            if not claim_pat.search(haystack):
                continue
            presence_pat = _TOPIC_PRESENCE_PATTERNS.get(topic)
            if presence_pat and presence_pat.search(text):
                cr["dedup_suppressed"] = True
                cr["global_cross_clause_suppressed_topic"] = topic
            break
