"""계약유형을 제목이 아니라 **법률효과**로 판정한다 (2026-09-09 지시 항목 2).

증상: 호텔 신축 공사도급계약이 `앱개발/소프트웨어개발/SI/유지보수/SaaS`로
분류됐다. 그 결과 계약유형별 체크리스트가 잘못 주입되고, 정부지원금·개인정보
같은 무관한 룰이 따라 들어왔다.

판정 기준은 제목이 아니라 **이 계약이 만들어내는 법률효과**다:

    일을 완성하고 대가를 받는다            → construction_contract
    물품을 공급하고 설치까지 한다          → supply_installation
    개발 성과물을 창출해 인도한다          → development_service
    비밀정보를 보호할 의무만 진다          → nda_confidentiality
    물건을 빌려주고 사용료를 받는다        → rental_lease
    제3자에게 판매·중개한다                → sales_agency
    권리를 사용하게 해주고 로열티를 받는다 → license

확신도가 낮거나 상위 두 유형이 팽팽하면 `REVIEW_FAILED_CONTRACT_TYPE_UNCERTAIN`
으로 처리하고 **어떤 유형별 체크리스트도 주입하지 않는다** — 틀린 유형의
체크리스트를 넣는 것이 유형을 모른다고 말하는 것보다 나쁘다.

하드코딩 금지: 회사명·계약서명·조항번호를 신호로 쓰지 않는다. 전부 거래
구조를 나타내는 일반 법률 어휘다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

REVIEW_FAILED_CONTRACT_TYPE_UNCERTAIN = "REVIEW_FAILED_CONTRACT_TYPE_UNCERTAIN"

#: 확신도 임계값. 아래면 유형을 단정하지 않는다.
MIN_CONFIDENCE = 0.55
#: 상위 두 유형의 점수 차가 이 비율 미만이면 "충돌"로 본다.
MIN_MARGIN = 0.18
#: 다른 유형이 이 점수 이상이면 NDA 는 부수 의무로 강등된다(잔여 유형 규칙).
#: 급부·대가 교환을 증명하는 신호가 최소 두 개는 모여야 하는 수준으로 잡는다.
_NDA_RESIDUAL_THRESHOLD = 5


@dataclass(frozen=True)
class TypeSignal:
    pattern: re.Pattern[str]
    weight: int
    #: 이 신호가 무엇을 증명하는지 — 리포트에 그대로 보여준다.
    rationale: str


def _s(regex: str, weight: int, rationale: str) -> TypeSignal:
    return TypeSignal(re.compile(regex, re.IGNORECASE), weight, rationale)


#: 계약유형 → 법률효과 신호. weight 는 "그 신호가 그 유형만의 것인가"에 비례.
#: 예: "준공검사"는 공사도급의 고유 신호(4점), "검수"는 여러 유형 공통(1점).
_TYPE_SIGNALS: dict[str, tuple[TypeSignal, ...]] = {
    "construction_contract": (
        _s(r"도\s*급\s*(?:인|계약|금액)", 4, "도급 구조(일의 완성 + 대가)"),
        _s(r"준\s*공\s*(?:검사|예정일|일|계|필)", 4, "준공 개념 = 일의 완성"),
        _s(r"착\s*공", 3, "착공 시점 개념"),
        _s(r"기\s*성\s*(?:금|고|율|부분)", 4, "기성 기준 대가 지급"),
        _s(r"수\s*급\s*인", 4, "수급인 지위"),
        _s(r"시\s*공|공\s*사\s*현\s*장|감\s*리", 3, "시공·현장·감리"),
        _s(r"설계도서|시방서|공정표", 3, "설계도서 기반 이행"),
        _s(r"하자\s*(?:보수|담보)\s*(?:보증금|책임)", 2, "하자담보책임 구조"),
        _s(r"사용\s*승인|준공\s*인가", 3, "인허가 연동 완성"),
        _s(r"산업안전보건법|중대재해|안전관리자", 2, "건설 안전법령 적용"),
        # 영문 공사계약 — "범용"이려면 언어에 종속되면 안 된다.
        _s(r"\bthe\s+works\b|\bcontract\s+works\b", 4, "the Works = 공사 목적물"),
        _s(r"\bpractical\s+completion\b|\btaking[- ]over\b", 4, "완성·인수 개념"),
        _s(r"\bdefects?\s+liability\b|\bmaking\s+good\b", 3, "하자책임기간"),
        _s(r"\bprogress\s+payment|\binterim\s+certificate\b", 3, "기성 지급"),
        _s(r"\bcontractor\b.{0,40}\bemployer\b|\bemployer\b.{0,40}\bcontractor\b", 3,
           "Contractor/Employer 지위"),
    ),
    "supply_installation": (
        _s(r"납\s*품", 3, "물품 인도 의무"),
        _s(r"설\s*치\s*(?:공사|작업|완료)", 3, "설치 급부 결합"),
        _s(r"시\s*운\s*전|시험\s*가동", 3, "시운전 = 설치 완료 판정"),
        _s(r"물\s*품|기\s*자\s*재|장\s*비", 2, "물품 목적물"),
        _s(r"검\s*수\s*(?:조서|완료|기준)", 2, "검수 기준"),
        _s(r"소유권\s*(?:이전|유보)|위험\s*이전", 3, "소유권·위험 이전 시점"),
        _s(r"\bcommissioning\b|\bsite\s+acceptance\s+test", 3, "시운전·현장검수"),
        _s(r"\btitle\s+(?:and\s+risk\s+)?(?:shall\s+)?pass(?:es)?\b", 3, "소유권·위험 이전"),
        _s(r"\bdelivery\s+(?:and\s+)?installation\b|\bsupply\s+and\s+install", 3,
           "공급 + 설치 결합"),
    ),
    "development_service": (
        _s(r"개\s*발\s*(?:용역|계약|업무|범위)", 3, "개발 급부"),
        _s(r"산\s*출\s*물|deliverable", 3, "산출물 인도"),
        _s(r"소\s*스\s*코\s*드|source\s*code", 4, "소스코드 귀속 쟁점"),
        _s(r"마\s*일\s*스\s*톤|milestone", 2, "마일스톤 기준"),
        _s(r"유\s*지\s*보\s*수|하\s*자\s*보\s*수\s*기\s*간.{0,10}개발", 2, "개발 후 유지보수"),
        _s(r"요\s*구\s*사\s*항\s*정\s*의|기능\s*명세", 2, "요구사항 기반 이행"),
        _s(r"SaaS|클라우드\s*서비스|API\s*연동", 2, "소프트웨어 서비스"),
        _s(r"\bstatement\s+of\s+work\b|\bSOW\b", 3, "SOW 기반 개발"),
        _s(r"\bacceptance\s+test", 2, "인수 시험"),
    ),
    "nda_confidentiality": (
        _s(r"비\s*밀\s*유\s*지", 4, "비밀유지 의무가 주된 급부"),
        _s(r"비\s*밀\s*정\s*보", 4, "비밀정보 정의"),
        _s(r"목적\s*외\s*(?:사용|이용)\s*금지", 3, "목적 외 사용 금지"),
        _s(r"반\s*환\s*(?:또는|·|/)?\s*폐\s*기", 3, "반환·폐기 의무"),
        _s(r"정보\s*제공자|정보\s*수령자|disclosing|receiving\s*party", 3, "제공자/수령자 지위"),
        _s(r"\bnon[- ]disclosure\b|\bconfidentiality\s+agreement\b", 4,
           "비밀유지가 계약의 표제 급부"),
    ),
    "rental_lease": (
        _s(r"임\s*대\s*(?:인|차|료)", 4, "임대차 구조"),
        _s(r"렌\s*탈\s*(?:료|기간|업자)", 4, "렌탈 구조"),
        _s(r"사\s*용\s*료|월\s*임\s*대\s*료", 2, "사용료 대가"),
        _s(r"반\s*납|회\s*수\s*(?:조건|시점)", 2, "목적물 반납"),
        _s(r"\bless(?:or|ee)\b|\blease\s+(?:term|agreement)\b", 4, "Lessor/Lessee 구조"),
        _s(r"\brent\b|\brental\s+(?:fee|payment)\b", 2, "임대료"),
    ),
    "sales_agency": (
        _s(r"대\s*리\s*점|위\s*탁\s*판\s*매", 4, "판매 대리·위탁 구조"),
        _s(r"판\s*매\s*수\s*수\s*료|용역수수료", 3, "판매 수수료 대가"),
        _s(r"최\s*종\s*소\s*비\s*자|고객과의\s*매매", 2, "최종소비자 판매"),
        _s(r"재\s*판\s*매|유\s*통\s*권", 2, "재판매·유통권"),
        _s(r"\bdistributor\b|\breseller\b|\bsales\s+agent\b", 4, "판매·유통 지위"),
        _s(r"\bcommission\b.{0,30}\bsales?\b|\bsales?\b.{0,30}\bcommission\b", 3,
           "판매 수수료"),
    ),
    "license": (
        _s(r"라\s*이\s*선\s*스|실\s*시\s*권", 4, "실시권 부여"),
        _s(r"로\s*열\s*티|royalty", 4, "로열티 대가"),
        _s(r"사\s*용\s*허\s*락|통상실시권|전용실시권", 3, "사용허락 구조"),
        # 영문 라이선스 계약(실측: FURSYS/Teknion LICENSE AGREEMENT)은 한국어
        # 신호가 0점이어서 "정보 제공자/수령자" 3점만으로 NDA 로 오분류됐다.
        _s(r"\blicen[cs]e\s+agreement\b|\blicen[cs]ed?\s+(?:products?|rights?|technology)\b",
           4, "라이선스 계약 구조"),
        _s(r"\blicensor\b|\blicensee\b", 4, "Licensor/Licensee 지위"),
        _s(r"\bsub[- ]?licen[cs]e\b|\broyalt(?:y|ies)\b", 3, "재실시권·로열티"),
        _s(r"\bexclusive\s+licen[cs]e\b|\bterritory\b", 2, "실시 범위·지역"),
    ),
}

#: 표기용 한국어 라벨.
TYPE_LABELS: dict[str, str] = {
    "construction_contract": "공사도급계약",
    "supply_installation": "물품공급·설치계약",
    "development_service": "개발용역계약",
    "nda_confidentiality": "비밀유지계약(NDA)",
    "rental_lease": "렌탈·임대차계약",
    "sales_agency": "판매대리·위탁판매계약",
    "license": "라이선스계약",
}


@dataclass
class TypeResolution:
    contract_type_code: str
    confidence: float
    #: 상위 후보 [(code, score, matched_rationales)]
    ranked: list[tuple[str, int, list[str]]] = field(default_factory=list)
    uncertain: bool = False
    reason: str = ""

    @property
    def label(self) -> str:
        return TYPE_LABELS.get(self.contract_type_code, self.contract_type_code or "미확정")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_type_code": self.contract_type_code,
            "contract_type_label": self.label,
            "confidence": round(self.confidence, 3),
            "uncertain": self.uncertain,
            "reason": self.reason,
            "ranked": [
                {"code": c, "label": TYPE_LABELS.get(c, c), "score": s, "signals": r[:6]}
                for c, s, r in self.ranked[:4]
            ],
            "review_status": REVIEW_FAILED_CONTRACT_TYPE_UNCERTAIN if self.uncertain else "",
        }


def score_types(text: str) -> list[tuple[str, int, list[str]]]:
    """유형별 법률효과 점수. 제목이 아니라 본문 전체를 본다."""
    hay = text or ""
    out: list[tuple[str, int, list[str]]] = []
    for code, signals in _TYPE_SIGNALS.items():
        score = 0
        hits: list[str] = []
        for sig in signals:
            if sig.pattern.search(hay):
                score += sig.weight
                hits.append(sig.rationale)
        out.append((code, score, hits))
    out.sort(key=lambda x: -x[1])
    return out


def resolve_contract_type(text: str, *, declared_type: str = "") -> TypeResolution:
    """법률효과 기반으로 계약유형을 확정하거나 '불확실'로 표시한다.

    `declared_type`(파일명·사용자 입력에서 온 유형)은 **동점을 깨는 데만**
    쓴다. 선언된 유형이 본문의 법률효과와 어긋나면 본문이 이긴다 — 제목보다
    실제 급부 구조가 계약의 성격을 정한다.
    """
    ranked = score_types(text)
    if not ranked or ranked[0][1] <= 0:
        return TypeResolution(
            contract_type_code="", confidence=0.0, ranked=ranked, uncertain=True,
            reason="본문에서 계약유형을 식별할 법률효과 신호를 찾지 못했습니다.",
        )

    # ── NDA 는 잔여(residual) 유형이다 ────────────────────────────────────
    # 거의 모든 상용계약에 비밀유지 **조항**이 있으므로, NDA 신호만 보면
    # 물품공급·공사·개발 계약이 전부 NDA 로 판정된다(실측: 장비 구매·설치
    # 계약이 NDA 8점 대 공급 5점으로 NDA 로 분류됨). 급부와 대가의 교환이
    # 따로 존재하면 그 계약의 성격은 그쪽이고, 비밀유지는 부수 의무다.
    _nda = next((s for c, s, _ in ranked if c == "nda_confidentiality"), 0)
    _best_other = max((s for c, s, _ in ranked if c != "nda_confidentiality"), default=0)
    if _nda > 0 and _best_other >= _NDA_RESIDUAL_THRESHOLD:
        ranked = [
            (c, (0 if c == "nda_confidentiality" else s), h + (
                ["다른 급부·대가 구조가 존재하므로 비밀유지는 부수 의무로 판단"]
                if c == "nda_confidentiality" else []
            ))
            for c, s, h in ranked
        ]
        ranked.sort(key=lambda x: -x[1])

    top_code, top_score, top_hits = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    # 확신도는 **상위 두 후보의 상대 우위**로 잰다. 전체 합으로 나누면 후보
    # 수가 많을수록 희석되어, 명백한 렌탈계약(8 대 5)이 42% 로 떨어진다.
    confidence = top_score / (top_score + second_score) if (top_score + second_score) else 0.0
    margin = (top_score - second_score) / top_score if top_score else 0.0

    declared = str(declared_type or "").strip().lower()
    declared_code = ""
    for code in _TYPE_SIGNALS:
        if code in declared:
            declared_code = code
            break

    if margin < MIN_MARGIN:
        # 팽팽하면 선언된 유형이 상위 후보 중 하나일 때만 그것으로 정한다.
        tied = [c for c, s, _ in ranked if top_score and (top_score - s) / top_score < MIN_MARGIN]
        if declared_code and declared_code in tied:
            return TypeResolution(
                contract_type_code=declared_code,
                confidence=confidence, ranked=ranked, uncertain=False,
                reason=(
                    f"상위 후보가 팽팽해({', '.join(TYPE_LABELS.get(c, c) for c in tied)}) "
                    f"선언된 유형({TYPE_LABELS.get(declared_code, declared_code)})으로 확정했습니다."
                ),
            )
        return TypeResolution(
            contract_type_code="", confidence=confidence, ranked=ranked, uncertain=True,
            reason=(
                "상위 계약유형 후보가 서로 충돌합니다: "
                + ", ".join(f"{TYPE_LABELS.get(c, c)}({s})" for c, s, _ in ranked[:3])
                + ". 유형별 체크리스트를 주입하지 않았습니다."
            ),
        )

    if confidence < MIN_CONFIDENCE:
        return TypeResolution(
            contract_type_code="", confidence=confidence, ranked=ranked, uncertain=True,
            reason=(
                f"최상위 후보 {TYPE_LABELS.get(top_code, top_code)}의 확신도가 "
                f"{confidence:.0%}로 기준({MIN_CONFIDENCE:.0%}) 미만입니다. "
                "유형별 체크리스트를 주입하지 않았습니다."
            ),
        )

    return TypeResolution(
        contract_type_code=top_code, confidence=confidence, ranked=ranked, uncertain=False,
        reason="법률효과 신호: " + "; ".join(top_hits[:5]),
    )


#: 선언 유형 문자열(파일명·드롭다운·세션값)이 가리키는 유형을 알아내기 위한
#: 한국어/영어 키워드. 선언값은 코드가 아니라 사람이 쓴 라벨로 들어온다 —
#: 실측: "앱개발/소프트웨어개발/SI/유지보수/SaaS" (development_service 를 의미).
_DECLARED_TYPE_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("construction_contract", ("공사", "도급", "건축", "시공", "construction", "works")),
    ("supply_installation", ("물품", "구매", "공급", "설치", "납품", "supply", "purchase", "install")),
    ("development_service", ("앱개발", "개발", "소프트웨어", "si", "saas", "유지보수",
                             "용역", "development", "service")),
    ("nda_confidentiality", ("비밀유지", "nda", "confidential")),
    ("rental_lease", ("렌탈", "임대", "리스", "rental", "lease")),
    ("sales_agency", ("대리점", "위탁판매", "판매지원", "유통", "dealer", "distribut", "agency")),
    ("license", ("라이선스", "실시권", "licen")),
)


def declared_type_code(declared_type: str) -> str:
    """선언 유형 문자열이 가리키는 유형 코드. 알 수 없으면 빈 문자열."""
    low = str(declared_type or "").strip().lower()
    if not low:
        return ""
    for code in _TYPE_SIGNALS:
        if code in low:
            return code
    for code, hints in _DECLARED_TYPE_HINTS:
        if any(h in low for h in hints):
            return code
    return ""


def declared_type_conflicts(resolution: TypeResolution, declared_type: str) -> str:
    """선언된 유형이 본문 판정과 어긋나면 그 사실을 설명한다(항목 2·13).

    조용히 덮어쓰지 않고 리포트에 남긴다 — 사용자가 파일명이나 드롭다운으로
    잘못 지정했을 때, 그 불일치 자체가 확인이 필요한 정보다. 실측 사례에서는
    공사도급계약이 "앱개발/소프트웨어개발/SI/유지보수/SaaS"로 선언되어 있었고,
    그 때문에 계약유형별 체크리스트가 통째로 잘못 주입됐다.
    """
    declared = str(declared_type or "").strip()
    if not declared or resolution.uncertain or not resolution.contract_type_code:
        return ""
    code = declared_type_code(declared)
    if not code or code == resolution.contract_type_code:
        return ""
    return (
        f"선언된 계약유형('{declared}' → {TYPE_LABELS.get(code, code)})과 "
        f"본문 법률효과 판정('{resolution.label}')이 다릅니다. "
        f"본문 구조를 기준으로 검토했으며, 선언 유형의 체크리스트는 주입하지 않았습니다."
    )
