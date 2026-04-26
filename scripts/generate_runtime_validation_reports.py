from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from multiprocessing import Process, Queue
from pathlib import Path
from typing import Any

from runtime.ai.config import load_ai_config
from runtime.ai.safe import sanitize_error_message
from runtime.law.config import load_law_api_config
from runtime.law.drf_client import LawApiError, LawDrfClient
from runtime.law.search_service import _find_list_of_dicts


@dataclass(frozen=True)
class HttpResult:
    ok: bool
    http_status: int | None
    elapsed_client_sec: float
    json_obj: dict[str, Any] | None
    error: str | None


def _http_worker(q: Queue, method: str, url: str, body_json: str | None, timeout_sec: float) -> None:
    data = None
    headers: dict[str, str] = {}
    if body_json is not None:
        data = body_json.encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as r:
            raw = r.read().decode("utf-8", errors="replace")
            try:
                obj = json.loads(raw) if raw else {}
            except Exception:
                obj = {"_raw_text": raw}
            q.put(
                {
                    "ok": True,
                    "http_status": int(getattr(r, "status", 0) or 0) or None,
                    "json_obj": obj if isinstance(obj, dict) else {"_raw": obj},
                    "error": None,
                }
            )
    except Exception as exc:
        q.put({"ok": False, "http_status": None, "json_obj": None, "error": str(exc)})


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _write_md(rel_path: str, text: str) -> None:
    p = _repo_root() / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _bool(v: Any) -> bool:
    return bool(v) and str(v).strip() != ""


def _short(s: Any, n: int = 240) -> str:
    t = str(s or "")
    t = " ".join(t.split())
    return t if len(t) <= n else t[: n - 3] + "..."


def _http_json(method: str, url: str, *, body: dict[str, Any] | None = None, timeout_sec: float = 30.0) -> HttpResult:
    q: Queue = Queue()
    body_json = json.dumps(body, ensure_ascii=False) if body is not None else None

    t0 = time.perf_counter()
    p = Process(target=_http_worker, args=(q, method, url, body_json, float(timeout_sec)))
    p.daemon = True
    p.start()
    p.join(timeout=timeout_sec + 2.0)
    dt = time.perf_counter() - t0
    if p.is_alive():
        try:
            p.terminate()
        except Exception:
            pass
        return HttpResult(ok=False, http_status=None, elapsed_client_sec=dt, json_obj=None, error="timeout")
    try:
        result = q.get_nowait()
    except Exception:
        result = {"ok": False, "http_status": None, "json_obj": None, "error": "no result"}
    return HttpResult(
        ok=bool(result.get("ok")),
        http_status=result.get("http_status"),
        elapsed_client_sec=dt,
        json_obj=result.get("json_obj") if isinstance(result.get("json_obj"), dict) else None,
        error=result.get("error"),
    )


def _env_runtime_validation() -> dict[str, Any]:
    root = _repo_root()
    candidates = [".env", ".env.local", "docs/.env", "docs/.env.local"]
    env_files = {c: (root / c).exists() for c in candidates}

    before = {
        "OPENAI_API_KEY": _bool(os.getenv("OPENAI_API_KEY")),
        "LAW_API_KEY": _bool(os.getenv("LAW_API_KEY")),
        "LAW_API_ENABLED": (os.getenv("LAW_API_ENABLED") or "").strip() or None,
    }

    ai = load_ai_config()
    law = load_law_api_config()

    after = {
        "OPENAI_API_KEY": _bool(os.getenv("OPENAI_API_KEY")),
        "LAW_API_KEY": _bool(os.getenv("LAW_API_KEY")),
        "LAW_API_ENABLED": (os.getenv("LAW_API_ENABLED") or "").strip() or None,
    }

    return {
        "env_files_exist": env_files,
        "env_before": before,
        "env_after_dotenv_load": after,
        "ai_config": {"provider": ai.provider, "api_key_present": _bool(ai.api_key), "model": ai.model},
        "law_config": {"enabled": bool(law.enabled), "api_key_present": _bool(law.api_key), "base_url": law.base_url},
    }


def _write_86(data: dict[str, Any]) -> None:
    env_files = data["env_files_exist"]
    before = data["env_before"]
    after = data["env_after_dotenv_load"]
    ai = data["ai_config"]
    law = data["law_config"]

    lines = []
    lines.append("# 런타임 환경변수/닷env 로딩 검증 (OPENAI_API_KEY, LAW_API_*)")
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
    lines.append(f"  - `OPENAI_API_KEY`: `{str(bool(before['OPENAI_API_KEY'])).lower()}`")
    lines.append(f"  - `LAW_API_KEY`: `{str(bool(before['LAW_API_KEY'])).lower()}`")
    lines.append(f"  - `LAW_API_ENABLED`: `{json.dumps(before['LAW_API_ENABLED'], ensure_ascii=False)}`")
    lines.append("- 로더 호출 후(.env 로딩 적용 포함)")
    lines.append(f"  - `OPENAI_API_KEY`: `{str(bool(after['OPENAI_API_KEY'])).lower()}`")
    lines.append(f"  - `LAW_API_KEY`: `{str(bool(after['LAW_API_KEY'])).lower()}`")
    lines.append(f"  - `LAW_API_ENABLED`: `{json.dumps(after['LAW_API_ENABLED'], ensure_ascii=False)}`")
    lines.append("")
    lines.append("## 5) config 로더가 두 키를 정상 인식하는지")
    lines.append(f"- `load_ai_config()` → provider=`{ai['provider']}`, api_key_present=`{str(bool(ai['api_key_present'])).lower()}`, model=`{ai['model']}`")
    lines.append(
        f"- `load_law_api_config()` → enabled=`{str(bool(law['enabled'])).lower()}`, api_key_present=`{str(bool(law['api_key_present'])).lower()}`, base_url=`{law['base_url']}`"
    )
    lines.append("")
    lines.append("## 판정")
    lines.append(f"- OpenAI: `{ai['provider']}` (키 미감지 시 mock)")
    lines.append(f"- 국가법령정보: enabled=`{str(bool(law['enabled'])).lower()}` / api_key_present=`{str(bool(law['api_key_present'])).lower()}`")
    lines.append("")
    _write_md("docs/review_output/86_env_runtime_validation.md", "\n".join(lines) + "\n")


def _write_87() -> dict[str, Any]:
    url = "http://127.0.0.1:8787/api/ai/health"
    res = _http_json("GET", url, timeout_sec=20.0)
    obj = res.json_obj or {}
    enabled = obj.get("enabled") if isinstance(obj, dict) else None
    provider = obj.get("provider") if isinstance(obj, dict) else None
    model = obj.get("model") if isinstance(obj, dict) else None
    elapsed = obj.get("elapsed_sec") if isinstance(obj, dict) else None
    ok = obj.get("ok") if isinstance(obj, dict) else None
    note = obj.get("note") if isinstance(obj, dict) else None
    err = obj.get("error") if isinstance(obj, dict) else None

    lines = []
    lines.append("# OpenAI health 런타임 체크 (/api/ai/health)")
    lines.append("")
    lines.append("## 확인 항목")
    lines.append("- enabled 값")
    lines.append("- mock인지 실제 provider인지")
    lines.append("- model 이름")
    lines.append("- 응답시간(서버 제공 elapsed_sec + 클라이언트 계측)")
    lines.append("- 실패 시 원인")
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
    if res.ok:
        if err:
            lines.append(f"- 실패 원인(서버): `{json.dumps(err, ensure_ascii=False)}`")
        elif note:
            lines.append(f"- note: `{json.dumps(note, ensure_ascii=False)}`")
    else:
        lines.append(f"- 실패 원인(클라이언트): `{json.dumps(res.error, ensure_ascii=False)}`")
    lines.append("")
    _write_md("docs/review_output/87_openai_health_runtime_check.md", "\n".join(lines) + "\n")

    return {
        "ok": res.ok,
        "enabled": enabled,
        "provider": provider,
        "model": model,
        "elapsed_client_sec": res.elapsed_client_sec,
        "elapsed_sec": elapsed,
        "error": res.error or err,
        "note": note,
    }


def _law_direct_search_check() -> dict[str, Any]:
    cfg = load_law_api_config()
    out: dict[str, Any] = {
        "LAW_API_ENABLED_expected_true": True,
        "LAW_API_ENABLED_effective": bool(cfg.enabled),
        "LAW_API_KEY_present": _bool(cfg.api_key),
        "LAW_API_BASE_URL": cfg.base_url,
        "timeout_sec": cfg.timeout_sec,
        "retry_count": cfg.retry_count,
    }
    client = LawDrfClient(
        api_key=str(cfg.api_key or ""),
        base_url=cfg.base_url,
        timeout_sec=cfg.timeout_sec,
        retry_count=cfg.retry_count,
    )

    def run(target: str, query: str) -> dict[str, Any]:
        t0 = time.perf_counter()
        try:
            resp = client.search(target=target, params={"query": query, "page": 1, "display": 3}, fmt="JSON")
            dt = time.perf_counter() - t0
            ok = isinstance(resp.json_obj, dict)
            items = _find_list_of_dicts(resp.json_obj) if ok else []
            return {
                "ok": True,
                "elapsed_client_sec": round(dt, 4),
                "parse_ok": ok,
                "item_count_guess": len(items),
            }
        except LawApiError as exc:
            dt = time.perf_counter() - t0
            msg = sanitize_error_message(str(exc.message))
            return {
                "ok": False,
                "elapsed_client_sec": round(dt, 4),
                "error": msg,
                "http_status": exc.status_code,
                "flags": {
                    "http_404_possible_base_url_issue": bool(exc.status_code == 404),
                    "ip_or_domain_restriction": any(x in msg for x in ("IP", "도메인", "등록")),
                    "auth_error": any(x in msg for x in ("인증", "OC", "키")),
                    "timeout_or_network": any(x in msg.lower() for x in ("timeout", "timed out", "연결", "connection")),
                },
            }
        except Exception as exc:
            dt = time.perf_counter() - t0
            return {"ok": False, "elapsed_client_sec": round(dt, 4), "error": sanitize_error_message(str(exc))}

    out["sample_query"] = "대리점법"
    out["law_search"] = run("law", out["sample_query"])
    out["precedent_search"] = run("prec", out["sample_query"])
    return out


def _write_88(data: dict[str, Any]) -> None:
    lines = []
    lines.append("# 국가법령정보 Open API(DRF) 런타임 호출 검증")
    lines.append("")
    lines.append("## 확인 항목")
    lines.append("- LAW_API_ENABLED=true 여부")
    lines.append("- LAW_API_KEY 적용 여부(값 미출력)")
    lines.append("- 샘플 키워드로 법령 검색 성공 여부")
    lines.append("- 샘플 키워드로 판례 검색 성공 여부")
    lines.append("- 응답 형식(JSON) 파싱 성공 여부")
    lines.append("- timeout / 인증오류 / IP제한 여부")
    lines.append("- 실패 시 원인 상세")
    lines.append("")
    lines.append("## 런타임 설정 인식")
    lines.append(f"- LAW_API_ENABLED(효과): `{str(bool(data['LAW_API_ENABLED_effective'])).lower()}`")
    lines.append(f"- LAW_API_KEY(존재): `{str(bool(data['LAW_API_KEY_present'])).lower()}`")
    lines.append(f"- base_url: `{data['LAW_API_BASE_URL']}`")
    lines.append(f"- timeout_sec: `{data['timeout_sec']}` / retry_count: `{data['retry_count']}`")
    lines.append("")

    def sec(title: str, d: dict[str, Any]) -> None:
        lines.append(f"## {title}")
        lines.append(f"- ok: `{str(bool(d.get('ok'))).lower()}`")
        lines.append(f"- elapsed_client_sec: `{json.dumps(d.get('elapsed_client_sec'))}`")
        if d.get("ok"):
            lines.append(f"- parse_ok: `{str(bool(d.get('parse_ok'))).lower()}`")
            lines.append(f"- item_count_guess: `{json.dumps(d.get('item_count_guess'))}`")
        else:
            lines.append(f"- error: `{json.dumps(d.get('error'), ensure_ascii=False)}`")
            if "http_status" in d:
                lines.append(f"- http_status: `{json.dumps(d.get('http_status'))}`")
            flags = d.get("flags")
            if isinstance(flags, dict):
                lines.append(
                    "- flags: "
                    + json.dumps({k: bool(v) for k, v in flags.items()}, ensure_ascii=False)
                )
        lines.append("")

    sec("1) 법령 검색 (target=law)", data["law_search"])
    sec("2) 판례 검색 (target=prec)", data["precedent_search"])
    lines.append("## 판정/해석")
    if isinstance(data.get("law_search"), dict) and data["law_search"].get("flags", {}).get("http_404_possible_base_url_issue"):
        lines.append("- HTTP 404가 관측되면 base_url이 `https://www.law.go.kr/DRF` 형태가 아닌지 우선 확인이 필요하다.")
    lines.append("- 키 값(OC)은 출력하지 않으며, 실패 시에도 원인만 기록했다.")
    lines.append("")
    _write_md("docs/review_output/88_law_api_runtime_check.md", "\n".join(lines) + "\n")


def _review_analyze_cases() -> list[dict[str, Any]]:
    url = "http://127.0.0.1:8787/api/review/analyze"
    timeout_sec = 25.0
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
        res = _http_json("POST", url, body=c["input"], timeout_sec=timeout_sec)
        item: dict[str, Any] = {"case_id": c["case_id"], "title": c["title"], "input": c["input"], "http": {"ok": res.ok, "elapsed_client_sec": round(res.elapsed_client_sec, 4), "http_status": res.http_status, "error": res.error}}
        if res.ok and isinstance(res.json_obj, dict):
            obj = res.json_obj
            summary = obj.get("summary") if isinstance(obj.get("summary"), dict) else None
            matched_rules = obj.get("matched_rules") if isinstance(obj.get("matched_rules"), list) else []
            matched_ids = [r.get("rule_id") for r in matched_rules if isinstance(r, dict) and isinstance(r.get("rule_id"), str)]
            law_search = obj.get("law_search") if isinstance(obj.get("law_search"), dict) else None

            def count_titles(xs: Any) -> int | None:
                if not isinstance(xs, list):
                    return None
                return len([x for x in xs if isinstance(x, dict) and isinstance(x.get("title"), str)])

            def pick_errors(xs: Any) -> list[str]:
                if not isinstance(xs, list):
                    return []
                errs = []
                for x in xs:
                    if isinstance(x, dict) and isinstance(x.get("error"), str):
                        errs.append(x["error"])
                return errs

            law_counts = None
            law_errors = None
            if law_search:
                results = law_search.get("results") if isinstance(law_search.get("results"), dict) else {}
                law_counts = {
                    "laws": count_titles(results.get("laws")),
                    "precedents": count_titles(results.get("precedents")),
                    "interpretations": count_titles(results.get("interpretations")),
                    "admin_rules": count_titles(results.get("admin_rules")),
                    "local_ordinances": count_titles(results.get("local_ordinances")),
                }
                law_errors = {
                    "laws": pick_errors(results.get("laws")),
                    "precedents": pick_errors(results.get("precedents")),
                    "interpretations": pick_errors(results.get("interpretations")),
                    "admin_rules": pick_errors(results.get("admin_rules")),
                    "local_ordinances": pick_errors(results.get("local_ordinances")),
                    "errors": law_search.get("errors") if isinstance(law_search.get("errors"), list) else [],
                }

            item["analysis"] = {
                "summary": summary,
                "matched_rule_ids": matched_ids,
                "law_search_present": bool(law_search is not None),
                "law_search_enabled": (law_search.get("enabled") if law_search else None),
                "law_counts": law_counts,
                "law_errors": law_errors,
            }
        out.append(item)
    return out


def _write_89(cases: list[dict[str, Any]]) -> None:
    lines = []
    lines.append("# /api/review/analyze + law_search 응답 포함 여부 검증")
    lines.append("")
    lines.append("## 참고(필드명)")
    lines.append("- 현재 `/api/review/analyze` 응답은 `issues/applied_rules` 대신 `matched_rules/checklist_rules` 구조를 사용한다.")
    lines.append("")
    for c in cases:
        lines.append(f"## {c['case_id']}: {c['title']}")
        lines.append("- 입력")
        lines.append(f"  - entity: `{c['input']['entity']}`")
        lines.append(f"  - contract_type: `{c['input']['contract_type']}`")
        lines.append(f"  - text: `{_short(c['input']['text'], 200)}`")
        http = c["http"]
        lines.append("- 호출 결과")
        lines.append(f"  - ok: `{str(bool(http['ok'])).lower()}`")
        lines.append(f"  - http_status: `{json.dumps(http.get('http_status'))}`")
        lines.append(f"  - elapsed_client_sec: `{json.dumps(http.get('elapsed_client_sec'))}`")
        if http.get("error"):
            lines.append(f"  - error: `{json.dumps(http.get('error'), ensure_ascii=False)}`")
        ana = c.get("analysis")
        if isinstance(ana, dict):
            lines.append("- review 요약(summary)")
            lines.append(f"  - {json.dumps(ana.get('summary'), ensure_ascii=False)}")
            lines.append("- matched_rules(rule_ids)")
            lines.append(f"  - {json.dumps(ana.get('matched_rule_ids'), ensure_ascii=False)}")
            lines.append("- law_search")
            lines.append(f"  - present: `{str(bool(ana.get('law_search_present'))).lower()}` / enabled: `{json.dumps(ana.get('law_search_enabled'))}`")
            lines.append(f"  - counts: `{json.dumps(ana.get('law_counts'), ensure_ascii=False)}`")
            errs = ana.get("law_errors")
            if isinstance(errs, dict):
                compact = {k: v for k, v in errs.items() if v}
                lines.append(f"  - errors: `{json.dumps(compact, ensure_ascii=False)}`")
        lines.append("")

    lines.append("## 결과 타당성(간단 판정 기준)")
    lines.append("- 대리점/비용전가 키워드가 포함된 경우 `RISK-006/ACT-009` 계열이 matched_rules에 나타나는지 확인")
    lines.append("- 하도급/기술자료 키워드가 포함된 경우 `RISK-005/ACT-008` 또는 `RISK-004/ACT-007` 계열이 나타나는지 확인")
    lines.append("- 안전/중대재해 키워드가 포함된 경우 `RISK-003/ACT-010` 계열이 나타나는지 확인")
    lines.append("")
    _write_md("docs/review_output/89_review_analyze_lawsearch_validation.md", "\n".join(lines) + "\n")


def _questions_generate_cases() -> list[dict[str, Any]]:
    url = "http://127.0.0.1:8787/api/questions/generate"
    timeout_sec = 25.0
    cases = [
        ("case-1", "대리점성 텍스트", {"entity": "퍼시스", "contract_type": "대리점/위탁/유통", "text": "대리점 계약이며 판촉비/광고비/반품비를 대리점이 부담합니다."}),
        ("case-2", "하도급성 텍스트", {"entity": "퍼시스", "contract_type": "공사/도급/하도급", "text": "하도급 거래로 단가 인하 및 재작업 비용 부담이 있습니다."}),
        ("case-3", "개인정보 처리 위탁 텍스트", {"entity": "퍼시스", "contract_type": "개인정보/처리위탁", "text": "개인정보 처리위탁(DPA) 및 재위탁, 보관기간, 파기 조항이 필요합니다."}),
        ("case-4", "모델계약/광고 문구", {"entity": "일룸", "contract_type": "광고/마케팅/협찬", "text": "광고 캠페인 및 모델(초상권) 사용 범위가 포함됩니다."}),
        ("case-5", "중대재해/현장작업 문구", {"entity": "바로스", "contract_type": "바로스(물류/설치)", "text": "물류센터 현장 작업, 안전관리, 중대재해 대응이 포함됩니다."}),
    ]

    out = []
    for cid, title, payload in cases:
        res = _http_json("POST", url, body=payload, timeout_sec=timeout_sec)
        item: dict[str, Any] = {"case_id": cid, "title": title, "input": payload, "http": {"ok": res.ok, "elapsed_client_sec": round(res.elapsed_client_sec, 4), "http_status": res.http_status, "error": res.error}}
        if res.ok and isinstance(res.json_obj, dict):
            obj = res.json_obj
            qs = obj.get("questions") if isinstance(obj.get("questions"), list) else []
            q_ids = [q.get("question_id") for q in qs if isinstance(q, dict) and isinstance(q.get("question_id"), str)]
            law_search = obj.get("law_search") if isinstance(obj.get("law_search"), dict) else None
            law_topics = law_search.get("queries") if isinstance(law_search, dict) else None
            item["analysis"] = {
                "count": obj.get("count"),
                "question_ids": q_ids,
                "law_topics_present": isinstance(law_topics, list),
                "law_topics_has_key_topics": any(t in set(law_topics or []) for t in ("대리점법", "하도급법", "개인정보보호법")),
                "has_q_law": any(qid.startswith("Q-LAW-") for qid in q_ids),
            }
        out.append(item)
    return out


def _write_90(cases: list[dict[str, Any]]) -> None:
    lines = []
    lines.append("# /api/questions/generate 법률 토픽 반영 검증")
    lines.append("")
    lines.append("## 확인 항목")
    lines.append("- 질문이 한 번에 1개씩 보여줄 수 있는 구조인지")
    lines.append("- 법률적으로 의미 있는 질문이 나오는지")
    lines.append("- 법인별 차이가 반영되는지(토픽 기반 Q-LAW 질문 포함 여부)")
    lines.append("")
    lines.append("## 구조 판정")
    lines.append("- API는 `questions: []` 배열로 질문을 반환하며, UI가 1개씩 순차 표시하는 방식에 적합하다.")
    lines.append("")
    for c in cases:
        lines.append(f"## {c['case_id']}: {c['title']}")
        lines.append(f"- input: entity=`{c['input']['entity']}`, contract_type=`{c['input']['contract_type']}`, text=`{_short(c['input']['text'], 140)}`")
        http = c["http"]
        lines.append(f"- http ok=`{str(bool(http['ok'])).lower()}` status=`{json.dumps(http.get('http_status'))}` elapsed=`{json.dumps(http.get('elapsed_client_sec'))}`")
        if http.get("error"):
            lines.append(f"- error: `{json.dumps(http.get('error'), ensure_ascii=False)}`")
        ana = c.get("analysis")
        if isinstance(ana, dict):
            lines.append(f"- count: `{json.dumps(ana.get('count'))}`")
            lines.append(f"- has_q_law(Q-LAW-*): `{str(bool(ana.get('has_q_law'))).lower()}`")
            lines.append(f"- law_topics_present: `{str(bool(ana.get('law_topics_present'))).lower()}` / has_key_topics: `{str(bool(ana.get('law_topics_has_key_topics'))).lower()}`")
            lines.append(f"- question_ids: `{json.dumps(ana.get('question_ids'), ensure_ascii=False)}`")
        lines.append("")
    _write_md("docs/review_output/90_question_engine_law_validation.md", "\n".join(lines) + "\n")


def _revision_suggest_text_check() -> dict[str, Any]:
    url = "http://127.0.0.1:8787/api/revision/suggest_text"
    payload = {
        "entity": "퍼시스",
        "contract_type": "대리점/위탁/유통",
        "text": "제1조(비용 부담) 대리점은 판촉비, 광고비 및 반품 비용을 전적으로 부담한다.\n제2조(기타) 본 계약은 당사와 대리점 간 대리점 거래를 규율한다.",
        "filename": None,
        "answers": None,
    }
    res = _http_json("POST", url, body=payload, timeout_sec=25.0)
    out: dict[str, Any] = {"http": {"ok": res.ok, "http_status": res.http_status, "elapsed_client_sec": round(res.elapsed_client_sec, 4), "error": res.error}, "input": payload}
    if res.ok and isinstance(res.json_obj, dict):
        obj = res.json_obj
        rev = obj.get("revision") if isinstance(obj.get("revision"), dict) else {}
        items = rev.get("items") if isinstance(rev.get("items"), list) else []
        first = items[0] if items and isinstance(items[0], dict) else None
        out["analysis"] = {
            "review_summary": obj.get("review_summary"),
            "law_search_present": isinstance(obj.get("law_search"), dict),
            "law_search_enabled": (obj.get("law_search") or {}).get("enabled") if isinstance(obj.get("law_search"), dict) else None,
            "ai_present": isinstance(obj.get("ai"), dict),
            "first_item": None,
        }
        if isinstance(first, dict):
            detected = first.get("detected_issues") if isinstance(first.get("detected_issues"), list) else []
            applied = first.get("applied_rules") if isinstance(first.get("applied_rules"), list) else []
            out["analysis"]["first_item"] = {
                "clause_title": first.get("clause_title"),
                "original_clause": _short(first.get("original_clause"), 220),
                "detected_issue_titles": [d.get("issue_title") for d in detected if isinstance(d, dict) and isinstance(d.get("issue_title"), str)][:3],
                "applied_rule_ids": [a.get("rule_id") for a in applied if isinstance(a, dict) and isinstance(a.get("rule_id"), str)][:5],
                "suggested_direction": first.get("suggested_direction"),
                "fallback_text_present": bool(first.get("fallback_text")),
                "approval_required": first.get("approval_required"),
            }
    return out


def _write_91(data: dict[str, Any]) -> None:
    lines = []
    lines.append("# /api/revision/suggest_text 수정 제안 + 법령 근거 결합 검증")
    lines.append("")
    lines.append("## 확인 항목")
    lines.append("- 원문 조항")
    lines.append("- 검출 issue")
    lines.append("- 적용 rule")
    lines.append("- law_search 또는 관련 법령 근거")
    lines.append("- 수정 제안 이유(suggested_direction)")
    lines.append("- fallback_text 또는 AI 보강 문안")
    lines.append("- approval_required 여부")
    lines.append("")
    lines.append("## 호출 결과")
    http = data["http"]
    lines.append(f"- ok: `{str(bool(http['ok'])).lower()}` / http_status: `{json.dumps(http.get('http_status'))}` / elapsed_client_sec: `{json.dumps(http.get('elapsed_client_sec'))}`")
    if http.get("error"):
        lines.append(f"- error: `{json.dumps(http.get('error'), ensure_ascii=False)}`")
    lines.append("")
    lines.append("## 입력(샘플)")
    lines.append(f"- entity: `{data['input']['entity']}` / contract_type: `{data['input']['contract_type']}`")
    lines.append(f"- text: `{_short(data['input']['text'], 280)}`")
    lines.append("")
    ana = data.get("analysis")
    if isinstance(ana, dict):
        lines.append("## 응답 요약")
        lines.append(f"- law_search_present: `{str(bool(ana.get('law_search_present'))).lower()}` / enabled: `{json.dumps(ana.get('law_search_enabled'))}`")
        lines.append(f"- ai_present: `{str(bool(ana.get('ai_present'))).lower()}`")
        first = ana.get("first_item")
        if isinstance(first, dict):
            lines.append("## 1) 첫 번째 이슈 조항(요약)")
            lines.append(f"- 원문 조항: `{json.dumps(first.get('original_clause'), ensure_ascii=False)}`")
            lines.append(f"- 검출 issue: `{json.dumps(first.get('detected_issue_titles'), ensure_ascii=False)}`")
            lines.append(f"- 적용 rule: `{json.dumps(first.get('applied_rule_ids'), ensure_ascii=False)}`")
            lines.append(f"- 수정 제안 방향: `{json.dumps(first.get('suggested_direction'), ensure_ascii=False)}`")
            lines.append(f"- fallback_text_present: `{str(bool(first.get('fallback_text_present'))).lower()}`")
            lines.append(f"- approval_required: `{json.dumps(first.get('approval_required'))}`")
        lines.append("")
    _write_md("docs/review_output/91_revision_law_grounding_validation.md", "\n".join(lines) + "\n")


def main() -> None:
    env_data = _env_runtime_validation()
    _write_86(env_data)
    _write_87()
    law_data = _law_direct_search_check()
    _write_88(law_data)
    review_cases = _review_analyze_cases()
    _write_89(review_cases)
    q_cases = _questions_generate_cases()
    _write_90(q_cases)
    rev_data = _revision_suggest_text_check()
    _write_91(rev_data)
    print("generated: 86,87,88,89,90,91")


if __name__ == "__main__":
    main()
