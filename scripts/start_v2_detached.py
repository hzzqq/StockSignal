# -*- coding: utf-8 -*-
"""Start StockSignal frontend-v2 services detached from ANY console window.

真实故障（2026-11-09）：旧 start_frontend_v2.bat 用 `start` 打开一个可见 cmd
窗口跑 Vite，用户关掉该窗口（或启动器窗口）服务就停了。

修复：用与 startup_sim.py 相同的已验证方案 —— Windows 下
CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP，POSIX 下 start_new_session，
进程不依赖任何控制台窗口；stdout/stderr 落盘到 logs/。
关闭任何命令行窗口都不会停止服务；停止请用 _stop_services.bat（按端口 kill）
或 taskkill /f /t /pid <PID>。

日志：logs/backend_v2.log、logs/frontend_v2.log
状态：logs/active_ports_v2.json（记录实际端口与本启动器拉起的 PID）
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


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """只有真的有人在监听才返回 True（不推测、不编造）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.35)
        return sock.connect_ex((host, int(port))) == 0


def wait_http(url: str, timeout: float = 30.0) -> bool:
    """任意 <500 的 HTTP 响应都算服务已就绪（401/404 说明进程确实在跑）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                return int(resp.status) < 500
        except urllib.error.HTTPError as exc:
            return exc.code < 500
        except Exception:
            time.sleep(0.5)
    return False


def _spawn_kwargs() -> dict:
    """与控制台窗口解耦的关键参数。"""
    if os.name == "nt":
        return {"creationflags": WINDOWS_FLAGS}
    return {"start_new_session": True}


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
    candidate = os.environ.get("SS_NPM", "")
    if candidate and (Path(candidate).is_file() or shutil.which(candidate)):
        return candidate
    return shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"


def build_env(backend_port: int) -> dict:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("VITE_ENABLE_MOCKS", "false")
    if backend_port != 5050:
        env["VITE_PROXY_TARGET"] = f"http://127.0.0.1:{backend_port}"
    return env


def spawn(argv: list[str], cwd: Path, log: Path, env: dict) -> subprocess.Popen:
    """后台启动；父进程只保留 PID，日志句柄交给子进程。"""
    LOGS.mkdir(parents=True, exist_ok=True)
    handle = open(log, "w", encoding="utf-8", errors="replace")
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


def main() -> int:
    backend_port = int(os.environ.get("SS_BACKEND_PORT") or os.environ.get("STOCKSIGNAL_PORT") or "5050")
    frontend_port = int(os.environ.get("SS_V2_PORT") or os.environ.get("STOCKSIGNAL_V2_PORT") or "5173")
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

    LOGS.mkdir(parents=True, exist_ok=True)
    PORTS_FILE.write_text(
        json.dumps({"backend": backend_port, "v2": frontend_port, "pids": pids},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("Waiting for services to become ready (up to 30s)...")
    backend_ok = wait_http(f"http://127.0.0.1:{backend_port}/api/health")
    frontend_ok = wait_http(f"http://127.0.0.1:{frontend_port}/")
    print(f"  backend  : {'OK' if backend_ok else 'NOT READY'}")
    print(f"  frontend : {'OK' if frontend_ok else 'NOT READY'}")
    print("")
    print("Services run in the background with NO visible console window.")
    print("It is SAFE to close this window: the services keep running.")
    print(f"Stop them with _stop_services.bat (ports {backend_port} / {frontend_port}),")
    print("or: taskkill /f /t /pid <PID>  using the PIDs printed above.")
    print("Logs: logs/backend_v2.log , logs/frontend_v2.log")
    print(f"State: {PORTS_FILE.relative_to(ROOT)}")

    if os.environ.get("SS_NO_BROWSER") != "1" and frontend_ok:
        webbrowser.open(f"http://127.0.0.1:{frontend_port}/", new=2)

    return 0 if (backend_ok and frontend_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
