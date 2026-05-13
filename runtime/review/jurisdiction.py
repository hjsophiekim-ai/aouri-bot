from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class JurisdictionProfile:
    kind: str
    has_foreign_entity: bool
    has_cross_border_signal: bool
    evidence: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "foreign_entity_involved": bool(self.has_foreign_entity),
            "cross_border": bool(self.has_cross_border_signal),
            "evidence": list(self.evidence),
        }


_FOREIGN_ENTITY_TOKENS = [
    "inc",
    "llc",
    "ltd",
    "corp",
    "gmbh",
    "pte",
    "s.a.",
    "s.a",
    "co., ltd",
    "co.,ltd",
]

_COUNTRY_TOKENS = [
    "usa",
    "u.s.",
    "united states",
    "미국",
    "vietnam",
    "베트남",
    "taiwan",
    "대만",
    "singapore",
    "싱가포르",
    "china",
    "중국",
    "japan",
    "일본",
    "hong kong",
    "홍콩",
    "eu",
    "europe",
    "영국",
    "uk",
    "germany",
    "deutschland",
    "german",
    "france",
    "french",
    "italy",
    "italian",
    "netherlands",
    "dutch",
    "denmark",
    "danish",
    "switzerland",
    "swiss",
    "sweden",
    "swedish",
    "norway",
    "norwegian",
    "australia",
    "canada",
    "austria",
    "belgium",
    "finland",
    "poland",
    "spain",
    "spanish",
    "portugal",
]

_CURRENCY_TOKENS = [
    "usd",
    "eur",
    "jpy",
    "cny",
    "sgd",
    "$",
    "€",
    "¥",
    "달러",
    "usd ",
    "eur ",
]

_CROSS_BORDER_TOKENS = [
    "export",
    "import",
    "해외",
    "국외",
    "overseas",
    "international",
    "cross-border",
    "cross border",
    "ship to",
    "shipping",
    "delivery to",
    "incoterms",
    "exw",
    "fob",
    "cif",
]

_KOREA_LAW_TOKENS = ["대한민국", "한국", "korea", "republic of korea", "준거법", "관할", "서울", "서울중앙지방법원"]


def _has_any_ci(text: str, needles: list[str]) -> bool:
    low = (text or "").lower()
    return any(n.lower() in low for n in needles if n)


def _looks_english_heavy(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return False
    sample = s[:4000]
    alpha = sum(1 for ch in sample if ("a" <= ch.lower() <= "z"))
    total = max(1, len(sample))
    return (alpha / total) >= 0.22


def classify_jurisdiction_profile(*, text: str, entity: str | None = None, contract_type: str | None = None, filename: str | None = None) -> JurisdictionProfile:
    t = (text or "")
    ev: list[str] = []

    foreign_entity = False
    cross_border = False

    if _has_any_ci(t, _FOREIGN_ENTITY_TOKENS):
        foreign_entity = True
        ev.append("foreign_entity_token")
    if _has_any_ci(t, _COUNTRY_TOKENS):
        cross_border = True
        ev.append("country_token")
    if _has_any_ci(t, _CURRENCY_TOKENS):
        cross_border = True
        ev.append("foreign_currency_token")
    if _has_any_ci(t, _CROSS_BORDER_TOKENS):
        cross_border = True
        ev.append("cross_border_token")
    if _looks_english_heavy(t):
        cross_border = True
        ev.append("english_heavy")

    ent = (entity or "")
    if _has_any_ci(ent, ["해외", "overseas"]) or _has_any_ci(t, ["해외법인", "overseas subsidiary", "foreign subsidiary"]):
        foreign_entity = True
        cross_border = True
        ev.append("overseas_entity_hint")

    ct = (contract_type or "")
    if _has_any_ci(ct, ["해외", "overseas", "international"]):
        cross_border = True
        ev.append("contract_type_hint")

    fn = (filename or "")
    if _has_any_ci(fn, ["en", "英文", "eng", "overseas", "international"]):
        cross_border = True
        ev.append("filename_hint")

    has_korea_law = _has_any_ci(t, _KOREA_LAW_TOKENS)
    has_foreign_law = bool(re.search(
        r"(뉴욕주|캘리포니아주|delaware|england|wales|singapore law|hong kong law|"
        r"california law|new york law|german law|laws of germany|stuttgart|munich|"
        r"frankfurt|hamburg|berlin|dutch law|french law|danish law|italian law|"
        r"swiss law|london|paris|amsterdam|vienna|brussels)",
        t, flags=re.IGNORECASE,
    ))
    if has_foreign_law:
        cross_border = True
        ev.append("foreign_governing_law")

    if cross_border or foreign_entity:
        kind = "foreign_entity_involved" if foreign_entity else "cross_border"
        return JurisdictionProfile(kind=kind, has_foreign_entity=foreign_entity, has_cross_border_signal=cross_border, evidence=ev[:8])

    if has_korea_law:
        ev.append("korea_law_venue_present")
    return JurisdictionProfile(kind="domestic_korea", has_foreign_entity=False, has_cross_border_signal=False, evidence=ev[:8])

