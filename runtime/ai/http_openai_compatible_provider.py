from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from runtime.ai.provider import AIMessage, AIRequest, AIResponse, AIUsage


class OpenAICompatibleHttpProvider:
    def __init__(self, *, api_key: str, endpoint: str, model: str) -> None:
        self._api_key = api_key
        self._endpoint = endpoint
        self._model = model

    def complete(self, req: AIRequest) -> AIResponse:
        payload = {
            "model": req.model or self._model,
            "messages": [{"role": m.role, "content": m.content} for m in req.messages],
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {self._api_key}",
        }
        http_req = Request(self._endpoint, data=data, headers=headers, method="POST")
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
            choices = obj.get("choices")
            if isinstance(choices, list) and choices:
                msg = choices[0].get("message") if isinstance(choices[0], dict) else None
                if isinstance(msg, dict):
                    content = str(msg.get("content") or "")
        usage_obj = obj.get("usage") if isinstance(obj, dict) else None
        usage = None
        if isinstance(usage_obj, dict):
            usage = AIUsage(
                input_tokens=int(usage_obj.get("prompt_tokens")) if usage_obj.get("prompt_tokens") is not None else None,
                output_tokens=int(usage_obj.get("completion_tokens")) if usage_obj.get("completion_tokens") is not None else None,
                total_tokens=int(usage_obj.get("total_tokens")) if usage_obj.get("total_tokens") is not None else None,
            )
        return AIResponse(content=content, usage=usage, raw=obj if isinstance(obj, dict) else None)


def build_messages(system: str, user: str) -> list[AIMessage]:
    out = []
    if system.strip():
        out.append(AIMessage(role="system", content=system))
    out.append(AIMessage(role="user", content=user))
    return out

