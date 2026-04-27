from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Timings:
    fast_sec: float
    deep_sec: float
    docx_sec: float
    docx_ok: bool
    baseline_total_sec: float


def _post_json(url: str, payload: dict[str, Any], *, timeout: float = 120.0) -> dict[str, Any]:
    b = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    resp = urlopen(Request(url, data=b, method="POST", headers={"Content-Type": "application/json; charset=utf-8"}), timeout=timeout).read()
    return json.loads(resp.decode("utf-8"))


def _get_json(url: str, *, timeout: float = 60.0) -> dict[str, Any]:
    resp = urlopen(Request(url, method="GET"), timeout=timeout).read()
    return json.loads(resp.decode("utf-8"))


def _post_docx(url: str, payload: dict[str, Any], *, timeout: float = 120.0) -> bytes:
    b = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return urlopen(
        Request(url, data=b, method="POST", headers={"Content-Type": "application/json; charset=utf-8"}),
        timeout=timeout,
    ).read()


def _avg(xs: list[float]) -> float:
    return (sum(xs) / max(1, len(xs))) if xs else 0.0


def _mx(xs: list[float]) -> float:
    return max(xs) if xs else 0.0


def _fmt(s: float) -> str:
    return f"{s:.2f}s"


def measure_one(*, base_url: str, payload: dict[str, Any]) -> Timings:
    t0 = time.time()
    fast = _post_json(base_url.rstrip("/") + "/api/review/analyze_fast", payload, timeout=120.0)
    t1 = time.time()
    if isinstance(fast, dict) and fast.get("error"):
        raise RuntimeError(str(fast.get("error")))
    deep = _post_json(base_url.rstrip("/") + "/api/review/analyze_deep", payload, timeout=180.0)
    t2 = time.time()
    if isinstance(deep, dict) and deep.get("error"):
        raise RuntimeError(str(deep.get("error")))
    clause_results = deep.get("clause_results") if isinstance(deep, dict) else None
    if not isinstance(clause_results, list):
        clause_results = []
    docx_ok = True
    try:
        if clause_results:
            docx_payload = {
                "input": {"entity": payload.get("entity"), "contract_type": payload.get("contract_type"), "filename": payload.get("filename")},
                "clause_results": clause_results,
            }
        else:
            docx_payload = {
                "input": {"entity": payload.get("entity"), "contract_type": payload.get("contract_type"), "filename": payload.get("filename")},
                "clause_results": [],
                "original_clauses": [{"clause_id": "KR-000", "clause_title": "(전체)", "text": str(payload.get("text") or "")}],
            }
        _ = _post_docx(base_url.rstrip("/") + "/api/revision/download_docx", docx_payload, timeout=180.0)
    except Exception:
        docx_ok = False
    t3 = time.time()

    t4 = time.time()
    _ = _post_json(base_url.rstrip("/") + "/api/review/analyze", payload, timeout=180.0)
    _ = _post_json(base_url.rstrip("/") + "/api/revision/suggest_text", payload, timeout=180.0)
    ct = quote(str(payload.get("contract_type", "") or ""), safe="")
    _ = _get_json(base_url.rstrip("/") + f"/api/draft/suggest?contract_type={ct}", timeout=60.0)
    t5 = time.time()

    return Timings(
        fast_sec=(t1 - t0),
        deep_sec=(t2 - t1),
        docx_sec=(t3 - t2),
        docx_ok=docx_ok,
        baseline_total_sec=(t5 - t4),
    )


def write_report(*, out_path: Path, base_url: str, cases: dict[str, list[Timings]]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# 187) Review Latency Benchmark\n")
    lines.append(f"- base_url: `{base_url}`")
    lines.append(f"- generated_at: `{time.strftime('%Y-%m-%d %H:%M:%S')}`\n")
    lines.append("## 측정 항목\n")
    lines.append("- fast(1차 summary)까지 시간: `POST /api/review/analyze_fast`")
    lines.append("- deep(정밀 조항결과)까지 추가 시간: `POST /api/review/analyze_deep`")
    lines.append("- docx 준비(다운로드 응답)까지 추가 시간: `POST /api/revision/download_docx`")
    lines.append("- 개선 전(순차) 총 소요: `/api/review/analyze` → `/api/revision/suggest_text` → `/api/draft/suggest`\n")

    lines.append("## 결과 요약\n")
    lines.append("| 케이스 | fast avg/max | deep avg/max | docx avg/max | baseline total avg/max |")
    lines.append("|---|---:|---:|---:|---:|")
    for name, ts in cases.items():
        fasts = [x.fast_sec for x in ts]
        deeps = [x.deep_sec for x in ts]
        docxs = [x.docx_sec for x in ts if x.docx_ok]
        bases = [x.baseline_total_sec for x in ts]
        docx_cell = f"{_fmt(_avg(docxs))} / {_fmt(_mx(docxs))}" if docxs else f"ERR({sum(1 for x in ts if not x.docx_ok)})"
        lines.append(
            f"| {name} | {_fmt(_avg(fasts))} / {_fmt(_mx(fasts))} | {_fmt(_avg(deeps))} / {_fmt(_mx(deeps))} | "
            f"{docx_cell} | {_fmt(_avg(bases))} / {_fmt(_mx(bases))} |"
        )

    lines.append("\n## 병목 단계(관찰)\n")
    lines.append("- deep 단계가 가장 큰 비중을 차지하는 경우가 대부분이며, 법령검색/AI 호출의 영향을 크게 받는다.")
    lines.append("- fast는 AI/Law를 제외하고 규칙 기반 screening 중심이라 비교적 안정적으로 짧다.\n")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    base = os.environ.get("AOURIBOT_BASE_URL") or "http://127.0.0.1:8787"
    fixtures = [
        ("짧은 계약서(NDA)", "runtime/tests/fixtures/nda_basic.txt", "NDA/비밀유지"),
        ("중간 길이(services)", "runtime/tests/fixtures/services_consulting.txt", "용역/컨설팅"),
        ("긴 계약서(app-dev)", "runtime/tests/fixtures/app_dev_contract.txt", "앱개발/소프트웨어개발/SI/유지보수/SaaS"),
    ]
    cases: dict[str, list[Timings]] = {}
    runs = int(os.environ.get("BENCH_RUNS") or "2")
    entity = os.environ.get("BENCH_ENTITY") or "일룸/데스커"
    for name, rel_path, ct in fixtures:
        text = Path(rel_path).read_text(encoding="utf-8")
        payload = {"entity": entity, "contract_type": ct, "filename": "bench.txt", "text": text, "answers": {}}
        arr: list[Timings] = []
        for _ in range(max(1, runs)):
            arr.append(measure_one(base_url=base, payload=payload))
        cases[name] = arr
    out_path = Path(r"C:\Users\FURSYS\Desktop\aouribot\docs\review_output\187_review_latency_benchmark.md")
    write_report(out_path=out_path, base_url=base, cases=cases)
    print(json.dumps({k: [t.__dict__ for t in v] for k, v in cases.items()}, ensure_ascii=False, indent=2))
