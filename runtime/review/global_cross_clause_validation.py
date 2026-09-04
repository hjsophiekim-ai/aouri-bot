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
    # 2026-09-03 지시(Article 8.2류 잔존 오탐) — AI가 "없다"고 단정하지 않고
    # 권고형/보완형으로 표현해도(예: "준거법 조항을 추가할 것을 권고한다")
    # 실질은 같은 부재 주장이므로 함께 잡는다.
    r"|추가할\s*것을\s*권고|추가로?\s*명시할\s*필요|보완이?\s*필요|신설할\s*필요|둘\s*필요"
    r"|\bmissing\b|\babsent\b|does\s+not\s+specify|not\s+specified|no\s+provision|\blacks?\b"
    r"|\bunspecified\b|\bunclear\b|should\s+(?:be\s+)?add(?:ed)?|recommend(?:s|ed)?\s+add(?:ing)?",
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
    # 범용 사내변호사형 검토 고도화(2026-09-03 지시) — governing_law/dispute_
    # resolution/liability_cap/notice_procedure 4개만으로는 여전히 새는
    # 카테고리가 많다는 회귀 지적에 따라 5개 topic 추가. 각 topic은 기존과
    # 동일하게 "claim(없다는 주장) 키워드 -> presence(실제로는 있다는 근거)
    # 패턴" 쌍으로만 정의하고, 특정 계약이나 조항번호에 의존하지 않는다.
    "confidentiality_survival": re.compile(
        r"비밀유지\s*(?:의무)?\s*(?:존속|survival)|confidentiality\s+surviv",
        re.IGNORECASE,
    ),
    "termination_cure": re.compile(
        r"해지\s*(?:절차|사유|요건)|시정\s*(?:기간|절차|기회)|cure\s+period|termination\s+for\s+(?:cause|breach)",
        re.IGNORECASE,
    ),
    "payment_refund": re.compile(
        r"대금\s*(?:반환|환불|정산)|환수|refund|repayment\s+of\s+(?:the\s+)?(?:advance|payment)",
        re.IGNORECASE,
    ),
    "indemnity": re.compile(
        r"면책|배상\s*책임|indemnif(?:y|ication)|hold\s+harmless",
        re.IGNORECASE,
    ),
    "assignment": re.compile(
        r"양도\s*(?:금지|제한|승인)?|assignment\s+(?:clause|provision)|assign\s+this\s+agreement",
        re.IGNORECASE,
    ),
    "force_majeure": re.compile(
        r"불가항력|force\s+majeure",
        re.IGNORECASE,
    ),
}

_TOPIC_PRESENCE_PATTERNS: dict[str, re.Pattern[str]] = {
    "governing_law": re.compile(
        r"준거법[은는이가]?\s*[\S ]{0,20}(?:법|법률)(?:으로|을|를)?\s*한다"
        r"|준거법[은는이가]?\s*[\S ]{0,20}(?:법|법률)\s*(?:이다|이며)"
        r"|governed\s+and\s+interpreted\s+by\s+the\s+laws?\s+of"
        r"|governed\s+by\s+the\s+laws?\s+of"
        r"|이\s*계약(?:서)?은\s*[\S ]{0,20}법(?:을|에)\s*따(?:라|른다)"
        # 2026-09-03 지시 — 어미가 "한다"로 안 끝나는 표/조문 형태 준거법
        # 지정도 잡도록 대안 어미 확장.
        r"|준거법[은는이가]?\s*[\S ]{0,20}(?:법|법률)(?:으로|을|를)?\s*(?:지정|정한다)",
        re.IGNORECASE,
    ),
    "dispute_resolution": re.compile(
        r"중재(?:에\s*의하여|로)\s*(?:최종\s*)?해결"
        r"|관할\s*법원(?:은|으로)\s*[\S ]{0,20}(?:로|으로)\s*한다"
        r"|settled\s+by\s+arbitration|final(?:ly)?\s+settled\s+by\s+arbitration"
        r"|exclusive\s+jurisdiction"
        # 2026-09-03 지시 — "관할은/중재지는 ...이다", "...에 따른 중재로"처럼
        # 어미가 다른 실제 계약 문구 변형에도 대응.
        r"|관할\s*법원(?:은|으로)?\s*[\S ]{0,20}(?:이다|로\s*한다)"
        r"|중재(?:규칙|절차)?[\S ]{0,20}(?:에\s*따라|의하여)\s*(?:중재로?)?\s*(?:해결|진행)",
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
    "confidentiality_survival": re.compile(
        r"비밀유지\s*(?:의무)?[은는이가]?\s*[\S ]{0,40}(?:\d+\s*년|\d+\s*개월)[\S ]{0,20}(?:존속|유지)"
        r"|confidentiality\s+obligations?\s+shall\s+survive[\S ]{0,40}\d+\s*(?:year|month)s?",
        re.IGNORECASE,
    ),
    "termination_cure": re.compile(
        r"(?:상당한|일정한?)\s*기간을?\s*정(?:하여|한)[\S ]{0,20}시정"
        r"|시정\s*(?:요구|기회)(?:를|가)\s*(?:부여|주어진다|있다)"
        r"|cure\s+period\s+of\s+\d+|opportunity\s+to\s+cure",
        re.IGNORECASE,
    ),
    "payment_refund": re.compile(
        r"반환(?:하여야|한다|할\s*의무)|환불(?:하여야|한다)"
        r"|shall\s+(?:refund|repay|return)\s+(?:the\s+)?(?:advance|payment|amount)",
        re.IGNORECASE,
    ),
    "indemnity": re.compile(
        r"(?:면책|배상)(?:하여야|한다|할\s*책임)"
        r"|shall\s+indemnify|indemnif(?:y|ies|ied)\s+and\s+hold\s+harmless",
        re.IGNORECASE,
    ),
    "assignment": re.compile(
        r"(?:사전\s*)?(?:서면\s*)?(?:동의|승인)\s*없이\s*양도(?:할\s*수\s*없다|하지\s*못한다)"
        r"|shall\s+not\s+assign[\S ]{0,40}without[\S ]{0,20}(?:prior\s+)?(?:written\s+)?consent",
        re.IGNORECASE,
    ),
    "force_majeure": re.compile(
        r"불가항력(?:으로|의)?\s*(?:인한|발생한)[\S ]{0,40}(?:책임을?\s*지지\s*않는다|면책)"
        r"|force\s+majeure\s+event",
        re.IGNORECASE,
    ),
}


def _finding_fields(cr: dict[str, Any]) -> list[str]:
    """Fields to scan, kept SEPARATE rather than concatenated into one
    haystack. A single finding can legitimately bundle two unrelated legal
    issues (e.g. a termination-cure-period suggestion AND a completely
    unrelated "IP ownership clause missing" critique inside the same
    suggested_direction list) — concatenating everything into one string
    lets an absence marker from issue A combine with a topic keyword from
    issue B and produce a false suppression for a topic the finding never
    actually claimed was absent. Each suggested_direction bullet is checked
    on its own; title/rewrite_reason/legal_business_reason are joined since
    they normally describe the SAME single issue.
    """
    base = " ".join(
        str(cr.get(k) or "") for k in ("clause_title", "rewrite_reason", "legal_business_reason")
    )
    fields = [base] if base.strip() else []
    sd = cr.get("suggested_direction")
    if isinstance(sd, list):
        fields.extend(str(x) for x in sd if isinstance(x, str) and x.strip())
    elif isinstance(sd, str) and sd.strip():
        fields.append(sd)
    return fields


def apply_global_cross_clause_validation(
    clause_results: list[dict[str, Any]],
    full_text: str,
) -> None:
    """In place: for every finding that claims a structural topic (governing
    law, dispute resolution, liability cap, notice procedure, confidentiality
    survival, termination cure, payment/refund, indemnity, assignment, force
    majeure) is missing — checked only against that finding's OWN
    clause-scoped text (its title/rewrite_reason/legal_business_reason),
    never against a neighboring clause — search the ENTIRE contract text for
    evidence the topic is actually addressed elsewhere. If found, suppress
    the finding (dedup_suppressed) instead of letting it reach the DOCX as a
    false "missing clause" positive.

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
        # Layer 1(common_legal_risk.py)의 결정론적 rule finding은 이 함수의
        # 대상이 아니다 — 이 함수는 "AI의 단일 clause 호출이 문서 전체를
        # 보지 못해 다른 조항에 이미 있는 내용을 '없다'고 잘못 주장하는"
        # 실패모드를 잡기 위한 것인데, Layer 1 rule은 애초에 자신이 매칭한
        # clause-scoped 텍스트를 근거로 의도적으로 만들어진 finding이라 그
        # 실패모드가 없다. 반대로 Layer 1 finding 자신의 서술(예: "정부지원금
        # 환수 구조가 불명확하다")이 absence-claim 어휘와 topic 키워드를
        # 우연히 함께 포함하면, 계약 어딘가의 무관한 문장(예: 제3자 채무
        # 반환 조항)에 걸려 완전히 다른 주제의 finding이 오억제될 수 있다.
        if bool(cr.get("is_common_legal_risk")):
            continue
        matched_topic: str | None = None
        for field in _finding_fields(cr):
            if not _ABSENCE_CLAIM_MARKERS.search(field):
                continue
            for topic, claim_pat in _TOPIC_CLAIM_KEYWORDS.items():
                if claim_pat.search(field):
                    matched_topic = topic
                    break
            if matched_topic:
                break
        if not matched_topic:
            continue
        presence_pat = _TOPIC_PRESENCE_PATTERNS.get(matched_topic)
        if presence_pat and presence_pat.search(text):
            cr["dedup_suppressed"] = True
            cr["global_cross_clause_suppressed_topic"] = matched_topic
