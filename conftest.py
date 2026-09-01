from __future__ import annotations

import sys
from pathlib import Path

# aouri-bot/ 자체를 sys.path에 강제로 넣어, pytest가 어느 cwd(예: 상위 aouribot/
# 폴더)에서 호출되어도 "runtime" 패키지를 항상 이 위치 기준으로 찾도록 한다.
# 이 파일이 없으면 pytest의 rootdir 추론이 호출 시점의 cwd에 의존해,
# 다른 중첩 폴더의 동일 이름 트리를 잘못 읽을 위험이 있다.
_PROJECT_ROOT = str(Path(__file__).resolve().parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
