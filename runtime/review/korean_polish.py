from __future__ import annotations

import re


def polish_korean_legal_style(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return ""
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = s.replace("상대방는", "상대방은").replace("상대방를", "상대방을").replace("상대방가", "상대방이")
    s = s.replace("당사은", "당사는").replace("당사가", "당사가").replace("당사를", "당사를")
    s = s.replace("상대방 및 그", "상대방과 그")
    s = re.sub(r"(구매자 보호 방향\([^)]*\)\s*기준으로\s*보완:\s*)", "", s)
    s = re.sub(r"(buyer_favorable\s*기준으로\s*보완[:：]?\s*)", "", s, flags=re.IGNORECASE)
    s = re.sub(r"(구매자 보호\s*중심으로\s*보완[:：]?\s*)", "", s)
    s = re.sub(r"\s+([,.)])", r"\1", s)
    s = re.sub(r"([(\[])\s+", r"\1", s)
    return s.strip()

