"""Multi-language contract clause parser for Korean and English NDAs."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


# ── Source-section detection ──────────────────────────────────────────────────
# dealer_rental_service_contract에서 고객용 렌탈계약서/별첨/첨부 양식과
# 대리점계약서 본문을 구분하기 위한 키워드 시그널

_MAIN_CONTRACT_SIGNALS = re.compile(
    r"공급업자와\s*대리점|대리점은\s+공급업자로부터\s+위탁|용역수수료|케어운영\s*수수료|"
    r"안정운영\s*수수료|거래보증금|오피스케어|위탁판매\s*대리점|위탁\s*수수료|"
    r"대리점\s+계약|대리점이\s+공급업자에게",
    re.IGNORECASE,
)

_CUSTOMER_FORM_SIGNALS = re.compile(
    r"퍼시스와\s*고객|고객은\s*퍼시스와|계약물품\s*및\s*금액|렌탈료\s*산정|"
    r"설치장소|렌탈\s*계약서|고객용|별도\s*작성|첨부\s*양식|별첨\s*[1-9]|"
    r"부속서|[Aa]ppendix|[Ee]xhibit|고객과\s+퍼시스",
    re.IGNORECASE,
)

_APPENDIX_SIGNALS = re.compile(
    r"별첨\s*\d|부속\s*서류|첨부\s*\d|[Aa]ppendix\s*\d|[Ee]xhibit\s*\d|"
    r"별지\s*\d|붙임\s*\d",
    re.IGNORECASE,
)


def detect_source_section_type(text_window: str) -> str:
    """계약서 텍스트 구간에서 source_section_type을 추론한다.

    Returns:
        'main_contract'         — 대리점계약서 본문 조항
        'customer_contract_form'— 고객용 렌탈계약서 양식
        'appendix'              — 별첨/부속서
        'unknown'               — 판단 불가
    """
    t = str(text_window or "")
    if _APPENDIX_SIGNALS.search(t):
        return "appendix"
    if _CUSTOMER_FORM_SIGNALS.search(t):
        return "customer_contract_form"
    if _MAIN_CONTRACT_SIGNALS.search(t):
        return "main_contract"
    return "unknown"


def normalize_clause_no(article_num: str, title: str = "") -> str:
    """'6'+'대리점의 의무' → '제6조 (대리점의 의무)' 형태로 정규화."""
    num = str(article_num or "").strip()
    t = str(title or "").strip()
    if not num:
        return ""
    base = f"제{num}조"
    return f"{base} ({t})" if t else base


@dataclass
class Clause:
    number: str
    title: str
    body: str
    language: str
    start_pos: int
    clause_no: str = field(default="")           # 예: "제6조 (대리점의 의무)"
    paragraph_no: str = field(default="")        # 예: "제3항"
    source_section_type: str = field(default="unknown")  # main_contract / customer_contract_form / appendix / unknown
    original_excerpt: str = field(default="")


KOREAN_CLAUSE_RE = re.compile(
    r"제\s*(\d+)\s*조\s*(?:\(([^)]+)\))?\s*\n?([\s\S]+?)(?=제\s*\d+\s*조|\Z)",
    re.MULTILINE,
)

ARTICLE_CLAUSE_RE = re.compile(
    r"(?:Article|Section|Clause)\s+(\d+)[.):]?\s*(?:\n?([^\n]{0,80})\n)?([\s\S]+?)"
    r"(?=(?:Article|Section|Clause)\s+\d+|\Z)",
    re.IGNORECASE | re.MULTILINE,
)

# English numbered "1. Title" or "1. Full sentence body" format
# Matches "N." at line start followed by any content
ENGLISH_NUMBERED_RE = re.compile(
    r"^(\d{1,2})\.\s+([\s\S]+?)(?=^\d{1,2}\.\s+|\Z)",
    re.MULTILINE,
)


def detect_language(text: str) -> str:
    korean_chars = len(re.findall(r"[가-힣]", text))
    total_alpha = len(re.findall(r"[a-zA-Z가-힣]", text))
    if total_alpha == 0:
        return "ko"
    return "ko" if korean_chars / total_alpha > 0.3 else "en"


def _split_heading_body(raw: str) -> tuple[str, str]:
    """Split numbered clause content into first-line title and body."""
    lines = raw.strip().splitlines()
    if not lines:
        return "", ""
    first = lines[0].strip()
    rest = "\n".join(lines[1:]).strip()
    # If first line is short and title-like (no sentence verbs), treat as title
    if len(first) <= 80 and not re.search(
        r"\b(shall|will|must|may|hereby)\b", first, re.IGNORECASE
    ):
        return first, rest
    return "", raw.strip()


def parse_clauses(full_text: str, detect_section_types: bool = False) -> List[Clause]:
    """Parse contract clauses from full_text.

    Args:
        full_text: raw contract text
        detect_section_types: if True, infer source_section_type for each clause
            using surrounding context (useful for dealer_rental contracts).
    """
    lang = detect_language(full_text)
    clauses: List[Clause] = []

    if lang == "ko":
        for m in KOREAN_CLAUSE_RE.finditer(full_text):
            num = m.group(1)
            title = m.group(2) or ""
            body = m.group(3).strip()
            # context window: 200 chars before + body start for section detection
            context_start = max(0, m.start() - 200)
            ctx_window = full_text[context_start: m.start() + min(len(body), 300)]
            stype = detect_source_section_type(ctx_window) if detect_section_types else "unknown"
            clauses.append(
                Clause(
                    number=num,
                    title=title,
                    body=body,
                    language="ko",
                    start_pos=m.start(),
                    clause_no=normalize_clause_no(num, title),
                    source_section_type=stype,
                    original_excerpt=body[:200],
                )
            )
    else:
        # Try "Article N" / "Section N" pattern first
        matches = list(ARTICLE_CLAUSE_RE.finditer(full_text))
        if matches:
            for m in matches:
                clauses.append(
                    Clause(
                        number=m.group(1),
                        title=(m.group(2) or "").strip(),
                        body=m.group(3).strip(),
                        language="en",
                        start_pos=m.start(),
                        clause_no=f"Article {m.group(1)}",
                    )
                )
        else:
            # Fallback: plain "1." numeric format
            for m in ENGLISH_NUMBERED_RE.finditer(full_text):
                title, body = _split_heading_body(m.group(2))
                clauses.append(
                    Clause(
                        number=m.group(1),
                        title=title,
                        body=body or m.group(2).strip(),
                        language="en",
                        start_pos=m.start(),
                    )
                )

    if not clauses:
        clauses.append(
            Clause(
                number="0",
                title="전문",
                body=full_text.strip(),
                language=lang,
                start_pos=0,
            )
        )

    return clauses
