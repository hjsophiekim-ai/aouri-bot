from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

from runtime.law.http import HttpClient


@dataclass(frozen=True)
class GuideParam:
    name: str
    value: str
    description: str


@dataclass(frozen=True)
class GuideEntry:
    guide_id: str
    title: str
    request_url: str
    request_params: list[GuideParam]
    change_log_lines: list[str]
    derived: dict[str, Any]


class LawOpenApiGuideCatalog:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def list_guide_ids(self) -> list[str]:
        html = self._http.get_text("https://open.law.go.kr/LSO/openApi/guideList.do")
        ids = re.findall(r"openApiGuide\('([^']+)'\)", html)
        return list(dict.fromkeys([i.strip() for i in ids if i.strip()]))

    def fetch_guide_entry(self, guide_id: str) -> GuideEntry:
        html = self._http.post_form_text(
            "https://open.law.go.kr/LSO/openApi/guideResult.do",
            form={"htmlName": guide_id},
        )
        title = _extract_title(html) or guide_id
        request_url = _extract_request_url(html) or ""
        params = _extract_request_params(html)
        change_log_lines = _extract_change_log_lines(html)
        derived = _derive_from_request_url(request_url)
        return GuideEntry(
            guide_id=guide_id,
            title=title,
            request_url=request_url,
            request_params=params,
            change_log_lines=change_log_lines,
            derived=derived,
        )


def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).replace("\xa0", " ").strip()


def _extract_title(html: str) -> str | None:
    start = html.find('class="guide_area"')
    if start != -1:
        sub = html[start : start + 5000]
        m = re.search(r"<h3>\s*([^<]+?)\s*</h3>", sub)
        if m:
            return _strip_tags(m.group(1))
    m = re.search(r"<h3>\s*([^<]+?)\s*</h3>", html)
    return _strip_tags(m.group(1)) if m else None


def _extract_request_url(html: str) -> str | None:
    m = re.search(r"-\s*요청 URL\s*:\s*([^<]+?)\s*</dt>", html)
    if not m:
        m = re.search(r"-\s*요청 URL\s*:\s*([^<]+?)\s*<", html)
    return _strip_tags(m.group(1)) if m else None


def _extract_request_params(html: str) -> list[GuideParam]:
    m = re.search(r"<table[^>]*class=\"blist guide\"[\s\S]*?<tbody>([\s\S]*?)</tbody>", html)
    if not m:
        return []
    body = m.group(1)
    out: list[GuideParam] = []
    rows = re.findall(r"<tr[^>]*>\s*([\s\S]*?)\s*</tr>", body)
    for row in rows:
        tds = re.findall(r"<td[^>]*>\s*([\s\S]*?)\s*</td>", row)
        if len(tds) < 3:
            continue
        a, b, c = tds[0], tds[1], tds[2]
        name = _strip_tags(a)
        value = _strip_tags(b)
        desc = _strip_tags(c)
        if not name:
            continue
        out.append(GuideParam(name=name, value=value, description=desc))
    return out


def _extract_change_log_lines(html: str) -> list[str]:
    lines = []
    for m in re.finditer(r"(\d{4}\.\s*\d{2}\.\s*\d{2}\.\s*\[[^\]]+\]\s*[^<\r\n]+)", html):
        line = _strip_tags(m.group(1))
        if line:
            lines.append(line)
    return list(dict.fromkeys(lines))


def _derive_from_request_url(request_url: str) -> dict[str, Any]:
    if not request_url:
        return {}
    parsed = urlparse(request_url)
    qs = parse_qs(parsed.query)
    out: dict[str, Any] = {
        "path": parsed.path,
        "host": parsed.netloc,
        "query": {k: (v[0] if len(v) == 1 else v) for k, v in qs.items()},
    }
    target = qs.get("target", [None])[0]
    out["target"] = target
    out["kind"] = "lawSearch" if parsed.path.endswith("/lawSearch.do") else "lawService" if parsed.path.endswith("/lawService.do") else None
    return out

