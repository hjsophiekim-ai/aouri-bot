"""Contract-level overview for the AI reviewer.

requirement.md (2026-08-28 지시): AI에게 개별 조항만 주지 말고 계약 목적,
당사자 지위, 거래구조, 계약기간, 대금구조, 핵심 산출물과 전체 조항 목차를
먼저 제공하여 contract-level understanding을 생성한 뒤 조항별 검토를
수행한다. 이 모듈은 이미 확정된 segmentation(ClauseChunk 목록)과 원문에서
이 요약을 도출한다 — 새로운 조항을 만들어내지 않고, 있는 조항 중 관련
표현을 뽑아 구조화할 뿐이다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from runtime.review.clause_extraction import ClauseChunk

_TERM_RX = re.compile(r"(계약\s*기간|유효\s*기간|존속\s*기간)[^.\n]{0,120}(?:년|개월|일)[^.\n]{0,40}\.?")
_PRICE_RX = re.compile(
    r"(대금|용역\s*대금|수수료|계약\s*금액)[^.\n]{0,100}(지급|지불|정산|청구)[^.\n]{0,60}\.?"
)
_PURPOSE_ARTICLE_TITLE_RX = re.compile(r"목적")


def _first_sentence(text: str, limit: int = 200) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    m = re.search(r"[.!?。]", t)
    s = t[: m.end()] if m else t
    return s[:limit].strip()


@dataclass(frozen=True)
class ContractOverview:
    article_toc: list[dict[str, str]] = field(default_factory=list)
    purpose: str | None = None
    contract_term: str | None = None
    payment_structure: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "article_toc": self.article_toc,
            "purpose": self.purpose,
            "contract_term": self.contract_term,
            "payment_structure": self.payment_structure,
        }


def build_contract_overview(*, clauses: list[ClauseChunk], full_text: str) -> ContractOverview:
    """Derive a compact contract-level summary from already-segmented
    clauses and the raw text — purpose/term/payment are extracted verbatim
    excerpts, never invented, so this cannot introduce new facts."""
    toc: list[dict[str, str]] = []
    seen_articles: set[str] = set()
    purpose: str | None = None
    for c in clauses:
        art = str(c.article_number or "").strip()
        if not art or art in seen_articles:
            continue
        seen_articles.add(art)
        title = str(c.title or "").strip()
        toc.append({"article_number": art, "title": title})
        if purpose is None and _PURPOSE_ARTICLE_TITLE_RX.search(title):
            purpose = _first_sentence(c.text)

    text = full_text or ""
    term_m = _TERM_RX.search(text)
    contract_term = term_m.group(0).strip() if term_m else None
    price_m = _PRICE_RX.search(text)
    payment_structure = price_m.group(0).strip() if price_m else None

    return ContractOverview(
        article_toc=toc,
        purpose=purpose,
        contract_term=contract_term,
        payment_structure=payment_structure,
    )
