from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class HttpResult:
    ok: bool
    status_code: int | None
    text: str | None
    error_message: str | None


class HttpClient:
    def __init__(
        self,
        *,
        timeout_sec: float = 20.0,
        retry_count: int = 2,
        retry_backoff_sec: float = 0.4,
        user_agent: str = "aouribot/1.0",
    ) -> None:
        self._timeout_sec = float(timeout_sec)
        self._retry_count = int(retry_count)
        self._retry_backoff_sec = float(retry_backoff_sec)
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": user_agent})

    def get_text(self, url: str) -> str:
        res = self._request("GET", url, data=None)
        if not res.ok or res.text is None:
            raise RuntimeError(res.error_message or "HTTP GET failed")
        return res.text

    def post_form_text(self, url: str, form: dict[str, str]) -> str:
        res = self._request("POST", url, data=form)
        if not res.ok or res.text is None:
            raise RuntimeError(res.error_message or "HTTP POST failed")
        return res.text

    def _request(self, method: str, url: str, data: dict[str, str] | None) -> HttpResult:
        last_exc: Exception | None = None
        for attempt in range(self._retry_count + 1):
            if attempt > 0:
                time.sleep(self._retry_backoff_sec * (2 ** (attempt - 1)))
            try:
                r = self._session.request(method, url, data=data, timeout=self._timeout_sec)
                txt = r.text
                if 200 <= r.status_code < 300:
                    return HttpResult(ok=True, status_code=r.status_code, text=txt, error_message=None)
                return HttpResult(
                    ok=False,
                    status_code=r.status_code,
                    text=txt,
                    error_message=f"HTTP {method} {url} failed: status={r.status_code}",
                )
            except Exception as exc:
                last_exc = exc
        return HttpResult(
            ok=False,
            status_code=None,
            text=None,
            error_message=f"HTTP {method} {url} failed: {type(last_exc).__name__ if last_exc else 'Error'}",
        )

