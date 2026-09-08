from __future__ import annotations

import os
import sys
from pathlib import Path

# aouri-bot/ 자체를 sys.path에 강제로 넣어, pytest가 어느 cwd(예: 상위 aouribot/
# 폴더)에서 호출되어도 "runtime" 패키지를 항상 이 위치 기준으로 찾도록 한다.
# 이 파일이 없으면 pytest의 rootdir 추론이 호출 시점의 cwd에 의존해,
# 다른 중첩 폴더의 동일 이름 트리를 잘못 읽을 위험이 있다.
_PROJECT_ROOT = str(Path(__file__).resolve().parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ── 테스트는 실제 API 키를 절대 쓰지 않는다 (2026-09-08) ─────────────────────
#
# `ai_mode` 기본값이 "auto"라서, canonical .env에 실제 키가 들어온 뒤로는
# test_api_server / test_integration_flow 같은 서버 테스트가 `create_ai_provider()`
# 를 통해 **실제 OpenAI 호출**을 하기 시작했다. 스위트 실행시간이 3분→10분+로
# 늘고 매 실행마다 과금이 발생했다.
#
# 그래서 세션 시작 시점에 .env 로딩을 끄고 키를 환경에서 제거한다. 결과적으로
# `load_ai_config()`는 provider="mock"을 돌려주고, 어떤 테스트도 실수로 유료
# 호출을 할 수 없다. 실제 파일은 읽지도 쓰지도 않는다.
#
# 실제 canonical .env를 봐야 하는 테스트(자동활성화 스모크)는 자기 setUp에서
# AOURIBOT_DOTENV_DISABLED를 직접 pop하고 tearDown에서 환경을 복원한다 —
# runtime/tests/test_entrypoint_dotenv_eager.py 참고.
#
# 실제 키로 통합검증이 필요하면: AOURIBOT_TEST_ALLOW_LIVE_AI=1 로 실행.
_SECRET_ENV_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "LAW_API_KEY",
    "LAW_API_ID",
)


def _allow_live_ai() -> bool:
    return (os.environ.get("AOURIBOT_TEST_ALLOW_LIVE_AI") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


if not _allow_live_ai():
    os.environ["AOURIBOT_DOTENV_DISABLED"] = "1"
    for _k in _SECRET_ENV_KEYS:
        os.environ.pop(_k, None)


def pytest_report_header(config) -> str:  # noqa: ANN001 - pytest hook
    if _allow_live_ai():
        return "aouribot: LIVE AI ENABLED (AOURIBOT_TEST_ALLOW_LIVE_AI=1) — real API calls will be billed"
    return "aouribot: dotenv disabled, API keys stripped — no live AI calls, real .env untouched"
