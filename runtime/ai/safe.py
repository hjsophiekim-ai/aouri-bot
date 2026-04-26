from __future__ import annotations

import re


def sanitize_error_message(msg: str) -> str:
    s = str(msg or "")
    s = re.sub(r"sk-[A-Za-z0-9]{10,}", "sk-***", s)
    s = s.replace("Bearer ", "Bearer ***")
    s = s.replace("authorization", "auth")
    s = s.strip()
    if len(s) > 400:
        s = s[:400] + "..."
    return s or "AI provider error"

