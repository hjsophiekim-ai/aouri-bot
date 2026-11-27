"""실제 데모 화면으로 업로드 → 사전질문 답변 → 검토 → 화면 확인 → 다운로드 (2026-11-02 지시 9항).

내부 API 를 직접 부르지 않고 브라우저(헤드리스 Edge)로 화면을 조작한다. 화면 캡처와 다운로드 파일을 OUT 에 남기고,
판정 스크립트가 읽는 실행 기록(00~04)을 세션 파일에서 만든다.

Usage:
  python scripts/ui_e2e_capture.py --input X.pdf --out DIR --entity 시디즈 --contract-type "디자인 개발 용역계약서" \
      --review-focus-json cfg/review_focus.json --answers cfg/answers.json
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _answer_for(title: str, spec: dict[str, str]) -> str:
    for k, v in spec.items():
        if k.startswith("~") and re.search(k[1:], title):
            return v
    return spec.get("__default__", "확인 필요")


def main() -> None:
    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--entity", default="")
    ap.add_argument("--contract-type", default="")
    ap.add_argument("--review-focus-json", required=True)
    ap.add_argument("--answers", required=True)
    ap.add_argument("--base-url", default="http://127.0.0.1:8787")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rf = json.loads(Path(args.review_focus_json).read_text(encoding="utf-8"))["review_focus"]
    spec = json.loads(Path(args.answers).read_text(encoding="utf-8"))
    log: dict = {"input": args.input, "started_at": time.strftime("%Y-%m-%d %H:%M:%S"), "mode": "ui_playwright",
                 "review_focus": rf, "downloads": {}, "answered": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1000}, accept_downloads=True)
        page.goto(args.base_url + "/demo")
        # 파일을 먼저 붙인다 — 붙이는 순간 화면이 자동 분류로 법인·계약유형 칸을 채우므로, 사용자가 적은 값은 그 뒤에 넣는다.
        page.set_input_files("#file", args.input)
        page.wait_for_timeout(4000)
        page.fill("#entity", args.entity)
        page.fill("#contractType", args.contract_type)
        page.fill("#reviewFocus", rf)
        page.wait_for_timeout(500)
        page.screenshot(path=str(out / "ui_01_start.png"), full_page=True)
        page.click("#btnStart")

        # 사전질문: 봇이 묻는 질문 제목을 읽고 답한다.
        page.wait_for_function("() => (typeof questions !== 'undefined') && questions.length >= 0 && "
                               "document.getElementById('stageChat').classList.contains('active')", timeout=600_000)
        for _ in range(20):
            done = page.evaluate("() => qIndex >= questions.length")
            if done:
                break
            q = page.evaluate("() => { const q = questions[qIndex]; return q ? (q.title || q.question_id) : ''; }")
            ans = _answer_for(q, spec)
            log["answered"].append({"question": q, "answer": ans})
            page.fill("#answerInput", ans)
            page.click("#btnNext")
            page.wait_for_timeout(400)
        page.screenshot(path=str(out / "ui_02_questions.png"), full_page=True)

        # 정밀 검토 완료까지 — 검토의견서 패널이 그려지고 1차 결과가 아닐 때.
        log["review_wait_started"] = time.strftime("%H:%M:%S")
        for k in range(80):   # 최대 40분 — 30초마다 상태를 남긴다(멈춤 진단용)
            ok = page.evaluate("() => !!(analyzeState && analyzeState.deepDone === true "
                               "&& !document.getElementById('briefPanelWrap').hidden)")
            if ok:
                break
            stage = page.evaluate("() => (document.getElementById('analyzeStageBadge')||{}).innerText || ''")
            log.setdefault("wait_trace", []).append(f"{time.strftime('%H:%M:%S')} {stage}")
            if k % 6 == 5:
                page.screenshot(path=str(out / "ui_wait_last.png"))
            page.wait_for_timeout(30_000)
        else:
            (out / "00_run_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
            raise SystemExit("review did not finish in 40 min")
        log["review_done_at"] = time.strftime("%H:%M:%S")
        page.wait_for_timeout(1500)
        log["session_id"] = page.evaluate("() => ctx.session_id")
        page.screenshot(path=str(out / "ui_03_result_full.png"), full_page=True)
        # 계약 조항 좌우 비교 화면(기본 화면) — 요약·HIGH 카드·문맥 펼침·완성문 전환·MEDIUM/LOW·보류·확인사항·모바일
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "scripts"))
        from ui_preview_change_set import capture as _cs_capture
        page.evaluate("() => window.scrollTo(0, 0)")
        page.screenshot(path=str(out / "ui_03b_result_top.png"))
        _cs_capture(page, out, prefix="ui_cs")
        page.evaluate("() => { const d = document.getElementById('briefPanelWrap'); if (d) d.open = true; }")
        panel = page.locator("#briefPanel")
        panel.screenshot(path=str(out / "ui_04_brief_panel.png"))
        # 접힌 긴 문구까지 펼친 화면
        page.evaluate("() => document.querySelectorAll('#briefPanel details').forEach(d => d.open = true)")
        panel.screenshot(path=str(out / "ui_05_brief_panel_expanded.png"))
        # 변경 표시가 있는 첫 쟁점 카드 근처
        first_diff = page.locator("#briefPanel div:has-text('변경 표시 (빨간 취소선')").first
        if first_diff.count():
            first_diff.scroll_into_view_if_needed()
            page.screenshot(path=str(out / "ui_06_first_diff_view.png"))

        for name, sel in (("09_brief.docx", "#btnConfirmRevision"), ("10_brief.pdf", "#btnConfirmRevisionPdf"),
                          ("07_redline.docx", "#btnCsRedline"), ("08_clean.docx", "#btnCsClean")):
            with page.expect_download(timeout=600_000) as dl:
                page.click(sel)
            dl.value.save_as(str(out / name))
            log["downloads"][name] = {"bytes": (out / name).stat().st_size, "suggested": dl.value.suggested_filename}
        # 내부 상세 분석본(접힌 영역 안)
        page.evaluate("() => { const d = document.getElementById('internalDetail'); if (d) d.open = true; }")
        for name, sel in (("05_report.docx", "#btnInternalDocx"), ("06_report.pdf", "#btnInternalPdf")):
            with page.expect_download(timeout=600_000) as dl:
                page.click(sel)
            dl.value.save_as(str(out / name))
            log["downloads"][name] = {"bytes": (out / name).stat().st_size, "suggested": dl.value.suggested_filename}
        page.screenshot(path=str(out / "ui_07_after_downloads.png"), full_page=False)
        browser.close()

    sess = json.loads((ROOT / "runtime/data/question_sessions" / f"{log['session_id']}.json").read_text(encoding="utf-8"))
    log["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    log["ai"] = (sess.get("review_result") or {}).get("ai")
    (out / "00_run_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "01_upload.json").write_text(json.dumps({"question_session_id": log["session_id"], "questions": sess.get("questions")},
                                                   ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "02_answers.json").write_text(json.dumps(sess.get("answers") or {}, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "04_review_deep.json").write_text(json.dumps({"review": sess.get("review_result")}, ensure_ascii=False),
                                             encoding="utf-8")
    print("ui e2e done:", out, log["session_id"])


if __name__ == "__main__":
    main()
