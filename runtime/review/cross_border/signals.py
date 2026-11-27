"""국제계약 여부 판정 — 국내/국제 판정의 단일 진실 원천.

신호군을 점수화한다. **신호군 하나만으로는 국제계약으로 보지 않는다**(예: 국내 계약이 분쟁해결 조항에서
"싱가포르국제중재센터"를 언급한 것만으로는 국제계약이 아니다). 판정은 서로 다른 신호군이 두 개 이상이고
점수가 임계치 이상일 때만 True.

신호군
- entity_form      외국 법인 형태 표지(s.r.l., GmbH, Inc., LLC, Pte. Ltd. …). "Ltd"·"Co., Ltd." 는 한국 주소
                   법인에도 쓰이므로 같은 당사자 블록에 외국 주소가 있을 때만 센다.
- foreign_address  주소 문맥(주소·Address·registered office·located at)과 함께 나온 외국 국가명
- foreign_tax_id   VAT·Cod. Fisc.·EIN·USCC 등 외국 세무번호
- bank             IBAN·SWIFT/BIC
- currency         외화(EUR·USD·JPY·CNY …), T/T·L/C 와 함께면 가중
- trade_terms      Incoterms·개별 조건, B/L, Commercial Invoice, Packing List, Proforma Invoice, 원산지증명·신고, FTA
- intl_norms       CISG, SIAC·ICC·HKIAC·KCAB 국제중재규칙·CIETAC·LCIA, 뉴욕협약
- bilingual        국·영 병기 + 언어 우선 조항
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from runtime.review.cross_border.evidence import quote_around

#: 국가명(영문·국문) → 정규 이름.
COUNTRIES: dict[str, str] = {
    "Italy": "Italy", "Italia": "Italy", "이탈리아": "Italy",
    "Germany": "Germany", "Deutschland": "Germany", "독일": "Germany",
    "France": "France", "프랑스": "France", "Spain": "Spain", "스페인": "Spain",
    "Austria": "Austria", "오스트리아": "Austria", "Switzerland": "Switzerland", "스위스": "Switzerland",
    "Netherlands": "Netherlands", "네덜란드": "Netherlands", "Belgium": "Belgium", "벨기에": "Belgium",
    "Denmark": "Denmark", "덴마크": "Denmark", "Sweden": "Sweden", "스웨덴": "Sweden",
    "Norway": "Norway", "노르웨이": "Norway", "Finland": "Finland", "핀란드": "Finland",
    "Poland": "Poland", "폴란드": "Poland", "Portugal": "Portugal", "포르투갈": "Portugal",
    "United Kingdom": "United Kingdom", "England": "United Kingdom", "영국": "United Kingdom",
    "Ireland": "Ireland", "아일랜드": "Ireland",
    "United States": "United States", "U.S.A.": "United States", "USA": "United States", "미국": "United States",
    "Canada": "Canada", "캐나다": "Canada", "Mexico": "Mexico", "멕시코": "Mexico", "Brazil": "Brazil", "브라질": "Brazil",
    "China": "China", "P.R.C.": "China", "PRC": "China", "중국": "China", "中国": "China",
    "Hong Kong": "Hong Kong", "홍콩": "Hong Kong", "Taiwan": "Taiwan", "대만": "Taiwan",
    "Japan": "Japan", "일본": "Japan", "日本": "Japan",
    "Singapore": "Singapore", "싱가포르": "Singapore", "Vietnam": "Vietnam", "Viet Nam": "Vietnam", "베트남": "Vietnam",
    "Thailand": "Thailand", "태국": "Thailand", "Malaysia": "Malaysia", "말레이시아": "Malaysia",
    "Indonesia": "Indonesia", "인도네시아": "Indonesia", "Philippines": "Philippines", "필리핀": "Philippines",
    "India": "India", "인도": "India", "Australia": "Australia", "호주": "Australia",
    "New Zealand": "New Zealand", "뉴질랜드": "New Zealand", "United Arab Emirates": "UAE", "UAE": "UAE",
    "Turkey": "Turkey", "Türkiye": "Turkey", "튀르키예": "Turkey", "Russia": "Russia", "러시아": "Russia",
    "Israel": "Israel", "이스라엘": "Israel",
}
KOREA_NAMES = ("Korea", "Republic of Korea", "대한민국", "한국", "Seoul", "서울")

#: 국제물품매매계약에 관한 유엔협약(CISG) 체약국(주요국). 여기에 없는 나라는 "확인 필요"로 둔다.
CISG_STATES = frozenset({
    "Korea", "Italy", "Germany", "France", "Spain", "Austria", "Switzerland", "Netherlands", "Belgium", "Denmark",
    "Sweden", "Norway", "Finland", "Poland", "Portugal", "United States", "Canada", "Mexico", "Brazil", "China",
    "Japan", "Singapore", "Vietnam", "Australia", "New Zealand", "Turkey", "Russia", "Israel",
})
#: 비체약국으로 알려진 주요국.
CISG_NON_STATES = frozenset({"United Kingdom", "Ireland", "India", "Thailand", "Malaysia", "Indonesia", "Philippines",
                             "UAE", "Taiwan"})

#: 주(州)·성(省) — 주소에 국가명 없이 쓰이는 경우가 많다("Downsview, Ontario").
REGIONS: dict[str, str] = {
    "Ontario": "Canada", "Quebec": "Canada", "British Columbia": "Canada", "Alberta": "Canada",
    "California": "United States", "Delaware": "United States", "New York": "United States", "Texas": "United States",
    "Illinois": "United States", "Michigan": "United States", "Massachusetts": "United States",
    "New Jersey": "United States", "Florida": "United States",
    "Guangdong": "China", "Zhejiang": "China", "Jiangsu": "China", "Shanghai": "China", "Shenzhen": "China",
    "Bavaria": "Germany", "Lombardy": "Italy", "Lombardia": "Italy", "Tokyo": "Japan", "Osaka": "Japan",
}
_ALL_PLACES = {**COUNTRIES, **REGIONS}
_RX_COUNTRY = re.compile(
    "|".join(sorted((re.escape(k) for k in _ALL_PLACES), key=len, reverse=True))
)
_RX_LAWS_OF = re.compile(
    r"(?:laws?\s+of|incorporated\s+in|organi[sz]ed\s+(?:and\s+existing\s+)?under\s+the\s+laws\s+of)\s+(?:the\s+)?"
    r"(?:State\s+of\s+|Province\s+of\s+|Republic\s+of\s+)?$", re.I)
_RX_ADDRESS_CTX = re.compile(r"주\s*소|소재지|Address|registered\s+office|principal\s+(?:office|place)|located\s+at|having\s+its", re.I)

_RX_FOREIGN_FORM = re.compile(
    r"\bs\.\s?r\.\s?l\.|\bS\.\s?p\.\s?A\.|\bGmbH\b|\bAG\b(?=[\s,.)]|$)|\bB\.V\.|\bN\.V\.|\bS\.A\.(?:S\.)?|\bSAS\b|\bS\.L\.|\bS\.A\.R\.L\."
    r"|\bInc\.|\bLLC\b|\bL\.L\.C\.|\bCorp\.|\bCorporation\b|\bPte\.?\s*Ltd\b|\bPty\.?\s*Ltd\b|\bK\.K\.|\bKabushiki\s+Kaisha\b"
    r"|株式会社|有限公司|\bOy\b|\bAB\b(?=[\s,.)]|$)|\bA/S\b|\bApS\b|\bSpA\b|\bSrl\b",
)
_RX_AMBIGUOUS_FORM = re.compile(r"\bCo\.,?\s*Ltd\.?|\bLtd\.?\b|\bLimited\b", re.I)
_RX_TAX_ID = re.compile(
    r"\bVAT\s*(?:No\.?|Number|ID|/|:)|\bCod\.?\s*Fisc|\bCodice\s+Fiscale|\bPartita\s+IVA|\bP\.\s?IVA\b|\bEIN\b|\bUSCC\b"
    r"|统一社会信用代码|\bUSt-?IdNr|\bSIRET\b|\bSIREN\b|\bABN\b|\bUEN\b|\bTax\s+ID\b(?![^\n]{0,40}(?:\d{3}-\d{2}-\d{5}))",
)
_RX_BANK = re.compile(r"\bIBAN\b|\bSWIFT\b|\bBIC\b")
_RX_CURRENCY = re.compile(r"\b(?:EUR|USD|JPY|CNY|RMB|GBP|CHF|HKD|SGD|AUD|CAD|VND)\b|€|US\$|￥|¥")
_RX_TT_LC = re.compile(r"\bT/T\b|\bL/C\b|telegraphic\s+transfer|letter\s+of\s+credit|전신송금|신용장", re.I)
_RX_TRADE = re.compile(
    r"Incoterms|\b(?:EXW|FCA|FAS|FOB|CFR|CIF|CPT|CIP|DAP|DPU|DDP)\b|\bB/L\b|Bill\s+of\s+Lading|선하증권"
    r"|Commercial\s+Invoice|Packing\s+List|Proforma\s+Invoice|견적송장|원산지\s*(?:증명|신고)|Certificate\s+of\s+Origin"
    r"|Origin\s+Declaration|\bFTA\b|수출\s*통관|수입\s*통관|export\s+customs|import\s+customs",
)
_RX_INTL_NORMS = re.compile(
    r"\bCISG\b|국제물품매매계약에\s*관한\s*(?:유엔|국제연합)\s*협약|United\s+Nations\s+Convention\s+on\s+Contracts\s+for\s+the\s+International\s+Sale"
    r"|\bSIAC\b|Singapore\s+International\s+Arbitration|싱가포르\s*국제\s*중재|\bICC\b|International\s+Chamber\s+of\s+Commerce"
    r"|\bHKIAC\b|\bCIETAC\b|\bLCIA\b|\bKCAB\b|국제\s*중재\s*규칙|International\s+Arbitration\s+Rules"
    r"|New\s+York\s+Convention|뉴욕\s*협약|\bUNCITRAL\b",
)
_RX_PREVAILING = re.compile(
    r"(?:영문|영어|English)\s*(?:본|판|version|text)?[^.\n]{0,40}(?:우선|prevail|govern)"
    r"|(?:국문|한국어|Korean)\s*(?:본|판|version|text)?[^.\n]{0,40}(?:우선|prevail|govern)"
    r"|in\s+case\s+of\s+(?:any\s+)?(?:discrepancy|conflict|inconsistency)[^.\n]{0,80}(?:version|text)[^.\n]{0,20}prevail",
    re.I,
)

#: 신호군 가중치.
_WEIGHTS = {"entity_form": 2, "foreign_address": 2, "foreign_tax_id": 2, "bank": 1, "currency": 1,
            "trade_terms": 1, "intl_norms": 1, "bilingual": 1}
THRESHOLD_SCORE = 3
THRESHOLD_GROUPS = 2


@dataclass
class Signal:
    group: str
    token: str
    evidence_quote: str
    weight: int = 1


@dataclass
class CrossBorderAssessment:
    is_cross_border: bool
    score: int
    groups: list[str]
    signals: list[Signal] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)       # 주소 문맥에서 확인된 외국 국가
    korea_party: bool = False
    bilingual: bool = False
    prevailing_language: str = ""                           # "en" / "ko" / ""
    prevailing_quote: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["signals"] = [asdict(s) for s in self.signals[:30]]
        return d


def _first(rx: re.Pattern[str], text: str) -> re.Match[str] | None:
    return rx.search(text)


def _country_near_address(text: str) -> list[tuple[str, re.Match[str]]]:
    """주소로 쓰인 외국 지명. (a) 주소 표지 뒤 같은 줄·같은 문장 안, (b) 당사자 블록의 주소 모양 줄 끝,
    (c) "laws of …/incorporated in …" 바로 뒤. 문장 속에 스친 국가명(중재기관 이름 등)은 세지 않는다."""
    out: list[tuple[str, re.Match[str]]] = []
    head_end = _operative_start(text)
    for m in _RX_COUNTRY.finditer(text):
        if not _word_boundary(text, m):
            continue
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        line_end = len(text) if line_end < 0 else line_end
        window = text[max(line_start, m.start() - 160): m.start()]
        ctx = _RX_ADDRESS_CTX.search(window)
        ok = bool(ctx) and not re.search(r"(?:다|요)\.|[.。]\s+[가-힣]", window[ctx.end():] if ctx else "")
        if not ok and m.start() < head_end:
            line = text[line_start:line_end]
            tail = text[m.end():line_end].strip(" .,)")
            # 지명 뒤에는 우편번호류만 올 수 있다("Ontario M3J 2J5") — "Singapore 지사" 같은 서술은 주소가 아니다
            ok = len(line) <= 90 and bool(re.search(r"[,\d]", line)) and bool(re.fullmatch(r"[A-Z0-9\s\-]{0,12}", tail))
        if not ok:
            ok = bool(_RX_LAWS_OF.search(text[max(0, m.start() - 80): m.start()]))
        if ok:
            out.append((_ALL_PLACES[m.group(0)], m))
    return out


def _word_boundary(text: str, m: re.Match[str]) -> bool:
    if not re.match(r"[A-Za-z]", m.group(0)):
        return True
    before = text[m.start() - 1] if m.start() > 0 else " "
    after = text[m.end()] if m.end() < len(text) else " "
    return not (before.isalpha() or after.isalpha())


def _operative_start(text: str) -> int:
    """본문 조항이 시작되는 위치 — 그 앞이 당사자 블록(전문)이다."""
    m = re.search(r"(?m)^\s*(?:제\s*1\s*조|Article\s+1\b|ARTICLE\s+1\b|Section\s+1\b|1\.\s+[A-Z가-힣])", text)
    return m.start() if m else min(len(text), 2500)


def is_bilingual(text: str) -> bool:
    """국문과 영문이 함께 실질적으로 쓰였는가(양쪽 글자 수가 모두 일정 비율 이상)."""
    t = text or ""
    ko = sum(1 for ch in t if "가" <= ch <= "힣")
    en = sum(1 for ch in t if ch.isascii() and ch.isalpha())
    total = ko + en
    return total > 400 and ko / total >= 0.15 and en / total >= 0.25


def assess_cross_border(text: str) -> CrossBorderAssessment:
    t = str(text or "")
    sig: list[Signal] = []

    def add(group: str, m: re.Match[str], weight: int | None = None) -> None:
        sig.append(Signal(group=group, token=m.group(0), evidence_quote=quote_around(t, m.start(), m.end(), before=40, after=40),
                          weight=_WEIGHTS[group] if weight is None else weight))

    addr = _country_near_address(t)
    for _c, m in addr[:4]:
        add("foreign_address", m)
    countries = list(dict.fromkeys(c for c, _m in addr))
    for m in list(_RX_FOREIGN_FORM.finditer(t))[:3]:
        add("entity_form", m)
    if not any(s.group == "entity_form" for s in sig) and addr:
        # "Co., Ltd." 는 외국 주소가 같은 당사자 블록(앞뒤 400자)에 있을 때만 외국 법인 표지로 센다
        for m in _RX_AMBIGUOUS_FORM.finditer(t):
            if any(abs(am.start() - m.start()) < 400 for _c, am in addr):
                add("entity_form", m)
                break
    for rx, g in ((_RX_TAX_ID, "foreign_tax_id"), (_RX_BANK, "bank"), (_RX_INTL_NORMS, "intl_norms")):
        m = _first(rx, t)
        if m:
            add(g, m)
    m = _first(_RX_CURRENCY, t)
    if m:
        add("currency", m, weight=2 if _RX_TT_LC.search(t) else 1)
    trade = list(_RX_TRADE.finditer(t))
    if trade:
        add("trade_terms", trade[0], weight=2 if len({x.group(0).upper() for x in trade}) >= 3 else 1)
    bil = is_bilingual(t)
    pm = _RX_PREVAILING.search(t)
    if bil and pm:
        add("bilingual", pm)
    prevailing = ""
    if pm:
        prevailing = "en" if re.search(r"영문|영어|English", pm.group(0), re.I) else "ko"

    groups = list(dict.fromkeys(s.group for s in sig))
    score = sum(max(s.weight for s in sig if s.group == g) for g in groups)
    korea = any(k in t for k in KOREA_NAMES)
    return CrossBorderAssessment(
        is_cross_border=len(groups) >= THRESHOLD_GROUPS and score >= THRESHOLD_SCORE,
        score=score, groups=groups, signals=sig, countries=countries, korea_party=korea,
        bilingual=bil, prevailing_language=prevailing, prevailing_quote=(pm.group(0) if pm else ""),
    )


_RX_CISG_NAME = re.compile(r"\bCISG\b|국제물품매매계약에\s*관한\s*(?:유엔|국제연합)\s*협약|Convention\s+on\s+Contracts\s+for\s+the\s+International\s+Sale", re.I)
_RX_CISG_OUT = re.compile(r"(?:CISG|Convention)[^.\n]{0,60}(?:shall\s+not\s+apply|is\s+(?:hereby\s+)?excluded|적용하지\s*아니|배제)", re.I)
_RX_GOODS_SALE = re.compile(r"매매|구매|공급|수입|수출|sale|purchase|supply|goods|Incoterms", re.I)


def cisg_applies(text: str) -> bool:
    """CISG 가 적용되는 국제 물품매매인가 — 국제계약 + 물품매매 + (CISG 지정 또는 상대국이 체약국) + 배제 조항 없음."""
    t = str(text or "")
    a = assess_cross_border(t)
    if not a.is_cross_border or not _RX_GOODS_SALE.search(t[:6000]) or _RX_CISG_OUT.search(t):
        return False
    if _RX_CISG_NAME.search(t):
        return True
    foreign = [c for c in a.countries if c != "Korea"]
    return bool(foreign) and a.korea_party and all(cisg_status(c) == "체약국" for c in foreign)


def cisg_status(country: str) -> str:
    if country in CISG_STATES:
        return "체약국"
    if country in CISG_NON_STATES:
        return "비체약국"
    return "확인 필요"
