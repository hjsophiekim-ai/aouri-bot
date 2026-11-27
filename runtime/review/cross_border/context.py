"""체크리스트가 공유하는 검토 맥락."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from runtime.review.cross_border.bilingual import Pair, paragraph_pairs
from runtime.review.cross_border.blanks import Blank, Layout, NegotiableValue, detect_blanks
from runtime.review.cross_border.evidence import quote_around
from runtime.review.cross_border.facts import TransactionFacts, extract_facts
from runtime.review.cross_border.signals import CrossBorderAssessment


@dataclass
class Ctx:
    text: str
    assessment: CrossBorderAssessment
    intl_type: str
    our_role: str = ""                 # buyer / seller / licensee / licensor / distributor / principal / client / service_provider
    our_label: str = ""
    their_label: str = ""
    answers_text: str = ""
    layout: Layout = field(init=False)
    facts: TransactionFacts = field(init=False)
    pairs: list[Pair] = field(init=False)
    blanks: list[Blank] = field(init=False)
    values: list[NegotiableValue] = field(init=False)

    def __post_init__(self) -> None:
        self.layout = Layout(self.text)
        self.facts = extract_facts(self.text)
        self.pairs = paragraph_pairs(self.text)
        self.blanks, self.values = detect_blanks(self.text)
        if not self.our_label and self.our_role:
            self.our_label = self.facts.label_of_role(self.our_role)
        if not self.their_label and self.our_role:
            other = {"buyer": "seller", "seller": "buyer", "licensee": "licensor", "licensor": "licensee",
                     "distributor": "principal", "principal": "distributor", "client": "service_provider",
                     "service_provider": "client"}.get(self.our_role, "")
            self.their_label = self.facts.label_of_role(other)

    # ── 원문 찾기 ──────────────────────────────────────────────────────────
    def pair(self, rx: re.Pattern[str]) -> Pair | None:
        for p in self.pairs:
            if rx.search(p.ko) or rx.search(p.en):
                return p
        # 짝지을 국·영 항이 없는 계약(영문 단일, "7.1 …" 번호 체계) — 본문 줄에서 찾는다
        pos = 0
        for line in self.text.splitlines(keepends=True):
            start = pos
            pos += len(line)
            s = line.strip()
            if not s or not rx.search(s) or self.layout.region(start) or re.fullmatch(r"\d{1,2}\.\s+[A-Za-z ,&/'()-]+", s):
                continue
            path = self.layout.path(start + (len(line) - len(line.lstrip())))
            ko = sum(1 for ch in s if "가" <= ch <= "힣")
            return Pair(path=path, ko=s if ko else "", en="" if ko else s)
        return None

    def find(self, rx: re.Pattern[str], *, before: int = 30, after: int = 60) -> tuple[str, str] | None:
        """(인용, 위치) — 첫 일치."""
        m = rx.search(self.text)
        if not m:
            return None
        return quote_around(self.text, m.start(), m.end(), before=before, after=after), self.layout.path(m.start())

    def exact(self, rx: re.Pattern[str], within: str = "") -> str:
        """원문에서 rx 가 맞는 부분 그대로(within 이 있으면 그 안에서)."""
        hay = within or self.text
        m = rx.search(hay)
        return m.group(0) if m else ""

    def has(self, rx: re.Pattern[str]) -> bool:
        return bool(rx.search(self.text))

    @property
    def buyer_side(self) -> bool:
        return self.our_role in ("buyer", "licensee", "client", "distributor")

    @property
    def korean_side(self) -> bool:
        """우리 쪽이 한국 법인인가 — 우리 호칭의 당사자 블록에 한국 주소가 있으면."""
        return self.assessment.korea_party

    def proposed_value(self, rx: re.Pattern[str]) -> str:
        """사용자 답변에 적힌 값(합의 전 제안값)."""
        for line in self.answers_text.splitlines():
            if re.search(r"Incoterms|인도\s*조건|선적\s*조건", line, re.I):
                m = rx.search(line.split(":", 1)[-1] if ":" in line else line)
                if m:
                    return m.group(0)
        return ""
