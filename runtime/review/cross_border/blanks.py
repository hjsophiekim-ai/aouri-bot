"""공란·미확정 선택지 탐지기(범용).

탐지 대상
- 빈 대괄호 `[ ]`, `[   ]`, `[      ]일`
- 대괄호 안의 안내 문구 `[대표자 성명 입력]`, `[insert name]`, `[●]`
- 대괄호 안에 나열된 선택지 `[ FCA … / FOB / CIF 중 선택 ]`
- 밑줄 `____`
- TBD · to be agreed · 추후 협의

대괄호 안에 값이 이미 들어 있으면(`[ 3 ]`, `[ 30 ]`, `[ 0.5 ]`) 공란이 아니라 **협상 가능한 확정값**이다. 단위·품목
표기(`[ML]`, `[CM 79X95 …]`)와 설명용 괄호(`[50% Advance / 50% Balance]`)는 공란이 아니다.

분류(2026-11-27 승인 기준)
- 체결 전 필수 확정(HIGH): 필수 거래조건(가격·수량·인도 시기·인도 조건·준거법·분쟁해결)의 공란, 그리고 다른 조항의
  작동을 막는 공란(예: 선적 기한 공란 → 지체상금 조항 작동 불가)
- 사업부 결정: 대표자 성명·체결일·서명란 등 기재 사항
- 단순 기재 누락: 그 밖의 공란

원문에 없는 공란은 만들지 않는다 — 모든 항목은 원문 정확 일치 인용을 갖는다.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from runtime.review.cross_border.evidence import quote_around, verify_quote

CLASS_MUST = "체결 전 필수 확정"
CLASS_BUSINESS = "사업부 결정"
CLASS_CLERICAL = "단순 기재 누락"

REGION_PREAMBLE = "전문(당사자 표)"
REGION_SIGNATURE = "서명란"

_RX_BRACKET = re.compile(r"\[([^\[\]\n]{0,200})\]")
_RX_UNDERSCORE = re.compile(r"_{3,}")
_RX_TBD = re.compile(r"\bTBD\b|\bto\s+be\s+(?:agreed|determined|confirmed|decided)\b|추후\s*(?:협의|결정)하여\s*정한다", re.I)
_RX_GUIDANCE = re.compile(r"입력|기재|작성|선택\s*$|insert|enter\b|fill\s+in|\bname\b|●|○○|xx+", re.I)
_RX_CHOICE_MARKER = re.compile(r"중\s*(?:택|선택)|선택|choose|select|either|one\s+of|권장|recommend", re.I)
_RX_TRADE_CODE = re.compile(r"\b(?:EXW|FCA|FAS|FOB|CFR|CIF|CPT|CIP|DAP|DPU|DDP)\b")
_RX_VALUE = re.compile(r"^\s*[\d.,]+\s*%?\s*$")

#: 필수 거래조건 범주 — (이름, 문맥 패턴). 앞쪽이 우선.
ESSENTIAL: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("delivery_terms", "인도 조건(Incoterms)", re.compile(r"Incoterms|인도\s*조건|delivery\s+terms?|\b(?:EXW|FCA|FOB|CIF|CFR|CPT|CIP|DAP|DPU|DDP)\b", re.I)),
    ("delivery_time", "인도(선적) 시기", re.compile(r"선적\s*기한|선적\s*\(|납\s*기|인도\s*(?:기한|시기|일자?)|shipment|delivery\s+(?:date|schedule|period)", re.I)),
    ("governing_law", "준거법", re.compile(r"준거법|governing\s+law|governed\s+by", re.I)),
    ("dispute", "분쟁해결", re.compile(r"중재|관할|arbitrat|jurisdiction|court", re.I)),
    ("price", "가격·대금", re.compile(r"단\s*가|가\s*격|계약\s*금액|대\s*금|unit\s+price|\bprice\b|contract\s+amount", re.I)),
    ("quantity", "수량", re.compile(r"수\s*량|quantity", re.I)),
)

#: 공란이 비면 작동하지 않는 조항을 찾는 연결 — (범주, 그 개념을 가리키는 말, 효과 낱말, 효과 설명)
DEPENDENCY: tuple[tuple[str, re.Pattern[str], re.Pattern[str], str], ...] = (
    ("delivery_time", re.compile(r"선적\s*기한|납\s*기|shipment\s+(?:date|schedule)|delivery\s+date", re.I),
     re.compile(r"지체상금|지연|지체|liquidated\s+damages|delay", re.I), "기한이 정해지지 않아 지연을 판단할 기준일이 없다 — 지체상금 조항이 작동하지 않는다"),
    ("price", re.compile(r"계약\s*금액|contract\s+(?:price|amount)", re.I),
     re.compile(r"%|퍼센트|percent", re.I), "금액이 정해지지 않아 금액의 비율로 정한 조항이 작동하지 않는다"),
)


@dataclass
class Blank:
    path: str
    region: str
    kind: str                       # empty / guidance / options / underscore / tbd
    category: str                   # ESSENTIAL 이름 또는 "execution" / "other"
    label: str
    classification: str
    quotes: list[str] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)
    options: list[str] = field(default_factory=list)
    dependencies: list[dict[str, str]] = field(default_factory=list)

    @property
    def risk(self) -> str:
        return "HIGH" if self.classification == CLASS_MUST else "LOW"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["risk"] = self.risk
        return d


@dataclass
class NegotiableValue:
    path: str
    value: str
    quote: str


@dataclass
class _Span:
    start: int
    end: int
    token: str
    kind: str
    inner: str = ""


# ── 위치 ──────────────────────────────────────────────────────────────────────

_RX_ARTICLE = re.compile(r"(?m)^\s*(?:제\s*(\d+)\s*조|Article\s+(\d+)\b|ARTICLE\s+(\d+)\b)")
_RX_SIGNATURE = re.compile(
    r"(?m)^.*(?:계약\s*체결일|Date\s+of\s+Execution|IN\s+WITNESS\s+WHEREOF|서명\s*날인|기명\s*날인|Authorized\s+Signature|Signed\s+by)", re.I)


class Layout:
    """본문의 조·항 위치와 전문·서명란 영역."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.articles: list[tuple[int, str]] = []
        seen: set[str] = set()
        for m in _RX_ARTICLE.finditer(text):
            num = next(g for g in m.groups() if g)
            if num in seen:          # 국·영 병기 머리("제1조 … / Article 1 …")는 같은 조
                continue
            seen.add(num)
            self.articles.append((m.start(), num))
        last_art = self.articles[-1][0] if self.articles else 0
        sig = next((m for m in _RX_SIGNATURE.finditer(text) if m.start() >= last_art), None)
        self.signature_start = sig.start() if sig else len(text)
        self.first_article = self.articles[0][0] if self.articles else 0

    def region(self, pos: int) -> str:
        if self.articles and pos < self.first_article:
            return REGION_PREAMBLE
        if pos >= self.signature_start:
            return REGION_SIGNATURE
        return ""

    def article(self, pos: int) -> str:
        num = ""
        for start, n in self.articles:
            if start <= pos:
                num = n
            else:
                break
        return num

    def paragraph(self, pos: int) -> str:
        art = self.article(pos)
        a_start = next((s for s, n in self.articles if n == art), 0)
        seg = self.text[a_start:pos]
        nums = re.findall(r"(?m)^\s*(\d{1,2})\.\s", seg)
        return nums[-1] if nums else ""

    def path(self, pos: int) -> str:
        reg = self.region(pos)
        if reg:
            return reg
        art = self.article(pos)
        if not art:
            return ""
        para = self.paragraph(pos)
        return f"제{art}조" + (f" 제{para}항" if para else "")

    def paragraph_text(self, pos: int) -> str:
        """pos 가 든 항(또는 줄) 본문."""
        line_start = self.text.rfind("\n", 0, pos) + 1
        line_end = self.text.find("\n", pos)
        return self.text[line_start: len(self.text) if line_end < 0 else line_end]


# ── 탐지 ──────────────────────────────────────────────────────────────────────

def _is_label_bracket(inner: str) -> bool:
    """단위·품목 표기 등 공란이 아닌 대괄호."""
    s = inner.strip()
    if not s:
        return False
    if re.fullmatch(r"[A-Z]{1,4}", s):                       # [ML] [NR]
        return True
    if re.match(r"(?:CM|MM|M|KG|PCS)\b", s, re.I) and re.search(r"\d", s):   # [CM 79X95 …]
        return True
    if re.fullmatch(r"(?:페이지|page)\s*\d+", s, re.I):
        return True
    return False


def _options_of(inner: str) -> list[str]:
    s = re.sub(r"(?:중\s*(?:택|선택)|선택|choose|select)[^/]*$", "", inner, flags=re.I)
    s = re.sub(r"[-–]\s*[^/]*(?:권장|recommend)[^/]*$", "", s, flags=re.I)
    parts = [p.strip(" -–") for p in re.split(r"\s*/\s*|\s+또는\s+|\s+or\s+", s) if p.strip(" -–")]
    return parts


def _spans(text: str) -> tuple[list[_Span], list[_Span]]:
    blanks: list[_Span] = []
    values: list[_Span] = []
    for m in _RX_BRACKET.finditer(text):
        inner = m.group(1)
        if not inner.strip():
            blanks.append(_Span(m.start(), m.end(), m.group(0), "empty", inner))
        elif _RX_VALUE.match(inner):
            values.append(_Span(m.start(), m.end(), m.group(0), "value", inner.strip()))
        elif _is_label_bracket(inner):
            continue
        elif ("/" in inner or re.search(r"\s(?:또는|or)\s", inner)) and (
                _RX_CHOICE_MARKER.search(inner) or len(_RX_TRADE_CODE.findall(inner)) >= 2):
            blanks.append(_Span(m.start(), m.end(), m.group(0), "options", inner))
        elif _RX_GUIDANCE.search(inner) and not re.search(r"\d+\s*%", inner):
            blanks.append(_Span(m.start(), m.end(), m.group(0), "guidance", inner))
    for m in _RX_UNDERSCORE.finditer(text):
        blanks.append(_Span(m.start(), m.end(), m.group(0), "underscore"))
    for m in _RX_TBD.finditer(text):
        blanks.append(_Span(m.start(), m.end(), m.group(0), "tbd"))
    blanks.sort(key=lambda s: s.start)
    return blanks, values


def _label(layout: Layout, sp: _Span) -> str:
    line = layout.paragraph_text(sp.start)
    before = line[: max(0, sp.start - (layout.text.rfind("\n", 0, sp.start) + 1))]
    # "1. 선적 기한 (Shipment Date): …" / "성명 / 직책 (Name / Title): ____" / "대표자 (Representative): [ … ]"
    m = re.match(r"^\s*(?:\d{1,2}\.\s*)?([^:(\[\n]{1,30}?)\s*(?:\([^)]*\))?\s*:", line)
    if m and m.end() <= len(before) + 1:
        return m.group(1).strip()
    m = re.match(r"^\s*(?:\d{1,2}\.\s*)?([^:(\[\n]{1,30}?)\s*(?:\([^)]*\))?\s*:", before)
    return m.group(1).strip() if m else ""


def _category(layout: Layout, sp: _Span, label: str) -> str:
    if layout.region(sp.start) in (REGION_SIGNATURE, REGION_PREAMBLE):
        return "execution"
    if sp.kind == "options" and _RX_TRADE_CODE.search(sp.inner):
        return "delivery_terms"
    line = layout.paragraph_text(sp.start)
    off = sp.start - (layout.text.rfind("\n", 0, sp.start) + 1)
    near = (label + " " + line[max(0, off - 120): off + 80])
    for name, _lab, rx in ESSENTIAL:
        if rx.search(label):
            return name
    for name, _lab, rx in ESSENTIAL:
        if rx.search(near):
            return name
    return "other"


def _dependencies(layout: Layout, category: str, own_path: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for cat, concept, effect, why in DEPENDENCY:
        if cat != category:
            continue
        for m in concept.finditer(layout.text):
            path = layout.path(m.start())
            if not path or path == own_path or path in (REGION_PREAMBLE, REGION_SIGNATURE):
                continue
            line = layout.paragraph_text(m.start())
            if not effect.search(line):
                continue
            if any(d["path"] == path for d in out):
                continue
            q = quote_around(layout.text, m.start(), m.end(), before=40, after=80)
            out.append({"path": path, "quote": q, "effect": why})
    return out


def detect_blanks(text: str) -> tuple[list[Blank], list[NegotiableValue]]:
    """(공란 목록, 협상 가능한 확정값 목록). 국·영 병기의 같은 공란은 한 항목으로 묶는다."""
    t = str(text or "")
    layout = Layout(t)
    spans, values = _spans(t)
    groups: dict[tuple[str, str, str], Blank] = {}
    order: list[tuple[str, str, str]] = []
    for sp in spans:
        path = layout.path(sp.start)
        label = _label(layout, sp)
        category = _category(layout, sp, label)
        region = layout.region(sp.start)
        if category == "execution":
            classification = CLASS_BUSINESS
        elif category != "other":
            classification = CLASS_MUST
        else:
            classification = CLASS_CLERICAL
        key = (path, category if category != "other" else label, "exec" if category == "execution" else "")
        if category == "execution":
            # 서명란·전문은 항목(대표자·성명·서명·체결일)별로 묶는다 — 국·영 표기가 같은 항목이면 하나로
            key = (path, _execution_item(label, layout.paragraph_text(sp.start)), "exec")
        q = quote_around(t, sp.start, sp.end, before=70, after=50)
        if not verify_quote(q, t):
            continue
        b = groups.get(key)
        if b is None:
            b = Blank(path=path, region=region, kind=sp.kind, category=category, label=label or key[1],
                      classification=classification)
            groups[key] = b
            order.append(key)
        if q not in b.quotes:
            b.quotes.append(q)
        b.tokens.append(sp.token)
        if sp.kind == "options":
            for o in _options_of(sp.inner):
                if o not in b.options:
                    b.options.append(o)
    out = [groups[k] for k in order]
    for b in out:
        if b.classification != CLASS_BUSINESS:
            b.dependencies = _dependencies(layout, b.category, b.path)
            if b.dependencies and b.classification == CLASS_CLERICAL:
                b.classification = CLASS_MUST
    nvals = [NegotiableValue(path=layout.path(v.start), value=v.inner,
                             quote=quote_around(t, v.start, v.end, before=50, after=30)) for v in values]
    return out, nvals


def _execution_item(label: str, line: str) -> str:
    s = f"{label} {line}"
    if re.search(r"체결일|Date\s+of\s+Execution|일자|\bDate\b", s, re.I):
        return "체결일"
    if re.search(r"대표자|Representative", s, re.I):
        return "대표자 성명"
    if re.search(r"서명|Signature", s, re.I) and not re.search(r"성명|Name", label, re.I):
        return "서명"
    if re.search(r"성명|Name|직책|Title", s, re.I):
        return "서명권자 성명·직책"
    return label or "기재 사항"
