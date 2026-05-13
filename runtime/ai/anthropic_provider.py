from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from runtime.ai.provider import AIMessage, AIRequest, AIResponse, AIUsage

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"


class AnthropicProvider:
    def __init__(self, *, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def complete(self, req: AIRequest) -> AIResponse:
        model = req.model or self._model

        system_content = ""
        messages: list[dict[str, str]] = []
        for m in req.messages:
            if m.role == "system":
                system_content = m.content
            else:
                messages.append({"role": m.role, "content": m.content})

        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": req.max_tokens,
            "messages": messages,
        }
        if system_content:
            payload["system"] = system_content
        if req.temperature is not None:
            payload["temperature"] = req.temperature

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_API_VERSION,
        }
        http_req = Request(ANTHROPIC_API_URL, data=data, headers=headers, method="POST")
        try:
            with urlopen(http_req, timeout=req.timeout_sec) as res:
                raw = res.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            try:
                msg = exc.read().decode("utf-8", errors="replace")
            except Exception:
                msg = str(exc)
            raise RuntimeError(msg) from exc

        obj = json.loads(raw) if raw else {}
        content = ""
        if isinstance(obj, dict):
            content_blocks = obj.get("content")
            if isinstance(content_blocks, list):
                for block in content_blocks:
                    if isinstance(block, dict) and block.get("type") == "text":
                        content = str(block.get("text") or "")
                        break

        usage_obj = obj.get("usage") if isinstance(obj, dict) else None
        usage = None
        if isinstance(usage_obj, dict):
            inp = usage_obj.get("input_tokens")
            out = usage_obj.get("output_tokens")
            usage = AIUsage(
                input_tokens=int(inp) if inp is not None else None,
                output_tokens=int(out) if out is not None else None,
                total_tokens=None,
            )
        return AIResponse(content=content, usage=usage, raw=obj if isinstance(obj, dict) else None)
