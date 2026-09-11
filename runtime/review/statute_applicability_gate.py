"""법률 적용요건 선판단 게이트 — "법률명이 떠올랐다"가 아니라 "법정 요건을
충족했다"를 먼저 확인한 뒤에만 그 법률 전용 rule/finding 을 살린다.

2026-09-10 지시 — "법률 적용요건을 먼저 판단. 법률명이 떠오른다고 바로
finding 생성하지 말 것. 각 법률마다 applicability gate 를 먼저 통과해야 함.
요건 불충족이면 해당 법률 전용 rule 은 전부 비활성화."

왜 필요했나 (골든 사례)
────────────────────
"콘텐츠 제작 대가로 가구를 제공하는 대물교환(바터) 계약"에서 아우리봇이
**하도급법 대물변제 금지 위반**을 HIGH 로 올렸다. 그러나 하도급법은

  · 원사업자가 **제조·수리·건설·용역위탁** 중 하나를 한 경우에만 적용되고,
  · 그중 용역위탁은 "**용역업을 영위하는 사업자**가 그 업에 따른 용역수행행위의
    전부 또는 일부를 다른 사업자에게 위탁" 하거나 "제3자로부터 위탁받은 용역을
    다시 위탁" 한 경우를 말한다(하도급법 제2조 제11항·제12항).

일룸은 **가구 제조·판매업**을 영위하며 영상제작을 업으로 하지 않는다. 자사
제품 홍보를 위한 부수적 콘텐츠를 외부에 맡긴 것은 용역위탁의 법정 정의에
해당하지 않는다. 제3자로부터 영상제작을 수주해 재위탁한 구조도 아니다.
→ **하도급법 비적용**이 먼저 나와야 했다.

설계 원칙
────────
· 특정 회사명·계약명·조항번호를 하드코딩하지 않는다. 판단은
  "**우리가 업으로 하는 일**" 과 "**이번에 위탁한 일**" 의 관계로만 한다.
· 우리 그룹이 어떤 업을 영위하는지는 계약이 아니라 **회사 정보**이므로
  `OUR_BUSINESS_DOMAINS` 에 데이터로 둔다(회사가 늘어나면 이 표만 고친다).
· 그래서 같은 로직이 반대 방향으로도 동작한다 — 영상제작사·광고대행사·
  방송사업자가 자기 콘텐츠 제작 업무 일부를 외주 주면 용역위탁 적용 가능성이
  살아난다.
· 요건을 확정할 수 없으면 "적용"도 "비적용"도 아닌 **사실확인 필요**로 둔다.
  모르는 것을 안다고 하지 않는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ── 업(業) 도메인 ────────────────────────────────────────────────────────────
#: 위탁 대상이 될 수 있는 일의 종류. 하도급법 판단은 "이 도메인이 우리 업에
#: 속하는가"로 환원된다.
DOMAIN_LABELS: dict[str, str] = {
    "manufacturing": "물품의 제조·가공",
    "furniture_manufacturing": "가구 제조",
    "furniture_sales": "가구 판매·유통",
    "installation_service": "설치·시공 용역",
    "logistics": "물류·운송",
    "construction": "건설공사",
    "repair": "수리",
    "content_production": "영상·콘텐츠 제작",
    "advertising_marketing": "광고·마케팅 대행",
    "software_development": "소프트웨어·시스템 개발",
    "design": "디자인",
    "consulting": "자문·컨설팅",
    "testing_inspection": "시험·검사·인증",
}

#: 우리(발주자) 측이 **업으로 영위하는** 도메인.
#:
#: 2026-09-10 확인 — 퍼시스그룹 계열사는 모두 가구를 제조·판매하거나
#: 설치용역·물류업무(레터스, 구 바로스)를 수행하는 회사다. 콘텐츠 제작, 광고·마케팅,
#: 소프트웨어 개발은 어느 계열사의 업도 아니다.
#:
#: 이 표는 "우리가 무엇을 업으로 하는가"라는 회사 사실이지 계약별 하드코딩이
#: 아니다. 계열사가 새 사업을 시작하면 여기만 고치면 판단이 따라 바뀐다.
GROUP_DEFAULT_BUSINESS_DOMAINS: frozenset[str] = frozenset({
    "manufacturing",
    "furniture_manufacturing",
    "furniture_sales",
    "installation_service",
    "logistics",
})

#: 계열사별 예외. `group_entities` 의 registry 에서 가져온다 — 회사명·상호변경
#: 이력은 그쪽이 단일 출처다(2026-09-11 지시: 바로스 → 레터스 상호 변경).
#: 이 dict 는 registry 를 거치지 않는 추가 예외를 넣기 위해 남겨 둔다.
OUR_BUSINESS_DOMAINS: dict[str, frozenset[str]] = {}


def our_business_domains(entity: str | None) -> frozenset[str]:
    """우리 회사가 업으로 영위하는 도메인 집합."""
    from runtime.review.group_entities import entity_business_domains

    name = str(entity or "").strip().lower()
    for key, domains in OUR_BUSINESS_DOMAINS.items():
        if key.lower() in name:
            return domains
    registered = entity_business_domains(entity)
    if registered:
        return registered
    return GROUP_DEFAULT_BUSINESS_DOMAINS


# ── 위탁 대상 도메인 추론 ────────────────────────────────────────────────────
_DOMAIN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("content_production", re.compile(
        r"영상\s*(제작|콘텐츠)|콘텐츠\s*제작|숏폼|유튜브|YouTube|촬영|편집본|썸네일"
        r"|영상물|방송\s*제작|사진\s*촬영",
        re.IGNORECASE)),
    ("advertising_marketing", re.compile(
        r"광고\s*대행|광고대행사|마케팅\s*대행|매체\s*집행|미디어렙|퍼포먼스\s*마케팅"
        r"|SNS\s*운영\s*대행|바이럴",
        re.IGNORECASE)),
    ("software_development", re.compile(
        r"소프트웨어\s*개발|시스템\s*개발|앱\s*개발|프로그램\s*개발|소스코드|SI\s*구축"
        r"|웹사이트\s*구축|API\s*개발",
        re.IGNORECASE)),
    ("construction", re.compile(
        r"건설공사|공사도급|시공사|건축공사|토목|착공|준공검사|공정률",
        re.IGNORECASE)),
    ("installation_service", re.compile(
        r"설치\s*용역|설치공사|납품\s*및\s*설치|현장\s*설치|가구\s*설치",
        re.IGNORECASE)),
    ("manufacturing", re.compile(
        r"제조위탁|OEM|ODM|주문\s*제작|사양(서)?\s*(에\s*따라|대로)\s*제작|임가공|가공위탁"
        r"|금형|생산\s*위탁",
        re.IGNORECASE)),
    ("repair", re.compile(r"수리위탁|정비\s*용역|보수\s*용역", re.IGNORECASE)),
    ("logistics", re.compile(r"운송\s*용역|화물\s*운송|물류\s*위탁|배송\s*대행", re.IGNORECASE)),
    ("testing_inspection", re.compile(r"시험\s*의뢰|검사\s*용역|인증\s*시험|성적서", re.IGNORECASE)),
    ("consulting", re.compile(r"자문\s*용역|컨설팅\s*용역|advisory", re.IGNORECASE)),
    ("design", re.compile(r"디자인\s*용역|설계\s*용역", re.IGNORECASE)),
]

#: 계약유형 코드 → 위탁 도메인. 분류기가 이미 확정한 값이 있으면 텍스트
#: 추론보다 우선한다.
_TYPE_CODE_DOMAIN: dict[str, str] = {
    "advertising_content_production": "content_production",
    "content_production": "content_production",
    "marketing_ai_search": "advertising_marketing",
    "software_dev": "software_development",
    "app_development": "software_development",
    "construction": "construction",
    "project_installation": "installation_service",
    "equipment_installation": "installation_service",
    "testing_inspection_service": "testing_inspection",
    "advisory": "consulting",
}

#: 제3자로부터 수주한 일을 다시 맡기는 구조(재위탁) 신호.
_RX_RE_ENTRUSTMENT = re.compile(
    r"재위탁|재하도급|하도급받은|수급받은\s*(용역|업무)|발주처(로부터|에서)\s*수주"
    r"|원도급(계약|사)|제3자로부터\s*위탁받[은아]",
    re.IGNORECASE,
)

#: 우리가 그 일을 **업으로 한다**는 계약 내 직접 신호(회사 표에 없더라도
#: 계약서 스스로 밝히면 존중한다).
_RX_WE_DO_IT_AS_BUSINESS = re.compile(
    r"당사의\s*주된\s*사업|영위하는\s*사업으로서|본업으로\s*하는|업으로\s*영위",
    re.IGNORECASE,
)


def infer_entrusted_domain(*, text: str, contract_type_code: str = "") -> str:
    """이번 계약에서 상대방에게 맡긴 일이 어느 도메인인지."""
    code = str(contract_type_code or "").strip()
    if code in _TYPE_CODE_DOMAIN:
        return _TYPE_CODE_DOMAIN[code]
    body = str(text or "")
    for domain, pat in _DOMAIN_PATTERNS:
        if pat.search(body):
            return domain
    return ""


# ── 판단 결과 ────────────────────────────────────────────────────────────────
CONCLUSION_APPLICABLE = "적용"
CONCLUSION_NOT_APPLICABLE = "비적용"
CONCLUSION_PARTIAL = "일부 적용"
CONCLUSION_NEEDS_FACTS = "사실확인 필요"


@dataclass
class StatuteDecision:
    """법률 하나에 대한 적용요건 판단."""

    statute: str
    conclusion: str
    reason: str
    #: 이 법률이 비적용일 때 함께 꺼야 하는 rule 주제 키워드.
    disabled_topics: list[str] = field(default_factory=list)
    facts_needed: list[str] = field(default_factory=list)

    @property
    def applicable(self) -> bool:
        return self.conclusion in (CONCLUSION_APPLICABLE, CONCLUSION_PARTIAL)

    @property
    def blocked(self) -> bool:
        """이 법률 전용 rule 을 비활성화해야 하는가."""
        return self.conclusion == CONCLUSION_NOT_APPLICABLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "statute": self.statute,
            "conclusion": self.conclusion,
            "applicable": self.applicable,
            "reason": self.reason,
            "disabled_topics": list(self.disabled_topics),
            "facts_needed": list(self.facts_needed),
        }


#: 하도급법 전용 rule 이 다루는 주제어. 비적용 확정 시 이 표현을 담은
#: finding 은 전부 제거한다(대금·단가·대물변제·부당해지·지급기한 등).
SUBCONTRACT_ACT_TOPICS: tuple[str, ...] = (
    "하도급법",
    "하도급거래",
    "하도급대금",
    "하도급 대금",
    "대물변제",
    "부당한 하도급대금",
    "부당 단가",
    "부당한 단가",
    "하도급대금 지급기한",
    "원사업자",
    "수급사업자",
    "발주자에 대한 직접지급",
)


def assess_subcontract_act(
    *,
    entity: str,
    text: str,
    contract_type_code: str = "",
) -> StatuteDecision:
    """하도급법 적용요건(법 제2조)을 선결적으로 판단한다.

    적용되려면 이번 위탁이 **제조위탁·수리위탁·건설위탁·용역위탁** 중
    하나여야 한다. 특히 용역위탁은 "용역업을 영위하는 사업자가 그 업에 따른
    용역수행행위의 전부 또는 일부를 위탁" 하거나 "위탁받은 용역을 재위탁"
    하는 경우로 법이 한정한다 — 외부 업체에 용역을 맡겼다는 사실만으로는
    성립하지 않는다.
    """
    body = str(text or "")
    ours = our_business_domains(entity)
    domain = infer_entrusted_domain(text=body, contract_type_code=contract_type_code)
    domain_label = DOMAIN_LABELS.get(domain, domain or "(도메인 미상)")
    ours_label = ", ".join(sorted(DOMAIN_LABELS.get(d, d) for d in ours))

    # (1) 재위탁 — 제3자로부터 위탁받은 일을 다시 맡기는 구조면 업 여부와
    #     무관하게 용역위탁이 성립할 수 있다.
    if _RX_RE_ENTRUSTMENT.search(body):
        return StatuteDecision(
            statute="하도급법",
            conclusion=CONCLUSION_APPLICABLE,
            reason=(
                "제3자로부터 위탁받은 업무를 다시 위탁하는 재위탁 구조가 확인되어, "
                "하도급법상 위탁(재위탁)에 해당할 수 있습니다."
            ),
        )

    # (2) 제조위탁 — 우리가 물품의 제조·판매를 업으로 하면서 사양을 정해
    #     제조·가공을 맡기면 제조위탁이다.
    if domain in ("manufacturing", "repair"):
        if ours & {"manufacturing", "furniture_manufacturing", "furniture_sales"}:
            return StatuteDecision(
                statute="하도급법",
                conclusion=CONCLUSION_APPLICABLE,
                reason=(
                    f"우리 회사가 {ours_label}을(를) 업으로 영위하면서 "
                    f"{domain_label}을(를) 위탁하는 구조로, 하도급법상 제조위탁에 해당합니다."
                ),
            )

    # (3) 건설위탁 — 건설업자가 건설공사를 위탁하는 경우.
    if domain == "construction" and ("construction" in ours):
        return StatuteDecision(
            statute="하도급법",
            conclusion=CONCLUSION_APPLICABLE,
            reason="건설업을 영위하는 사업자가 건설공사를 위탁하는 구조로 건설위탁에 해당합니다.",
        )

    # (4) 용역위탁 — 우리가 **그 용역업을 업으로 영위**해야 한다.
    if domain:
        if domain in ours or _RX_WE_DO_IT_AS_BUSINESS.search(body):
            return StatuteDecision(
                statute="하도급법",
                conclusion=CONCLUSION_APPLICABLE,
                reason=(
                    f"우리 회사가 {domain_label}을(를) 업으로 영위하면서 그 업에 따른 "
                    "용역수행행위의 일부를 위탁하는 구조로, 하도급법상 용역위탁에 해당합니다."
                ),
            )
        return StatuteDecision(
            statute="하도급법",
            conclusion=CONCLUSION_NOT_APPLICABLE,
            reason=(
                f"하도급법상 용역위탁은 '용역업을 영위하는 사업자가 그 업에 따른 용역수행행위를 "
                f"위탁'하는 경우를 말합니다(법 제2조 제11항). 우리 회사의 업은 {ours_label}이며 "
                f"{domain_label}을(를) 업으로 하지 않고, 제3자로부터 수주한 업무를 재위탁하는 "
                "구조도 아니므로 하도급법이 적용되지 않습니다."
            ),
            disabled_topics=list(SUBCONTRACT_ACT_TOPICS),
        )

    # 도메인을 특정하지 못하면 단정하지 않는다.
    return StatuteDecision(
        statute="하도급법",
        conclusion=CONCLUSION_NEEDS_FACTS,
        reason=(
            "위탁 대상 업무의 성격을 계약 문언만으로 특정하지 못해 하도급법상 위탁 유형"
            "(제조·수리·건설·용역) 해당 여부를 확정할 수 없습니다."
        ),
        facts_needed=["이번 계약으로 상대방에게 맡긴 업무가 무엇인지", "우리 회사가 그 업무를 업으로 영위하는지"],
    )


# ══════════════════════════════════════════════════════════════════════════
# 대리점법 — 대리점거래의 공정화에 관한 법률
# ══════════════════════════════════════════════════════════════════════════

#: 대리점법 전용 rule 이 다루는 주제어.
DEALER_ACT_TOPICS: tuple[str, ...] = (
    "대리점법",
    "대리점거래",
    "불이익 제공 금지",
    "경영간섭",
    "구입강제",
    "판매목표 강제",
    "경제적 이익 제공 강요",
)
# NOTE "거래상 지위 남용" 은 여기에 넣지 않는다 — 그것은 공정거래법 제45조의
# 개념이라 대리점법이 비적용이어도 그대로 성립한다. 대리점법 토픽에 넣었더니
# 대리점법 비적용 판정 하나가 전략적 제휴계약의 직접거래제한+배액위약벌
# finding 을 통째로 지웠다(실측, 2026-09-10).

#: 대리점법상 "대리점거래" = 공급업자로부터 상품·용역을 **공급받아 재판매**
#: 하거나 위탁판매하는 계속적 거래(법 제2조 제1호).
_RX_RESALE_RELATIONSHIP = re.compile(
    r"재판매|위탁판매|수탁판매|대리점|딜러|distributor|reseller|dealer(?:ship)?"
    r"|판매지역|판매\s*구역|판매목표|판매장려금|판촉비|공급가격|출고가",
    re.IGNORECASE,
)
_RX_CONTINUOUS_SUPPLY = re.compile(
    r"계속(?:적|하여)\s*(?:공급|거래)|기본계약|개별계약|발주(?:서|하여)"
    r"|공급받[아은]|납품받[아은]",
    re.IGNORECASE,
)


def assess_dealer_act(
    *,
    text: str,
    transaction_type: str = "",
) -> StatuteDecision:
    """대리점법 적용요건(법 제2조 제1호)을 선결적으로 판단한다.

    "대리점거래" 는 공급업자로부터 상품·용역을 공급받아 **재판매하거나
    위탁판매** 하는 계속적 거래를 말한다. 판매·유통 관계가 없으면 이 법의
    불이익제공·경영간섭·구입강제 조항은 적용될 여지가 없다.
    """
    body = str(text or "")
    if transaction_type == "distribution_resale":
        return StatuteDecision(
            statute="대리점법",
            conclusion=CONCLUSION_APPLICABLE,
            reason="공급업자–판매업자 간 재판매·위탁판매 구조로 대리점거래에 해당합니다.",
        )
    has_resale = bool(_RX_RESALE_RELATIONSHIP.search(body))
    has_continuous = bool(_RX_CONTINUOUS_SUPPLY.search(body))
    if has_resale and has_continuous:
        return StatuteDecision(
            statute="대리점법",
            conclusion=CONCLUSION_APPLICABLE,
            reason="상품을 공급받아 재판매하는 계속적 거래 구조가 확인되어 대리점거래에 해당할 수 있습니다.",
        )
    return StatuteDecision(
        statute="대리점법",
        conclusion=CONCLUSION_NOT_APPLICABLE,
        reason=(
            "대리점법상 '대리점거래'는 공급업자로부터 상품·용역을 공급받아 재판매하거나 "
            "위탁판매하는 계속적 거래를 말합니다(법 제2조 제1호). 이 계약에는 재판매·"
            "위탁판매 관계가 없어 대리점법이 적용되지 않습니다."
        ),
        disabled_topics=list(DEALER_ACT_TOPICS),
    )


# ══════════════════════════════════════════════════════════════════════════
# 개인정보 보호법
# ══════════════════════════════════════════════════════════════════════════

PRIVACY_ACT_TOPICS: tuple[str, ...] = (
    "개인정보 처리위탁",
    "수탁자 관리·감독",
    "정보주체",
    "개인정보 보호법",
    "개인정보보호법",
    "가명정보",
    "고유식별정보",
)

#: 실제로 개인정보를 처리하는 구조인지. 단어가 스치는 것으로는 부족하다.
_RX_PERSONAL_DATA_PROCESSING = re.compile(
    r"개인정보(?:의)?\s*(?:수집|이용|제공|처리|위탁|파기|보유)"
    r"|정보주체|고유식별정보|민감정보|가명정보"
    r"|성명[^.\n]{0,20}연락처|연락처[^.\n]{0,20}제공"
    r"|초상권|출연자[^.\n]{0,20}동의"
    r"|personal\s+(?:data|information)\s+(?:process|collect|transfer)",
    re.IGNORECASE,
)


#: 개인정보일 **가능성**이 있는 데이터가 오가는 신호. 확정 신호는 아니지만,
#: 이것이 있으면 "적용되지 않는다"고 단정해서는 안 된다.
_RX_DATA_FLOW = re.compile(
    r"데이터|정보의?\s*(?:제공|공유|이전|반출)|로그|이용자|사용자\s*정보|고객\s*정보"
    r"|생체|건강|수면|음성|영상\s*자료|촬영|학습\s*데이터|dataset|data\s+set",
    re.IGNORECASE,
)


def assess_privacy_act(*, text: str) -> StatuteDecision:
    """개인정보 보호법 — 실제 개인정보 처리가 있어야 적용된다.

    다만 "비적용" 은 **개인정보가 오갈 여지 자체가 없는** 계약에만 붙인다.
    데이터가 오가는데 그것이 개인정보인지 계약 문언만으로 판단할 수 없는
    경우는 `사실확인 필요` 다 — 여기서 성급히 비적용으로 확정하면 "개인정보
    처리 경계가 계약에 없다" 는 정당한 지적까지 함께 지워진다(실측: AI·수면
    데이터 공동연구 NDA 에서 개인정보 경계 finding 이 통째로 사라졌다).
    """
    body = str(text or "")
    if _RX_PERSONAL_DATA_PROCESSING.search(body):
        return StatuteDecision(
            statute="개인정보보호법",
            conclusion=CONCLUSION_PARTIAL,
            reason="계약 이행 과정에서 개인정보(초상·연락처 등)를 수집·제공하는 구조가 확인되어 해당 부분에 적용됩니다.",
        )
    if _RX_DATA_FLOW.search(body):
        return StatuteDecision(
            statute="개인정보보호법",
            conclusion=CONCLUSION_NEEDS_FACTS,
            reason=(
                "데이터가 오가는 구조는 있으나 그 데이터에 개인정보가 포함되는지가 "
                "계약 문언만으로 확정되지 않습니다. 포함된다면 수집·이용 근거와 "
                "처리위탁 요건을 갖추어야 합니다."
            ),
            facts_needed=["주고받는 데이터에 개인정보(식별 가능한 정보)가 포함되는지"],
        )
    return StatuteDecision(
        statute="개인정보보호법",
        conclusion=CONCLUSION_NOT_APPLICABLE,
        reason="이 계약에서 개인정보를 수집·이용·제공·위탁하는 구조가 확인되지 않습니다.",
        disabled_topics=list(PRIVACY_ACT_TOPICS),
    )


# ══════════════════════════════════════════════════════════════════════════
# 건설산업기본법
# ══════════════════════════════════════════════════════════════════════════

CONSTRUCTION_ACT_TOPICS: tuple[str, ...] = (
    "건설산업기본법",
    "건설공사 도급",
    "하도급 제한",
    "건설업 등록",
    "시공관리",
)

#: 건설공사 도급의 개별 신호. 하나만으로는 부족하다 — "시공" 이라는 단어는
#: 가구 설치·전략적 제휴 계약에도 흔히 등장한다(실측: 전략적 제휴계약이
#: "시공" 16회만으로 건설산업기본법 적용으로 판정됐다).
_CONSTRUCTION_SIGNALS: tuple[str, ...] = (
    r"건설공사", r"공사도급", r"착공", r"준공(?:검사|일|계)", r"기성(?:고|금|검사)",
    r"설계변경", r"공정률", r"현장대리인", r"하자보수보증금", r"건설업\s*등록",
    r"construction\s+works",
)


def _construction_signal_count(text: str) -> int:
    body = str(text or "")
    return sum(1 for p in _CONSTRUCTION_SIGNALS if re.search(p, body, re.IGNORECASE))


def assess_construction_act(*, text: str, transaction_type: str = "") -> StatuteDecision:
    """건설산업기본법 — 실제 건설공사 도급이어야 적용된다."""
    if transaction_type == "construction_works" or _construction_signal_count(text) >= 2:
        return StatuteDecision(
            statute="건설산업기본법",
            conclusion=CONCLUSION_APPLICABLE,
            reason="건설공사의 도급 구조(착공·준공·기성·설계변경 등)가 확인됩니다.",
        )
    return StatuteDecision(
        statute="건설산업기본법",
        conclusion=CONCLUSION_NOT_APPLICABLE,
        reason="이 계약은 건설공사의 도급이 아니므로 건설산업기본법이 적용되지 않습니다.",
        disabled_topics=list(CONSTRUCTION_ACT_TOPICS),
    )


# ══════════════════════════════════════════════════════════════════════════
# 대규모유통업법
# ══════════════════════════════════════════════════════════════════════════

LARGE_RETAIL_ACT_TOPICS: tuple[str, ...] = (
    "대규모유통업법",
    "대규모유통업",
    "판매장려금 수취",
    "納品業者",
    "납품업자",
    "매장 임차인",
)

_RX_LARGE_RETAIL = re.compile(
    r"대규모유통업|백화점|대형마트|아웃렛|면세점|납품업자|매장\s*임차"
    r"|직매입|특약매입|판매수수료\s*매장",
    re.IGNORECASE,
)


def assess_large_retail_act(*, text: str) -> StatuteDecision:
    """대규모유통업법 — 대규모유통업자–납품업자 관계여야 적용된다."""
    if _RX_LARGE_RETAIL.search(str(text or "")):
        return StatuteDecision(
            statute="대규모유통업법",
            conclusion=CONCLUSION_NEEDS_FACTS,
            reason=(
                "대규모유통업자–납품업자 관계로 보이는 표현이 있습니다. 상대방의 매출액·"
                "매장면적 요건(법 제2조 제1호) 충족 여부를 확인해야 적용 여부가 확정됩니다."
            ),
            facts_needed=["상대방이 법정 매출액·매장면적 요건을 충족하는 대규모유통업자인지"],
        )
    return StatuteDecision(
        statute="대규모유통업법",
        conclusion=CONCLUSION_NOT_APPLICABLE,
        reason="대규모유통업자와 납품업자 사이의 거래가 아니므로 적용되지 않습니다.",
        disabled_topics=list(LARGE_RETAIL_ACT_TOPICS),
    )


# ══════════════════════════════════════════════════════════════════════════
# 표시·광고의 공정화에 관한 법률
# ══════════════════════════════════════════════════════════════════════════

AD_ACT_TOPICS: tuple[str, ...] = (
    "표시광고법",
    "표시·광고의 공정화",
    "협찬 표시",
    "추천·보증",
    "기만적 표시",
)

_RX_ADVERTISING = re.compile(
    r"광고|홍보|협찬|추천·?\s*보증|표시·?\s*광고|마케팅\s*콘텐츠|인플루언서"
    r"|advertis|sponsorship|endorsement",
    re.IGNORECASE,
)


def assess_advertising_act(*, text: str) -> StatuteDecision:
    """표시광고법 — 대외 광고·표시 행위가 있어야 적용된다."""
    if _RX_ADVERTISING.search(str(text or "")):
        return StatuteDecision(
            statute="표시광고법",
            conclusion=CONCLUSION_PARTIAL,
            reason="광고·협찬 표시 행위가 예정되어 있어 표시·광고 관련 부분에 적용됩니다.",
        )
    return StatuteDecision(
        statute="표시광고법",
        conclusion=CONCLUSION_NOT_APPLICABLE,
        reason="대외 광고·표시 행위가 예정되어 있지 않습니다.",
        disabled_topics=list(AD_ACT_TOPICS),
    )


def assess_statutes(
    *,
    entity: str,
    text: str,
    contract_type_code: str = "",
    transaction_type: str = "",
) -> list[StatuteDecision]:
    """적용요건 게이트가 정의된 법률을 **모두** 판단한다(2026-09-10 지시 항목 3).

    "키워드가 보인다 → 법률 적용" 을 끊는 것이 목적이므로, 판단 순서를
    반드시 `사실관계 → 법정 적용요건 → 적용/비적용` 으로 고정한다.
    요건 불충족이면 그 법률 전용 rule 전체를 비활성화한다.

    `transaction_type` 은 `legal_state` 가 확정한 거래 원형이다. 있으면
    텍스트 휴리스틱보다 우선한다 — 같은 판단을 두 번 하지 않기 위함이다.
    """
    return [
        assess_subcontract_act(entity=entity, text=text, contract_type_code=contract_type_code),
        assess_dealer_act(text=text, transaction_type=transaction_type),
        assess_privacy_act(text=text),
        assess_construction_act(text=text, transaction_type=transaction_type),
        assess_large_retail_act(text=text),
        assess_advertising_act(text=text),
    ]


def blocked_topics(decisions: list[StatuteDecision]) -> list[str]:
    out: list[str] = []
    for d in decisions:
        if d.blocked:
            out.extend(d.disabled_topics)
    return out


#: 그 법률의 **의무·금지·제재를 주장**하는 문장의 표지. 비적용 법률을 근거로
#: 무엇인가를 요구하는 finding 만 제거 대상이다.
_RX_STATUTE_ASSERTION = re.compile(
    r"위반|위법|무효|금지|의무|해당(?:한다|할\s*수\s*있|됩니다)|적용(?:된다|됩니다|받)"
    r"|시정명령|과징금|과태료|제재|처벌|규정에\s*따라",
)

#: 반대로, 이런 finding 은 그 법률을 적용하는 것이 아니라 **사실확인·누락**을
#: 지적하는 것이므로 비적용 판정과 무관하게 남긴다.
_RX_FACT_OR_GAP = re.compile(
    r"확인이?\s*필요|확정되지\s*(?:않|아니)|규정되지\s*(?:않|아니)|없습니다|누락"
    r"|불명확|특정되지\s*(?:않|아니)|경계|별도\s*계약|사실관계",
)


def deactivate_inapplicable_statute_findings(
    clause_results: list[dict[str, Any]],
    decisions: list[StatuteDecision],
) -> list[dict[str, Any]]:
    """비적용으로 확정된 법률 **전용** finding 을 제거한다.

    [2026-09-10 보정] "그 법률 이름이 등장한다" 만으로 지우면 과차단이 된다.
    실측: AI·수면 데이터 공동연구 NDA 에서 "개인정보 처리 경계가 계약에
    규정되지 않았다" 는 정당한 지적이, 개인정보보호법 비적용 판정 때문에
    함께 삭제됐다. 그 finding 은 그 법을 **적용**하는 것이 아니라 사실확인·
    누락을 지적하는 것이다.

    그래서 제거 대상을 "법률명 + 그 법의 의무·금지·제재를 **주장**하는 문장"
    으로 좁히고, 사실확인·누락 지적은 남긴다.

    제거 내역을 돌려준다 — 조용히 사라지지 않게 하기 위함이다.
    """
    topics = blocked_topics(decisions)
    if not topics:
        return []
    reasons = {d.statute: d.reason for d in decisions if d.blocked}
    removed: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            kept.append(cr)
            continue
        blob = " ".join(
            str(cr.get(k) or "")
            for k in (
                "issue_title", "problem", "rewrite_reason", "legal_business_reason",
                "suggested_rewrite", "recommendation_text", "negotiation_strategy",
            )
        )
        detected = cr.get("detected_issue_list")
        if isinstance(detected, list):
            blob += " " + " ".join(
                str(d.get("issue_title") or "") for d in detected if isinstance(d, dict)
            )
        hit = next((t for t in topics if t in blob), "")
        if not hit:
            kept.append(cr)
            continue
        # 그 법을 근거로 무엇인가를 **주장**하지 않으면 제거 대상이 아니다.
        if not _RX_STATUTE_ASSERTION.search(blob):
            kept.append(cr)
            continue
        # 사실확인·누락 지적은 법률 적용이 아니라 계약 미비의 지적이다.
        if _RX_FACT_OR_GAP.search(blob):
            kept.append(cr)
            continue
        removed.append({
            "clause_id": str(cr.get("clause_id") or ""),
            "matched_topic": hit,
            "reason": next(iter(reasons.values()), ""),
        })
    clause_results[:] = kept
    return removed
