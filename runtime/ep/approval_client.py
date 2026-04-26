from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import json


@dataclass(frozen=True)
class ApprovalClientResult:
    ok: bool
    external_reference: str | None
    error_message: str | None


class ApprovalClient(Protocol):
    def submit(self, payload: dict[str, Any]) -> ApprovalClientResult: ...


class StubApprovalClient:
    def submit(self, payload: dict[str, Any]) -> ApprovalClientResult:
        hid = str(payload.get("handoff_id") or "UNKNOWN")
        return ApprovalClientResult(ok=True, external_reference=f"STUB-{hid}", error_message=None)


class HttpApprovalClient:
    def __init__(self, *, endpoint: str, bearer_token: str | None, timeout_sec: float) -> None:
        self._endpoint = endpoint
        self._bearer_token = bearer_token
        self._timeout_sec = timeout_sec

    def submit(self, payload: dict[str, Any]) -> ApprovalClientResult:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if self._bearer_token:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        req = Request(self._endpoint, data=data, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=self._timeout_sec) as res:
                raw = res.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            try:
                msg = exc.read().decode("utf-8", errors="replace")
            except Exception:
                msg = str(exc)
            return ApprovalClientResult(ok=False, external_reference=None, error_message=msg)
        except Exception as exc:
            return ApprovalClientResult(ok=False, external_reference=None, error_message=str(exc))

        try:
            obj = json.loads(raw) if raw else {}
        except Exception:
            obj = {}
        ext = None
        if isinstance(obj, dict):
            ext = obj.get("approval_request_id") or obj.get("external_reference")
        return ApprovalClientResult(ok=True, external_reference=str(ext) if ext else None, error_message=None)

