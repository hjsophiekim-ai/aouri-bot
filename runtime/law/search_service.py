from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from runtime.law.cache import JsonFileCache
from runtime.law.config import LawApiConfig
from runtime.law.drf_client import LawApiError, LawDrfClient
from runtime.law.priority_rules import get_priority_topics_with_context


@dataclass(frozen=True)
class LawReference:
    source: str
    target: str
    title: str
    snippet: str | None
    identifiers: dict[str, str]
    drf_detail_url: str | None


class LawSearchService:
    def __init__(self, *, cfg: LawApiConfig, cache: JsonFileCache) -> None:
        self._cfg = cfg
        self._cache = cache
        self._client = LawDrfClient(
            api_key=str(cfg.api_key or ""),
            base_url=cfg.base_url,
            timeout_sec=min(float(cfg.timeout_sec), 3.0),
            retry_count=0,
        )

    def search_for_review(
        self,
        *,
        entity: str,
        contract_type: str,
        text: str,
        matched_rules: list[dict[str, Any]] | None,
        max_per_type: int = 3,
    ) -> dict[str, Any]:
        if not self._cfg.enabled or not self._cfg.api_key:
            return {
                "enabled": False,
                "note": "LAW_API_ENABLED=false 또는 LAW_API_KEY 미설정",
                "queries": [],
                "results": {"laws": [], "precedents": [], "interpretations": [], "admin_rules": [], "local_ordinances": []},
                "errors": [],
            }

        topics = _derive_topics(entity=entity, contract_type=contract_type, text=text, matched_rules=matched_rules or [])
        queries_all = list(dict.fromkeys([t for t in topics if isinstance(t, str) and t.strip()]))
        queries = queries_all[:3]

        max_items = min(int(max_per_type), 3)
        out = {"enabled": True, "queries": queries, "results": {}, "errors": []}
        context_text = str(text or "")
        out["results"]["laws"] = self._search_target("law", queries, context_text=context_text, matched_rules=matched_rules or [], max_items=max_items)
        out["results"]["precedents"] = self._search_target("prec", queries, context_text=context_text, matched_rules=matched_rules or [], max_items=max_items)
        out["results"]["interpretations"] = self._search_target("expc", queries, context_text=context_text, matched_rules=matched_rules or [], max_items=max_items)
        out["results"]["admin_rules"] = []
        out["results"]["local_ordinances"] = []
        return out

    def _search_target(
        self,
        target: str,
        queries: list[str],
        *,
        context_text: str,
        matched_rules: list[dict[str, Any]],
        max_items: int,
    ) -> list[dict[str, Any]]:
        collected: list[LawReference] = []
        errors: list[str] = []

        for q in queries:
            if len(collected) >= max_items:
                break
            try:
                res = self._cached_search(target=target, query=q, page=1, display=max_items, fmt="JSON")
            except Exception as exc:
                errors.append(str(exc))
                continue
            refs = _extract_references_from_json(
                source_query=q,
                target=target,
                base_url=self._cfg.base_url,
                json_obj=res,
            )
            collected.extend(refs[:max_items])

        uniq: dict[str, LawReference] = {}
        for r in collected:
            key = f"{r.target}:{r.drf_detail_url or ''}:{r.title}"
            if key not in uniq:
                uniq[key] = r

        reranked = _rerank_and_filter_references(
            references=list(uniq.values()),
            context_text=str(context_text or ""),
            matched_rules=matched_rules,
            max_items=max_items,
        )

        return [
            {
                "source_query": r.source,
                "target": r.target,
                "title": r.title,
                "snippet": r.snippet,
                "identifiers": r.identifiers,
                "drf_detail_url": r.drf_detail_url,
            }
            for r in reranked[:max_items]
        ] + ([] if not errors else [{"error": "; ".join(errors)}])

    def _cached_search(self, *, target: str, query: str, page: int, display: int, fmt: str) -> dict[str, Any]:
        key = self._cache.make_key(
            "law_search",
            {
                "base_url": self._cfg.base_url,
                "target": target,
                "query": query,
                "page": page,
                "display": display,
                "fmt": fmt,
            },
        )
        hit = self._cache.get(key)
        if isinstance(hit, dict):
            return hit
        try:
            resp = self._client.search(target=target, params={"query": query, "page": page, "display": display}, fmt=fmt)
            obj = resp.json_obj if isinstance(resp.json_obj, dict) else {"raw_text": resp.raw_text}
        except LawApiError as exc:
            raise RuntimeError(exc.message) from exc
        self._cache.set(key, obj, ttl_sec=60 * 60 * 6)
        return obj


def _derive_topics(*, entity: str, contract_type: str, text: str, matched_rules: list[dict[str, Any]]) -> list[str]:
    t = (contract_type or "").strip()
    out: list[str] = []
    out.extend(get_priority_topics_with_context(entity=entity, contract_type=contract_type, text=text))

    if "대리점" in t or "유통" in t or "위탁" in t:
        out.extend(["대리점법", "공정거래"])
    if "하도급" in t or "도급" in t or "공사" in t:
        out.extend(["하도급법", "공정거래"])
    if "개인정보" in t or "처리위탁" in t:
        out.append("개인정보보호법")
    if "광고" in t or "마케팅" in t or "협찬" in t:
        out.extend(["표시광고", "소비자보호"])
    if "바로스" in t or "물류" in t or "설치" in t:
        out.extend(["산업안전보건법", "중대재해처벌법"])

    txt = text or ""
    if any(k in txt for k in ("개인정보", "처리위탁", "주민등록", "privacy", "DPA", "dpa")):
        out.append("개인정보보호법")
    if any(k in txt for k in ("대리점", "위탁판매", "판매장려금", "판촉", "리베이트")):
        out.append("대리점법")
    if any(k in txt for k in ("하도급", "기술자료", "단가", "재하도급", "원사업자", "수급사업자")):
        out.extend(["하도급법", "기술자료"])
    if any(k in txt for k in ("안전", "산업안전", "중대재해", "현장", "작업", "공사")):
        out.extend(["산업안전보건법", "중대재해처벌법"])
    if any(k in txt for k in ("표시광고", "과장", "허위", "광고", "소비자", "보증")):
        out.extend(["표시광고", "소비자보호"])

    for r in matched_rules:
        rid = str(r.get("rule_id") or "")
        if rid in ("RISK-006", "ACT-009"):
            out.extend(["대리점법", "판매장려금", "판촉비", "반품", "광고비"])
        if rid in ("RISK-005", "ACT-008", "RISK-004", "ACT-007"):
            out.extend(["하도급법", "단가", "감액", "기술자료"])
        if rid in ("RISK-003", "ACT-010"):
            out.extend(["산업안전보건법", "중대재해처벌법"])
        if rid in ("RISK-001", "RISK-002"):
            out.extend(["손해배상", "책임 제한", "면책"])

    if entity:
        out.append(str(entity))
    return out


def _tokenize(text: str) -> set[str]:
    s = (text or "").lower()
    s = re.sub(r"[^0-9a-z가-힣]+", " ", s)
    parts = [p.strip() for p in s.split() if p.strip()]
    stop = {"및", "또는", "등", "에", "의", "을", "를", "이", "가", "은", "는", "and", "or", "the", "a", "an", "to", "of"}
    return {p for p in parts if p not in stop and len(p) >= 2}


def _rule_terms(matched_rules: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for r in matched_rules:
        if not isinstance(r, dict):
            continue
        rid = r.get("rule_id")
        if isinstance(rid, str) and rid:
            out.add(rid.lower())
        mks = r.get("matched_keywords")
        if isinstance(mks, list):
            for x in mks:
                if isinstance(x, str) and x.strip():
                    out.add(x.strip().lower())
    return out


def _is_noise_title(title: str) -> bool:
    t = (title or "").strip()
    if not t:
        return True
    bad = ["입법예고", "조례안", "광고", "홍보", "채용", "공고", "보도자료", "안내"]
    return any(b in t for b in bad)


def _score_reference(ref: LawReference, *, context_terms: set[str]) -> int:
    title_terms = _tokenize(ref.title)
    snippet_terms = _tokenize(ref.snippet or "")
    overlap = context_terms.intersection(title_terms.union(snippet_terms))
    score = len(overlap)
    if ref.target == "law":
        score += 2
    if ref.target == "prec":
        score += 1
    return score


def _rerank_and_filter_references(
    *,
    references: list[LawReference],
    context_text: str,
    matched_rules: list[dict[str, Any]],
    max_items: int,
) -> list[LawReference]:
    ctx = context_text or ""
    context_terms = _tokenize(ctx).union(_rule_terms(matched_rules))
    scored: list[tuple[int, LawReference]] = []
    for r in references:
        if _is_noise_title(r.title):
            continue
        score = _score_reference(r, context_terms=context_terms)
        if score <= 1:
            continue
        scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[: max(1, int(max_items))]]


def _extract_references_from_json(
    *,
    source_query: str,
    target: str,
    base_url: str,
    json_obj: dict[str, Any],
) -> list[LawReference]:
    items = _find_list_of_dicts(json_obj)
    out: list[LawReference] = []
    for it in items:
        title = _pick_title(it) or f"{target} item"
        snippet = _pick_snippet(it)
        identifiers = _pick_identifiers(it)
        detail_url = _build_detail_url(base_url=base_url, target=target, identifiers=identifiers)
        out.append(
            LawReference(
                source=source_query,
                target=target,
                title=title,
                snippet=snippet,
                identifiers=identifiers,
                drf_detail_url=detail_url,
            )
        )
    return out


def _find_list_of_dicts(obj: Any) -> list[dict[str, Any]]:
    queue: list[Any] = [obj]
    visited = 0
    while queue and visited < 2000:
        cur = queue.pop(0)
        visited += 1
        if isinstance(cur, list) and cur and all(isinstance(x, dict) for x in cur):
            return [x for x in cur if isinstance(x, dict)]
        if isinstance(cur, dict):
            queue.extend(list(cur.values()))
        elif isinstance(cur, list):
            queue.extend(cur)
    return []


def _pick_title(item: dict[str, Any]) -> str | None:
    keys = [
        "법령명한글",
        "법령명",
        "현행법령명",
        "사건명",
        "판례명",
        "제목",
        "TITLE",
        "title",
        "name",
    ]
    for k in keys:
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    for k, v in item.items():
        if isinstance(v, str) and v.strip() and ("명" in k or "제목" in k or "title" in str(k).lower()):
            return v.strip()
    return None


def _pick_snippet(item: dict[str, Any]) -> str | None:
    keys = [
        "요지",
        "판시사항",
        "summary",
        "요약",
        "취지",
        "설명",
    ]
    for k in keys:
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            s = v.strip()
            return s[:240] + ("…" if len(s) > 240 else "")
    return None


def _pick_identifiers(item: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in ("ID", "MST", "LM", "LD", "JO", "efYd", "prncYd"):
        v = item.get(key)
        if isinstance(v, (str, int)) and str(v).strip():
            out[key] = str(v).strip()
    for k, v in item.items():
        lk = str(k).strip()
        if lk in out:
            continue
        if lk.upper() in out:
            continue
        if lk.upper() in ("ID", "MST") and isinstance(v, (str, int)) and str(v).strip():
            out[lk.upper()] = str(v).strip()
    return out


def _build_detail_url(*, base_url: str, target: str, identifiers: dict[str, str]) -> str | None:
    if not identifiers:
        return None
    q: dict[str, str] = {"target": target, "type": "HTML"}
    if "ID" in identifiers:
        q["ID"] = identifiers["ID"]
    if "MST" in identifiers:
        q["MST"] = identifiers["MST"]
    if "LM" in identifiers:
        q["LM"] = identifiers["LM"]
    if "LD" in identifiers:
        q["LD"] = identifiers["LD"]
    if "JO" in identifiers:
        q["JO"] = identifiers["JO"]
    if "efYd" in identifiers:
        q["efYd"] = identifiers["efYd"]
    if "prncYd" in identifiers:
        q["prncYd"] = identifiers["prncYd"]
    if "ID" not in q and "MST" not in q:
        return None
    return f"{base_url.rstrip('/')}/lawService.do?{urlencode(q)}"

