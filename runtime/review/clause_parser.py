"""Multi-language contract clause parser for Korean and English NDAs."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List


@dataclass
class Clause:
    number: str
    title: str
    body: str
    language: str
    start_pos: int


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


def parse_clauses(full_text: str) -> List[Clause]:
    lang = detect_language(full_text)
    clauses: List[Clause] = []

    if lang == "ko":
        for m in KOREAN_CLAUSE_RE.finditer(full_text):
            clauses.append(
                Clause(
                    number=m.group(1),
                    title=m.group(2) or "",
                    body=m.group(3).strip(),
                    language="ko",
                    start_pos=m.start(),
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
