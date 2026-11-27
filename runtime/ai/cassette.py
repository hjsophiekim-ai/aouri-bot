"""AI 응답 녹화·재생 (개발 검증용, 기본 꺼짐).

같은 계약을 게이트만 고치며 여러 번 돌릴 때 매번 유료 호출을 하지 않으려고 둔다.
`runtime/data/ai_cassette.json` 이 있을 때만 켜진다:
    {"mode": "record" | "replay", "dir": "<응답 저장 폴더>"}
- record: 실제 호출 후 응답을 저장한다.
- replay: 같은 요청(모델·메시지 해시)의 저장 응답을 돌려준다. 없으면 실제 호출 후 저장한다.
최종 검증(새 세션·캐시 없음)은 이 파일을 지운 상태에서 실제 AI 로 돌린다 — 보고서에 구분해 적는다.
"""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

from runtime.ai.provider import AIProvider, AIRequest, AIResponse, AIUsage

_FLAG = Path(__file__).resolve().parents[1] / "data" / "ai_cassette.json"
_LOCK = threading.Lock()


def cassette_config() -> dict | None:
    try:
        cfg = json.loads(_FLAG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if cfg.get("mode") in ("record", "replay") and cfg.get("dir"):
        return cfg
    return None


def _key(req: AIRequest) -> str:
    blob = json.dumps(
        {"model": req.model, "messages": [[m.role, m.content] for m in req.messages]},
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class CassetteProvider:
    def __init__(self, inner: AIProvider, cfg: dict) -> None:
        self.inner = inner
        self.mode = cfg["mode"]
        self.dir = Path(cfg["dir"])
        self.dir.mkdir(parents=True, exist_ok=True)

    def complete(self, req: AIRequest) -> AIResponse:
        path = self.dir / f"{_key(req)}.json"
        if self.mode == "replay" and path.exists():
            d = json.loads(path.read_text(encoding="utf-8"))
            self._log("hit", path.name)
            return AIResponse(content=d["content"], usage=None, raw={"cassette": "replay"})
        resp = self.inner.complete(req)
        u = resp.usage
        with _LOCK:
            path.write_text(json.dumps({
                "content": resp.content,
                "usage": [u.input_tokens, u.output_tokens, u.total_tokens] if u else None,
            }, ensure_ascii=False), encoding="utf-8")
        self._log("miss" if self.mode == "replay" else "record", path.name)
        return resp

    def _log(self, kind: str, name: str) -> None:
        with _LOCK:
            with (self.dir / "_log.txt").open("a", encoding="utf-8") as f:
                f.write(f"{kind} {name}\n")


def maybe_wrap(provider: AIProvider) -> AIProvider:
    cfg = cassette_config()
    return CassetteProvider(provider, cfg) if cfg else provider


__all__ = ["CassetteProvider", "cassette_config", "maybe_wrap", "AIUsage"]
