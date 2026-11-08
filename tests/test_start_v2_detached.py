# -*- coding: utf-8 -*-
"""守卫：frontend-v2 启动器必须后台常驻，关掉命令行窗口服务不能停。

真实故障（2026-11-09）：start_frontend_v2.bat 用 `start` 打开可见 cmd 窗口跑
Vite，脚本还写着 "Close the Frontend v2 console to stop the UI"。用户关掉那个
窗口，整个 v2 就没了。

修复（双保险）：
1) .bat 只作为状态显示窗口；服务由 start_frontend_v2_hidden.vbs 在隐藏
   console 中以 --worker 分支启动（v1 已生产验证的 WshShell.Run 0/False 模式），
   可见窗口与服务不共享控制台，关闭窗口不会下发 CTRL_CLOSE_EVENT；
2) scripts/start_v2_detached.py 用 CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
   拉起后端/Vite，日志落盘，按端口停止。
"""
from __future__ import annotations

import importlib
import os
import re
import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BAT = ROOT / "start_frontend_v2.bat"
SH = ROOT / "start_frontend_v2.sh"
VBS = ROOT / "start_frontend_v2_hidden.vbs"
LAUNCHER = ROOT / "scripts" / "start_v2_detached.py"


def _launcher_module():
    return importlib.import_module("scripts.start_v2_detached")


def test_bat_never_starts_a_visible_service_window():
    """不得再用 start 打开 Vite/后端可见窗口，也不得暗示关窗口即停止。"""
    text = BAT.read_bytes().decode("ascii")
    assert not re.search(r"(?m)^\s*start\s+\"StockSignal", text), \
        "启动脚本又用 start 开了可见服务窗口（关窗口会杀服务）"
    assert 'Close the "Frontend v2" console' not in text
    assert "Close the" not in text


def test_bat_delegates_to_hidden_worker_and_keeps_mock_default():
    text = BAT.read_bytes().decode("ascii")
    assert "scripts\\start_v2_detached.py" in text
    assert "start_frontend_v2_hidden.vbs" in text
    assert "wscript.exe //nologo" in text
    assert '"--worker"' in text
    assert "logs\\launcher_v2.log" in text
    assert "SS_NO_BROWSER" in text, "应允许不弹浏览器（自动化验证/无桌面环境）"
    # 可见窗口分支先拉起隐藏 worker，Python 启动器只在 worker 分支被调用
    assert text.index("wscript.exe") < text.index('"%PY%" "%PROJECT_DIR%scripts\\start_v2_detached.py"')
    assert 'set "VITE_ENABLE_MOCKS=false"' in text
    assert "STOCKSIGNAL_USE_MOCKS" in text
    assert "The services keep running after this window is closed." in text
    assert "_stop_services.bat" in text


def test_hidden_vbs_is_hidden_and_does_not_wait():
    text = VBS.read_bytes().decode("ascii")
    assert "Option Explicit" in text
    assert "WScript.Arguments.Count" in text
    assert "cmd.exe /d /c" in text
    assert ", 0, False" in text, "0 = 隐藏窗口，False = 不等待（v1 已验证模式）"
    assert "sh.Run" in text


def test_bat_is_ascii_crlf():
    raw = BAT.read_bytes()
    raw.decode("ascii")
    assert b"\n" not in raw.replace(b"\r\n", b""), "bat 必须 CRLF"


def test_launcher_uses_real_detached_flags():
    src = LAUNCHER.read_text(encoding="utf-8")
    assert "CREATE_NO_WINDOW" in src
    assert "CREATE_NEW_PROCESS_GROUP" in src
    assert "start_new_session" in src
    assert "stdin=subprocess.DEVNULL" in src
    assert "stdout=handle" in src and "stderr=subprocess.STDOUT" in src
    module = _launcher_module()
    if os.name == "nt":
        assert module.WINDOWS_FLAGS & module.CREATE_NO_WINDOW
        assert module.WINDOWS_FLAGS & module.CREATE_NEW_PROCESS_GROUP
        assert module._spawn_kwargs() == {"creationflags": module.WINDOWS_FLAGS}
    else:
        assert module._spawn_kwargs() == {"start_new_session": True}


def test_launcher_logs_and_state_paths():
    src = LAUNCHER.read_text(encoding="utf-8")
    assert 'BE_LOG = LOGS / "backend_v2.log"' in src
    assert 'FE_LOG = LOGS / "frontend_v2.log"' in src
    assert 'PORTS_FILE = LOGS / "active_ports_v2.json"' in src
    assert "port_in_use(backend_port)" in src, "端口已监听时应跳过，避免重复拉起"
    assert "webbrowser.open" in src


def test_port_in_use_detects_real_listener_only():
    """端口探测必须基于真实 socket，不允许恒真/恒假兜底。"""
    module = _launcher_module()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        assert module.port_in_use(port) is True
    free_port = None
    for _ in range(5):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            candidate = probe.getsockname()[1]
        if not module.port_in_use(candidate):
            free_port = candidate
            break
    assert free_port is not None, "找不到空闲端口，port_in_use 疑似恒真"


def test_sh_uses_the_same_detached_launcher():
    text = SH.read_text(encoding="utf-8")
    assert "scripts/start_v2_detached.py" in text
    assert "export VITE_ENABLE_MOCKS=false" in text
    assert "STOCKSIGNAL_USE_MOCKS" in text
    assert "nohup npm run dev" not in text, "旧 nohup 方式在 Windows Git Bash 关窗口时仍可能被回收"
    assert "The services keep running after this terminal is closed." in text
