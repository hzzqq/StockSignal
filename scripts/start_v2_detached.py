# -*- coding: utf-8 -*-
"""Start StockSignal frontend-v2 services detached from ANY console window.

真实故障（2026-11-09）：旧 start_frontend_v2.bat 用 `start` 打开一个可见 cmd
窗口跑 Vite，用户关掉该窗口（或启动器窗口）服务就停了。

修复：用与 startup_sim.py 相同的已验证方案 —— Windows 下
CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP，POSIX 下 start_new_session，
进程不依赖任何控制台窗口；stdout/stderr 追加写 logs/。
关闭任何命令行窗口都不会停止服务；停止请用 _stop_services.bat（按端口 kill）。

日志：logs/backend_v2.log、logs/frontend_v2.log（追加，不截断）
状态：logs/active_ports_v2.json（真实端口 + 本启动器拉起的 PID + 健康结果）
并发：logs/start_v2.lock 单实例锁，防止重复双击拉起两个 Vite 抢端口
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
FE_DIR = ROOT / "frontend-v2"

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
WINDOWS_FLAGS = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP

BE_LOG = LOGS / "backend_v2.log"
FE_LOG = LOGS / "frontend_v2.log"
PORTS_FILE = LOGS / "active_ports_v2.json"
LOCK_FILE = LOGS / "start_v2.lock"
LOCK_STALE_SECONDS = 120


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """只有真的有人在监听才返回 True（不推测、不编造）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.35)
        return sock.connect_ex((host, int(port))) == 0


def wait_http(url: str, timeout: float = 30.0) -> bool:
    """2xx/3xx/4xx 都算服务已起；5xx 是启动期瞬态，继续等到 deadline。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if int(resp.status) < 500:
                    return True
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def _spawn_kwargs() -> dict:
    """与控制台窗口解耦的关键参数。"""
    if os.name == "nt":
        return {"creationflags": WINDOWS_FLAGS}
    return {"start_new_session": True}


def rotate_log(log: Path, max_bytes: int = 5_000_000) -> None:
    """日志超过阈值则轮转（保留最近一份 .1 历史），防止无限追加拖垮磁盘。

    仅在 spawn 真正要落盘前调用；轮转失败静默忽略，绝不阻断启动。
    """
    try:
        if not log.exists() or log.stat().st_size <= max_bytes:
            return
        rotated = log.with_name(log.name + ".1")
        try:
            rotated.unlink()
        except OSError:
            pass
        log.rename(rotated)
    except OSError:
        pass


def resolve_python() -> str:
    candidates = [
        os.environ.get("SS_PY", ""),
        str(ROOT / "venv" / "Scripts" / "python.exe"),
        str(Path(os.environ.get("USERPROFILE", "")) / ".workbuddy/binaries/python/envs/default/Scripts/python.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return sys.executable


def resolve_npm() -> str:
    """返回真正可执行的 npm 路径；shutil.which 结果优先于原始候选值。"""
    candidate = os.environ.get("SS_NPM", "")
    if candidate:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
        if Path(candidate).is_file():
            return candidate
    if os.name == "nt":
        return shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"
    return shutil.which("npm") or "npm"


def build_env(backend_port: int) -> dict:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("VITE_ENABLE_MOCKS", "false")
    # 无条件覆盖：清掉上一次自定义端口遗留的陈旧代理目标
    env["VITE_PROXY_TARGET"] = f"http://127.0.0.1:{backend_port}"
    return env


def spawn(argv: list[str], cwd: Path, log: Path, env: dict) -> subprocess.Popen:
    """后台启动；日志追加不截断，父进程只保留 PID。"""
    LOGS.mkdir(parents=True, exist_ok=True)
    rotate_log(log)
    handle = open(log, "a", encoding="utf-8", errors="replace")
    handle.write(f"\n==== spawn {time.strftime('%Y-%m-%d %H:%M:%S')} ====\n")
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            **_spawn_kwargs(),
        )
    finally:
        # 子进程持有自己的句柄副本；父进程关闭不影响它继续写日志
        handle.close()
    return proc


class SingleInstance:
    """原子文件锁，防止重复双击并发拉起两个 Vite；陈旧锁自动清理。"""

    def __init__(self, path: Path, stale_seconds: float = LOCK_STALE_SECONDS):
        self.path = path
        self.stale_seconds = stale_seconds
        self.held = False

    def _create(self) -> bool:
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("ascii"))
            os.close(fd)
            self.held = True
            return True
        except FileExistsError:
            return False

    def __enter__(self) -> bool:
        LOGS.mkdir(parents=True, exist_ok=True)
        if self._create():
            return True
        try:
            if time.time() - self.path.stat().st_mtime > self.stale_seconds:
                self.path.unlink()
                return self._create()
        except OSError:
            pass
        return False

    def __exit__(self, *_args) -> None:
        if self.held:
            try:
                self.path.unlink()
            except OSError:
                pass


def _previous_state() -> dict:
    try:
        return json.loads(PORTS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main() -> int:
    backend_port = int(os.environ.get("SS_BACKEND_PORT") or os.environ.get("STOCKSIGNAL_PORT") or "5050")
    frontend_port = int(os.environ.get("SS_V2_PORT") or os.environ.get("STOCKSIGNAL_V2_PORT") or "5173")

    with SingleInstance(LOCK_FILE) as locked:
        if not locked:
            print("Another v2 start is already in progress. Nothing to do; state file left untouched.")
            return 0
        return _run(backend_port, frontend_port)


def _run(backend_port: int, frontend_port: int) -> int:
    env = build_env(backend_port)
    python = resolve_python()
    npm = resolve_npm()

    print("=" * 54)
    print("  StockSignal Frontend v2 - background launcher")
    print("=" * 54)
    print(f"  Backend  : http://127.0.0.1:{backend_port}/api/health")
    print(f"  Frontend : http://127.0.0.1:{frontend_port}/")
    print(f"  Data     : real backend (MSW={env['VITE_ENABLE_MOCKS']})")
    print("=" * 54)

    previous = _previous_state()
    pids: dict[str, int] = {}

    if port_in_use(backend_port):
        print(f"[skip] backend already listening on {backend_port}")
    else:
        proc = spawn(
            [python, "-m", "flask", "--app", "backend.app:app", "run",
             "--host", "127.0.0.1", "--port", str(backend_port)],
            ROOT, BE_LOG, env,
        )
        pids["backend"] = proc.pid
        print(f"[start] backend PID={proc.pid} -> logs/backend_v2.log")

    if os.name == "nt":
        frontend_argv = ["cmd.exe", "/d", "/c", npm, "run", "dev", "--", "--port", str(frontend_port)]
    else:
        frontend_argv = [npm, "run", "dev", "--", "--port", str(frontend_port)]

    if port_in_use(frontend_port):
        print(f"[skip] frontend already listening on {frontend_port}")
    else:
        proc = spawn(frontend_argv, FE_DIR, FE_LOG, env)
        pids["frontend"] = proc.pid
        print(f"[start] frontend PID={proc.pid} -> logs/frontend_v2.log")

    print("Waiting for services to become ready (up to 30s)...")
    backend_ok = wait_http(f"http://127.0.0.1:{backend_port}/api/health")
    frontend_ok = wait_http(f"http://127.0.0.1:{frontend_port}/")
    print(f"  backend  : {'OK' if backend_ok else 'NOT READY'}")
    print(f"  frontend : {'OK' if frontend_ok else 'NOT READY'}")

    # 本进程没拉起任何服务时（例如重复启动、端口已被占用），不得抹掉已有真实 PID
    same_ports = previous.get("backend") == backend_port and previous.get("v2") == frontend_port
    effective_pids = pids or (previous.get("pids") if same_ports else {})
    LOGS.mkdir(parents=True, exist_ok=True)
    PORTS_FILE.write_text(
        json.dumps({
            "backend": backend_port,
            "v2": frontend_port,
            "pids": effective_pids,
            "backend_ok": backend_ok,
            "frontend_ok": frontend_ok,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("")
    print("Services run in the background with NO visible console window.")
    print("It is SAFE to close this window: the services keep running.")
    print(f"Stop them with _stop_services.bat (ports {backend_port} / {frontend_port}),")
    print("or: taskkill /f /t /pid <PID>  using the PIDs printed above.")
    print("Logs: logs/backend_v2.log , logs/frontend_v2.log")
    print(f"State: {PORTS_FILE.relative_to(ROOT)}")

    # .bat 的可见窗口负责打开浏览器；.sh 通过 SS_OPEN_BROWSER=1 让这里打开一次
    if (os.environ.get("SS_NO_BROWSER") != "1"
            and os.environ.get("SS_OPEN_BROWSER") == "1" and frontend_ok):
        webbrowser.open(f"http://127.0.0.1:{frontend_port}/", new=2)

    return 0 if (backend_ok and frontend_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
