from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree


@dataclass(frozen=True)
class LawApiError(RuntimeError):
    message: str
    status_code: int | None = None
    response_text: str | None = None

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class DrfResponse:
    url: str
    status_code: int | None
    format: str
    raw_text: str
    json_obj: dict[str, Any] | None
    xml_root: ElementTree.Element | None


class LawDrfClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://www.law.go.kr/DRF",
        timeout_sec: float = 20.0,
        retry_count: int = 2,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_sec = float(timeout_sec)
        self._retry_count = int(retry_count)

    def search(self, *, target: str, params: dict[str, Any] | None = None, fmt: str = "JSON") -> DrfResponse:
        return self._call("lawSearch.do", target=target, params=params, fmt=fmt)

    def service(self, *, target: str, params: dict[str, Any] | None = None, fmt: str = "JSON") -> DrfResponse:
        return self._call("lawService.do", target=target, params=params, fmt=fmt)

    def search_laws(self, *, query: str, page: int = 1, display: int = 10, fmt: str = "JSON") -> DrfResponse:
        return self.search(target="law", params={"query": query, "page": page, "display": display}, fmt=fmt)

    def get_law_detail(
        self,
        *,
        law_id: str | None = None,
        mst: str | None = None,
        lm: str | None = None,
        ld: str | None = None,
        jo: str | None = None,
        fmt: str = "JSON",
    ) -> DrfResponse:
        p: dict[str, Any] = {}
        if law_id:
            p["ID"] = law_id
        if mst:
            p["MST"] = mst
        if lm:
            p["LM"] = lm
        if ld:
            p["LD"] = ld
        if jo:
            p["JO"] = jo
        if "ID" not in p and "MST" not in p:
            raise LawApiError("법령 본문 조회에는 ID 또는 MST 중 하나가 필요합니다.")
        return self.service(target="law", params=p, fmt=fmt)

    def search_precedents(self, *, query: str, page: int = 1, display: int = 10, fmt: str = "JSON") -> DrfResponse:
        return self.search(target="prec", params={"query": query, "page": page, "display": display}, fmt=fmt)

    def get_precedent_detail(self, *, precedent_id: str, lm: str | None = None, fmt: str = "JSON") -> DrfResponse:
        p: dict[str, Any] = {"ID": precedent_id}
        if lm:
            p["LM"] = lm
        return self.service(target="prec", params=p, fmt=fmt)

    def search_interpretations(self, *, query: str, page: int = 1, display: int = 10, fmt: str = "JSON") -> DrfResponse:
        return self.search(target="expc", params={"query": query, "page": page, "display": display}, fmt=fmt)

    def get_interpretation_detail(self, *, interpretation_id: str, fmt: str = "JSON") -> DrfResponse:
        return self.service(target="expc", params={"ID": interpretation_id}, fmt=fmt)

    def search_admin_rules(self, *, query: str, page: int = 1, display: int = 10, fmt: str = "JSON") -> DrfResponse:
        return self.search(target="admrul", params={"query": query, "page": page, "display": display}, fmt=fmt)

    def get_admin_rule_detail(self, *, admin_rule_id: str, fmt: str = "JSON") -> DrfResponse:
        return self.service(target="admrul", params={"ID": admin_rule_id}, fmt=fmt)

    def search_local_ordinances(self, *, query: str, page: int = 1, display: int = 10, fmt: str = "JSON") -> DrfResponse:
        return self.search(target="ordin", params={"query": query, "page": page, "display": display}, fmt=fmt)

    def get_local_ordinance_detail(self, *, ordinance_id: str, fmt: str = "JSON") -> DrfResponse:
        return self.service(target="ordin", params={"ID": ordinance_id}, fmt=fmt)

    def _call(self, endpoint: str, *, target: str, params: dict[str, Any] | None, fmt: str) -> DrfResponse:
        format_upper = str(fmt or "JSON").strip().upper()
        if format_upper not in ("JSON", "XML", "HTML"):
            raise LawApiError("type(fmt)는 JSON/XML/HTML 중 하나여야 합니다.")

        q: dict[str, Any] = {"OC": self._api_key, "target": target, "type": format_upper}
        if params:
            for k, v in params.items():
                if v is None:
                    continue
                q[str(k)] = str(v)

        url = f"{self._base_url}/{endpoint}?{urlencode(q, doseq=True)}"
        raw = self._fetch_text(url)

        obj = None
        root = None
        if format_upper == "JSON":
            try:
                parsed = json.loads(raw) if raw else {}
                obj = parsed if isinstance(parsed, dict) else {"_raw": parsed}
            except Exception as exc:
                raise LawApiError("JSON 응답 파싱에 실패했습니다.", response_text=raw) from exc
        if format_upper == "XML":
            try:
                root = ElementTree.fromstring(raw.encode("utf-8", errors="replace"))
            except Exception as exc:
                raise LawApiError("XML 응답 파싱에 실패했습니다.", response_text=raw) from exc

        return DrfResponse(
            url=url,
            status_code=200,
            format=format_upper,
            raw_text=raw,
            json_obj=obj,
            xml_root=root,
        )

    def _fetch_text(self, url: str) -> str:
        last_exc: Exception | None = None
        last_status: int | None = None
        last_body: str | None = None

        for attempt in range(self._retry_count + 1):
            if attempt > 0:
                time.sleep(0.4 * (2 ** (attempt - 1)))
            try:
                req = Request(url, headers={"User-Agent": "aouribot/1.0"})
                with urlopen(req, timeout=self._timeout_sec) as res:
                    raw = res.read().decode("utf-8", errors="replace")
                    return raw
            except HTTPError as exc:
                last_status = int(getattr(exc, "code", 0) or 0) or None
                try:
                    last_body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    last_body = None
                last_exc = exc
            except URLError as exc:
                last_exc = exc
            except Exception as exc:
                last_exc = exc

        msg = "국가법령정보 Open API 호출에 실패했습니다."
        if last_status:
            msg += f" (HTTP {last_status})"
        raise LawApiError(msg, status_code=last_status, response_text=last_body) from last_exc

