"""국·영 병기 조항 짝짓기.

같은 조의 같은 항 번호("2. …")를 가진 국문 줄과 영문 줄을 한 쌍으로 묶는다. 한 줄 안에 국문 뒤 영문이 괄호로 붙은
경우("… 목적으로 한다. (This Agreement governs …)")도 나눈다. 짝을 지은 뒤 비교는 각 체크리스트가 자기 주제로 한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from runtime.review.cross_border.blanks import Layout


@dataclass
class Pair:
    path: str
    ko: str
    en: str


def _lang(line: str) -> str:
    ko = sum(1 for ch in line if "가" <= ch <= "힣")
    en = sum(1 for ch in line if ch.isascii() and ch.isalpha())
    if ko == 0 and en == 0:
        return ""
    return "ko" if ko >= en * 0.25 else "en"


_RX_INLINE_EN = re.compile(r"\((?=(?:This|The|Subject|Notwithstanding|In\s+case|Party|Seller|Buyer)\b)([^()]*(?:\([^()]*\)[^()]*)*)\)")


def paragraph_pairs(text: str) -> list[Pair]:
    t = str(text or "")
    layout = Layout(t)
    acc: dict[str, dict[str, str]] = {}
    order: list[str] = []
    pos = 0
    current = ""
    for line in t.splitlines(keepends=True):
        start = pos
        pos += len(line)
        s = line.strip()
        art = layout.article(start)
        if not art or layout.region(start):
            current = ""
            continue
        mnum = re.match(r"^(\d{1,2})\.\s", s)
        if not mnum:
            # 항 안의 호·목 줄("가. …", "(a) …")은 직전 항에 붙인다 — 언어별로
            if current and s and re.match(r"^(?:[가-하]\.|\([a-z]\)|[a-z]\)|[①-⑳]|[-•·])\s*", s):
                lang = _lang(s)
                if lang:
                    acc[current][lang] = (acc[current][lang] + " " + s).strip()
            elif re.match(r"^\s*(?:제\s*\d+\s*조|Article\s+\d+)", s):
                current = ""
            continue
        path = f"제{art}조 제{mnum.group(1)}항"
        current = path
        lang = _lang(s)
        if not lang:
            continue
        slot = acc.setdefault(path, {"ko": "", "en": ""})
        if path not in order:
            order.append(path)
        if lang == "ko":
            m = _RX_INLINE_EN.search(s)
            if m and not slot["en"]:
                slot["en"] = m.group(1).strip()
                s = (s[:m.start()] + s[m.end():]).strip()
            slot["ko"] = (slot["ko"] + " " + s).strip()
        else:
            slot["en"] = (slot["en"] + " " + s).strip()
    return [Pair(path=p, ko=acc[p]["ko"], en=acc[p]["en"]) for p in order]


def pair_for(text: str, rx: re.Pattern[str]) -> Pair | None:
    """국문 또는 영문이 rx 에 맞는 첫 쌍."""
    for p in paragraph_pairs(text):
        if rx.search(p.ko) or rx.search(p.en):
            return p
    return None
