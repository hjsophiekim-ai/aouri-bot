from __future__ import annotations

import json
import re
from typing import Any

from runtime.ai.http_openai_compatible_provider import build_messages
from runtime.ai.provider import AIProvider, AIRequest

META_EXTRACTION_SYSTEM = (
    "You are a contract metadata extraction assistant. "
    "Extract key metadata from contract text and return ONLY valid JSON, no markdown, no explanation."
)

META_EXTRACTION_USER_TEMPLATE = """\
Extract metadata from the contract text below.
Return ONLY a JSON object with exactly these fields:
- "party_a": name of first party (string)
- "party_b": name of second party (string)
- "governing_law": governing law (e.g., "German law", "Korean law", "New York law", null if unclear)
- "jurisdiction": dispute resolution venue or city or court (e.g., "Stuttgart", "Seoul Central District Court", "ICC", null if unclear)
- "contract_type": type in English (e.g., "NDA", "Service Agreement", "Supply Agreement")
- "language": primary language — one of "Korean", "English", "Bilingual"
- "is_cross_border": true if parties appear to be from different countries, false otherwise

Contract text (first 3000 chars):
{text}
"""


def extract_contract_meta(
    text: str,
    *,
    ai_provider: AIProvider,
    model: str,
    max_tokens: int = 512,
    timeout_sec: float = 30.0,
    temperature: float = 0.1,
) -> dict[str, Any]:
    """LLM으로 계약서 메타데이터(당사자, 준거법, 관할)를 추출한다. 실패 시 빈 dict 반환."""
    if not text or not text.strip():
        return {}
    sample = text[:3000]
    user_prompt = META_EXTRACTION_USER_TEMPLATE.format(text=sample)
    try:
        req = AIRequest(
            model=model,
            messages=build_messages(META_EXTRACTION_SYSTEM, user_prompt),
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_sec=timeout_sec,
        )
        resp = ai_provider.complete(req)
        content = (resp.content or "").strip()
        if not content:
            return {}
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```\s*$", "", content.strip())
        data = json.loads(content)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}
