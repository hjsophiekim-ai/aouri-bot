"""저장된 실행의 clause_meta.change_set 을 실제 데모 화면 코드로 그려 캡처한다(서버·AI 없이 화면만 확인).

Usage: python scripts/ui_preview_change_set.py RUN_DIR OUT_DIR
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def capture(page, out: Path, prefix: str = "pv") -> None:
    """결과 화면의 비교 영역을 여러 상태로 캡처한다(ui_e2e_capture 와 함께 쓴다)."""
    panel = page.locator("#csPanel")
    panel.screenshot(path=str(out / f"{prefix}_01_compare_panel.png"))
    page.locator("#csPanel .csTop").screenshot(path=str(out / f"{prefix}_02_summary.png"))
    first = page.locator("#csHigh .csCard").first
    if first.count():
        first.screenshot(path=str(out / f"{prefix}_03_first_high_card.png"))
        btn = first.locator(".csCtxBtn").first
        if btn.count():
            btn.click()
            first.screenshot(path=str(out / f"{prefix}_04_context_expanded.png"))
        first.locator(".csSeg button").nth(1).click()
        first.screenshot(path=str(out / f"{prefix}_05_clean_view.png"))
        first.locator(".csSeg button").nth(0).click()
    page.evaluate("() => { for (const id of ['csOtherWrap','csHeldWrap']) { const d = document.getElementById(id); if (d) d.open = true; } }")
    page.locator("#csOtherWrap").screenshot(path=str(out / f"{prefix}_06_medium_low_open.png"))
    if page.locator("#csHeldWrap:not([hidden])").count():
        page.locator("#csHeldWrap").screenshot(path=str(out / f"{prefix}_07_held.png"))
    page.locator("#csConfirm").screenshot(path=str(out / f"{prefix}_08_confirmations.png"))
    page.set_viewport_size({"width": 390, "height": 900})
    page.wait_for_timeout(300)
    if first.count():
        first.screenshot(path=str(out / f"{prefix}_09_mobile_card.png"))
    page.set_viewport_size({"width": 1400, "height": 1000})


def main() -> int:
    from playwright.sync_api import sync_playwright

    from runtime.admin.internal_demo_chat_ui import INTERNAL_DEMO_CHAT_HTML

    run, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    meta = json.loads((run / "04_review_deep.json").read_text(encoding="utf-8"))["review"]["clause_meta"]
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=True)
        page = b.new_page(viewport={"width": 1400, "height": 1000})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.set_content(INTERNAL_DEMO_CHAT_HTML)
        page.evaluate("(m) => { document.querySelectorAll('.stage').forEach(s => s.classList.remove('active'));"
                      " document.getElementById('stageResult').classList.add('active');"
                      " analyzeState.deepDone = true; renderChangeSet(m); }", meta)
        page.wait_for_timeout(300)
        page.screenshot(path=str(out / "pv_00_full.png"), full_page=True)
        capture(page, out)
        b.close()
    print("errors:", errors)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
