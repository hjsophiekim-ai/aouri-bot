"""거래 사실 추출 — 전문·목적 조항·품목표·대금 조항에서 원문 그대로.

추출에 실제로 실패한 필드만 비워 두고(호출부가 "확인 필요"를 표시), 추측해서 채우지 않는다. 당사자 표에
"구매자 (Buyer)"처럼 지위가 명시돼 있으면 지위는 확정으로 본다. 우리 회사가 어느 쪽인지는 여기서 정하지 않는다.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from runtime.review.cross_border.evidence import quote_around

#: 당사자 표·서두의 지위 표기 → 지위 코드.
_ROLE_WORDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("buyer", re.compile(r"구매자|매수인|수입자|Buyer|Purchaser|Importer", re.I)),
    ("seller", re.compile(r"공급자|매도인|판매자|수출자|Seller|Supplier|Vendor|Exporter|Manufacturer", re.I)),
    ("licensor", re.compile(r"Licensor|라이선서|허락권자", re.I)),
    ("licensee", re.compile(r"Licensee|라이선시|이용권자", re.I)),
    ("distributor", re.compile(r"Distributor|Dealer|대리점|총판", re.I)),
    ("principal", re.compile(r"Principal|Company(?=\s*\))", re.I)),
    ("service_provider", re.compile(r"Service\s+Provider|Consultant|Contractor|수급인|용역\s*제공자", re.I)),
    ("client", re.compile(r"\bClient\b|Customer|위탁자|발주자", re.I)),
)
_Q = r"[\"“”'‘’]"
_RX_PARTY_DEF = re.compile(
    rf"(?P<role>[가-힣A-Za-z]{{2,20}})\s*\(\s*(?:(?P<en>[A-Za-z]{{2,20}})\s*/\s*)?(?:이하|hereinafter(?:\s+referred\s+to\s+as)?)?\s*{_Q}?(?P<label>[가-힣A-Za-z ]{{1,15}}?){_Q}?\s*\)"
)
_RX_EN_DEF = re.compile(rf"\(\s*(?:hereinafter(?:\s+referred\s+to\s+as)?\s+|the\s+)?{_Q}(?P<label>[A-Z][A-Za-z ]{{2,20}}){_Q}\s*\)")
_RX_PURPOSE = re.compile(r"[^.\n]{10,400}?(?:목적으로\s*한다|위하여\s*체결한다|위해\s*체결한다|is\s+entered\s+into[^.\n]{0,300}|governs[^.\n]{0,300})[.)]?")
_RX_TOTAL = re.compile(r"(?:총\s*계약\s*금액|계약\s*금액|Total\s+(?:Contract\s+)?(?:Amount|Price))[^\n]{0,80}?(?P<cur>EUR|USD|JPY|CNY|KRW|GBP|CHF|원|€|\$)\s*(?P<amt>[\d,]+(?:\.\d+)?)", re.I)
_RX_SPLIT = re.compile(r"선급금\s*(?P<adv>\d{1,3})\s*%[^\n]{0,40}?잔금\s*(?P<bal>\d{1,3})\s*%|(?P<adv2>\d{1,3})\s*%\s*Advance[^\n]{0,30}?(?P<bal2>\d{1,3})\s*%\s*Balance", re.I)
_RX_METHOD = re.compile(r"\bT/T\b|\bL/C\b|전신송금|신용장|wire\s+transfer|bank\s+transfer|D/P|D/A", re.I)


@dataclass
class PartyFact:
    role: str            # buyer / seller / …
    role_word: str       # 원문 지위 표기
    label: str           # 계약상 호칭("갑")
    quote: str


@dataclass
class TransactionFacts:
    purpose: str = ""
    purpose_quote: str = ""
    parties: list[PartyFact] = field(default_factory=list)
    currency: str = ""
    total_amount: str = ""
    amount_quote: str = ""
    advance_pct: int | None = None
    balance_pct: int | None = None
    split_quote: str = ""
    method: str = ""
    payer_role: str = ""
    missing: list[str] = field(default_factory=list)

    def role_of_label(self, label: str) -> str:
        return next((p.role for p in self.parties if p.label == label or p.role_word == label), "")

    def label_of_role(self, role: str) -> str:
        return next((p.label for p in self.parties if p.role == role), "")

    def payment_flow(self) -> str:
        if not self.total_amount:
            return ""
        payer = {"buyer": "구매자", "licensee": "라이선시", "client": "위탁자"}.get(self.payer_role, "")
        split = f"선급금 {self.advance_pct}% / 잔금 {self.balance_pct}%" if self.advance_pct is not None else ""
        parts = [f"{payer}가 지급".strip() if payer else "", f"{self.currency} {self.total_amount}", split, self.method]
        return ", ".join(p for p in parts if p)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["payment_flow"] = self.payment_flow()
        return d


def _role_for(word: str) -> str:
    return next((code for code, rx in _ROLE_WORDS if rx.fullmatch(word.strip()) or rx.search(word)), "")


def extract_facts(text: str) -> TransactionFacts:
    t = str(text or "")
    f = TransactionFacts()
    head = t[:6000]
    for m in _RX_PARTY_DEF.finditer(head):
        role = _role_for(m.group("role")) or _role_for(m.group("en") or "")
        label = (m.group("label") or "").strip()
        if not role or not label or any(p.role == role for p in f.parties):
            continue
        f.parties.append(PartyFact(role=role, role_word=m.group("role"), label=label,
                                   quote=quote_around(t, m.start(), m.end(), before=0, after=10)))
    # 영문 서두: (hereinafter "Distributor") / (the "Licensee") — 호칭 자체가 지위어다
    for m in _RX_EN_DEF.finditer(head):
        label = m.group("label").strip()
        role = _role_for(label)
        if role and not any(p.role == role for p in f.parties):
            f.parties.append(PartyFact(role=role, role_word=label, label=label,
                                       quote=quote_around(t, m.start(), m.end(), before=0, after=0)))
    pm = _RX_PURPOSE.search(head)
    if pm:
        f.purpose = re.sub(r"\s+", " ", pm.group(0)).strip()
        f.purpose_quote = f.purpose if f.purpose in t else quote_around(t, pm.start(), pm.end(), before=0, after=0)
    am = _RX_TOTAL.search(t)
    if am:
        f.currency = {"€": "EUR", "$": "USD", "원": "KRW"}.get(am.group("cur"), am.group("cur").upper())
        f.total_amount = am.group("amt")
        f.amount_quote = quote_around(t, am.start(), am.end(), before=0, after=10)
    sm = _RX_SPLIT.search(t)
    if sm:
        f.advance_pct = int(sm.group("adv") or sm.group("adv2"))
        f.balance_pct = int(sm.group("bal") or sm.group("bal2"))
        f.split_quote = quote_around(t, sm.start(), sm.end(), before=0, after=0)
    mm = _RX_METHOD.search(t)
    if mm:
        f.method = mm.group(0)
    roles = {p.role for p in f.parties}
    f.payer_role = next((r for r in ("buyer", "licensee", "client") if r in roles), "")
    if not f.purpose:
        f.missing.append("거래 목적")
    if not f.parties:
        f.missing.append("당사자별 지위")
    if not f.total_amount and not f.split_quote:
        f.missing.append("지급 금액·구조")
    return f
