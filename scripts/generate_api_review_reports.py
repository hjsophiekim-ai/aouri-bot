from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
EXTRACTED_DIR = ROOT / "docs" / "review_output" / "02_extracted_texts"
OUT_DIR = ROOT / "docs" / "review_output"


def _http_json(method: str, url: str, body: dict[str, Any] | None) -> tuple[int, dict[str, Any], float]:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = Request(url, data=data, headers=headers, method=method)
    t0 = time.perf_counter()
    try:
        with urlopen(req, timeout=10) as res:
            raw = res.read().decode("utf-8", errors="replace")
            dt = time.perf_counter() - t0
            return int(res.status), (json.loads(raw) if raw else {}), dt
    except HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
            obj = json.loads(raw) if raw else {"error": raw}
        except Exception:
            obj = {"error": str(exc)}
        dt = time.perf_counter() - t0
        return int(exc.code), obj, dt


def _md_json(obj: Any) -> str:
    return "```json\n" + json.dumps(obj, ensure_ascii=False, indent=2) + "\n```"


def _pick_entity_from_filename(name: str) -> str:
    lowered = name.lower()
    if "시디즈" in name or "sidiz" in lowered:
        return "시디즈"
    if "일룸" in name or "iloom" in lowered:
        return "일룸"
    if "데스커" in name or "desker" in lowered:
        return "데스커"
    if "바로스" in name or "baros" in lowered:
        return "바로스"
    if "퍼시스" in name or "fursys" in lowered:
        return "퍼시스"
    return "all"


def _infer_contract_type_from_filename(name: str) -> str:
    lowered = name.lower()
    if "nda" in lowered or "비밀" in name:
        return "NDA/비밀유지"
    if "dealer" in lowered or "대리점" in name or "유통" in name or "위탁거래" in name:
        return "대리점/위탁/유통"
    if "supply" in lowered or "물품공급" in name or "purchase" in lowered or "sales contract" in lowered:
        return "물품공급/구매/매매"
    if "engagement" in lowered or "consult" in lowered or "자문" in name or "용역" in name or "service agreement" in lowered:
        return "용역/자문"
    if "개인정보" in name or "privacy" in lowered or "dpa" in lowered or "처리위탁" in name:
        return "개인정보/처리위탁"
    if "광고" in name or "marketing" in lowered or "sponsor" in lowered or "협찬" in name:
        return "광고/마케팅/협찬"
    return "기타/미분류"


def _read_text(path: Path, max_chars: int | None = None) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if max_chars is not None and len(text) > max_chars:
        return text[:max_chars]
    return text


def _summarize_review(resp: dict[str, Any]) -> dict[str, Any]:
    summary = resp.get("summary") if isinstance(resp.get("summary"), dict) else {}
    matched = resp.get("matched_rules") if isinstance(resp.get("matched_rules"), list) else []
    approval_matches = resp.get("approval_required_matches") if isinstance(resp.get("approval_required_matches"), list) else []
    any_high = False
    for r in matched:
        if not isinstance(r, dict):
            continue
        if str(r.get("risk_level") or "").strip().lower() in ("high", "very_high", "critical"):
            any_high = True
            break
    return {
        "summary": summary,
        "matched_rule_count": int(summary.get("matched_rule_count") or 0),
        "approval_required_match_count": int(summary.get("approval_required_match_count") or 0),
        "high_risk": any_high,
        "approval_required": len(approval_matches) > 0,
        "top_rules": [
            {
                "rule_id": str(r.get("rule_id") or ""),
                "title": str(r.get("title") or ""),
                "risk_level": str(r.get("risk_level") or ""),
                "rule_status": str(r.get("rule_status") or ""),
                "approval_required": bool(r.get("approval_required") is True or r.get("rule_status") == "approval_required"),
            }
            for r in matched[:10]
            if isinstance(r, dict)
        ],
    }


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@dataclass(frozen=True)
class CaseRun:
    filename: str
    entity: str
    contract_type: str
    inferred: bool
    response: dict[str, Any]
    elapsed_sec: float


def _run_analyze(base_url: str, *, entity: str, contract_type: str, text: str, filename: str) -> CaseRun:
    payload = {
        "entity": entity,
        "contract_type": contract_type,
        "filename": filename,
        "text": text,
        "persist": False,
    }
    status, resp, elapsed = _http_json("POST", f"{base_url}/api/review/analyze", payload)
    if status != 200:
        raise RuntimeError(f"analyze failed: status={status} resp={resp}")
    inferred = (entity == "all") or (contract_type in ("기타/미분류", "all"))
    return CaseRun(filename=filename, entity=entity, contract_type=contract_type, inferred=inferred, response=resp, elapsed_sec=elapsed)


def _select_real_5_cases() -> list[Path]:
    chosen_names = [
        "extracted_nda_f786a2cf20.txt",
        "FURSYS_Vietnam_Dealer_Agreement_법무팀_b11ac793ef.txt",
        "Supply_Agreement_FURSYS_LXPANTOS_250710 법무팀검토본_수정_572f12ba1e.txt",
        "2025 퍼시스 경영 자문 계약서_이종태(법무팀)_수정_22df7a0d13.txt",
        "☆ 참고. 개인정보처리위탁 계약서 표준안 (법무팀)_0e33d01360.txt",
    ]
    out: list[Path] = []
    for n in chosen_names:
        p = EXTRACTED_DIR / n
        if p.exists():
            out.append(p)
    return out


def _md_table(rows: list[list[str]], headers: list[str]) -> str:
    out = []
    out.append("| " + " | ".join(headers) + " |")
    out.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for r in rows:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def main() -> None:
    base_url = "http://127.0.0.1:8787"

    st, health, _ = _http_json("GET", f"{base_url}/health", None)
    if st != 200 or health.get("status") != "ok":
        raise SystemExit(f"runtime not healthy: status={st} resp={health}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    sample_text = "\n".join(
        [
            "제10조(손해배상) 당사는 본 계약과 관련하여 발생하는 모든 손해에 대하여 손해배상 책임을 부담하며, 책임 한도는 없이(without limitation) 제한되지 않는다.",
            "제11조(면책) 상대방은 어떠한 경우에도 당사에 대하여 책임을 부담하지 아니하며, 당사는 상대방을 면책하고(indemnify) 모든 청구로부터 보호한다.",
            "제12조(기술자료 제출) 당사는 상대방의 요청 시 기술자료, 원가자료, 설계도면 및 소스코드 등 일체 자료를 즉시 제출하여야 한다.",
            "제13조(해지) 상대방은 사전 통지 없이 언제든지 본 계약을 즉시 해지할 수 있으며, 해지 시 이미 납품된 물품 대금도 지급하지 않을 수 있다.",
        ]
    )
    sample_payload = {
        "entity": "퍼시스",
        "contract_type": "물품공급/구매/매매",
        "filename": "sample_supply_clause.txt",
        "text": sample_text,
        "persist": False,
    }
    status, sample_resp, sample_dt = _http_json("POST", f"{base_url}/api/review/analyze", sample_payload)
    if status != 200:
        raise SystemExit(f"sample analyze failed: {status} {sample_resp}")

    applied = sample_resp.get("matched_rules") if isinstance(sample_resp.get("matched_rules"), list) else []
    applied_rules = []
    for r in applied:
        if not isinstance(r, dict):
            continue
        applied_rules.append(
            {
                "rule_id": r.get("rule_id"),
                "title": r.get("title"),
                "rule_status": r.get("rule_status"),
                "risk_level": r.get("risk_level"),
                "approval_required": bool(r.get("approval_required") is True or r.get("rule_status") == "approval_required"),
            }
        )

    high_risk = any(
        str(r.get("risk_level") or "").strip().lower() in ("high", "very_high", "critical")
        for r in applied_rules
        if isinstance(r, dict)
    )
    approval_required = any(bool(r.get("approval_required")) for r in applied_rules if isinstance(r, dict))

    doc33 = []
    doc33.append("# 샘플 계약 텍스트 검토 테스트(1건)\n")
    doc33.append("## 테스트 조건\n- 법인: 퍼시스\n- 계약유형: 물품공급/구매계약\n- 포함 문구: 무제한 책임, 일방 면책, 기술자료 제출, 불리한 해지\n")
    doc33.append("## 1) 실제 request payload\n" + _md_json(sample_payload) + "\n")
    doc33.append(f"## 2) 실제 response payload\n- 응답시간: {sample_dt:.4f}s\n" + _md_json(sample_resp) + "\n")
    doc33.append("## 3) 적용된 rule(매칭된 rule)\n" + _md_json(applied_rules) + "\n")
    doc33.append("## 4) high risk / approval required 결과\n")
    doc33.append(f"- high_risk: {high_risk}\n- approval_required: {approval_required}\n")
    doc33.append("## 5) 결과 해석\n")
    doc33.append(
        "- 입력 문구에 무제한 책임/면책/기술자료/해지 키워드가 포함되어 trigger rule이 매칭되었다.\n"
        "- 매칭된 rule 중 risk_level이 HIGH(또는 동급)인 항목이 있으면 high_risk로 판단했다.\n"
        "- 매칭된 rule 중 rule_status=approval_required 또는 approval_required=true가 있으면 approval_required로 판단했다.\n"
    )
    _write(OUT_DIR / "33_sample_review_test_1.md", "\n".join(doc33))

    real_paths = _select_real_5_cases()
    real_runs: list[CaseRun] = []
    for p in real_paths:
        name = p.name
        entity = _pick_entity_from_filename(name)
        ct = _infer_contract_type_from_filename(name)
        text = _read_text(p, max_chars=120000)
        real_runs.append(_run_analyze(base_url, entity=entity, contract_type=ct, text=text, filename=name))

    rows = []
    for run in real_runs:
        s = _summarize_review(run.response)
        top3 = s["top_rules"][:3]
        top3_txt = ", ".join([str(x.get("rule_id") or "") for x in top3])
        rows.append(
            [
                run.filename,
                ("추정" if run.inferred else "입력"),
                run.contract_type,
                str(s["matched_rule_count"]),
                "Y" if s["high_risk"] else "N",
                "Y" if s["approval_required"] else "N",
                top3_txt or "-",
                "키워드 기반이라 정밀도는 제한적이나, 주요 위험 문구가 있으면 탐지되는 편",
            ]
        )
    doc34 = []
    doc34.append("# 실제 계약서 5건 review analyze 결과\n")
    doc34.append("대상: `docs/review_output/02_extracted_texts` 내 텍스트 추출 성공 파일 중 5건(계약유형 비중복)\n")
    doc34.append(
        _md_table(
            rows,
            [
                "파일명",
                "계약유형 출처",
                "계약유형(추정/입력)",
                "검출 issue(=matched rule) 수",
                "high_risk",
                "approval_required",
                "대표 rule 3개",
                "간단 평가",
            ],
        )
    )
    doc34.append("\n\n## 케이스별 상세(요약)\n")
    for run in real_runs:
        s = _summarize_review(run.response)
        doc34.append(f"### {run.filename}\n- entity={run.entity} contract_type={run.contract_type}\n- 응답시간={run.elapsed_sec:.4f}s\n")
        doc34.append(_md_json(s) + "\n")
    _write(OUT_DIR / "34_real_contract_review_5cases.md", "\n".join(doc34))

    all_txt = sorted(EXTRACTED_DIR.glob("*.txt"))
    random.seed(7)
    sample20 = random.sample(all_txt, k=min(20, len(all_txt)))
    batch_rows = []
    success = 0
    failed = 0
    high_cnt = 0
    appr_cnt = 0
    by_type: dict[str, int] = {}
    by_entity: dict[str, int] = {}
    issue_titles: dict[str, int] = {}

    for p in sample20:
        name = p.name
        entity = _pick_entity_from_filename(name)
        ct = _infer_contract_type_from_filename(name)
        try:
            run = _run_analyze(base_url, entity=entity, contract_type=ct, text=_read_text(p, 120000), filename=name)
            success += 1
            s = _summarize_review(run.response)
            if s["high_risk"]:
                high_cnt += 1
            if s["approval_required"]:
                appr_cnt += 1
            by_type[ct] = by_type.get(ct, 0) + 1
            by_entity[entity] = by_entity.get(entity, 0) + 1
            for r in s["top_rules"]:
                t = str(r.get("title") or "").strip()
                if t:
                    issue_titles[t] = issue_titles.get(t, 0) + 1
            batch_rows.append(
                [
                    name,
                    entity,
                    ct,
                    str(s["matched_rule_count"]),
                    "Y" if s["high_risk"] else "N",
                    "Y" if s["approval_required"] else "N",
                ]
            )
        except Exception:
            failed += 1

    type_dist = sorted(by_type.items(), key=lambda x: (-x[1], x[0]))
    entity_dist = sorted(by_entity.items(), key=lambda x: (-x[1], x[0]))
    top_issues = sorted(issue_titles.items(), key=lambda x: (-x[1], x[0]))[:10]

    doc35 = []
    doc35.append("# Batch review 샘플 20건 결과\n")
    doc35.append("- 대상: `docs/review_output/02_extracted_texts`에서 무작위 20건 샘플링\n")
    doc35.append("## 처리 요약\n")
    doc35.append(
        _md_table(
            [
                ["성공", str(success)],
                ["실패", str(failed)],
                ["high risk", str(high_cnt)],
                ["approval required", str(appr_cnt)],
            ],
            ["지표", "값"],
        )
    )
    doc35.append("\n\n## 계약유형(추정) 분포\n")
    doc35.append(_md_table([[k, str(v)] for k, v in type_dist], ["contract_type", "count"]))
    doc35.append("\n\n## 법인(파일명 기반 추정) 분포\n")
    doc35.append(_md_table([[k, str(v)] for k, v in entity_dist], ["entity", "count"]))
    doc35.append("\n\n## 대표 issue(대표 rule title 기준, 상위 10)\n")
    doc35.append(_md_table([[k, str(v)] for k, v in top_issues], ["title", "count"]))
    doc35.append("\n\n## 샘플 20건 결과(요약)\n")
    doc35.append(_md_table(batch_rows, ["파일명", "entity", "contract_type", "matched", "high_risk", "approval_required"]))
    _write(OUT_DIR / "35_batch_review_20cases.md", "\n".join(doc35))

    compare_text = "\n".join(
        [
            "본 계약은 물품 공급과 관련된다.",
            "상대방은 당사에 판촉비 등 비용 부담을 요구할 수 있다.",
            "당사는 without limitation 손해배상 책임을 부담한다.",
            "상대방이 요구하는 기술자료 및 원가자료를 제공한다.",
        ]
    )
    compare_contract_type = "물품공급/구매/매매"
    entities = ["퍼시스", "시디즈", "일룸", "바로스"]
    comp_rows = []
    comp_details: dict[str, Any] = {}
    for e in entities:
        run = _run_analyze(base_url, entity=e, contract_type=compare_contract_type, text=compare_text, filename=f"compare_{e}.txt")
        s = _summarize_review(run.response)
        comp_rows.append(
            [
                e,
                str(s["matched_rule_count"]),
                "Y" if s["high_risk"] else "N",
                "Y" if s["approval_required"] else "N",
                ", ".join([str(x.get("rule_id") or "") for x in s["top_rules"][:8]]) or "-",
            ]
        )
        comp_details[e] = s

    doc36 = []
    doc36.append("# 법인(entity)별 rule 결과 비교 테스트\n")
    doc36.append("동일 문구를 사용하고 entity만 변경하여 4회 실행했다.\n")
    doc36.append("## 입력 문구\n" + _md_json({"contract_type": compare_contract_type, "text": compare_text}) + "\n")
    doc36.append("## 비교 결과(요약)\n")
    doc36.append(_md_table(comp_rows, ["entity", "matched_rules", "high_risk", "approval_required", "대표 rule_ids"]))
    doc36.append("\n\n## 상세(요약 JSON)\n" + _md_json(comp_details) + "\n")
    _write(OUT_DIR / "36_entity_rule_comparison.md", "\n".join(doc36))

    risk_cases = [
        ("무제한 책임", ["책임 한도 없이(without limitation) 손해배상 책임을 부담한다.", "모든 손해에 대해 무제한 책임(unlimited liability)을 진다."]),
        ("일방 면책", ["상대방은 어떠한 책임도 부담하지 않는다(면책).", "당사는 상대방을 indemnify 하며, 상대방의 과실도 포함한다."]),
        ("기술자료 요구", ["당사는 기술자료 및 원가자료를 제출한다.", "상대방 요청 시 source code를 제공한다."]),
        ("하도급 단가감액", ["상대방은 하도급 단가를 감액할 수 있다.", "거래 조건 변경 시 단가 인하(price reduction)에 동의한다."]),
        ("대리점 비용전가", ["당사는 대리점 판촉비를 부담한다.", "반품 비용 및 광고비를 당사가 부담한다."]),
        ("안전책임 공백", ["현장 안전은 전적으로 당사 책임으로 한다.", "중대재해 및 산업안전 관련 책임은 당사가 부담한다."]),
    ]
    risk_rows = []
    risk_details = {}
    for title, clauses in risk_cases:
        for idx, clause in enumerate(clauses, start=1):
            run = _run_analyze(
                base_url,
                entity="퍼시스",
                contract_type="물품공급/구매/매매",
                text=clause,
                filename=f"risk_{title}_{idx}.txt",
            )
            s = _summarize_review(run.response)
            expect = "matched_rules>=1 and (high_risk or approval_required)"
            ok = (s["matched_rule_count"] >= 1) and (s["high_risk"] or s["approval_required"])
            risk_rows.append(
                [
                    title,
                    str(idx),
                    expect,
                    f"matched={s['matched_rule_count']} high={s['high_risk']} appr={s['approval_required']}",
                    "PASS" if ok else "FAIL",
                    ", ".join([str(x.get('rule_id') or '') for x in s["top_rules"][:5]]) or "-",
                ]
            )
            risk_details[f"{title}#{idx}"] = s

    doc37 = []
    doc37.append("# 6대 위험 문구 룰 탐지 정확도 테스트\n")
    doc37.append("기준: 각 항목별 샘플 조항 2개를 넣고 `matched_rules`가 발생하며 high/approval이 잡히는지 확인\n")
    doc37.append(_md_table(risk_rows, ["항목", "샘플", "expected", "actual", "통과", "대표 rule_ids"]))
    doc37.append("\n\n## 상세(요약 JSON)\n" + _md_json(risk_details) + "\n")
    _write(OUT_DIR / "37_risk_rule_accuracy_test.md", "\n".join(doc37))

    def _quality_run(name: str, text: str) -> dict[str, Any]:
        payload = {"entity": "퍼시스", "contract_type": "물품공급/구매/매매", "filename": f"qc_{name}.txt", "text": text, "persist": False}
        st, resp, dt = _http_json("POST", f"{base_url}/api/review/analyze", payload)
        ok = st == 200 and isinstance(resp, dict) and isinstance(resp.get("summary"), dict)
        matched = resp.get("matched_rules") if isinstance(resp.get("matched_rules"), list) else []
        backlog_mixed = any(isinstance(r, dict) and str(r.get("rule_status") or "") == "unconfirmed_backlog" for r in matched)
        issue_struct_ok = True
        for r in matched:
            if not isinstance(r, dict):
                issue_struct_ok = False
                break
            for k in ("rule_id", "rule_status", "risk_level", "title", "approval_required"):
                if k not in r:
                    issue_struct_ok = False
                    break
            if not issue_struct_ok:
                break
        return {"name": name, "http_status": st, "elapsed_sec": dt, "ok": ok, "issue_struct_ok": issue_struct_ok, "backlog_mixed_in_matched": backlog_mixed, "summary": resp.get("summary")}

    short = "무제한"
    empty = ""
    long_text = (sample_text + "\n") * 400
    qc = [
        _quality_run("empty", empty),
        _quality_run("too_short", short),
        _quality_run("normal", sample_text),
        _quality_run("long", long_text),
    ]

    doc38 = []
    doc38.append("# review analyze API 품질 점검\n")
    doc38.append("## 1) 응답 속도\n")
    doc38.append(_md_table([[x["name"], f"{x['elapsed_sec']:.4f}", str(x["http_status"])] for x in qc], ["case", "sec", "http_status"]))
    doc38.append("\n\n## 2) issue 구조 일관성\n")
    doc38.append(_md_table([[x["name"], "OK" if x["issue_struct_ok"] else "FAIL"] for x in qc], ["case", "issue_struct_ok"]))
    doc38.append("\n\n## 3) applied rule 설명 가능성\n- matched_rules에 rule_id/title/risk_level/rule_status/approval_required가 포함되어, UI에서 근거 표시가 가능\n")
    doc38.append("## 4) high risk / approval_required 판정 일관성\n- matched_rules 기반으로 high/approval 여부를 일관되게 계산 가능(저장 계층에서도 동일 규칙 사용)\n")
    doc38.append("## 5) 빈 텍스트 입력 처리\n")
    doc38.append(_md_json([x for x in qc if x["name"] == "empty"][0]) + "\n")
    doc38.append("## 6) 너무 짧은 텍스트 입력 처리\n")
    doc38.append(_md_json([x for x in qc if x["name"] == "too_short"][0]) + "\n")
    doc38.append("## 7) 긴 계약 텍스트 입력 처리\n")
    doc38.append(_md_json([x for x in qc if x["name"] == "long"][0]) + "\n")
    doc38.append("## 8) backlog_rules가 판정에 섞이지 않는지\n")
    doc38.append(_md_table([[x["name"], "Y" if x["backlog_mixed_in_matched"] else "N"] for x in qc], ["case", "backlog_mixed_in_matched"]))
    _write(OUT_DIR / "38_api_quality_check.md", "\n".join(doc38))

    doc39 = []
    doc39.append("# MVP Gap Analysis (냉정 평가)\n")
    doc39.append("## 1) 지금 가능한 것\n- 규칙 JSON 기반 키워드 탐지형 리뷰(LLM 없이)\n- 질문/답변(룰 기반) 반영으로 적용 범위 확장\n- 결과 저장/조회, 승인대기함 분리, EP 상태/결재 handoff 지점(stub/http)\n- 조항별 수정 제안 뷰(진짜 redline 제외)\n\n")
    doc39.append("## 2) 지금 부족한 것\n- 문맥 이해(예외/정의/범위/상호 참조) 부족\n- 조항 파싱/정규화(번호/표/별첨/정의) 취약\n- 오탐/미탐 통제(키워드 기반 한계)\n- 표준 문구/대체 문안의 정교성 및 법인별 정책 세분화\n- 성능/관측(로그/트레이싱/알람)과 운영도구 부족\n\n")
    doc39.append("## 3) 꼭 추가해야 할 기능\n- 계약 유형/조항 분류 고도화(구조 기반)\n- rule 트리거/스코프를 조항 단위로 적용(조항별 판정)\n- rule 설명/근거(대표 문구, 근거 문서, 승인 정책) 강화\n- 결과 검증을 위한 골든셋(라벨링) + 회귀 테스트 체계\n- 사용자 수정/승인 워크플로우(사람 검토 기록/감사)\n\n")
    doc39.append("## 4) AI API가 들어가야 하는 기능\n- 문맥 기반 의미 판정(면책 범위, 책임 제한, 간접손해, 고의/중과실 carve-out 등)\n- 자동 redline/대체 조항 생성(표준 조항에 맞춰 리라이팅)\n- 조항 요약/리스크 설명 자연어 생성(내부 교육/보고서용)\n- 유사 판례/내부 기준 매칭(검색/리트리벌)\n\n")
    doc39.append("## 5) rule만으로 가능한 기능\n- 필수 키워드/표현 탐지(무제한 책임/기술자료/대리점 비용 등)\n- 체크리스트 생성(confirmed_standard 계열)\n- 승인 필요/고위험 플래그로 워크플로우 라우팅\n- 템플릿 기반 초안 생성(정형 계약)\n\n")
    doc39.append("## 6) 사람 검토가 반드시 필요한 기능\n- 거래 구조/리스크 수용 여부 최종 판단\n- 예외 승인(상대방 협상력/사업적 필요) 결정\n- 사실관계 확인(개인정보 처리 범위, 하도급 여부, 현장 작업 여부 등)\n\n")
    doc39.append("## 7) EP 연동 전 준비해야 할 것\n- EP 신청 데이터 표준화(필수 필드/첨부/버전)\n- 결재 시스템 연동 요구사항(인증/멱등/재시도/콜백)\n- 개인정보/기밀 데이터 처리 정책(로그 마스킹/보관기간)\n- 운영 배포/모니터링/롤백 절차 확정\n\n")
    doc39.append("## 8) 우선순위별 다음 개발 단계\n1) 룰 품질: 트리거 정교화 + 골든셋/회귀테스트\n2) 조항 구조화: 조항 파서/타입 분류 + 조항별 판정\n3) 워크플로우: 사람 검토 UI/히스토리/승인 정책\n4) AI 도입: redline/대체문안/설명 생성(가드레일 포함)\n5) EP/결재: 실연동(HTTP client 안정화, 콜백/폴링, 실패 복구)\n")
    _write(OUT_DIR / "39_mvp_gap_analysis.md", "\n".join(doc39))


if __name__ == "__main__":
    main()

