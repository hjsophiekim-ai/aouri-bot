"""거래 흐름 우선 검토 · 개인정보 처리 흐름 · 검토서↔Word 반영 대조 증거 (2026-11-12).

Usage: python scripts/check_privacy_linkage.py OUT_DIR
실제 HTTP 경로(업로드→답변→검토→다운로드)로 Word 파일까지 만들고, 시험별 기대값/실제값과 조항별 Word 반영 결과를 남긴다.
AI 없이 결정적으로 돈다. 결과: OUT_DIR/cases.md, OUT_DIR/cases.json, OUT_DIR/*.docx
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["AOURIBOT_DOTENV_DISABLED"] = "1"
for _k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
    os.environ.pop(_k, None)

from runtime.tests import test_privacy_term_linkage as T  # noqa: E402


def row(case: str, item: str, expected: str, actual: str, ok: bool) -> dict:
    return {"case": case, "item": item, "expected": expected, "actual": actual, "result": "통과" if ok else "실패"}


def reflection(run: dict) -> list[dict]:
    """검토서에 수정 문구로 실린 수정안마다: 위치·조치·문구 첫 줄·Word 적용 결과·수락본에서 찾은 조."""
    acc = run["accepted"]
    rep = {r["clause_id"]: r for r in run["meta"].get("redline_apply_report") or []}
    out = []
    for cr in run["review"]["clause_results"]:
        ri = cr.get("redline_instruction") or {}
        txt = str(ri.get("final_clause_text") or ri.get("replacement_text") or cr.get("suggested_rewrite") or "")
        if not (cr.get("has_rewrite_change") or cr.get("has_addition")) or str(cr.get("risk_tier")).upper() not in ("HIGH", "MEDIUM")                 or cr.get("keep_as_is") or cr.get("dedup_suppressed"):
            continue
        r = rep.get(cr["clause_id"], {})
        first = next((ln for ln in txt.split("\n") if len(ln.strip()) >= 15), txt)[:80]
        core = re.sub(r"^\s*(?:\(\d+\)|[①-⑳])\s*", "", first)[:40]
        where = ""
        for no in sorted({m.group(1) + (f"의{m.group(2)}" if m.group(2) else "") for p in acc
                          for m in [re.match(r"^\s*제\s*(\d+)\s*조(?:\s*의\s*(\d+))?", p)] if m}, key=lambda x: [int(y) for y in x.split("의")]):
            if core and core in " ".join(T.article_block(acc, no)):
                where = f"제{no.split('의')[0]}조" + (f"의{no.split('의')[1]}" if "의" in no else "")
                break
        action = {"insert_after": "추가", "new_clause": "추가(새 조)", "replace": "교체"}.get(str(ri.get("edit_type")), str(ri.get("edit_type")))
        if ri.get("held"):
            action = "보류"
        out.append({"clause_id": cr["clause_id"], "location": ri.get("edit_location") or cr.get("display_path"), "action": action,
                    "reason": str(cr.get("problem") or "")[:120], "proposal": first, "apply": r.get("status") or ("held" if ri.get("held") else "—"),
                    "hold_reason": str(ri.get("hold_reason") or r.get("reason") or "")[:100],
                    "found_in_word": where or ("—" if ri.get("held") else "없음")})
    return out


def main() -> int:
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    # 단계 단위(식권 — 요청서 원문 그대로, 번호 이어 쓴 요청)
    text = T.meal_text()
    st, crs = T.stage(text, T.meal_req(), "일룸홀딩스")
    r = st["role"]
    rows.append(row("식권", "우리 법인·역할(서명란 공란)", "고객회사(요청서 근거), 법인명은 서명 전 확인",
                    f"{r['our_label']} / {r['basis_kind']} / 서명 전 확인 {len(r['pre_sign_checks'])}건", r["our_label"] == "고객회사" and bool(r["pre_sign_checks"])))
    rr = {x["original_user_text"]: x for x in st["request_rows"]}
    ex = next(v for k, v in rr.items() if k.endswith("중도해지 가능 여부"))
    co = next(v for k, v in rr.items() if k.endswith("해지 시 위약금·비용"))
    rows.append(row("식권", "중도해지 가능 여부(별개 질문)", "임의 해지권 없음 + 제13·3·15조 연결 + 갱신 거절 경로",
                    ex["brief_answer"] + " / 근거 " + ", ".join(ex["relevant_clause_paths"]),
                    "조항은 없습니다" in ex["judgment"] and {"제13조", "제3조", "제15조"} <= set(ex["relevant_clause_paths"])))
    rows.append(row("식권", "해지 시 위약금(별개 질문)", "별지1 무료 → 0원, 정의 없는 '서비스 수수료', 자동 연장 적용, 제14조 정산",
                    co["brief_answer"], all(k in co["judgment"] for k in ("0원", "서비스 수수료", "자동 연장", "제14조"))))
    st2, _ = T.stage(text, T.MEAL_REQ_NUMBERED, "일룸홀딩스")
    rows.append(row("식권(번호 요청)", "'1. … 2. …' 한 줄 요청 분리", "질문 2개, 중도해지 질문 중복 없음",
                    " | ".join(x["original_user_text"] for x in st2["request_rows"]), len(st2["request_rows"]) == 2))
    pr = st["privacy"]
    acts = {a["key"]: a for a in pr["activities"]}
    rows.append(row("식권", "개인정보 흐름(제6~8조·종료·홍보 연결)", "명단 지정·가입·개인별 내역·관리자 화면·보관·홍보, 제8조 일반 조항 불충분",
                    "; ".join(f"{k}:{','.join(a['basis'])}" for k, a in acts.items()) + f" / 일반조항 {pr['generic_only']} / 홍보 {pr['promo'].get('path')}",
                    {"roster", "signup", "history", "admin", "retain"} <= set(acts) and pr["generic_only"] == ["제8조"]))
    held = [a for a in pr["activities"] if a["relation"].startswith("판단 보류")]
    rows.append(row("식권", "운영자료 없이 처리 관계 단정 금지", "후보가 여럿인 활동은 '판단 보류' + 확인 항목·개시 전 조건",
                    f"보류 {len(held)}/{len(pr['activities'])}건, 미제공 자료 {len(pr['docs_missing'])}건, 개시 전 조건 {len(pr['pre_launch'])}건",
                    all(a["relation"].startswith("판단 보류") for a in pr["activities"] if len(a["relation_candidates"]) > 1)))

    srv = T.Server()
    try:
        meal = srv.run(T.meal_docx(), T.meal_req(), "일룸홀딩스")
        outs = srv.run(T.OUTSOURCE_TXT, T.GENERAL_REQ, "퍼시스")
        sup = srv.run(T.SUPPLY_TXT, T.GENERAL_REQ, "퍼시스")
        for name, run in (("meal_voucher", meal), ("customer_support", outs), ("furniture_supply", sup)):
            (out_dir / f"{name}_redline.docx").write_bytes(run["redline"])
            if run["clean_status"] == 200:
                (out_dir / f"{name}_clean.docx").write_bytes(run["clean"])
            (out_dir / f"{name}_report.docx").write_bytes(run["report"])
        a15 = " ".join(T.article_block(meal["accepted"], "15"))
        rows.append(row("식권", "위약금 수정안이 실제 제15조에 적용", "Word 변경 수락본 제15조 안에 ③④ 문구",
                        a15[a15.find("③"):a15.find("③") + 90] if "③" in a15 else "없음",
                        "본 조의 위약금 산정 기준 금액은" in a15 and "손해배상액의 예정" in a15))
        fc = meal["meta"]["final_docx_check"]
        rows.append(row("식권", "Word 재검사·일치", "통과, 최종본 차단 없음, 앱·검토서·Word 일치",
                        f"{fc['status']} / 차단 {fc.get('final_blocked')} / 일치 {meal['meta']['output_consistency']['ok']} / 클린본 {meal['clean_status']}",
                        fc["status"] == "통과" and meal["meta"]["output_consistency"]["ok"] and meal["clean_status"] == 200))
        opr = outs["meta"]["deal_flow"]["privacy"]
        rows.append(row("다른 계약(상담 대행)", "'개인정보' 낱말 없이 고객 명단·관리자 조회 → 검토 시작", "활성, 명단 항목 추출, Word 에 제2조의2",
                        f"활성 {opr['active']} / 명단 {next(a['items'] for a in opr['activities'] if a['key'] == 'roster')} / "
                        f"제2조의2 {'있음' if T.article_block(outs['accepted'], '2의2') else '없음'}",
                        opr["active"] and bool(T.article_block(outs["accepted"], "2의2"))))
        sacc = " ".join(sup["accepted"])
        rows.append(row("다른 계약(원자재 납품)", "개인 정보 처리 없음 → 위탁·개인정보 조항 넣지 않음", "비활성, Word 에 '개인정보'·'위탁' 없음",
                        f"활성 {sup['meta']['deal_flow']['privacy']['active']} / 개인정보 {'개인정보' in sacc} / 위탁 {'위탁' in sacc}",
                        not sup["meta"]["deal_flow"]["privacy"]["active"] and "개인정보" not in sacc and "위탁" not in sacc))

        # 실패 주입
        from runtime.questions.storage import load_session, save_session
        from runtime.review.delivery_docs import finalize_review_meta

        doc = load_session(meal["sid"])
        r1 = copy.deepcopy(doc["review_result"])
        finalize_review_meta(doc, r1, build=T.dropping_build("link_penalty_scope", times=1))
        f1 = r1["clause_meta"]["final_docx_check"]
        rows.append(row("실패 주입(1회 누락)", "탐지 → 재생성 → 재검사", "1회차 NOT_IN_DOCX → 재생성 → 통과",
                        " / ".join(f"{h['round']}회차 문제 {len(h['problems'])}건 {h.get('repairs') or ''}" for h in f1["history"]) + f" → {f1['status']}",
                        f1["status"] == "통과" and len(f1["history"]) >= 2))
        r2 = copy.deepcopy(doc["review_result"])
        finalize_review_meta(doc, r2, build=T.dropping_build("link_penalty_scope", times=99))
        f2 = r2["clause_meta"]["final_docx_check"]
        d2 = copy.deepcopy(doc)
        d2["review_result"] = r2
        save_session(d2)
        try:
            body, code = srv.clean(meal["sid"])
        finally:
            save_session(doc)
        rows.append(row("실패 주입(계속 누락)", "'제안만 있음·파일 미반영' + 최종본 차단", "미통과·final_blocked·검토서 표시·클린본 409",
                        f"{f2['status']} / 차단 {f2['final_blocked']} / 미반영 {[x['location'] for x in f2['not_reflected']]} / "
                        f"검토서 표시 {'제안만 있음·파일 미반영' in json.dumps(r2['clause_meta']['business_brief'], ensure_ascii=False)} / 클린본 {code}",
                        f2["status"] == "미통과" and f2["final_blocked"] and code == 409))
        refl = reflection(meal)
        refl_o = reflection(outs)
    finally:
        srv.close()

    md = ["| 시험 | 항목 | 기대값 | 실제값 | 결과 |", "|---|---|---|---|---|"]
    for x in rows:
        md.append(f"| {x['case']} | {x['item']} | {x['expected']} | {x['actual'].replace('|', '/')} | {x['result']} |")
    for title, rf in (("식권 플랫폼 — 조항별 Word 반영", refl), ("상담 대행 — 조항별 Word 반영", refl_o)):
        md += ["", f"### {title}", "", "| 위치 | 조치 | 수정 이유 | 제안 문구(첫 줄) | Word 적용 | 수락본에서 찾은 조 | 보류 사유 |", "|---|---|---|---|---|---|---|"]
        for x in rf:
            md.append(f"| {x['location']} | {x['action']} | {x['reason'][:60]} | {x['proposal'][:60]} | {x['apply']} | {x['found_in_word']} | {x['hold_reason'][:60]} |")
    (out_dir / "cases.md").write_text("\n".join(md), encoding="utf-8")
    (out_dir / "cases.json").write_text(json.dumps({"rows": rows, "meal_reflection": refl, "outsourcing_reflection": refl_o,
                                                    "meal_privacy": pr, "meal_linkage": st["term_linkage"],
                                                    "failure_single": f1, "failure_persistent": {k: v for k, v in f2.items() if k != "docs"}},
                                                   ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("\n".join(md))
    return 0 if all(x["result"] == "통과" for x in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
