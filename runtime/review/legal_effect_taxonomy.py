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
    "delegated_design_or_construction_service",
    # KOTRA 3자 컨설팅계약(2026-09-02 지시, 범용 사내변호사형 검토 고도화)에서
    # 확인된, 계약유형과 무관하게 적용되는 추가 legal effect.
    "third_party_debt_guarantee",
    "counterparty_broad_self_liability_shield",
    # Force Majeure(2026-09-04 지시) — 이 태그가 없으면 effects_overlap()이
    # "원문 태그 없음=무조건 통과"로 처리해, 불가항력 조항에 SLA/지체상금류
    # 문구가 섞여도 REVIEW_FAILED_SEMANTIC_MISMATCH가 못 잡는 구멍이 있었다.
    "force_majeure",
    # NDA/IP 계약군(2026-09-08 지시, 항목 3) — 같은 이유의 구멍을 메운다.
    # 예컨대 "무보증" 조항(no_warranty)에 "광고 콘텐츠 저작권 이전"
    # (ip_ownership_transfer) 수정문안이 붙어도, 두 효과 모두 태그가
    # 없으면 effects_overlap()이 무조건 통과시켜 semantic gate가 침묵했다.
    "no_warranty",
    "ip_ownership_allocation",
    "ip_ownership_transfer",
    "license_grant",
    "data_processing_restriction",
    "personal_data_protection",
    "content_deliverable_inspection",
    "advertising_media_license",
    "portrait_or_location_release",
    # [2026-09-15] 분쟁해결·준거법 조항에 태그가 하나도 없어, 그 조항에 엉뚱한
    # 지적이 걸려도 anchor 게이트가 판단 근거를 갖지 못했다(실측: 제9조
    # "분쟁 해결 및 관할" 의 효과가 빈 목록이었다).
    "dispute_resolution_forum",
    "governing_law",
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
        re.compile(r"shall\s+pay|payment\s+(?:of|shall\s+be\s+made)|invoice[^.\n]{0,20}paid", re.IGNORECASE),
    ],
    "payment_withholding": [
        re.compile(r"대금[^.\n]{0,20}(거부|거절|유예|보류)할\s*수\s*있다", re.DOTALL),
    ],
    "liquidated_damages": [
        re.compile(r"지체상금|위약금|위약벌"),
        re.compile(r"liquidated\s+damages|late\s+(?:delivery\s+)?penalty|penalty\s+of\s+[0-9]", re.IGNORECASE),
    ],
    "consequential_damages": [
        re.compile(r"간접적?\s*손해|특별\s*손해|예상\s*손실|일실\s*이익|위자료"),
    ],
    "uncapped_liability": [
        re.compile(r"(배상|책임)(?:에는?)?\s*(?:상한|한도)(?:이|가)?\s*없다|일체의\s*(손해|법률비용)"),
    ],
    "indemnity": [
        re.compile(r"면책(?:시켜야|하여야|한다)|손해를?\s*배상하고\s*면책"),
        re.compile(r"indemnif(?:y|ies|ication)|hold\s+harmless", re.IGNORECASE),
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
        re.compile(r"terminate[^.\n]{0,60}(?:breach|default|failure\s+to\s+(?:perform|comply))", re.IGNORECASE),
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
        # [2026-09-14 지시] "추가과업 이슈에 저작권 문구 삽입 금지" 를 강제하려면
        # 추가과업·과업변경 어휘가 먼저 이 태그로 잡혀야 한다. 종전 패턴은
        # "추가로 요구하는 사항" 형태만 잡아, 계약서가 실제로 쓰는 "추가 과업",
        # "과업 범위의 변경", "change order" 를 전부 놓쳤다 — 태그가 비면
        # effects_overlap() 이 "의견 없음" 으로 무조건 통과시키므로 게이트가 침묵한다.
        re.compile(
            r"추가로?\s*요구하는\s*사항"
            r"|(?:과업|업무|용역|작업)\s*(?:의\s*)?범위[^.\n]{0,12}(?:변경|확대|추가|조정)"
            r"|추가\s*(?:과업|업무|용역|작업|발주|요청사항)"
            r"|과업\s*(?:변경|지시서?)"
            r"|범위를?\s*변경"
            r"|scope\s*(?:change|creep)|change\s*order"
            r"|additional\s+(?:work|works|services|scope|deliverables)",
            re.IGNORECASE,
        ),
    ],
    "confidentiality": [
        re.compile(r"비밀\s*(정보|유지)|기밀\s*정보|confidential"),
        re.compile(r"non-?disclosure|proprietary\s+information", re.IGNORECASE),
    ],
    "return_destruction": [
        re.compile(r"반환하거나?\s*폐기|파기하거나?\s*폐기|반환\s*또는\s*파기"),
    ],
    "ethics_morality": [
        re.compile(r"품위를?\s*유지|윤리\s*(헌장|규범)|사회적으로\s*비난받"),
    ],
    "force_majeure": [
        re.compile(r"불가항력|force\s+majeure", re.IGNORECASE),
    ],
    "no_warranty": [
        re.compile(r"어떠한\s*보증도\s*하지\s*아니한다|보증하지\s*아니한다|현\s*상태\s*그대로\s*제공|as\s+is", re.IGNORECASE),
    ],
    "ip_ownership_allocation": [
        re.compile(r"(지식재산권|저작권|특허권|소유권)[^.\n]{0,40}(귀속|에게\s*있다|보유한다)"),
    ],
    "ip_ownership_transfer": [
        re.compile(r"(지식재산권|저작(?:재산)?권|특허권)[^.\n]{0,30}(양도|이전)(?:한다|하여야|하기로)"),
        re.compile(r"(?:assign|transfer)s?\s+(?:all\s+)?(?:right|title|ownership|intellectual\s+property)", re.IGNORECASE),
    ],
    "license_grant": [
        re.compile(r"사용을?\s*허락|실시권을?\s*(?:부여|허락)|이용을?\s*허락|라이선스를?\s*부여"),
        re.compile(r"grants?\s+(?:a\s+)?[^.\n]{0,40}licen[cs]e", re.IGNORECASE),
    ],
    "data_processing_restriction": [
        # [2026-09-14] 실제 조문은 제한어가 문장 끝에 한 번만 오고 그 앞에 학습
        # 유형이 길게 열거된다 — "…모델의 학습, 사전학습, 미세조정, 성능 개선,
        # 평가용 데이터셋 구축에 사용하거나 … 사용할 수 없다". 30자 창 안에서만
        # 제한어를 찾던 종전 패턴은 이 형태를 통째로 놓쳤고, 그 결과 범용 모델
        # 학습 제한 조문이 confidentiality 로만 태깅됐다(퍼시스 NDA 실측).
        re.compile(
            r"(?:범용\s*)?(?:인공지능|AI)\s*모델"
            r"|사전\s*학습|미세\s*조정|파인\s*튜닝|파인튜닝"
            r"|(?:학습|훈련|데이터셋)[^.\n]{0,60}(?:사용할\s*수\s*없|금지|제한|승인|동의)"
            r"|모델[^.\n]{0,40}(?:학습|성능\s*개선)",
            re.IGNORECASE,
        ),
    ],
    "personal_data_protection": [
        re.compile(
            r"개인정보[^.\n]{0,40}(처리|보호|위탁|파기|이전|수집|이용|제공|동의|보유)"
            r"|민감정보|정보주체|고유식별정보"
        ),
    ],
    "content_deliverable_inspection": [
        re.compile(
            r"(콘텐츠|시안|산출물|납품물)[^.\n]{0,15}검수"
            r"|검수(?:의|를|가|는|에|로|하여|한|해)?\s*(?:기준|절차|기간|기한|합격|불합격)"
            r"|검수(?:에|를|의)?\s*(?:합격|불합격)"
            r"|합격\s*간주|수정\s*요청\s*횟수"
        ),
    ],
    "advertising_media_license": [
        re.compile(r"광고\s*매체|매체\s*사용권|광고\s*집행|SNS[^.\n]{0,12}(게재|노출|활용)"),
    ],
    "portrait_or_location_release": [
        re.compile(r"초상권|퍼블리시티권|촬영\s*장소|출연\s*동의"),
    ],
    "dispute_resolution_forum": [
        re.compile(
            r"관할\s*법원|전속\s*관할|합의\s*관할|제1심\s*법원"
            r"|중재(?:인|판정|기관|규칙)|대한상사중재원|분쟁의?\s*해결"
            r"|jurisdiction|arbitration|competent\s+court",
            re.IGNORECASE,
        ),
    ],
    "governing_law": [
        re.compile(
            r"준거법|대한민국\s*법(?:률|령)?(?:을|에)?\s*(?:따른다|적용)"
            r"|governing\s+law|governed\s+by\s+the\s+laws?",
            re.IGNORECASE,
        ),
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
