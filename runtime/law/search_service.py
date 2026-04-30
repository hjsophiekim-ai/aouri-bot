from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
import time

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
    reason_code: str | None = None
    relevance_score: int | None = None


class LawSearchService:
    def __init__(self, *, cfg: LawApiConfig, cache: JsonFileCache) -> None:
        self._cfg = cfg
        self._cache = cache
        self._client = LawDrfClient(
            api_key=str(cfg.api_key or ""),
            base_url=cfg.base_url,
            timeout_sec=min(float(cfg.timeout_sec), 6.0),
            retry_count=max(int(cfg.retry_count), 0),
        )

    def search_for_review(
        self,
        *,
        entity: str,
        contract_type: str,
        text: str,
        matched_rules: list[dict[str, Any]] | None,
        scope: str = "contract",
        max_per_type: int = 3,
        time_budget_sec: float = 3.5,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self._cfg.enabled or not self._cfg.api_key:
            return {
                "enabled": False,
                "note": "LAW_API_ENABLED=false 또는 LAW_API_KEY 미설정",
                "queries": [],
                "results": {"laws": [], "precedents": [], "interpretations": [], "admin_rules": [], "local_ordinances": []},
                "errors": [],
            }

        if scope not in ("contract", "clause"):
            scope = "contract"
        qobjs = _derive_queries(
            entity=entity,
            contract_type=contract_type,
            text=text,
            matched_rules=matched_rules or [],
            scope=scope,
            context=context,
        )
        queries = [q["query"] for q in qobjs if isinstance(q.get("query"), str) and q["query"].strip()]
        profile = _infer_contract_profile(contract_type=str(contract_type or ""), text=str(text or ""))
        query_limit = 4 if scope == "contract" else 4
        if scope == "contract" and profile == "app_dev":
            query_limit = 4
        queries = list(dict.fromkeys(queries))[:query_limit]

        max_items = min(int(max_per_type), 3)
        start_ts = time.time()
        out = {"enabled": True, "queries": queries, "query_reasons": qobjs[:10], "results": {}, "errors": []}
        context_text = str(text or "")
        out["results"]["laws"] = self._search_target(
            "law",
            queries,
            context_text=context_text,
            matched_rules=matched_rules or [],
            max_items=max_items,
            query_reasons=qobjs,
            start_ts=start_ts,
            time_budget_sec=float(time_budget_sec),
            profile=profile,
        )
        out["results"]["precedents"] = self._search_target(
            "prec",
            queries,
            context_text=context_text,
            matched_rules=matched_rules or [],
            max_items=max_items,
            query_reasons=qobjs,
            start_ts=start_ts,
            time_budget_sec=float(time_budget_sec),
            profile=profile,
        )
        out["results"]["interpretations"] = self._search_target(
            "expc",
            queries,
            context_text=context_text,
            matched_rules=matched_rules or [],
            max_items=max_items,
            query_reasons=qobjs,
            start_ts=start_ts,
            time_budget_sec=float(time_budget_sec),
            profile=profile,
        )
        out["results"]["admin_rules"] = []
        out["results"]["local_ordinances"] = []

        if (
            scope == "clause"
            and isinstance(out.get("results"), dict)
            and all(isinstance(out["results"].get(k), list) and len(out["results"].get(k) or []) == 0 for k in ("laws", "precedents", "interpretations"))
        ):
            fb = _fallback_clause_queries(profile=profile, text=context_text, matched_rules=matched_rules or [])
            fb_q = [x["query"] for x in fb if isinstance(x.get("query"), str) and x["query"].strip()]
            fb_q = list(dict.fromkeys(fb_q))[:4]
            if fb_q:
                out["queries"] = list(dict.fromkeys(list(out.get("queries") or []) + fb_q))[:10]
                out["query_reasons"] = list(out.get("query_reasons") or []) + fb[:6]
                out["results"]["laws"] = self._search_target(
                    "law",
                    fb_q,
                    context_text=context_text,
                    matched_rules=matched_rules or [],
                    max_items=max_items,
                    query_reasons=fb,
                    start_ts=start_ts,
                    time_budget_sec=float(time_budget_sec),
                )
                out["results"]["precedents"] = self._search_target(
                    "prec",
                    fb_q,
                    context_text=context_text,
                    matched_rules=matched_rules or [],
                    max_items=max_items,
                    query_reasons=fb,
                    start_ts=start_ts,
                    time_budget_sec=float(time_budget_sec),
                )
                out["results"]["interpretations"] = self._search_target(
                    "expc",
                    fb_q,
                    context_text=context_text,
                    matched_rules=matched_rules or [],
                    max_items=max_items,
                    query_reasons=fb,
                    start_ts=start_ts,
                    time_budget_sec=float(time_budget_sec),
                )
        if (
            scope == "contract"
            and isinstance(out.get("results"), dict)
            and all(isinstance(out["results"].get(k), list) and len(out["results"].get(k) or []) == 0 for k in ("laws", "precedents", "interpretations"))
        ):
            fb = _fallback_contract_queries(profile=profile, text=context_text, matched_rules=matched_rules or [])
            fb_q = [x["query"] for x in fb if isinstance(x.get("query"), str) and x["query"].strip()]
            fb_q = list(dict.fromkeys(fb_q))[:4]
            if fb_q:
                out["queries"] = list(dict.fromkeys(list(out.get("queries") or []) + fb_q))[:10]
                out["query_reasons"] = list(out.get("query_reasons") or []) + fb[:6]
                out["results"]["laws"] = self._search_target(
                    "law",
                    fb_q,
                    context_text=context_text,
                    matched_rules=matched_rules or [],
                    max_items=max_items,
                    query_reasons=fb,
                    start_ts=start_ts,
                    time_budget_sec=float(time_budget_sec),
                    profile=profile,
                )
                out["results"]["precedents"] = self._search_target(
                    "prec",
                    fb_q,
                    context_text=context_text,
                    matched_rules=matched_rules or [],
                    max_items=max_items,
                    query_reasons=fb,
                    start_ts=start_ts,
                    time_budget_sec=float(time_budget_sec),
                    profile=profile,
                )
                out["results"]["interpretations"] = self._search_target(
                    "expc",
                    fb_q,
                    context_text=context_text,
                    matched_rules=matched_rules or [],
                    max_items=max_items,
                    query_reasons=fb,
                    start_ts=start_ts,
                    time_budget_sec=float(time_budget_sec),
                    profile=profile,
                )
        return out

    def _search_target(
        self,
        target: str,
        queries: list[str],
        *,
        context_text: str,
        matched_rules: list[dict[str, Any]],
        max_items: int,
        query_reasons: list[dict[str, str]],
        start_ts: float,
        time_budget_sec: float,
        profile: str,
    ) -> list[dict[str, Any]]:
        collected: list[LawReference] = []
        errors: list[str] = []

        display = min(20, max(10, int(max_items) * 4))
        for q in queries:
            if (time.time() - start_ts) > float(time_budget_sec):
                break
            if len(collected) >= max_items:
                break
            try:
                q_eff = _normalize_law_title_query(q) if target == "law" else q
                if not isinstance(q_eff, str) or not q_eff.strip():
                    q_eff = q
                res = self._cached_search(target=target, query=q_eff, page=1, display=display, fmt="JSON")
            except Exception as exc:
                errors.append(str(exc))
                continue
            reason_code = _pick_query_reason_code(q, qobjs=query_reasons)
            refs = _extract_references_from_json(
                source_query=q,
                target=target,
                base_url=self._cfg.base_url,
                json_obj=res,
                reason_code=reason_code,
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
            profile=profile,
        )

        return [
            {
                "source_query": r.source,
                "target": r.target,
                "title": r.title,
                "snippet": r.snippet,
                "identifiers": r.identifiers,
                "drf_detail_url": r.drf_detail_url,
                "reason_code": r.reason_code,
                "relevance_score": r.relevance_score,
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


def _derive_queries(
    *,
    entity: str,
    contract_type: str,
    text: str,
    matched_rules: list[dict[str, Any]],
    scope: str,
    context: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    ct = (contract_type or "").strip()
    txt = (text or "")
    out: list[dict[str, str]] = []

    profile = _infer_contract_profile(contract_type=ct, text=txt)
    if scope == "clause":
        out.extend(_derive_clause_queries(profile=profile, text=txt, matched_rules=matched_rules, context=context))
    if scope == "contract" and profile == "purchase_installation":
        out.extend(
            [
                {"query": "민법 매매 하자담보 손해배상", "reason_code": "contract_profile:purchase_installation"},
                {"query": "민법 도급 하자담보 지체 손해배상", "reason_code": "contract_profile:purchase_installation"},
                {"query": "상법 상사매매 검사 통지", "reason_code": "contract_profile:purchase_installation"},
                {"query": "산업안전보건법 설치 작업 안전관리", "reason_code": "contract_profile:purchase_installation"},
                {"query": "중대재해처벌법 안전보건 확보의무", "reason_code": "contract_profile:purchase_installation"},
                {"query": "제조물책임법 품질보증 하자보수", "reason_code": "contract_profile:purchase_installation"},
            ]
        )
    elif scope == "contract" and profile == "app_dev":
        out.extend(
            [
                {"query": "민법 도급 채무불이행 손해배상", "reason_code": "contract_profile:app_dev"},
                {"query": "저작권법 프로그램 저작권 양도", "reason_code": "contract_profile:app_dev"},
                {"query": "부정경쟁방지법 영업비밀 소스코드", "reason_code": "contract_profile:app_dev"},
                {"query": "개인정보보호법 개인정보 유출 손해배상", "reason_code": "contract_profile:app_dev"},
            ]
        )
        if any(k in txt for k in ("이용자", "회원", "결제", "통신판매", "서비스 제공")):
            out.append({"query": "전자상거래법 통신판매 소비자", "reason_code": "contract_profile:app_dev"})
    elif scope == "contract":
        for t in get_priority_topics_with_context(entity=entity, contract_type=contract_type, text=text):
            out.append({"query": t, "reason_code": "entity_priority"})

    if profile != "purchase_installation":
        if "대리점" in ct or "유통" in ct or "위탁" in ct:
            out.extend([{"query": "대리점법", "reason_code": "contract_type:dealer"}, {"query": "공정거래", "reason_code": "contract_type:dealer"}])
    if "하도급" in ct or "도급" in ct or "공사" in ct:
        out.extend([{"query": "하도급법", "reason_code": "contract_type:subcontract"}, {"query": "공정거래", "reason_code": "contract_type:subcontract"}])
    if "개인정보" in ct or "처리위탁" in ct:
        out.append({"query": "개인정보보호법", "reason_code": "contract_type:privacy"})
    if profile != "app_dev" and ("광고" in ct or "마케팅" in ct or "협찬" in ct):
        out.extend([{"query": "표시광고", "reason_code": "contract_type:ads"}, {"query": "소비자보호", "reason_code": "contract_type:ads"}])
    if "바로스" in ct or "물류" in ct or "설치" in ct:
        out.extend([{"query": "산업안전보건법", "reason_code": "contract_type:safety"}, {"query": "중대재해처벌법", "reason_code": "contract_type:safety"}])

    if any(k in txt for k in ("개인정보", "처리위탁", "주민등록", "privacy", "DPA", "dpa")):
        out.append({"query": "개인정보보호법", "reason_code": "text:privacy"})
    if profile != "purchase_installation":
        if any(k in txt for k in ("대리점", "위탁판매", "판매장려금", "판촉", "리베이트")):
            out.append({"query": "대리점법", "reason_code": "text:dealer"})
    if any(k in txt for k in ("하도급", "기술자료", "단가", "재하도급", "원사업자", "수급사업자")):
        out.extend([{"query": "하도급법", "reason_code": "text:subcontract"}, {"query": "기술자료", "reason_code": "text:tech"}])
    if any(k in txt for k in ("안전", "산업안전", "중대재해", "현장", "작업", "공사")):
        out.extend([{"query": "산업안전보건법", "reason_code": "text:safety"}, {"query": "중대재해처벌법", "reason_code": "text:safety"}])
    if profile != "app_dev" and any(k in txt for k in ("표시광고", "과장", "허위", "광고", "소비자", "보증")):
        out.extend([{"query": "표시광고", "reason_code": "text:ads"}, {"query": "소비자보호", "reason_code": "text:ads"}])

    for r in matched_rules:
        rid = str(r.get("rule_id") or "")
        if rid in ("RISK-006", "ACT-009"):
            if profile != "purchase_installation":
                out.extend(
                    [
                        {"query": "대리점법", "reason_code": "rule:RISK-006"},
                        {"query": "판매장려금", "reason_code": "rule:RISK-006"},
                        {"query": "판촉비", "reason_code": "rule:RISK-006"},
                        {"query": "반품", "reason_code": "rule:RISK-006"},
                        {"query": "광고비", "reason_code": "rule:RISK-006"},
                    ]
                )
        if rid in ("RISK-005", "ACT-008", "RISK-004", "ACT-007"):
            out.extend(
                [
                    {"query": "하도급법", "reason_code": f"rule:{rid}"},
                    {"query": "단가 감액", "reason_code": f"rule:{rid}"},
                    {"query": "기술자료", "reason_code": f"rule:{rid}"},
                ]
            )
        if rid in ("RISK-003", "ACT-010"):
            out.extend([{"query": "산업안전보건법", "reason_code": f"rule:{rid}"}, {"query": "중대재해처벌법", "reason_code": f"rule:{rid}"}])
        if rid in ("RISK-001", "RISK-002"):
            out.extend(
                [
                    {"query": "민법 손해배상", "reason_code": f"rule:{rid}"},
                    {"query": "책임 제한", "reason_code": f"rule:{rid}"},
                    {"query": "면책", "reason_code": f"rule:{rid}"},
                ]
            )
        if rid.startswith("APP-"):
            if rid in ("APP-001", "APP-008"):
                out.extend(
                    [
                        {"query": "저작권법 프로그램 저작권", "reason_code": f"rule:{rid}"},
                        {"query": "제3자 권리침해 보증 손해배상", "reason_code": f"rule:{rid}"},
                    ]
                )
            if rid == "APP-002":
                out.extend([{"query": "저작권법 라이선스 위반 손해배상", "reason_code": f"rule:{rid}"}, {"query": "오픈소스 라이선스 의무", "reason_code": f"rule:{rid}"}])
            if rid in ("APP-003", "APP-004", "APP-005", "APP-006", "APP-011", "APP-012"):
                out.extend([{"query": "민법 도급 하자보수 손해배상", "reason_code": f"rule:{rid}"}, {"query": "민법 채무불이행 지체 손해배상", "reason_code": f"rule:{rid}"}])
            if rid in ("APP-007", "APP-010"):
                out.extend(
                    [
                        {"query": "개인정보보호법 개인정보 유출 통지", "reason_code": f"rule:{rid}"},
                        {"query": "개인정보보호법 개인정보 파기 삭제", "reason_code": f"rule:{rid}"},
                        {"query": "정보통신망 침해사고", "reason_code": f"rule:{rid}"},
                    ]
                )
            if rid == "APP-009":
                out.extend([{"query": "민법 도급 재하도급 책임", "reason_code": f"rule:{rid}"}, {"query": "재위탁 사전 승인 책임", "reason_code": f"rule:{rid}"}])

    if scope == "contract" and entity and profile != "purchase_installation":
        out.append({"query": str(entity), "reason_code": "entity"})
    return out


def _derive_clause_queries(
    *, profile: str, text: str, matched_rules: list[dict[str, Any]], context: dict[str, Any] | None
) -> list[dict[str, str]]:
    t = text or ""
    out: list[dict[str, str]] = []
    posture = ""
    try:
        posture = str((context or {}).get("review_posture") or "")
    except Exception:
        posture = ""

    def has_any(kws: list[str]) -> bool:
        return any(k in t for k in kws)

    if profile == "app_dev":
        out.extend(
            [
                {"query": "민법 도급 채무불이행 손해배상", "reason_code": "clause_profile:app_dev"},
                {"query": "저작권법 프로그램 저작권 양도 이용허락", "reason_code": "clause_profile:app_dev"},
                {"query": "부정경쟁방지법 영업비밀 소스코드", "reason_code": "clause_profile:app_dev"},
                {"query": "개인정보보호법 처리위탁 재위탁 유출 손해배상", "reason_code": "clause_profile:app_dev"},
            ]
        )
    elif profile == "purchase_installation":
        out.extend(
            [
                {"query": "민법 매매 하자담보 손해배상", "reason_code": "clause_profile:purchase_installation"},
                {"query": "민법 도급 하자담보 지체 손해배상", "reason_code": "clause_profile:purchase_installation"},
                {"query": "상법 상사매매 검사 통지", "reason_code": "clause_profile:purchase_installation"},
                {"query": "산업안전보건법 설치 작업 안전관리", "reason_code": "clause_profile:purchase_installation"},
                {"query": "중대재해처벌법 안전보건 확보의무", "reason_code": "clause_profile:purchase_installation"},
                {"query": "제조물책임법 결함 손해배상", "reason_code": "clause_profile:purchase_installation"},
            ]
        )
    else:
        out.append({"query": "민법 계약 손해배상", "reason_code": "clause_profile:generic"})

    if has_any(["검수", "인수", "간주검수", "재검수", "테스트", "시운전"]):
        out.append({"query": "검수 간주검수 재검수 기준 기간", "reason_code": "clause_topic:acceptance"})
    if has_any(["지연", "지체", "지체상금", "납기", "마일스톤"]):
        out.append({"query": "지체상금 지연 손해배상 감액", "reason_code": "clause_topic:delay"})
    if has_any(["저작권", "지식재산", "산출물", "소스코드", "프로그램"]):
        out.append({"query": "저작권법 프로그램 저작권 양도 이용허락", "reason_code": "clause_topic:ip"})
    if has_any(["오픈소스", "라이선스", "GPL", "MIT", "Apache", "서드파티"]):
        out.append({"query": "오픈소스 라이선스 위반 소스 공개 의무", "reason_code": "clause_topic:oss"})
    if has_any(["개인정보", "처리위탁", "수탁", "국외이전", "파기", "삭제"]):
        out.append({"query": "개인정보보호법 처리위탁 재위탁 유출 통지", "reason_code": "clause_topic:privacy"})
    if has_any(["보안", "침해", "유출", "사고", "취약점", "암호화"]):
        out.append({"query": "정보통신망 침해사고 보안사고 통지", "reason_code": "clause_topic:security"})
    if has_any(["재위탁", "하도급", "외주", "협력업체"]):
        out.append({"query": "재위탁 사전 승인 연대책임", "reason_code": "clause_topic:subcontract"})
    if has_any(["해지", "종료", "인수인계", "전환", "데이터", "반환", "삭제"]):
        out.append({"query": "계약 해지 종료 인수인계 데이터 반환 삭제", "reason_code": "clause_topic:exit"})
    if has_any(["책임제한", "면책", "손해배상", "배상", "상한"]):
        out.append({"query": "책임제한 면책 손해배상 유효성", "reason_code": "clause_topic:liability"})

    if posture:
        out.append({"query": f"계약 당사자 보호 방향 {posture}", "reason_code": "clause_context:posture"})

    for r in matched_rules[:4]:
        rid = str(r.get("rule_id") or "").strip()
        if rid:
            out.append({"query": f"{rid} 관련 법령", "reason_code": "clause_rule_id"})

    return out


def _fallback_clause_queries(*, profile: str, text: str, matched_rules: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if profile == "app_dev":
        out.extend(
            [
                {"query": "민법 도급 손해배상", "reason_code": "fallback:app_dev"},
                {"query": "저작권법", "reason_code": "fallback:app_dev"},
                {"query": "부정경쟁방지법 영업비밀", "reason_code": "fallback:app_dev"},
                {"query": "개인정보보호법 처리위탁", "reason_code": "fallback:app_dev"},
            ]
        )
    elif profile == "purchase_installation":
        out.extend(
            [
                {"query": "민법 매매 하자담보", "reason_code": "fallback:purchase_installation"},
                {"query": "산업안전보건법", "reason_code": "fallback:purchase_installation"},
                {"query": "중대재해처벌법", "reason_code": "fallback:purchase_installation"},
            ]
        )
    else:
        out.append({"query": "민법 계약 손해배상", "reason_code": "fallback:generic"})

    if any(k in (text or "") for k in ("대리점", "유통", "위탁판매", "판매장려금", "판촉", "리베이트")):
        out.append({"query": "대리점법", "reason_code": "fallback:dealer"})
    if any(k in (text or "") for k in ("하도급", "재하도급", "수급사업자", "원사업자", "기술자료")):
        out.append({"query": "하도급법", "reason_code": "fallback:subcontract"})
    if matched_rules:
        out.append({"query": "계약서 책임 제한 면책 유효성", "reason_code": "fallback:rules"})
    return out


def _fallback_contract_queries(*, profile: str, text: str, matched_rules: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if profile == "app_dev":
        out.extend(
            [
                {"query": "저작권법", "reason_code": "fallback_contract:app_dev"},
                {"query": "개인정보보호법", "reason_code": "fallback_contract:app_dev"},
                {"query": "부정경쟁방지법", "reason_code": "fallback_contract:app_dev"},
                {"query": "민법", "reason_code": "fallback_contract:app_dev"},
            ]
        )
    elif profile == "purchase_installation":
        out.extend(
            [
                {"query": "민법", "reason_code": "fallback_contract:purchase_installation"},
                {"query": "상법", "reason_code": "fallback_contract:purchase_installation"},
                {"query": "산업안전보건법", "reason_code": "fallback_contract:purchase_installation"},
                {"query": "중대재해처벌법", "reason_code": "fallback_contract:purchase_installation"},
            ]
        )

    if not out:
        if any(k in (text or "") for k in ("대리점", "유통", "위탁판매", "판매장려금", "판촉", "리베이트")):
            out.append({"query": "대리점법", "reason_code": "fallback_contract:text_dealer"})
        if any(k in (text or "") for k in ("하도급", "재하도급", "수급사업자", "원사업자", "기술자료")):
            out.append({"query": "하도급법", "reason_code": "fallback_contract:text_subcontract"})
        if any(k in (text or "") for k in ("개인정보", "처리위탁", "주민등록", "privacy", "DPA", "dpa")):
            out.append({"query": "개인정보보호법", "reason_code": "fallback_contract:text_privacy"})
        if any(k in (text or "") for k in ("안전", "산업안전", "중대재해", "현장", "작업", "공사")):
            out.extend(
                [
                    {"query": "산업안전보건법", "reason_code": "fallback_contract:text_safety"},
                    {"query": "중대재해처벌법", "reason_code": "fallback_contract:text_safety"},
                ]
            )
    if not out:
        out.append({"query": "민법", "reason_code": "fallback_contract:generic"})
    if matched_rules:
        out.append({"query": "책임 제한 면책 손해배상", "reason_code": "fallback_contract:rules"})
    return out


def _infer_contract_profile(*, contract_type: str, text: str) -> str:
    ct = contract_type or ""
    t = text or ""
    low = (ct + "\n" + t).lower()

    def has_any(needles: list[str]) -> bool:
        return any(n.lower() in low for n in needles if n)

    def has_app_dev_strong() -> bool:
        return has_any(
            [
                "소스코드",
                "source code",
                "오픈소스",
                "open source",
                "sbom",
                "sow",
                "statement of work",
                "api 연동",
                "프로그램 개발",
                "소프트웨어 개발",
                "앱 개발",
                "저작권 양도",
            ]
        )

    if has_any(["운영대행", "위탁운영", "운영위탁", "공간운영", "매장운영", "라운지", "시설관리", "관리용역", "운영용역", "서비스위탁"]) and not has_app_dev_strong():
        return "operations"

    if has_any(["대리점", "유통", "위탁판매", "판매대행"]) or has_any(["판매장려금", "판촉", "리베이트", "대리점거래"]):
        return "dealer"

    if has_any(["앱개발", "소프트웨어개발", "si", "saas"]) or has_app_dev_strong():
        return "app_dev"

    if any(k in ct for k in ("물품공급/구매/매매", "장비공급", "구매")) and any(k in ct for k in ("설치", "시운전")):
        return "purchase_installation"
    if any(k in t for k in ("장비", "설치", "시운전", "기계", "물품", "제품")) and any(k in t for k in ("대금", "납품", "매매", "구매")):
        return "purchase_installation"
    return "generic"


def _pick_query_reason_code(query: str, *, qobjs: list[dict[str, str]] | None) -> str | None:
    if not qobjs:
        return None
    for q in qobjs:
        if q.get("query") == query:
            return q.get("reason_code")
    return None


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


_LAW_QUERY_ALIASES: dict[str, str] = {
    "대리점법": "대리점거래의 공정화에 관한 법률",
    "하도급법": "하도급거래 공정화에 관한 법률",
    "공정거래": "독점규제 및 공정거래에 관한 법률",
    "표시광고": "표시·광고의 공정화에 관한 법률",
    "소비자보호": "소비자기본법",
    "전자상거래법": "전자상거래 등에서의 소비자보호에 관한 법률",
    "부정경쟁방지법": "부정경쟁방지 및 영업비밀보호에 관한 법률",
}


def _normalize_law_title_query(query: str) -> str:
    q = (query or "").strip()
    if not q:
        return q
    if q in _LAW_QUERY_ALIASES:
        return _LAW_QUERY_ALIASES[q]
    for tok in re.split(r"\s+", q):
        t = (tok or "").strip()
        if not t:
            continue
        if t in _LAW_QUERY_ALIASES:
            return _LAW_QUERY_ALIASES[t]
        if t.endswith("법"):
            return t
        if t in ("민법", "상법", "형법"):
            return t
    for k in (
        "개인정보보호법",
        "저작권법",
        "산업안전보건법",
        "중대재해처벌법",
        "제조물책임법",
        "하도급법",
        "대리점법",
        "부정경쟁방지법",
        "전자상거래법",
        "민법",
        "상법",
    ):
        if k in q:
            return _LAW_QUERY_ALIASES.get(k, k)
    return _LAW_QUERY_ALIASES.get(q.split()[0], q.split()[0])


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


_BANNED_ALWAYS_TITLES = (
    "난민법",
    "난민법 시행령",
    "난민법 시행규칙",
)


def _allowed_law_keywords_by_profile(profile: str) -> tuple[str, ...]:
    if profile == "app_dev":
        return (
            "민법",
            "저작권법",
            "부정경쟁방지",
            "개인정보",
            "정보통신",
            "전자상거래",
        )
    if profile == "operations":
        return (
            "민법",
            "상법",
            "하도급거래 공정화",
            "대리점거래의 공정화",
            "독점규제 및 공정거래",
            "산업안전보건",
            "중대재해",
            "개인정보",
            "근로기준",
            "파견근로자",
        )
    if profile == "dealer":
        return (
            "대리점거래의 공정화",
            "독점규제 및 공정거래",
            "표시·광고의 공정화",
            "하도급거래 공정화",
            "민법",
            "상법",
            "개인정보",
        )
    if profile == "purchase_installation":
        return (
            "민법",
            "상법",
            "산업안전보건",
            "중대재해",
            "제조물책임",
            "개인정보",
        )
    return ("민법", "상법", "개인정보", "하도급거래 공정화")


def _is_banned_title(title: str) -> bool:
    t = (title or "").strip()
    if not t:
        return False
    return any(b in t for b in _BANNED_ALWAYS_TITLES)


def _is_allowed_law_title(title: str, *, profile: str) -> bool:
    t = (title or "").strip()
    if not t:
        return False
    allowed = _allowed_law_keywords_by_profile(profile)
    return any(k in t for k in allowed)


def _rerank_and_filter_references(
    *,
    references: list[LawReference],
    context_text: str,
    matched_rules: list[dict[str, Any]],
    max_items: int,
    profile: str,
) -> list[LawReference]:
    ctx = context_text or ""
    context_terms = _tokenize(ctx).union(_rule_terms(matched_rules))
    scored: list[tuple[int, LawReference]] = []
    for r in references:
        if _is_noise_title(r.title):
            continue
        if _is_banned_title(r.title):
            continue
        if r.target == "law" and not _is_allowed_law_title(r.title, profile=profile):
            continue
        title_terms = _tokenize(r.title)
        snippet_terms = _tokenize(r.snippet or "")
        overlap_cnt = len(context_terms.intersection(title_terms.union(snippet_terms)))
        score = _score_reference(r, context_terms=context_terms)
        if r.target in ("prec", "expc") and overlap_cnt < 2:
            continue
        rr = LawReference(
            source=r.source,
            target=r.target,
            title=r.title,
            snippet=r.snippet,
            identifiers=r.identifiers,
            drf_detail_url=r.drf_detail_url,
            reason_code=r.reason_code,
            relevance_score=score,
        )
        scored.append((score, rr))
    scored.sort(key=lambda x: x[0], reverse=True)
    picked = [r for _, r in scored[: max(1, int(max_items))]]
    if picked:
        return picked
    if profile and any(r.target == "law" for r in references):
        fb: list[tuple[int, LawReference]] = []
        for r in references:
            if r.target != "law":
                continue
            if _is_noise_title(r.title) or _is_banned_title(r.title):
                continue
            if not _is_allowed_law_title(r.title, profile=profile):
                continue
            score = _score_reference(r, context_terms=context_terms)
            fb.append((score, r))
        fb.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in fb[: max(1, int(max_items))]]
    return []


def _extract_references_from_json(
    *,
    source_query: str,
    target: str,
    base_url: str,
    json_obj: dict[str, Any],
    reason_code: str | None,
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
                reason_code=reason_code,
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

