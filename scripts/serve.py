"""아우리봇 로컬 서버 supervisor — 콘솔 신호와 부모 프로세스로부터 분리해 띄운다.

왜 이렇게까지 하나 (2026-09-14)
──────────────────────────
서버가 하루에 여섯 번 조용히 사라졌다. 화면에는 "서버 연결 오류 (업로드):
Failed to fetch" 또는 "검토 시작을 눌러도 페이지가 안 넘어감" 으로만 보였다.

로그를 남기고 보니 **매번 마지막 줄이 `^C`** 였다. 크래시가 아니라
**CTRL_C_EVENT** 를 받고 종료된 것이다. 터미널에서 `start` 로 띄우든 배치
supervisor 로 띄우든, 그 프로세스가 부모 콘솔과 같은 **프로세스 그룹**에
남아 있으면 부모 쪽에서 명령 하나가 끝나거나 중단될 때 Ctrl+C 가 그룹 전체로
전파된다. 서버는 그 신호를 그대로 맞는다.

그래서 세 가지를 동시에 건다.

  1. `DETACHED_PROCESS`        — 콘솔 자체를 물려받지 않는다.
  2. `CREATE_NEW_PROCESS_GROUP`— Ctrl+C 가 전파되는 그룹에서 빠져나온다.
  3. `SIGINT` 무시             — 그래도 신호가 오면 무시한다(이중 방어).

추가로 `CREATE_BREAKAWAY_FROM_JOB` 을 시도한다 — 부모가 Job Object 로 자식을
묶어 두는 환경(일부 터미널·에이전트 하네스)에서 부모가 정리될 때 같이 죽는
것을 막는다. 그 job 이 breakaway 를 허용하지 않으면 조용히 빼고 재시도한다.

그래도 부족했다 (2026-09-14 2차)
──────────────────────────────
위 세 가지를 전부 걸고도 서버가 `exit=3221225786` 으로 죽었다. 이 값은
`0xC000013A` = **STATUS_CONTROL_C_EXIT** 이다. 즉 프로세스 생성 플래그로
빠져나왔다고 생각한 뒤에도 콘솔 Ctrl+C 이벤트가 여전히 도달하고 있었다.

그래서 마지막 수단으로 **Windows 작업 스케줄러**를 쓴다(`--install-task`).
스케줄러가 띄운 프로세스는 어떤 콘솔에도 속하지 않고, 이 터미널의 자식도
아니다. 콘솔 제어 이벤트가 닿을 경로 자체가 없다.

    python scripts/serve.py --install-task   # 등록 + 즉시 기동 (로그온 시 자동)
    python scripts/serve.py --uninstall-task # 등록 해제

사용법
──────
    python scripts/serve.py --install-task  # 권장. 스케줄러에 등록하고 띄운다
    python scripts/serve.py                # 분리 기동(콘솔 신호에 약할 수 있다)
    python scripts/serve.py --foreground   # 이 콘솔에서 직접 돌린다(디버그용)
    python scripts/serve.py --stop         # 떠 있는 서버를 내린다
    python scripts/serve.py --status       # 상태 확인

또는 `scripts\\serve.cmd` (같은 일을 한다).
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# cwd 에 의존하지 않는다 — 이 파일 위치 기준으로 code repo 루트를 잡는다
# (tech_repo_layout: 외부 aouribot 아래에 runtime 트리를 만들지 말 것).
ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
PID_FILE = LOG_DIR / "server.pid"

HOST = "127.0.0.1"
PORT = 8787
RESTART_DELAY_SEC = 3
#: 기동 직후 죽으면 재시작해도 같은 결과다(포트 충돌·설정 오류). 그만둔다.
MIN_HEALTHY_RUN_SEC = 5
MAX_RAPID_FAILURES = 3

# Windows 프로세스 생성 플래그. 다른 OS 에서는 0 이라 영향이 없다.
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_BREAKAWAY_FROM_JOB = 0x01000000

#: 서버 자식에게 주는 플래그. **콘솔을 갖지 않게** 하는 것이 핵심이다.
#:
#: 콘솔이 없는 부모에서 콘솔 앱을 띄우면 Windows 가 자식에게 새 콘솔을
#: 할당하고, 그 콘솔로 Ctrl+C 가 도달한다. 프로세스 그룹만 바꾸는 것으로는
#: 막지 못했다 — 서버가 계속 exit=0xC000013A 로 죽었다(2026-09-15 실측).
_CHILD_FLAGS = (
    (_DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0
)

#: 자식 안에서 한 번 더 막는다 — 신호가 어떻게든 도달해도 무시하고 계속 돈다.
#: runtime/app.py 를 건드리지 않기 위해 런처에서 감싼다.
_SERVER_BOOTSTRAP = (
    "import signal, runpy\n"
    "for _s in (getattr(signal, 'SIGINT', None), getattr(signal, 'SIGBREAK', None)):\n"
    "    if _s is not None:\n"
    "        try:\n"
    "            signal.signal(_s, signal.SIG_IGN)\n"
    "        except (ValueError, OSError):\n"
    "            pass\n"
    "runpy.run_module('runtime.app', run_name='__main__')\n"
)


def _use_utf8_streams() -> None:
    """콘솔 기본 코드페이지가 CP949 라 '—' 같은 문자에서 print 가 죽는다.

    실측: supervisor 가 첫 로그 한 줄에서 UnicodeEncodeError 로 즉사했고,
    콘솔이 없는 분리 프로세스라 그 트레이스백조차 보이지 않았다.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def _child_env() -> dict[str, str]:
    """자식 프로세스도 같은 이유로 죽지 않게 한다."""
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    return env


def _log_path() -> Path:
    return LOG_DIR / f"server_{datetime.now():%Y%m%d}.log"


def _log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}"
    try:
        print(line, flush=True)
    except Exception:  # noqa: BLE001
        # 콘솔에 못 쓰더라도 파일 기록은 반드시 남긴다 — 로그가 없으면
        # 다음에 또 원인을 못 찾는다. pythonw 로 돌면 sys.stdout 이 None
        # 이라 AttributeError 까지 난다(작업 스케줄러 기동 시 실제 발생).
        pass
    with _log_path().open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _port_in_use() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((HOST, PORT)) == 0


def _health() -> dict[str, object] | None:
    try:
        with urllib.request.urlopen(f"http://{HOST}:{PORT}/health", timeout=3) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None


# ── 분리 기동 ────────────────────────────────────────────────────────────────

def spawn_detached() -> int:
    """supervisor 를 콘솔·프로세스 그룹에서 떼어 내 띄우고 그 PID 를 돌려준다."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-u", str(Path(__file__).resolve()), "--foreground"]
    base_flags = _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP

    # supervisor 자신의 출력도 파일로 받는다 — 콘솔이 없으므로 버리면 사라진다.
    out = (LOG_DIR / "supervisor.log").open("a", encoding="utf-8")
    for flags in (base_flags | _CREATE_BREAKAWAY_FROM_JOB, base_flags):
        try:
            proc = subprocess.Popen(  # noqa: S603 - 우리 자신을 다시 실행한다
                cmd,
                cwd=str(ROOT),
                stdout=out,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=flags if os.name == "nt" else 0,
                close_fds=True,
                env=_child_env(),
                start_new_session=(os.name != "nt"),
            )
            return proc.pid
        except OSError:
            # 부모 job 이 breakaway 를 허용하지 않는 환경 — 플래그를 빼고 재시도.
            continue
    raise RuntimeError("서버 프로세스를 띄우지 못했습니다.")


# ── supervisor 본체 ─────────────────────────────────────────────────────────

def run_supervisor() -> int:
    # 이 프로세스로 전달되는 Ctrl+C 는 무시한다. 새 프로세스 그룹으로 떼어냈어도
    # 환경에 따라 신호가 도달할 수 있고, 그때 서버가 통째로 내려갔다.
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except (ValueError, OSError):
        pass

    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")

    _log(f"supervisor 시작 (pid={os.getpid()}) — http://{HOST}:{PORT}/demo")
    _log(f"로그: {_log_path()}")

    attempt = 0
    rapid_failures = 0
    try:
        while True:
            if _port_in_use():
                _log(f"포트 {PORT} 를 다른 프로세스가 사용 중입니다. supervisor 를 종료합니다.")
                return 1

            attempt += 1
            _log(f"서버 기동 (#{attempt})")
            started = time.monotonic()

            with _log_path().open("a", encoding="utf-8") as fh:
                proc = subprocess.Popen(  # noqa: S603
                    [sys.executable, "-u", "-c", _SERVER_BOOTSTRAP],
                    cwd=str(ROOT),
                    stdout=fh,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    creationflags=_CHILD_FLAGS,
                    close_fds=True,
                    env=_child_env(),
                )
                code = proc.wait()

            ran_for = time.monotonic() - started
            _log(f"서버 종료 (exit={code}, 가동 {ran_for:.0f}초)")

            # 0xC000013A(STATUS_CONTROL_C_EXIT)는 설정·포트 문제가 아니라
            # 외부에서 들어온 신호다. 이걸로 supervisor 를 멈추면, 신호가
            # 몇 번 몰려온 것만으로 서버가 영구히 내려간다(실측).
            _killed_by_signal = (code or 0) in (0xC000013A, 0xC000013A - (1 << 32))
            if ran_for < MIN_HEALTHY_RUN_SEC and not _killed_by_signal:
                rapid_failures += 1
                if rapid_failures >= MAX_RAPID_FAILURES:
                    _log(
                        f"기동 직후 종료가 {rapid_failures}회 연속입니다 — 설정·포트 문제로 "
                        "보고 supervisor 를 종료합니다. 위 로그를 확인하세요."
                    )
                    return code or 1
            else:
                rapid_failures = 0

            _log(f"{RESTART_DELAY_SEC}초 후 다시 띄웁니다.")
            time.sleep(RESTART_DELAY_SEC)
    finally:
        PID_FILE.unlink(missing_ok=True)


# ── 제어 명령 ────────────────────────────────────────────────────────────────

TASK_NAME = "AouriBotServer"


def _pythonw() -> str:
    """콘솔 없이 도는 인터프리터. 없으면 python 을 그대로 쓴다."""
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return str(candidate) if candidate.exists() else sys.executable


def _schtasks(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603,S607
        ["schtasks", *args], capture_output=True, text=True, check=False,
    )


def cmd_install_task() -> int:
    """작업 스케줄러에 등록하고 즉시 기동한다.

    스케줄러가 띄운 프로세스는 어떤 콘솔에도 속하지 않는다. 이 터미널의
    자식도 아니므로 콘솔 Ctrl+C 이벤트가 닿을 경로가 없다 — 프로세스 생성
    플래그만으로는 막지 못했던 `STATUS_CONTROL_C_EXIT` 를 여기서 끊는다.

    관리자 권한은 필요 없다(현재 사용자 계정의 로그온 트리거 작업).
    """
    if os.name != "nt":
        print("작업 스케줄러 등록은 Windows 에서만 지원합니다.")
        return 1

    script = str(Path(__file__).resolve())
    action = f'"{_pythonw()}" "{script}" --foreground'
    created = _schtasks(
        "/create", "/tn", TASK_NAME, "/tr", action,
        "/sc", "onlogon", "/rl", "limited", "/f",
    )
    if created.returncode != 0:
        print("작업 등록 실패:")
        print((created.stdout or "") + (created.stderr or ""))
        return created.returncode

    print(f"작업 스케줄러에 등록했습니다: {TASK_NAME} (로그온 시 자동 기동)")

    # 이미 떠 있으면 중복 기동하지 않는다.
    if _health() is not None:
        print(f"이미 실행 중입니다 — http://{HOST}:{PORT}/demo")
        return 0
    if _port_in_use():
        print(f"포트 {PORT} 를 다른 프로세스가 쓰고 있습니다:  python scripts/serve.py --stop")
        return 1

    run = _schtasks("/run", "/tn", TASK_NAME)
    if run.returncode != 0:
        print("작업 실행 실패:")
        print((run.stdout or "") + (run.stderr or ""))
        return run.returncode

    for _ in range(40):
        time.sleep(1)
        if _health() is not None:
            print(f"준비 완료 — http://{HOST}:{PORT}/demo")
            print(f"로그: {_log_path()}")
            return 0
    print("40초 안에 응답하지 않았습니다. 로그를 확인하세요:")
    print(f"    {_log_path()}")
    return 1


def cmd_uninstall_task() -> int:
    if os.name != "nt":
        return 0
    _schtasks("/end", "/tn", TASK_NAME)
    deleted = _schtasks("/delete", "/tn", TASK_NAME, "/f")
    print("작업 등록 해제" if deleted.returncode == 0 else "등록된 작업이 없습니다.")
    return 0


def cmd_status() -> int:
    health = _health()
    if health is not None:
        print(f"서버 실행 중 — http://{HOST}:{PORT}/demo  (health={health})")
        return 0
    if _port_in_use():
        print(f"포트 {PORT} 는 열려 있으나 /health 응답이 없습니다.")
        return 2
    print("서버가 실행 중이 아닙니다.  python scripts/serve.py  로 띄우세요.")
    return 1


def cmd_stop() -> int:
    stopped = []
    if os.name == "nt":
        # 스케줄러로 띄운 경우 supervisor 는 PID 파일과 별개로 돌고 있다.
        if _schtasks("/end", "/tn", TASK_NAME).returncode == 0:
            stopped.append(f"scheduled task({TASK_NAME})")
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text(encoding="utf-8").strip())
            os.kill(pid, signal.SIGTERM)
            stopped.append(f"supervisor({pid})")
        except (ValueError, OSError, ProcessLookupError):
            pass
        PID_FILE.unlink(missing_ok=True)
    if os.name == "nt":
        # supervisor 를 내려도 서버 자식은 남을 수 있다. 포트를 쥔 쪽을 정리한다.
        subprocess.run(  # noqa: S603,S607
            ["powershell", "-NoProfile", "-Command",
             f"Get-NetTCPConnection -LocalPort {PORT} -State Listen -ErrorAction SilentlyContinue"
             " | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"],
            capture_output=True, check=False,
        )
        stopped.append(f"port {PORT} listener")
    print("종료: " + (", ".join(stopped) if stopped else "실행 중인 서버 없음"))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="아우리봇 로컬 서버")
    parser.add_argument("--foreground", action="store_true",
                        help="이 콘솔에서 supervisor 를 직접 실행(디버그용)")
    parser.add_argument("--stop", action="store_true", help="실행 중인 서버 종료")
    parser.add_argument("--status", action="store_true", help="상태 확인")
    parser.add_argument("--install-task", action="store_true",
                        help="작업 스케줄러에 등록하고 기동(권장 — 콘솔 신호에서 완전히 분리)")
    parser.add_argument("--uninstall-task", action="store_true", help="작업 스케줄러 등록 해제")
    args = parser.parse_args()
    _use_utf8_streams()

    if args.status:
        return cmd_status()
    if args.uninstall_task:
        return cmd_uninstall_task()
    if args.install_task:
        return cmd_install_task()
    if args.stop:
        return cmd_stop()
    if args.foreground:
        return run_supervisor()

    if _health() is not None:
        print(f"이미 실행 중입니다 — http://{HOST}:{PORT}/demo")
        return 0
    if _port_in_use():
        print(f"포트 {PORT} 를 다른 프로세스가 쓰고 있습니다. 먼저 정리하세요:")
        print("    python scripts/serve.py --stop")
        return 1

    pid = spawn_detached()
    print(f"서버를 분리 기동했습니다 (supervisor pid={pid}).")
    for _ in range(30):
        time.sleep(1)
        if _health() is not None:
            print(f"준비 완료 — http://{HOST}:{PORT}/demo")
            print(f"로그: {_log_path()}")
            print("종료하려면:  python scripts/serve.py --stop")
            return 0
    print("30초 안에 응답하지 않았습니다. 로그를 확인하세요:")
    print(f"    {_log_path()}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
