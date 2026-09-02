"""Universal legal-effect taxonomy — shared vocabulary between the AI clause
reviewer and the rule-based fallback, so both "speak the same language" when
classifying what a clause actually DOES rather than what words it contains
(변호사형 전체계약 판단 지시, 2026-09-01 — Layer 1: Universal Legal Effect
Analysis).

This module has two jobs:
  1. `LEGAL_EFFECT_TAGS` — the canonical list of effect categories, applied
     to every contract type (not gated by contract_type_code). The AI prompt
     is told to classify each clause into one or more of these tags instead
     of inventing its own vocabulary.
  2. `infer_legal_effects()` — a lightweight, purely textual fallback tagger
     used when no AI provider is configured (or as a sanity cross-check
     alongside the AI's own tags). It is deliberately conservative: it only
     asserts a tag when a fairly specific phrase pattern is present, and
     returns an empty list rather than guessing when nothing matches —
     Layer 1 must still run without AI, but "no opinion" is safer than a
     wrong opinion for something this consequential.
"""
from __future__ import annotations

import re

LEGAL_EFFECT_TAGS: tuple[str, ...] = (
    "payment_obligation",
    "payment_withholding",
    "liquidated_damages",
    "consequential_damages",
    "uncapped_liability",
    "indemnity",
    "third_party_liability",
    "standard_of_care",
    "unilateral_termination",
    "termination_for_breach",
    "convenience_termination",
    "cross_default",
    "waiver_of_claims",
    "survival",
    "assignment",
    "unilateral_amendment",
    "scope_change",
    "confidentiality",
    "return_destruction",
    "ethics_morality",
    # 혼합형 전략제휴/공급계약(2026-09-02 지시)에서 추가된 태그 — 계약
    # 유형과 무관하게 "우리 회사에 장기적 경제적 구속·영업자유 제한이
    # 있는가"를 판단하기 위한 legal effect.
    "minimum_purchase_commitment",
    "non_circumvention",
    "direct_dealing_restriction",
    "penalty_for_bypass",
    "rebate_or_support_payment",
)

# Each tag maps to a list of (regex, requires_dotall) fairly specific phrase
# patterns — deliberately more specific than a bare keyword so a clause that
# merely *mentions* a word in passing (e.g. "계약이 해지되거나" as a trigger
# condition inside a return/destruction clause) doesn't get mis-tagged with
# an unrelated effect. This is the same "action, not word" principle applied
# to clause_topic.py's payment-detection fix, generalized to all 19 tags.
_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "payment_obligation": [
        re.compile(r"대금[^.\n]{0,20}(지급|지불|납부)|(지급|지불|납부)[^.\n]{0,20}대금", re.DOTALL),
    ],
    "payment_withholding": [
        re.compile(r"대금[^.\n]{0,20}(거부|거절|유예|보류)할\s*수\s*있다", re.DOTALL),
    ],
    "liquidated_damages": [
        re.compile(r"지체상금|위약금|위약벌"),
    ],
    "consequential_damages": [
        re.compile(r"간접적?\s*손해|특별\s*손해|예상\s*손실|일실\s*이익|위자료"),
    ],
    "uncapped_liability": [
        re.compile(r"(배상|책임)(?:에는?)?\s*(?:상한|한도)(?:이|가)?\s*없다|일체의\s*(손해|법률비용)"),
    ],
    "indemnity": [
        re.compile(r"면책(?:시켜야|하여야|한다)|손해를?\s*배상하고\s*면책"),
    ],
    "third_party_liability": [
        re.compile(r"(제\s*3\s*자|하청업체|수급인|협력사)[^.\n]{0,90}(연대하여|고의|과실)[^.\n]{0,60}(배상|책임)", re.DOTALL),
    ],
    "standard_of_care": [
        re.compile(r"선량한\s*관리자|가능한\s*최선의\s*노력|주의\s*의무를?\s*다하"),
    ],
    "unilateral_termination": [
        re.compile(r"(일방적으로|임의로)\s*(해지|해제)할?\s*수\s*있다|사전\s*통지(?:만으로|후)\s*해지"),
    ],
    "termination_for_breach": [
        re.compile(r"(위반|불이행)[^.\n]{0,40}(해지|해제)할?\s*수\s*있다", re.DOTALL),
    ],
    "convenience_termination": [
        re.compile(r"(경영상의?\s*이유|경영\s*판단)[^.\n]{0,60}(해지|해제)할?\s*수\s*있다", re.DOTALL),
    ],
    "cross_default": [
        re.compile(r"(본\s*계약|이\s*계약)[^.\n]{0,60}(위반|불이행)[^.\n]{0,60}(정식\s*계약|관련된?\s*계약|다른\s*계약)[^.\n]{0,20}(해지|해제)", re.DOTALL),
    ],
    "waiver_of_claims": [
        re.compile(r"손해배상\s*청구를?\s*하지\s*않는|청구권을?\s*포기"),
    ],
    "survival": [
        re.compile(r"(계약\s*종료|해지)\s*후에?도\s*(존속|유효)|계약\s*종료\s*후\s*\d+\s*(년|개월)간?\s*(존속|유효)"),
    ],
    "assignment": [
        re.compile(r"양도|하도급|재위임|하수급"),
    ],
    "unilateral_amendment": [
        re.compile(r"(일방적으로|임의로)\s*(변경|수정)할?\s*수\s*있다"),
    ],
    "scope_change": [
        re.compile(r"추가로?\s*요구하는\s*사항|범위를?\s*변경|scope\s*change", re.IGNORECASE),
    ],
    "confidentiality": [
        re.compile(r"비밀\s*(정보|유지)|기밀\s*정보|confidential"),
    ],
    "return_destruction": [
        re.compile(r"반환하거나?\s*폐기|파기하거나?\s*폐기|반환\s*또는\s*파기"),
    ],
    "ethics_morality": [
        re.compile(r"품위를?\s*유지|윤리\s*(헌장|규범)|사회적으로\s*비난받"),
    ],
}


def infer_legal_effects(text: str) -> list[str]:
    """Return the subset of LEGAL_EFFECT_TAGS whose phrase pattern matches
    somewhere in `text`. Conservative by design — used as the non-AI
    fallback tagger and as a sanity cross-check against the AI's own tags."""
    hay = text or ""
    out: list[str] = []
    for tag in LEGAL_EFFECT_TAGS:
        pats = _PATTERNS.get(tag) or []
        if any(p.search(hay) for p in pats):
            out.append(tag)
    return out


def effects_overlap(a: list[str] | None, b: list[str] | None) -> bool:
    """True if the two effect-tag lists share at least one tag, OR either
    side is empty (an empty tag list means "no opinion", not "no effect" —
    it must never itself trigger a mismatch)."""
    sa, sb = set(a or []), set(b or [])
    if not sa or not sb:
        return True
    return bool(sa & sb)
