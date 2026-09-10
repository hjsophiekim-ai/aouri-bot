"""조항의 **법률효과**를 계약유형보다 먼저 확정하는 의미 레이어.

2026-09-10 아키텍처 지시 항목 2 — "계약유형보다 먼저 법률효과를 이해.
처음 보는 계약에서도 각 조항을 legal-effect taxonomy 로 분류. 계약유형별
템플릿은 이 semantic layer 를 보조하는 역할만 하고, finding 생성의 출발점이
되지 않도록 할 것."

왜 필요했나
──────────
종전 엔진은 **계약유형 enum 이 출발점**이었다. `contract_classifier` 가
키워드 if-else 캐스케이드로 유형 코드 하나를 고르고, 그 코드에 매달린
체크리스트·룰팩·질문세트가 통째로 실행된다. 그래서 두 가지가 동시에 깨졌다.

1. **enum 에 없는 계약유형은 갈 곳이 없다.** 실측: 34,000자짜리 영문
   LICENSE AGREEMENT("Licensor", "Royalty", "Licensed Products")가
   `purchase_supply`(물품 구매·공급 계약)로 분류됐다. license 유형이 enum 에
   아예 없어서, "공급/purchase price/warranty period" 신호 3개가 먼저 걸린
   것이다. 그 뒤 모든 검토는 물품매매 체크리스트로 진행됐다.
2. **한 유형을 고치면 다른 유형이 깨진다.** 캐스케이드의 분기 순서를 바꾸는
   순간 다른 계약이 다른 가지로 떨어지기 때문이다.

이 모듈이 하는 일
──────────────
계약유형을 묻지 않고, 조항 하나하나가 **무엇을 법적으로 하는지**를 14개
범주로 분류한다. 이 범주는 계약유형과 무관하게 존재한다 — 어떤 계약이든
대금 조항은 대금 조항이고, 면책 조항은 면책 조항이다.

    scope_performance      급부의 범위·내용
    payment_consideration  대가·지급
    delivery_acceptance    인도·검수
    ownership_risk         소유권·위험 이전
    ip_license             지식재산권 귀속·실시허락
    confidentiality        비밀유지
    data_privacy           개인정보·데이터
    liability_indemnity    책임·면책·손해배상
    warranty               보증·하자담보
    termination            해지·해제·존속
    change_order           변경·추가과업
    subcontracting         재위탁·하도급
    dispute                분쟁·관할·준거법
    compliance             법령준수·윤리·표시광고

그리고 계약 전체의 **효과 프로파일**(어느 범주가 지배적인가)로 거래 원형
(archetype)을 추정한다. 이 추정은 enum 에 없는 유형도 표현할 수 있고
(`ip_license`, `barter_exchange`), 무엇보다 **finding 의 출발점이 되지 않는다** —
조항의 효과가 출발점이고, 유형은 그 위에 얹는 보조 라벨이다.

설계 규칙: 회사명·계약명·조항번호를 쓰지 않는다. 판정은 법률효과 어휘로만 한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ── 14개 법률효과 범주 ───────────────────────────────────────────────────────
EFFECT_SCOPE = "scope_performance"
EFFECT_PAYMENT = "payment_consideration"
EFFECT_DELIVERY = "delivery_acceptance"
EFFECT_OWNERSHIP = "ownership_risk"
EFFECT_IP = "ip_license"
EFFECT_CONFIDENTIALITY = "confidentiality"
EFFECT_PRIVACY = "data_privacy"
EFFECT_LIABILITY = "liability_indemnity"
EFFECT_WARRANTY = "warranty"
EFFECT_TERMINATION = "termination"
EFFECT_CHANGE = "change_order"
EFFECT_SUBCONTRACT = "subcontracting"
EFFECT_DISPUTE = "dispute"
EFFECT_COMPLIANCE = "compliance"
EFFECT_OTHER = "other"

CLAUSE_EFFECTS: tuple[str, ...] = (
    EFFECT_SCOPE, EFFECT_PAYMENT, EFFECT_DELIVERY, EFFECT_OWNERSHIP, EFFECT_IP,
    EFFECT_CONFIDENTIALITY, EFFECT_PRIVACY, EFFECT_LIABILITY, EFFECT_WARRANTY,
    EFFECT_TERMINATION, EFFECT_CHANGE, EFFECT_SUBCONTRACT, EFFECT_DISPUTE,
    EFFECT_COMPLIANCE,
)

EFFECT_LABELS: dict[str, str] = {
    EFFECT_SCOPE: "급부 범위·이행",
    EFFECT_PAYMENT: "대가·지급",
    EFFECT_DELIVERY: "인도·검수",
    EFFECT_OWNERSHIP: "소유권·위험 이전",
    EFFECT_IP: "지식재산권·실시허락",
    EFFECT_CONFIDENTIALITY: "비밀유지",
    EFFECT_PRIVACY: "개인정보·데이터",
    EFFECT_LIABILITY: "책임·면책·손해배상",
    EFFECT_WARRANTY: "보증·하자담보",
    EFFECT_TERMINATION: "해지·존속",
    EFFECT_CHANGE: "변경·추가과업",
    EFFECT_SUBCONTRACT: "재위탁·하도급",
    EFFECT_DISPUTE: "분쟁·관할",
    EFFECT_COMPLIANCE: "법령준수·표시",
    EFFECT_OTHER: "기타",
}

#: 범주별 판정 패턴. 제목(title)에 걸리면 본문보다 강한 신호로 본다 —
#: 조 제목은 그 조가 무엇을 규율하는지 당사자가 직접 붙인 이름이기 때문이다.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (EFFECT_IP, re.compile(
        r"저작권|저작인격권|지식재산|지적재산|특허|상표|디자인권|실시권|실시허락"
        r"|사용권\s*(?:허여|부여)|라이선스|licen[cs]e|royalt|intellectual\s+property"
        r"|copyright|trademark|patent|know[- ]how|2차적저작물|무형자산",
        re.IGNORECASE)),
    (EFFECT_PRIVACY, re.compile(
        r"개인정보|정보주체|민감정보|고유식별정보|가명정보|초상권|퍼블리시티"
        r"|personal\s+(?:data|information)|GDPR|privacy|data\s+subject",
        re.IGNORECASE)),
    (EFFECT_CONFIDENTIALITY, re.compile(
        r"비밀유지|비밀정보|기밀|영업비밀|누설|confidential|non[- ]disclosure|NDA\b"
        r"|trade\s+secret",
        re.IGNORECASE)),
    (EFFECT_SUBCONTRACT, re.compile(
        r"재위탁|재하도급|하도급|하청|외주|제3자에게\s*위탁|subcontract|outsourc",
        re.IGNORECASE)),
    (EFFECT_WARRANTY, re.compile(
        r"하자담보|하자보수|품질보증|보증기간|무상\s*수리|하자\s*책임"
        r"|warrant(?:y|ies)|defect\s+liability|guarantee\s+period",
        re.IGNORECASE)),
    (EFFECT_LIABILITY, re.compile(
        r"손해배상|배상책임|면책|구상|책임\s*(?:제한|한도|범위)|위약(?:금|벌)"
        r"|지체상금|연대책임|무과실|indemnif|liabilit|damages|hold\s+harmless"
        r"|limitation\s+of\s+liability",
        re.IGNORECASE)),
    (EFFECT_TERMINATION, re.compile(
        r"해지|해제|계약\s*종료|존속|중도\s*종료|기간\s*만료"
        r"|terminat|expir(?:y|ation)|surviv",
        re.IGNORECASE)),
    (EFFECT_CHANGE, re.compile(
        r"설계\s*변경|추가\s*(?:공사|과업|업무)|변경\s*(?:요청|명령|절차)|과업\s*변경"
        r"|공기\s*연장|change\s+order|variation|amendment\s+to\s+the\s+scope",
        re.IGNORECASE)),
    (EFFECT_DISPUTE, re.compile(
        r"관할|준거법|중재|분쟁\s*(?:해결|처리)|소송|governing\s+law|jurisdiction"
        r"|arbitrat|dispute\s+resolution|venue",
        re.IGNORECASE)),
    (EFFECT_COMPLIANCE, re.compile(
        r"관계\s*법령\s*준수|법령\s*준수|윤리|반부패|청탁금지|표시·?\s*광고|협찬\s*표시"
        r"|compliance|anti[- ]corruption|FCPA|applicable\s+laws?\s+and\s+regulations",
        re.IGNORECASE)),
    (EFFECT_DELIVERY, re.compile(
        r"납품|인도|납기|검수|수령|인수(?:확인|검사)?|설치\s*완료|delivery|deliverable"
        r"|acceptance|inspection|hand[- ]over",
        re.IGNORECASE)),
    (EFFECT_OWNERSHIP, re.compile(
        r"소유권|위험\s*(?:부담|이전)|멸실|훼손\s*책임|title\s+to|risk\s+of\s+loss"
        r"|passing\s+of\s+(?:title|risk)|ownership\s+of\s+the\s+goods",
        re.IGNORECASE)),
    (EFFECT_PAYMENT, re.compile(
        r"대금|대가|지급|정산|세금계산서|보수|수수료|요금|단가|선급금|기성"
        r"|payment|price|fee|invoice|royalty\s+payment|remuneration|consideration",
        re.IGNORECASE)),
    (EFFECT_SCOPE, re.compile(
        r"업무\s*범위|용역\s*범위|제공\s*범위|과업|산출물|목적물|이행\s*방법"
        r"|scope\s+of\s+(?:work|services)|services\s+to\s+be|obligations\s+of",
        re.IGNORECASE)),
)

#: 제목만으로도 범주를 확정할 수 있는 강한 표제어.
_TITLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (eff, pat) for eff, pat in _PATTERNS
)


def classify_clause_effects(*, title: str | None, text: str | None) -> list[str]:
    """조항 하나의 법률효과 범주. 여러 개일 수 있다(복합 조항).

    제목에 걸린 범주를 먼저 두고, 본문에서 추가로 걸린 범주를 뒤에 붙인다.
    아무것도 걸리지 않으면 `other`.
    """
    t = str(title or "")
    b = str(text or "")
    from_title = [eff for eff, pat in _TITLE_PATTERNS if t and pat.search(t)]
    from_body = [eff for eff, pat in _PATTERNS if b and pat.search(b)]
    out: list[str] = []
    for eff in from_title + from_body:
        if eff not in out:
            out.append(eff)
    return out or [EFFECT_OTHER]


def primary_effect(*, title: str | None, text: str | None) -> str:
    return classify_clause_effects(title=title, text=text)[0]


# ── 거래 원형(archetype) ─────────────────────────────────────────────────────
#
# 계약유형 enum 과 별개로, 효과 프로파일에서 직접 읽어내는 거래의 형태.
# enum 에 없는 유형도 표현할 수 있어야 하므로 이 어휘를 따로 둔다.
ARCHETYPE_LICENSE = "ip_license"
ARCHETYPE_NDA = "confidentiality_only"
ARCHETYPE_GOODS = "goods_supply"
ARCHETYPE_SERVICE = "service_engagement"
ARCHETYPE_WORKS = "construction_works"
ARCHETYPE_DISTRIBUTION = "distribution_resale"
ARCHETYPE_BARTER = "non_monetary_exchange"
ARCHETYPE_LEASE = "lease_rental"
ARCHETYPE_UNKNOWN = "unknown"

ARCHETYPE_LABELS: dict[str, str] = {
    ARCHETYPE_LICENSE: "지식재산권 실시허락(라이선스)",
    ARCHETYPE_NDA: "비밀유지",
    ARCHETYPE_GOODS: "물품 공급·매매",
    ARCHETYPE_SERVICE: "용역·도급",
    ARCHETYPE_WORKS: "건설공사 도급",
    ARCHETYPE_DISTRIBUTION: "판매·유통",
    ARCHETYPE_BARTER: "대물교환(무현금)",
    ARCHETYPE_LEASE: "임대차·렌탈",
    ARCHETYPE_UNKNOWN: "미상",
}

#: 계약의 **자기 규정** — 표제와 정의조항이 스스로 밝히는 성격. 본문 어휘
#: 빈도보다 강한 신호다(라이선스 계약이 대금·보증 조항을 갖는 것은 당연하다).
_RX_SELF_DECLARED: tuple[tuple[str, re.Pattern[str]], ...] = (
    (ARCHETYPE_LICENSE, re.compile(
        r"license\s+agreement|licen[cs]ing\s+agreement|라이선스\s*계약|실시권\s*계약"
        r"|기술도입\s*계약|상표\s*사용\s*계약"
        r'|["“]?licensor["”]?|["“]?licensee["”]?|실시권자|허락권자',
        re.IGNORECASE)),
    (ARCHETYPE_NDA, re.compile(
        r"비밀유지\s*(?:계약|약정)|non[- ]disclosure\s+agreement|confidentiality\s+agreement"
        r"|기밀유지\s*(?:계약|약정)",
        re.IGNORECASE)),
    (ARCHETYPE_BARTER, re.compile(
        r"대물교환|물물교환|바터|barter"
        r"|별도의\s*현금\s*대가를\s*지급하지\s*아니|현금\s*지급이\s*없",
        re.IGNORECASE)),
    (ARCHETYPE_WORKS, re.compile(
        r"공사도급\s*계약|건설공사\s*계약|construction\s+contract|works\s+contract",
        re.IGNORECASE)),
    (ARCHETYPE_LEASE, re.compile(
        r"임대차\s*계약|렌탈\s*계약|lease\s+agreement|rental\s+agreement",
        re.IGNORECASE)),
    (ARCHETYPE_DISTRIBUTION, re.compile(
        r"대리점\s*계약|판매\s*대리점|위탁판매\s*계약|distribution\s+agreement"
        r"|dealer(?:ship)?\s+agreement|reseller\s+agreement",
        re.IGNORECASE)),
    (ARCHETYPE_GOODS, re.compile(
        r"물품\s*(?:공급|구매|매매)\s*계약|supply\s+agreement|purchase\s+agreement"
        r"|sale\s+of\s+goods",
        re.IGNORECASE)),
    (ARCHETYPE_SERVICE, re.compile(
        r"용역\s*계약|도급\s*계약|자문\s*계약|제작\s*계약|위탁\s*계약"
        r"|services?\s+agreement|consult(?:ing|ancy)\s+agreement",
        re.IGNORECASE)),
)

#: 표제·정의 탐색 범위. 계약의 성격 선언은 문서 앞머리에 온다.
_HEAD_CHARS = 2500


@dataclass
class ContractEffectProfile:
    """계약 전체의 법률효과 프로파일."""

    effect_counts: dict[str, int] = field(default_factory=dict)
    dominant_effects: list[str] = field(default_factory=list)
    archetype: str = ARCHETYPE_UNKNOWN
    archetype_label: str = ARCHETYPE_LABELS[ARCHETYPE_UNKNOWN]
    archetype_basis: str = ""
    self_declared: bool = False
    is_non_monetary: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "effect_counts": dict(self.effect_counts),
            "dominant_effects": list(self.dominant_effects),
            "archetype": self.archetype,
            "archetype_label": self.archetype_label,
            "archetype_basis": self.archetype_basis,
            "self_declared": self.self_declared,
            "is_non_monetary": self.is_non_monetary,
        }

    def has(self, effect: str, *, minimum: int = 1) -> bool:
        return int(self.effect_counts.get(effect, 0)) >= minimum


def _clause_pairs(clauses: list[Any] | None) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for c in (clauses or []):
        if isinstance(c, dict):
            out.append((str(c.get("title") or c.get("clause_title") or ""), str(c.get("text") or "")))
        else:
            out.append((str(getattr(c, "title", "") or ""), str(getattr(c, "text", "") or "")))
    return out


def build_effect_profile(
    *,
    text: str,
    clauses: list[Any] | None = None,
) -> ContractEffectProfile:
    """조항별 효과를 집계해 계약 전체의 프로파일과 거래 원형을 만든다."""
    body = str(text or "")
    counts: dict[str, int] = {}
    for title, clause_text in _clause_pairs(clauses):
        for eff in classify_clause_effects(title=title, text=clause_text):
            if eff == EFFECT_OTHER:
                continue
            counts[eff] = counts.get(eff, 0) + 1
    if not counts:
        # 조 단위 분해가 안 된 문서(스캔 PDF 등)는 전문 하나로 본다.
        for eff in classify_clause_effects(title="", text=body):
            if eff != EFFECT_OTHER:
                counts[eff] = counts.get(eff, 0) + 1

    dominant = [e for e, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]]

    head = body[:_HEAD_CHARS]
    is_non_monetary = bool(
        re.search(
            r"대물교환|물물교환|바터|barter|별도의\s*현금\s*대가를\s*지급하지\s*아니"
            r"|현금\s*지급이\s*없|금전\s*지급을\s*청구할\s*수\s*없",
            body, re.IGNORECASE,
        )
    )

    # 1순위: 계약이 스스로 밝힌 성격(표제·정의). 라이선스 계약이 대금·보증
    # 조항을 갖는 것은 당연하므로, 본문 어휘 빈도로 뒤집지 않는다.
    for archetype, pat in _RX_SELF_DECLARED:
        if pat.search(head):
            return ContractEffectProfile(
                effect_counts=counts,
                dominant_effects=dominant,
                archetype=archetype,
                archetype_label=ARCHETYPE_LABELS[archetype],
                archetype_basis=f"계약 표제·정의가 스스로 '{ARCHETYPE_LABELS[archetype]}'로 규정",
                self_declared=True,
                is_non_monetary=is_non_monetary or archetype == ARCHETYPE_BARTER,
            )

    # 2순위: 효과 프로파일. 지배 범주의 조합으로 원형을 읽는다.
    def n(eff: str) -> int:
        return int(counts.get(eff, 0))

    # 판매·유통 구조 신호. 표제가 없어도 이 장치들이 있으면 유통 거래다.
    _resale_signals = sum(
        1 for pat in (
            r"판매지역|판매\s*구역|영업\s*지역",
            r"판매장려금|판촉비|리베이트|인센티브",
            r"재판매|매입.{0,10}판매|사입|위탁판매",
            r"대리점|딜러|distributor|reseller|dealer",
            r"판매\s*목표|판매\s*실적|최소\s*구매",
        )
        if re.search(pat, body, re.IGNORECASE)
    )

    archetype = ARCHETYPE_UNKNOWN
    basis = ""
    if is_non_monetary:
        archetype, basis = ARCHETYPE_BARTER, "금전 대가가 없는 교환 구조"
    elif _resale_signals >= 3:
        archetype, basis = (
            ARCHETYPE_DISTRIBUTION,
            f"판매지역·장려금·재판매 등 유통 구조 신호 {_resale_signals}개",
        )
    elif (
        n(EFFECT_CONFIDENTIALITY) >= 2
        and not n(EFFECT_PAYMENT)
        and n(EFFECT_CONFIDENTIALITY) > n(EFFECT_DELIVERY)
    ):
        # NDA 에도 "정보의 제공·수령" 문언이 있어 delivery 가 잡힌다. 그것은
        # 물품 인도가 아니므로, 대가 구조가 없고 비밀유지가 압도적이면 NDA 다.
        archetype, basis = ARCHETYPE_NDA, "대가 구조 없이 비밀유지가 급부의 전부"
    elif n(EFFECT_IP) >= 2 and n(EFFECT_IP) >= n(EFFECT_DELIVERY):
        archetype, basis = ARCHETYPE_LICENSE, "지식재산권 실시허락이 급부의 중심"
    elif n(EFFECT_CHANGE) and n(EFFECT_DELIVERY) and n(EFFECT_SCOPE):
        archetype, basis = ARCHETYPE_WORKS, "설계변경·공정·검수 구조"
    elif n(EFFECT_OWNERSHIP) and n(EFFECT_DELIVERY) and n(EFFECT_PAYMENT):
        archetype, basis = ARCHETYPE_GOODS, "인도·소유권 이전·대금 구조"
    elif n(EFFECT_SCOPE) and n(EFFECT_PAYMENT):
        archetype, basis = ARCHETYPE_SERVICE, "급부 범위와 대가가 중심"

    return ContractEffectProfile(
        effect_counts=counts,
        dominant_effects=dominant,
        archetype=archetype,
        archetype_label=ARCHETYPE_LABELS.get(archetype, archetype),
        archetype_basis=basis,
        self_declared=False,
        is_non_monetary=is_non_monetary,
    )
