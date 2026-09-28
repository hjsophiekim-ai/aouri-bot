"""Employee NDA 거래모델 — 임직원 비밀유지계약을 **질문·검토 전에** 확정한다.

2026-09-28 지시. 실측: 신규 입사자(Accounting Associate) 비밀유지계약을 NDA 로
인식한 뒤에도 사전질문에 "대가(금액·단가) 산정 근거 — 부가가치세·특수관계인",
"최대 손해 규모를 계약 대가 기준으로", "개인정보 제3자 제공·재위탁 절차" 가
나갔다. 필수 검토항목에는 다른 NDA(기술협업) 의 "범용 AI 학습 제한",
"음성·수면·건강 정보" 가 사용자 검토항목처럼 들어갔다.

원인은 하나다 — 'NDA' 라는 큰 분류만 있고, 그 안에서 **누가 누구에게 무엇을
지키겠다고 약속하는지**(거래모델)를 세우는 단계가 없었다. 사업 파트너 간
상호 NDA 와 고용관계의 직원 비밀유지 서약은 법률효과가 다르다. 후자에는
대가도, 처리위탁도, 공동개발 결과도 없다. 대신 고용법(경업금지 무효, 내부고발·
임금논의 보호, 영업비밀 면책 고지)이 적용된다.

이 모듈이 하는 일
──────────────
계약 원문(+ 담당자 설명)에서 아래를 확정해 하나의 값으로 얼린다.

    contract_type / subtype          nda_confidentiality / employee_nda
    employer / employee              계약서가 부르는 당사자 명칭
    our_company / our_side           우리 회사(계열사 표에서 확인) / employer
    governing_law                    준거법 (예: California, USA)
    purpose                          비밀유지 약정의 주된 목적
    information_types                직원이 접근하는 정보 유형
    personal_data_structure          내부 직원 접근 / 외부 처리위탁 / 제3자 제공
    post_employment / carve-outs     퇴직 후 제한·법정 공개 예외의 존재 여부

**하드코딩 금지** — 특정 회사명·조항번호를 쓰지 않는다. 당사자는 계약서의
정의 문언에서, 우리 회사는 `group_entities` 표에서, 관할은 준거법 조항에서
읽는다. 확신할 수 없으면 `confident=False` 로 두고 **아무것도 끄지 않는다**
(광고·건설 거래모델과 같은 원칙).

질문 생성(`questions/employee_nda_questions.py`)과 검토 파이프라인
(`clause_level`)은 같은 함수 `resolve_employee_nda_model()` 을 부른다 —
두 곳이 각자 판단하면 질문과 리포트가 서로 다른 계약을 말하게 된다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

SUBTYPE_EMPLOYEE_NDA = "employee_nda"
EMPLOYEE_NDA_LABEL = "임직원 비밀유지계약(Employee NDA / Employee Confidentiality Agreement)"

PD_EMPLOYEE_INTERNAL = "employee_internal_access"
PD_PROCESSOR = "processor_outsourcing"
PD_THIRD_PARTY = "third_party_disclosure"

PD_LABELS: dict[str, str] = {
    PD_EMPLOYEE_INTERNAL: "내부 직원의 업무상 접근(employee internal access)",
    PD_PROCESSOR: "외부 업체에 대한 처리위탁(processor/vendor outsourcing)",
    PD_THIRD_PARTY: "독립된 제3자에 대한 제공(third-party disclosure)",
}

#: 비밀유지 계열로 인정하는 canonical 유형. 이 밖의 유형에서는 판정하지 않는다.
NDA_TYPE_CODES = frozenset({"nda_confidentiality"})


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


# ── 1. 직원이 **당사자**로 정의되는가 ─────────────────────────────────────
# "직원" 이라는 낱말은 사업자 간 NDA 에도 나온다("its employees and advisors").
# 당사자 정의 문언(괄호 정의·"이하 …라 한다")에서 직원을 부를 때만 센다.
_RX_EMPLOYEE_PARTY_EN = _rx(
    r"\(\s*(?:the\s+)?[\"“”']?\s*(?:Employee|Associate|Team\s+Member|Staff\s+Member)\s*[\"“”']?\s*\)"
)
_RX_EMPLOYEE_PARTY_KO = _rx(
    r"(?:이하|以下)\s*[\"“”'‘’「]?\s*(?:직원|근로자|임직원|서약자|사원|피고용인)\s*[\"“”'‘’」]?\s*(?:이?라|으로)\s*(?:한다|칭한다|함)"
)
_RX_EMPLOYER_PARTY_EN = _rx(
    r"\(\s*(?:the\s+)?[\"“”']?\s*(?:Company|Employer)\s*[\"“”']?\s*\)"
)
_RX_EMPLOYER_PARTY_KO = _rx(
    r"(?:이하|以下)\s*[\"“”'‘’「]?\s*(?:회사|사용자|고용주)\s*[\"“”'‘’」]?\s*(?:이?라|으로)\s*(?:한다|칭한다|함)"
)

# ── 2. 고용관계 신호 ──────────────────────────────────────────────────────
_EMPLOYMENT_SIGNALS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("consideration_of_employment", _rx(r"consideration\s+of\s+(?:the\s+)?Employee['’]?s?\s+(?:employment|continued\s+employment)|in\s+consideration\s+of\s+(?:my|your|the)?\s*(?:employment|continued\s+employment)")),
    ("employed_by", _rx(r"employed\s+by\s+the\s+(?:Company|Employer)|position\s+of\s+[A-Z][\w\s/&-]{2,60}")),
    ("termination_of_employment", _rx(r"(?:termination|end|separation)\s+(?:of|from)\s+(?:Employee['’]?s\s+)?employment|after\s+employment\s+ends|following\s+separation")),
    ("at_will", _rx(r"at[- ]will")),
    ("during_employment", _rx(r"during\s+(?:Employee['’]?s\s+)?employment|course\s+of\s+(?:Employee['’]?s\s+)?(?:employment|duties)")),
    ("ko_hired", _rx(r"입사|채용|근로계약|고용계약")),
    ("ko_during_employment", _rx(r"재직\s*(?:중|기간|하는\s*동안)")),
    ("ko_after_employment", _rx(r"퇴직\s*(?:후|시|이후)|퇴사\s*(?:후|시|이후)")),
)

# ── 3. 사업자 간 거래 신호 — 있으면 확신하지 않는다 ─────────────────────
_RX_COMMERCIAL_CONSIDERATION = _rx(
    r"대금|용역비|계약금액|단가|수수료\s*(?:를|은|는)?\s*지급|purchase\s+price|\bfees?\s+(?:of|payable|shall)|\$\s?\d[\d,]*|USD\s?\d"
)

# ── 4. 준거법 ─────────────────────────────────────────────────────────────
_US_STATES = (
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
    "Delaware", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa",
    "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan",
    "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina",
    "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island",
    "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont",
    "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming",
)
_RX_GOVERNING_EN = _rx(
    r"govern(?:ed|s)?\s+by[^.]{0,80}?laws?\s+of\s+(?:the\s+)?(?:State\s+of\s+|Commonwealth\s+of\s+)?("
    + "|".join(re.escape(s) for s in _US_STATES)
    + r"|England(?:\s+and\s+Wales)?|Korea|the\s+Republic\s+of\s+Korea|Singapore|Hong\s+Kong|Japan|Vietnam|Taiwan)"
)
_RX_GOVERNING_KO = _rx(r"(대한민국|한국)\s*법(?:령|률)?(?:을|에)?\s*(?:준거법|따른다|의한다|적용)")

# ── 5. 직원이 접근하는 정보 유형 ──────────────────────────────────────────
INFO_TYPE_LABELS: dict[str, str] = {
    "financial": "재무·회계 정보",
    "payroll_hr_personal": "급여·인사·직원 개인정보",
    "banking_credentials": "금융계좌·시스템 접근권한",
    "tax": "세무 신고 자료",
    "customer_vendor": "고객·거래처 정보",
    "pricing_cost": "가격·원가·거래조건",
    "business_plan": "사업계획·예산·전망",
    "technical": "기술자료·소스코드·설계",
    "trade_secret": "영업비밀",
    "affiliate": "계열사 정보",
}
_INFO_TYPE_PATTERNS: dict[str, re.Pattern[str]] = {
    "financial": _rx(r"financial\s+statements?|general\s+ledger|trial\s+balance|journal\s+entr|accounts?\s+(?:payable|receivable)|재무제표|회계"),
    "payroll_hr_personal": _rx(r"payroll|employee\s+compensation|benefits\s+information|personnel\s+(?:files?|records?)|employee\s+records?|급여|인사\s*(?:정보|기록)|임직원\s*개인정보"),
    "banking_credentials": _rx(r"bank(?:ing)?\s+(?:information|account)|wire\s+transfer|login\s+credentials|passwords?|access\s+rights|계좌|비밀번호|접근\s*권한"),
    "tax": _rx(r"tax\s+(?:returns?|records?|filings?)|taxing\s+authorit|세무\s*신고"),
    "customer_vendor": _rx(r"customer|client|vendor|supplier|고객|거래처|협력사"),
    "pricing_cost": _rx(r"pricing|price\s+list|cost\s+(?:data|information|structure)|billing\s+arrangements?|payment\s+terms|가격|원가|단가\s*정보"),
    "business_plan": _rx(r"budgets?|forecasts?|business\s+plans?|financial\s+models?|strategic\s+plans?|사업\s*계획|예산"),
    "technical": _rx(r"source\s+code|technical\s+(?:data|information)|designs?\s+(?:and|or)\s+specifications|engineering|know[- ]how|기술\s*자료|소스\s*코드|설계\s*도"),
    "trade_secret": _rx(r"trade\s+secrets?|영업\s*비밀"),
    "affiliate": _rx(r"affiliat|계열사|관계\s*회사|자회사|모회사"),
}

# ── 6. 개인정보 취급 구조 — 담당자 설명이 계약 추정보다 우선한다 ─────────
# "위탁이 아니라 내부 직원이…" 처럼 부정문 안에 '위탁' 이 들어 있으므로,
# 내부 접근 문형을 먼저 본다.
_RX_PD_INTERNAL_USER = _rx(
    r"위탁\s*(?:이|은|는)?\s*아니|위탁\s*(?:하지|하는\s*것이)\s*(?:않|아니)|외부\s*위탁\s*(?:없|아님|아니)"
    r"|(?:내부|사내|자사)\s*(?:직원|임직원|인력|담당자)"
    r"|직원이\s*(?:직접|내부적으로)?\s*[^.\n]{0,30}(?:수행|처리|취급|담당)"
    r"|in[- ]house|internal\s+(?:staff|employees?|personnel)|not\s+(?:a\s+)?(?:processor|outsourc)"
)
_RX_PD_PROCESSOR = _rx(
    r"(?:개인정보\s*)?처리\s*위탁|수탁\s*(?:자|사|업체)|외부\s*(?:업체|대행사|전문업체)(?:에|에게)\s*(?:위탁|맡기)"
    r"|\bprocessors?\b|service\s+providers?\s+(?:who|that)\s+process|outsourc"
)
_RX_PD_THIRD_PARTY = _rx(
    r"개인정보[^.\n]{0,20}제\s*3\s*자\s*(?:에게\s*)?제공|third[- ]party\s+disclosure\s+of\s+personal|sell\s+(?:or\s+share\s+)?personal"
)

# ── 7. 퇴직 후 제한 / 지식재산 / 반환 / 법정 공개 예외 ───────────────────
_RX_NONCOMPETE = _rx(r"non[- ]?compet|shall\s+not\s+(?:engage|compete)|경업\s*금지|경쟁\s*업체\s*(?:에|로)\s*(?:취업|전직)")
_RX_CUSTOMER_NONSOLICIT = _rx(r"(?:solicit|induce)[^.]{0,60}(?:customers?|clients?)|고객\s*(?:유인|권유)\s*금지")
_RX_EMPLOYEE_NONSOLICIT = _rx(r"(?:solicit|hire|recruit|induce)[^.]{0,60}employees?\s+(?:of|to\s+leave)|(?:직원|인력)\s*(?:유인|빼가기|스카우트)\s*금지")
_RX_RESTRAINT_DISCLAIMER = _rx(
    r"does\s+not\s+restrict[^.]{0,80}(?:employment|services)|16600|nothing\s+in\s+this\s+agreement[^.]{0,80}restrain"
)
_RX_IP_ASSIGNMENT = _rx(
    r"hereby\s+assigns?|assign(?:s|ment)?\s+(?:to\s+the\s+Company\s+)?(?:all\s+)?(?:right,?\s+title|inventions?)|work\s+(?:made\s+)?for\s+hire|inventions?\s+assignment"
    r"|직무\s*발명|발명[^.\n]{0,20}(?:승계|귀속)|업무\s*(?:상|성과물)[^.\n]{0,20}(?:귀속|양도)"
)
_RX_RETURN = _rx(r"return\s+(?:all|of\s+Company)|permanently\s+delete|destroy\s+all|반환|파기|삭제")
_CARVE_OUTS: dict[str, re.Pattern[str]] = {
    "required_by_law": _rx(r"required\s+by\s+law|court\s+order|subpoena|법령에\s*따라|법원의?\s*명령"),
    "government_reporting": _rx(r"government\s+agency|(?:SEC|EEOC|Department\s+of\s+Labor|Labor\s+Commissioner)|정부\s*기관|수사\s*기관"),
    "whistleblower": _rx(r"whistleblower|1102\.5|공익\s*신고|내부\s*고발"),
    "dtsa_notice": _rx(r"Defend\s+Trade\s+Secrets\s+Act|18\s*U\.?S\.?C\.?\s*§?\s*1833"),
    "wage_discussion": _rx(r"discuss[^.]{0,40}wages|Labor\s+Code\s+Sections?\s+232|임금[^.\n]{0,20}(?:논의|공개)"),
    "nlra_section7": _rx(r"Section\s+7\s+of\s+the\s+National\s+Labor\s+Relations\s+Act|\bNLRA\b"),
    "unlawful_acts_workplace": _rx(
        r"unlawful\s+acts?\s+in\s+the\s+workplace|harassment\s+or\s+discrimination|12964\.5"
    ),
}

_RX_POSITION = _rx(r"(?:in\s+the\s+)?position\s+of\s+([A-Z][A-Za-z/&\- ]{2,60}?)(?:[.,;\n]|\s+\()")
_RX_POSITION_TITLE = _rx(r"\(\s*([A-Z][A-Za-z/&\- ]{2,60}?)\s*\)\s*$")


@dataclass(frozen=True)
class EmployeeNdaModel:
    """임직원 비밀유지계약의 확정 거래모델. 만들어진 뒤에는 바뀌지 않는다."""

    is_employee_nda: bool = False
    confident: bool = False
    contract_type: str = ""
    subtype: str = ""
    label: str = ""
    employer_label: str = ""
    employee_label: str = ""
    our_company: str = ""
    our_side: str = ""
    counterparty_role: str = ""
    relationship: str = ""
    position: str = ""
    governing_law: str = ""
    jurisdiction_key: str = ""
    purpose: str = ""
    information_types: tuple[str, ...] = ()
    contract_mentions_affiliates: bool = False
    named_affiliates_in_contract: tuple[str, ...] = ()
    requested_affiliates: tuple[str, ...] = ()
    personal_data_structure: str = ""
    personal_data_basis: str = ""
    noncompete_present: bool = False
    customer_nonsolicit_present: bool = False
    employee_nonsolicit_present: bool = False
    restraint_disclaimer_present: bool = False
    ip_assignment_present: bool = False
    return_deletion_present: bool = False
    carve_outs: tuple[str, ...] = ()
    evidence: tuple[str, ...] = field(default_factory=tuple)
    reason: str = ""

    @property
    def is_california(self) -> bool:
        return self.jurisdiction_key == "us_california"

    @property
    def personal_data_internal(self) -> bool:
        return self.personal_data_structure == PD_EMPLOYEE_INTERNAL

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_employee_nda": self.is_employee_nda,
            "confident": self.confident,
            "contract_type": self.contract_type,
            "subtype": self.subtype,
            "label": self.label,
            "employer_label": self.employer_label,
            "employee_label": self.employee_label,
            "our_company": self.our_company,
            "our_side": self.our_side,
            "counterparty_role": self.counterparty_role,
            "relationship": self.relationship,
            "position": self.position,
            "governing_law": self.governing_law,
            "jurisdiction_key": self.jurisdiction_key,
            "purpose": self.purpose,
            "information_types": list(self.information_types),
            "information_type_labels": [INFO_TYPE_LABELS.get(t, t) for t in self.information_types],
            "contract_mentions_affiliates": self.contract_mentions_affiliates,
            "named_affiliates_in_contract": list(self.named_affiliates_in_contract),
            "requested_affiliates": list(self.requested_affiliates),
            "personal_data_structure": self.personal_data_structure,
            "personal_data_structure_label": PD_LABELS.get(self.personal_data_structure, ""),
            "personal_data_basis": self.personal_data_basis,
            "noncompete_present": self.noncompete_present,
            "customer_nonsolicit_present": self.customer_nonsolicit_present,
            "employee_nonsolicit_present": self.employee_nonsolicit_present,
            "restraint_disclaimer_present": self.restraint_disclaimer_present,
            "ip_assignment_present": self.ip_assignment_present,
            "return_deletion_present": self.return_deletion_present,
            "carve_outs": list(self.carve_outs),
            "evidence": list(self.evidence),
            "reason": self.reason,
        }


def _employer_label(text: str) -> str:
    """당사자 정의 문언에서 사용자(회사) 명칭을 읽는다.

    "by and between Fursys America, Inc., a [STATE] corporation … (the “Company”)"
    → "Fursys America, Inc." — 법인 형태 표기(Inc./LLC/Ltd.)까지는 이름에 포함하고
    그 뒤의 설립지·주소 설명은 버린다.
    """
    m = re.search(
        r"between\s+(.{2,160}?)\s*\(\s*(?:the\s+)?[\"“”']?\s*(?:Company|Employer)\s*[\"“”']?\s*\)",
        text, re.IGNORECASE | re.DOTALL,
    )
    if not m:
        # 국문: "주식회사 일룸(이하 "회사"라 한다)" — 괄호 정의 바로 앞의 법인명.
        mk = re.search(
            r"((?:주식회사\s*)?[가-힣A-Za-z0-9&]{2,30}(?:\s*주식회사)?)\s*\(\s*이하\s*[\"“”'‘’「]?\s*(?:회사|사용자|고용주)",
            text,
        )
        return mk.group(1).strip() if mk else ""
    raw = re.sub(r"\s+", " ", m.group(1)).strip()
    corp = re.match(
        r"(.+?(?:,?\s*(?:Inc|LLC|L\.L\.C|Ltd|Co|Corp|Corporation|Limited|GmbH|주식회사)\.?))(?=[\s,]|$)",
        raw,
    )
    name = corp.group(1) if corp else raw.split(",")[0]
    return name.strip(" ,")


def _governing_law(text: str) -> tuple[str, str]:
    m = _RX_GOVERNING_EN.search(text)
    if m:
        place = re.sub(r"\s+", " ", m.group(1)).strip()
        if place in _US_STATES:
            return f"{place}, USA", "us_" + place.lower().replace(" ", "_")
        low = place.lower()
        if "korea" in low:
            return "대한민국", "kr"
        return place, low.replace(" ", "_")
    if _RX_GOVERNING_KO.search(text):
        return "대한민국", "kr"
    return "", ""


def _position(text: str) -> str:
    m = _RX_POSITION.search(text)
    if m:
        return m.group(1).strip()
    head = text[:400]
    for line in head.splitlines():
        mt = _RX_POSITION_TITLE.search(line.strip())
        if mt and "agreement" not in mt.group(1).lower():
            return mt.group(1).strip()
    return ""


def _group_names(text: str) -> list[str]:
    try:
        from runtime.review.group_entities import find_group_entities
    except Exception:  # noqa: BLE001
        return []
    return [e.name for e in find_group_entities(text)]


def _resolve_group_name(name: str) -> str:
    try:
        from runtime.review.group_entities import resolve_entity
    except Exception:  # noqa: BLE001
        return ""
    ent = resolve_entity(name)
    return ent.name if ent is not None else ""


def _requested_affiliates(user_text: str, employer_group_name: str) -> tuple[str, ...]:
    """글(담당자 설명 또는 계약 원문)에 **명시된** 계열사 — 우리 회사 자신은 뺀다.

    긴 이름 우선 매칭이라 "시디즈 아메리카" 가 잡히면 "시디즈" 는 따로 세지
    않는다(같은 문자열 안의 짧은 이름을 다른 법인으로 오인하지 않기 위함).
    """
    out: list[str] = []
    try:
        from runtime.review.group_entities import GROUP_ENTITIES, _norm
    except Exception:  # noqa: BLE001
        return ()
    body = _norm(user_text)
    if not body:
        return ()
    spans: list[tuple[int, int, str]] = []
    for ent in GROUP_ENTITIES:
        for nm in ent.all_names():
            key = _norm(nm)
            if not key or len(key) < 2:
                continue
            start = body.find(key)
            while start >= 0:
                spans.append((start, start + len(key), ent.name))
                start = body.find(key, start + 1)
    # 긴 매칭이 짧은 매칭을 덮는다.
    spans.sort(key=lambda s: (-(s[1] - s[0]), s[0]))
    taken: list[tuple[int, int]] = []
    for a, b, name in spans:
        if any(not (b <= x or a >= y) for x, y in taken):
            continue
        taken.append((a, b))
        if name != employer_group_name and name not in out:
            out.append(name)
    return tuple(out)


def resolve_personal_data_structure(
    *, contract_text: str, user_text: str, is_employee_nda: bool, information_types: tuple[str, ...],
) -> tuple[str, str]:
    """개인정보 취급 구조를 A(내부 접근)/B(처리위탁)/C(제3자 제공) 중 하나로 정한다.

    담당자의 명시적 설명이 가장 강하다. 설명이 없으면 계약 구조로 추정한다 —
    직원 비밀유지 서약에서 직원은 사용자 조직의 일부이므로, 직원이 급여·인사
    정보를 다루는 것은 처리위탁이 아니라 **내부 접근**이다.
    """
    user = str(user_text or "")
    if user.strip():
        if _RX_PD_INTERNAL_USER.search(user):
            return PD_EMPLOYEE_INTERNAL, "user_answer"
        if _RX_PD_THIRD_PARTY.search(user):
            return PD_THIRD_PARTY, "user_answer"
        if _RX_PD_PROCESSOR.search(user):
            return PD_PROCESSOR, "user_answer"
    body = str(contract_text or "")
    if is_employee_nda:
        if _RX_PD_THIRD_PARTY.search(body):
            return PD_THIRD_PARTY, "contract"
        if "payroll_hr_personal" in information_types or "customer_vendor" in information_types:
            return PD_EMPLOYEE_INTERNAL, "contract"
    return "", ""


def resolve_employee_nda_model(
    *,
    contract_text: str,
    user_description: str = "",
    entity: str = "",
    contract_type_code: str = "",
) -> EmployeeNdaModel:
    """계약이 임직원 비밀유지계약인지 판정하고 거래모델을 확정한다.

    `contract_type_code` 가 넘어왔고 비밀유지 계열이 아니면 판정하지 않는다 —
    확정된 canonical 유형을 이 모듈이 뒤집지 않는다. 코드가 비어 있으면(업로드
    직후 등) 원문의 비밀유지 문언을 직접 확인한다.
    """
    text = str(contract_text or "")
    user = str(user_description or "")
    code = str(contract_type_code or "").strip()
    if not text.strip():
        return EmployeeNdaModel(reason="원문 없음")
    if code and code not in NDA_TYPE_CODES:
        return EmployeeNdaModel(reason=f"canonical 유형이 비밀유지 계열이 아님({code})")
    if not code and not re.search(r"confidential|non[- ]?disclosure|비밀\s*유지|기밀\s*유지|영업\s*비밀", text, re.IGNORECASE):
        return EmployeeNdaModel(reason="비밀유지 문언 없음")

    evidence: list[str] = []
    employee_party = bool(_RX_EMPLOYEE_PARTY_EN.search(text) or _RX_EMPLOYEE_PARTY_KO.search(text))
    employer_party = bool(_RX_EMPLOYER_PARTY_EN.search(text) or _RX_EMPLOYER_PARTY_KO.search(text))
    if employee_party:
        evidence.append("employee_defined_as_party")
    if employer_party:
        evidence.append("employer_defined_as_party")
    employment_hits = [name for name, rx in _EMPLOYMENT_SIGNALS if rx.search(text)]
    evidence.extend(f"employment:{h}" for h in employment_hits)
    user_says_employee = bool(re.search(
        r"신규\s*입사|입사자|임직원|직원\s*(?:용|대상)?\s*(?:NDA|비밀유지|서약)|employee\s+(?:nda|confidentiality)",
        user, re.IGNORECASE,
    ))
    if user_says_employee:
        evidence.append("user_description:employee")
    commercial = bool(_RX_COMMERCIAL_CONSIDERATION.search(text))
    if commercial:
        evidence.append("commercial_consideration_present")

    is_employee = employee_party and (len(employment_hits) >= 1 or user_says_employee)
    if not is_employee:
        return EmployeeNdaModel(evidence=tuple(evidence), reason="직원이 당사자로 정의되지 않았거나 고용관계 신호 없음")
    confident = (
        employee_party and employer_party
        and (len(employment_hits) >= 2 or (employment_hits and user_says_employee))
        and not commercial
    )

    employer = _employer_label(text)
    our_company = _resolve_group_name(employer) or _resolve_group_name(entity)
    if not our_company:
        names = _group_names(employer or text[:600])
        our_company = names[0] if names else ""
    governing_law, jur_key = _governing_law(text)
    info_types = tuple(t for t, rx in _INFO_TYPE_PATTERNS.items() if rx.search(text))
    contract_affiliates = "affiliate" in info_types
    named_in_contract = _requested_affiliates(text, our_company)
    requested = _requested_affiliates(user, our_company)
    pd_structure, pd_basis = resolve_personal_data_structure(
        contract_text=text, user_text=user, is_employee_nda=True, information_types=info_types,
    )
    carve = tuple(k for k, rx in _CARVE_OUTS.items() if rx.search(text))

    return EmployeeNdaModel(
        is_employee_nda=True,
        confident=confident,
        contract_type="nda_confidentiality",
        subtype=SUBTYPE_EMPLOYEE_NDA,
        label=EMPLOYEE_NDA_LABEL,
        employer_label=employer or "Company",
        employee_label="Employee" if _RX_EMPLOYEE_PARTY_EN.search(text) else "직원",
        our_company=our_company,
        our_side="employer",
        counterparty_role="employee",
        relationship="employer_employee",
        position=_position(text),
        governing_law=governing_law,
        jurisdiction_key=jur_key,
        purpose="직원이 업무 중 접하는 회사(및 계열사)의 기밀정보와 개인정보를 보호",
        information_types=info_types,
        contract_mentions_affiliates=contract_affiliates,
        named_affiliates_in_contract=named_in_contract,
        requested_affiliates=requested,
        personal_data_structure=pd_structure,
        personal_data_basis=pd_basis,
        noncompete_present=bool(_RX_NONCOMPETE.search(text)),
        customer_nonsolicit_present=bool(_RX_CUSTOMER_NONSOLICIT.search(text)),
        employee_nonsolicit_present=bool(_RX_EMPLOYEE_NONSOLICIT.search(text)),
        restraint_disclaimer_present=bool(_RX_RESTRAINT_DISCLAIMER.search(text)),
        ip_assignment_present=bool(_RX_IP_ASSIGNMENT.search(text)),
        return_deletion_present=bool(_RX_RETURN.search(text)),
        carve_outs=carve,
        evidence=tuple(evidence),
        reason=(
            "직원이 당사자로 정의되고 고용관계를 대가로 한 비밀유지 서약"
            + ("" if confident else " — 사업자 간 대가 문언이 있거나 신호가 부족해 확신하지 않음")
        ),
    )
