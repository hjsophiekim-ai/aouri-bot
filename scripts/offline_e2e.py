"""AI 없이(결정적·무과금) 같은 HTTP 경로로 업로드→검토→다운로드를 돌린다.

현재 작업 트리 코드로 서버를 이 프로세스 안에 새로 띄운다(캐시·이전 세션 없음) — 떠 있는 운영
서버(8787)는 건드리지 않는다. 인자는 e2e_upload_review_download.py 와 같다(--base-url 제외).
끝나면 다운로드 산출물을 판정용 텍스트로 바꾼다.

Usage: python scripts/offline_e2e.py --input X --out-dir DIR [--entity ..] [--review-focus ..] [--answers ..]
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

# AI 키를 지우고 dotenv 를 끈다 — conftest.py 와 같은 방식.
os.environ["AOURIBOT_DOTENV_DISABLED"] = "1"
for _k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LLM_PROVIDER", "AI_PROVIDER"):
    os.environ.pop(_k, None)

from runtime.api.server import build_httpd  # noqa: E402
from runtime.rules.loader import RuleLoader  # noqa: E402
from runtime.services.query_service import RuleQueryService  # noqa: E402

import e2e_upload_review_download as e2e  # noqa: E402
import run_texts  # noqa: E402


def main() -> None:
    loader = RuleLoader()
    loader.load()
    httpd = build_httpd("127.0.0.1", 0, RuleQueryService(loader))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    sys.argv = [sys.argv[0], *sys.argv[1:], "--base-url", f"http://127.0.0.1:{port}"]
    try:
        e2e.main()
    finally:
        httpd.shutdown()
    out = Path(sys.argv[sys.argv.index("--out-dir") + 1])
    print(run_texts.convert(out))


if __name__ == "__main__":
    main()
