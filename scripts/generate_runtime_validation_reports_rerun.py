from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.ai.config import load_ai_config
from runtime.ai.safe import sanitize_error_message
from runtime.law.config import load_law_api_config
from runtime.law.drf_client import LawApiError, LawDrfClient
from runtime.law.search_service import _find_list_of_dicts


@dataclass(frozen=True)
class HttpJsonResult:
    ok: bool
    http_status: int | None
    elapsed_client_sec: float
    json_obj: dict[str, Any] | None
    error: str | None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _write_md(rel_path: str, text: str) -> None:
    p = _repo_root() / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _short(s: Any, n: int = 240) -> str:
    t = str(s or "")
    t = " ".join(t.split())
    return t if len(t) <= n else t[: n - 3] + "..."


def _http_json(method: str, url: str, *, body: dict[str, Any] | None = None, timeout_sec: float = 15.0) -> HttpJsonResult:
    data = None
    headers: dict[str, str] = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=float(timeout_sec)) as r:
            raw = r.read().decode("utf-8", errors="replace")
            dt = time.perf_counter() - t0
            try:
                obj = json.loads(raw) if raw else {}
            except Exception:
                obj = {"_raw_text": raw}
            return HttpJsonResult(
                ok=True,
                http_status=int(getattr(r, "status", 0) or 0) or None,
                elapsed_client_sec=dt,
                json_obj=obj if isinstance(obj, dict) else {"_raw": obj},
                error=None,
            )
    except Exception as exc:
        dt = time.perf_counter() - t0
        return HttpJsonResult(ok=False, http_status=None, elapsed_client_sec=dt, json_obj=None, error=str(exc))


def generate_102_env_validation() -> None:
    root = _repo_root()
    candidates = [".env", ".env.local", "docs/.env", "docs/.env.local"]
    env_files = {c: (root / c).exists() for c in candidates}

    before = {
        "OPENAI_API_KEY_present": bool((os.getenv("OPENAI_API_KEY") or "").strip()),
        "LAW_API_KEY_present": bool((os.getenv("LAW_API_KEY") or "").strip()),
        "LAW_API_ENABLED_value": (os.getenv("LAW_API_ENABLED") or "").strip() or None,
    }

    ai = load_ai_config()
    law = load_law_api_config()

    after = {
        "OPENAI_API_KEY_present": bool((os.getenv("OPENAI_API_KEY") or "").strip()),
        "LAW_API_KEY_present": bool((os.getenv("LAW_API_KEY") or "").strip()),
        "LAW_API_ENABLED_value": (os.getenv("LAW_API_ENABLED") or "").strip() or None,
    }

    lines = []
    lines.append("# 런타임 환경변수/닷env 로딩 재검증(102)")
    lines.append("")
    lines.append("## 원칙")
    lines.append("- 실제 키 값은 절대 출력하지 않고, 존재 여부만 true/false로 기록한다.")
    lines.append("")
    lines.append("## 1) .env 파일 존재 여부")
    for k, v in env_files.items():
        lines.append(f"- `{k}`: `{str(bool(v)).lower()}`")
    lines.append("")
    lines.append("## 2)~4) 프로세스 환경변수 존재 여부(로더 호출 전/후)")
    lines.append("- 로더 호출 전")
    lines.append(f"  - `OPENAI_API_KEY`: `{str(bool(before['OPENAI_API_KEY_present'])).lower()}`")
    lines.append(f"  - `LAW_API_KEY`: `{str(bool(before['LAW_API_KEY_present'])).lower()}`")
    lines.append(f"  - `LAW_API_ENABLED`: `{json.dumps(before['LAW_API_ENABLED_value'], ensure_ascii=False)}`")
    lines.append("- 로더 호출 후(.env 로딩 적용 포함)")
    lines.append(f"  - `OPENAI_API_KEY`: `{str(bool(after['OPENAI_API_KEY_present'])).lower()}`")
    lines.append(f"  - `LAW_API_KEY`: `{str(bool(after['LAW_API_KEY_present'])).lower()}`")
    lines.append(f"  - `LAW_API_ENABLED`: `{json.dumps(after['LAW_API_ENABLED_value'], ensure_ascii=False)}`")
    lines.append("")
    lines.append("## 5) config 로더 인식")
    lines.append(f"- `load_ai_config()` → provider=`{ai.provider}`, api_key_present=`{str(bool(ai.api_key)).lower()}`, model=`{ai.model}`")
    lines.append(
        f"- `load_law_api_config()` → enabled=`{str(bool(law.enabled)).lower()}`, api_key_present=`{str(bool(law.api_key)).lower()}`, base_url=`{law.base_url}`"
    )
    lines.append("")
    _write_md("docs/review_output/102_env_runtime_validation_rerun.md", "\n".join(lines) + "\n")


def generate_103_openai_health() -> dict[str, Any]:
    url = "http://127.0.0.1:8787/api/ai/health"
    res = _http_json("GET", url, timeout_sec=10.0)
    obj = res.json_obj or {}
    enabled = obj.get("enabled") if isinstance(obj, dict) else None
    provider = obj.get("provider") if isinstance(obj, dict) else None
    model = obj.get("model") if isinstance(obj, dict) else None
    elapsed = obj.get("elapsed_sec") if isinstance(obj, dict) else None
    ok = obj.get("ok") if isinstance(obj, dict) else None
    note = obj.get("note") if isinstance(obj, dict) else None
    err = obj.get("error") if isinstance(obj, dict) else None

    lines = []
    lines.append("# OpenAI health 런타임 재검증(103) (/api/ai/health)")
    lines.append("")
    lines.append("## 결과")
    lines.append(f"- 요청: `{url}`")
    lines.append(f"- HTTP: `{json.dumps(res.http_status)}`")
    lines.append(f"- 클라이언트 응답시간: `{round(res.elapsed_client_sec, 4)}` sec")
    lines.append(f"- enabled: `{json.dumps(enabled)}`")
    lines.append(f"- provider: `{json.dumps(provider, ensure_ascii=False)}`")
    lines.append(f"- model: `{json.dumps(model, ensure_ascii=False)}`")
    lines.append(f"- elapsed_sec(서버): `{json.dumps(elapsed)}`")
    lines.append(f"- ok(서버): `{json.dumps(ok)}`")
    if err:
        lines.append(f"- 실패 원인(서버): `{json.dumps(err, ensure_ascii=False)}`")
    if note:
        lines.append(f"- note: `{json.dumps(note, ensure_ascii=False)}`")
    if res.error and not err:
        lines.append(f"- 실패 원인(클라이언트): `{json.dumps(res.error, ensure_ascii=False)}`")
    lines.append("")
    _write_md("docs/review_output/103_openai_health_runtime_check_rerun.md", "\n".join(lines) + "\n")

    return {
        "enabled": enabled,
        "provider": provider,
        "model": model,
        "elapsed_client_sec": res.elapsed_client_sec,
        "elapsed_sec": elapsed,
        "ok": ok,
        "error": res.error or err,
    }


def generate_104_law_api_check() -> dict[str, Any]:
    cfg = load_law_api_config()
    out: dict[str, Any] = {
        "enabled": bool(cfg.enabled),
        "api_key_present": bool(cfg.api_key),
        "base_url": cfg.base_url,
        "timeout_sec": cfg.timeout_sec,
        "retry_count": cfg.retry_count,
        "sample_query": "대리점법",
    }
    client = LawDrfClient(
        api_key=str(cfg.api_key or ""),
        base_url=cfg.base_url,
        timeout_sec=min(float(cfg.timeout_sec), 5.0),
        retry_count=0,
    )

    def run(target: str, query: str) -> dict[str, Any]:
        t0 = time.perf_counter()
        try:
            resp = client.search(target=target, params={"query": query, "page": 1, "display": 3}, fmt="JSON")
            dt = time.perf_counter() - t0
            ok = isinstance(resp.json_obj, dict)
            items = _find_list_of_dicts(resp.json_obj) if ok else []
            return {"ok": True, "elapsed_client_sec": round(dt, 4), "parse_ok": ok, "item_count_guess": len(items)}
        except LawApiError as exc:
            dt = time.perf_counter() - t0
            return {
                "ok": False,
                "elapsed_client_sec": round(dt, 4),
                "http_status": exc.status_code,
                "error": sanitize_error_message(str(exc.message)),
            }
        except Exception as exc:
            dt = time.perf_counter() - t0
            return {"ok": False, "elapsed_client_sec": round(dt, 4), "error": sanitize_error_message(str(exc))}

    out["law_search"] = run("law", out["sample_query"])
    out["precedent_search"] = run("prec", out["sample_query"])

    lines = []
    lines.append("# 국가법령정보 Open API(DRF) 런타임 호출 재검증(104)")
    lines.append("")
    lines.append("## 런타임 설정 인식(값 미노출)")
    lines.append(f"- enabled: `{str(bool(out['enabled'])).lower()}`")
    lines.append(f"- api_key_present: `{str(bool(out['api_key_present'])).lower()}`")
    lines.append(f"- base_url: `{out['base_url']}`")
    lines.append("")
    lines.append("## 1) 법령 검색 (target=law)")
    lines.append(f"- {json.dumps(out['law_search'], ensure_ascii=False)}")
    lines.append("")
    lines.append("## 2) 판례 검색 (target=prec)")
    lines.append(f"- {json.dumps(out['precedent_search'], ensure_ascii=False)}")
    lines.append("")
    _write_md("docs/review_output/104_law_api_runtime_check_rerun.md", "\n".join(lines) + "\n")
    return out


def generate_105_review_analyze() -> list[dict[str, Any]]:
    url = "http://127.0.0.1:8787/api/review/analyze"
    cases = [
        {
            "case_id": "case-1",
            "title": "퍼시스 + 대리점/유통 관련 텍스트",
            "input": {
                "entity": "퍼시스",
                "contract_type": "대리점/위탁/유통",
                "text": "대리점 계약입니다. 판촉비/광고비/반품 비용을 대리점이 부담합니다. 판매장려금 조건이 있습니다.",
                "persist": False,
            },
        },
        {
            "case_id": "case-2",
            "title": "퍼시스 + 하도급/기술자료 관련 텍스트",
            "input": {
                "entity": "퍼시스",
                "contract_type": "공사/도급/하도급",
                "text": "하도급 거래로서 단가 인하(감액) 및 원가자료/기술자료 제출을 요구합니다. 재하도급 제한 조항이 있습니다.",
                "persist": False,
            },
        },
        {
            "case_id": "case-3",
            "title": "바로스 + 안전/물류센터 관련 텍스트",
            "input": {
                "entity": "바로스",
                "contract_type": "바로스(물류/설치)",
                "text": "물류센터 현장 작업이 포함됩니다. 안전관리 책임, 산업안전보건, 중대재해 관련 조항이 있습니다.",
                "persist": False,
            },
        },
    ]

    out = []
    for c in cases:
        res = _http_json("POST", url, body=c["input"], timeout_sec=10.0)
        item: dict[str, Any] = {
            "case_id": c["case_id"],
            "title": c["title"],
            "http": {
                "ok": res.ok,
                "http_status": res.http_status,
                "elapsed_client_sec": round(res.elapsed_client_sec, 4),
                "error": res.error,
            },
        }
        if res.ok and isinstance(res.json_obj, dict):
            obj = res.json_obj
            summary = obj.get("summary") if isinstance(obj.get("summary"), dict) else None
            matched_rules = obj.get("matched_rules") if isinstance(obj.get("matched_rules"), list) else []
            matched_ids = [r.get("rule_id") for r in matched_rules if isinstance(r, dict) and isinstance(r.get("rule_id"), str)]
            law_search = obj.get("law_search") if isinstance(obj.get("law_search"), dict) else None

            def count_titles(xs: Any) -> int:
                if not isinstance(xs, list):
                    return 0
                return len([x for x in xs if isinstance(x, dict) and isinstance(x.get("title"), str)])

            counts = None
            if law_search:
                results = law_search.get("results") if isinstance(law_search.get("results"), dict) else {}
                counts = {
                    "laws": count_titles(results.get("laws")),
                    "precedents": count_titles(results.get("precedents")),
                    "interpretations": count_titles(results.get("interpretations")),
                    "admin_rules": count_titles(results.get("admin_rules")),
                    "local_ordinances": count_titles(results.get("local_ordinances")),
                }

            item["analysis"] = {
                "summary": summary,
                "matched_rule_ids": matched_ids,
                "law_search_present": bool(law_search is not None),
                "law_search_enabled": (law_search.get("enabled") if law_search else None),
                "law_counts": counts,
            }
        out.append(item)

    lines = []
    lines.append("# /api/review/analyze + law_search 재검증(105)")
    lines.append("")
    for c in out:
        lines.append(f"## {c['case_id']}: {c['title']}")
        http = c["http"]
        lines.append(f"- http ok=`{str(bool(http['ok'])).lower()}` status=`{json.dumps(http.get('http_status'))}` elapsed=`{json.dumps(http.get('elapsed_client_sec'))}`")
        if http.get("error"):
            lines.append(f"- error: `{json.dumps(http.get('error'), ensure_ascii=False)}`")
        ana = c.get("analysis")
        if isinstance(ana, dict):
            lines.append(f"- matched_rule_ids: `{json.dumps(ana.get('matched_rule_ids'), ensure_ascii=False)}`")
            lines.append(f"- law_search: present=`{str(bool(ana.get('law_search_present'))).lower()}`, enabled=`{json.dumps(ana.get('law_search_enabled'))}`")
            lines.append(f"- law_counts: `{json.dumps(ana.get('law_counts'), ensure_ascii=False)}`")
        lines.append("")
    _write_md("docs/review_output/105_review_analyze_lawsearch_validation_rerun.md", "\n".join(lines) + "\n")
    return out


def generate_106_questions_generate() -> list[dict[str, Any]]:
    url = "http://127.0.0.1:8787/api/questions/generate"
    cases = [
        ("case-1", "대리점성 텍스트", {"entity": "퍼시스", "contract_type": "대리점/위탁/유통", "text": "대리점 계약이며 판촉비/광고비/반품비를 대리점이 부담합니다."}),
        ("case-2", "하도급성 텍스트", {"entity": "퍼시스", "contract_type": "공사/도급/하도급", "text": "하도급 거래로 단가 인하 및 재작업 비용 부담이 있습니다."}),
        ("case-3", "개인정보 처리 위탁 텍스트", {"entity": "퍼시스", "contract_type": "개인정보/처리위탁", "text": "개인정보 처리위탁(DPA) 및 재위탁, 보관기간, 파기 조항이 필요합니다."}),
        ("case-4", "모델계약/광고 문구", {"entity": "일룸", "contract_type": "광고/마케팅/협찬", "text": "광고 캠페인 및 모델(초상권) 사용 범위가 포함됩니다."}),
        ("case-5", "중대재해/현장작업 문구", {"entity": "바로스", "contract_type": "바로스(물류/설치)", "text": "물류센터 현장 작업, 안전관리, 중대재해 대응이 포함됩니다."}),
    ]

    out = []
    for cid, title, payload in cases:
        res = _http_json("POST", url, body=payload, timeout_sec=10.0)
        item: dict[str, Any] = {
            "case_id": cid,
            "title": title,
            "http": {"ok": res.ok, "http_status": res.http_status, "elapsed_client_sec": round(res.elapsed_client_sec, 4), "error": res.error},
        }
        if res.ok and isinstance(res.json_obj, dict):
            obj = res.json_obj
            qs = obj.get("questions") if isinstance(obj.get("questions"), list) else []
            q_ids = [q.get("question_id") for q in qs if isinstance(q, dict) and isinstance(q.get("question_id"), str)]
            law_search = obj.get("law_search") if isinstance(obj.get("law_search"), dict) else None
            law_topics = law_search.get("queries") if isinstance(law_search, dict) else None
            item["analysis"] = {
                "count": obj.get("count"),
                "has_q_law": any(qid.startswith("Q-LAW-") for qid in q_ids),
                "law_topics_present": isinstance(law_topics, list),
                "question_ids": q_ids,
            }
        out.append(item)

    lines = []
    lines.append("# /api/questions/generate 재검증(106)")
    lines.append("")
    lines.append("## 구조")
    lines.append("- API는 `questions: []` 배열을 반환하므로 UI에서 1개씩 순차 표시가 가능하다.")
    lines.append("")
    for c in out:
        http = c["http"]
        lines.append(f"## {c['case_id']}: {c['title']}")
        lines.append(f"- http ok=`{str(bool(http['ok'])).lower()}` status=`{json.dumps(http.get('http_status'))}` elapsed=`{json.dumps(http.get('elapsed_client_sec'))}`")
        if http.get("error"):
            lines.append(f"- error: `{json.dumps(http.get('error'), ensure_ascii=False)}`")
        ana = c.get("analysis")
        if isinstance(ana, dict):
            lines.append(f"- count: `{json.dumps(ana.get('count'))}` / has_q_law: `{str(bool(ana.get('has_q_law'))).lower()}` / law_topics_present: `{str(bool(ana.get('law_topics_present'))).lower()}`")
            lines.append(f"- question_ids: `{json.dumps(ana.get('question_ids'), ensure_ascii=False)}`")
        lines.append("")
    _write_md("docs/review_output/106_question_engine_law_validation_rerun.md", "\n".join(lines) + "\n")
    return out


def generate_107_revision_suggest_text() -> dict[str, Any]:
    url = "http://127.0.0.1:8787/api/revision/suggest_text"
    payload = {
        "entity": "퍼시스",
        "contract_type": "대리점/위탁/유통",
        "text": "제1조(비용 부담) 대리점은 판촉비, 광고비 및 반품 비용을 전적으로 부담한다.\n제2조(기타) 본 계약은 당사와 대리점 간 대리점 거래를 규율한다.",
        "filename": None,
        "answers": None,
    }
    res = _http_json("POST", url, body=payload, timeout_sec=10.0)
    out: dict[str, Any] = {
        "http": {"ok": res.ok, "http_status": res.http_status, "elapsed_client_sec": round(res.elapsed_client_sec, 4), "error": res.error},
    }
    if res.ok and isinstance(res.json_obj, dict):
        obj = res.json_obj
        rev = obj.get("revision") if isinstance(obj.get("revision"), dict) else {}
        items = rev.get("items") if isinstance(rev.get("items"), list) else []
        first = items[0] if items and isinstance(items[0], dict) else None
        out["analysis"] = {
            "law_search_present": isinstance(obj.get("law_search"), dict),
            "law_search_enabled": (obj.get("law_search") or {}).get("enabled") if isinstance(obj.get("law_search"), dict) else None,
            "ai_present": isinstance(obj.get("ai"), dict),
            "first_item": None,
        }
        if isinstance(first, dict):
            detected = first.get("detected_issues") if isinstance(first.get("detected_issues"), list) else []
            applied = first.get("applied_rules") if isinstance(first.get("applied_rules"), list) else []
            out["analysis"]["first_item"] = {
                "original_clause": _short(first.get("original_clause"), 220),
                "detected_issue_titles": [d.get("issue_title") for d in detected if isinstance(d, dict) and isinstance(d.get("issue_title"), str)][:3],
                "applied_rule_ids": [a.get("rule_id") for a in applied if isinstance(a, dict) and isinstance(a.get("rule_id"), str)][:5],
                "fallback_text_present": bool(first.get("fallback_text")),
                "approval_required": first.get("approval_required"),
            }

    lines = []
    lines.append("# /api/revision/suggest_text 재검증(107)")
    lines.append("")
    http = out["http"]
    lines.append(f"- ok: `{str(bool(http['ok'])).lower()}` / http_status: `{json.dumps(http.get('http_status'))}` / elapsed_client_sec: `{json.dumps(http.get('elapsed_client_sec'))}`")
    if http.get("error"):
        lines.append(f"- error: `{json.dumps(http.get('error'), ensure_ascii=False)}`")
    ana = out.get("analysis")
    if isinstance(ana, dict):
        lines.append(f"- law_search_present: `{str(bool(ana.get('law_search_present'))).lower()}` / enabled: `{json.dumps(ana.get('law_search_enabled'))}`")
        lines.append(f"- ai_present: `{str(bool(ana.get('ai_present'))).lower()}`")
        first = ana.get("first_item")
        if isinstance(first, dict):
            lines.append(f"- first_item.applied_rule_ids: `{json.dumps(first.get('applied_rule_ids'), ensure_ascii=False)}`")
            lines.append(f"- first_item.fallback_text_present: `{str(bool(first.get('fallback_text_present'))).lower()}`")
            lines.append(f"- first_item.approval_required: `{json.dumps(first.get('approval_required'))}`")
    lines.append("")
    _write_md("docs/review_output/107_revision_law_grounding_validation_rerun.md", "\n".join(lines) + "\n")
    return out


def main() -> None:
    generate_102_env_validation()
    generate_103_openai_health()
    generate_104_law_api_check()
    generate_105_review_analyze()
    generate_106_questions_generate()
    generate_107_revision_suggest_text()
    print("generated: 102~107")


if __name__ == "__main__":
    main()

