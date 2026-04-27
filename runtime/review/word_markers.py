from __future__ import annotations

import re

_WORD_XML_PATTERNS = [
    r"<\s*w\d*:[^>]+>",
    r"</\s*w\d*:[^>]+>",
    r"\bw\d*:rPr\b",
    r"\bw\d*:pPr\b",
    r"\bw\d*:ins\b",
    r"\bw\d*:del\b",
    r"\bw\d*:delText\b",
    r"<\?xml\b",
    r"xmlns:w\d*=",
]

_WORD_XML_RE = re.compile("|".join(f"(?:{p})" for p in _WORD_XML_PATTERNS), flags=re.IGNORECASE)


def contains_wordprocessingml_markers(text: str) -> bool:
    s = text or ""
    if not s:
        return False
    return _WORD_XML_RE.search(s) is not None

