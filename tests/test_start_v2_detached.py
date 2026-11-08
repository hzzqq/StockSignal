# -*- coding: utf-8 -*-
"""守卫：frontend-v2 后台常驻链路 + 停止链路必须真实有效。

真实故障（2026-11-09）：
1) start_frontend_v2.bat 用 `start` 打开可见 cmd 窗口跑 Vite，关窗口服务就没了；
2) 改成 VBS 隐藏 worker + Python detached 后，_stop_services.bat 却仍按 v1
   active_ports.json + 硬编码 5173 停止，既停不掉自定义端口，又会因裸
   `findstr ":port "` 命中 Foreign Address / TIME_WAIT / UDP 行而误杀无关进程；
3) 早期守卫全是 `in text` 子串判断，靠 .bat 头部 rem 注释就能喂饱。

本文件的 bat 断言一律先剥离注释/echo，只检查**可执行行**；并附真实反例测试。
"""
from __future__ import annotations

import importlib
import os
import re
import socket
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BAT = ROOT / "start_frontend_v2.bat"
STOP_BAT = ROOT / "_stop_services.bat"
SH = ROOT / "start_frontend_v2.sh"
VBS = ROOT / "start_frontend_v2_hidden.vbs"
LAUNCHER = ROOT / "scripts" / "start_v2_detached.py"
VITE_CFG = ROOT / "frontend-v2" / "vite.config.ts"


def _launcher_module():
    return importlib.import_module("scripts.start_v2_detached")


def _code_lines(path: Path) -> str:
    """只保留可执行行：rem / :: / echo / @echo 全部剔除。

    不这么做的话，把真正启动服务的两行注释掉、注释里留着关键字，守卫仍会全绿。
    """
    text = path.read_bytes().decode("ascii")
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        low = stripped.lower()
        if low.startswith(("rem ", "rem\t", "::", "@echo", "echo ", "echo.", "echo\t")):
            continue
        out.append(stripped)
    return "\n".join(out)


# ---------------------------------------------------------------- 启动链路

def test_bat_never_starts_a_visible_service_window():
    """除打开浏览器外不得用 start 启动任何服务，也不得暗示关窗口即停止。"""
    code = _code_lines(BAT)
    starts = [l for l in code.splitlines() if re.match(r"(?i)^start\s", l)]
    assert all("http://127.0.0.1:" in l for l in starts), \
        f"可见窗口 start 只能用于打开浏览器，发现服务窗口: {starts}"
    assert not re.search(r"(?mi)^start\s+\"StockSignal", code)
    assert "Close the" not in BAT.read_bytes().decode("ascii")


def test_bat_delegates_to_hidden_worker_on_executable_lines():
    """把真正启动的两行注释掉，本守卫必须变红（注释不能喂饱断言）。"""
    code = _code_lines(BAT)
    assert "start_frontend_v2_hidden.vbs" in code
    assert "wscript.exe //nologo" in code
    assert '"--worker"' in code
    assert "scripts\\start_v2_detached.py" in code
    assert "logs\\launcher_v2.log" in code
    assert "SS_NO_BROWSER" in code
    assert code.index("wscript.exe") < code.index('"%PY%" "%PROJECT_DIR%scripts\\start_v2_detached.py"')
    assert 'set "VITE_ENABLE_MOCKS=false"' in code
    assert "STOCKSIGNAL_USE_MOCKS" in code
    assert "_stop_services.bat" in BAT.read_bytes().decode("ascii")


def test_bat_wait_loop_accepts_only_tcp_listening_rows():
    code = _code_lines(BAT)
    netstat_lines = [l for l in code.splitlines() if "netstat" in l]
    assert netstat_lines, "启动脚本必须轮询端口"
    assert all("-p tcp" in l and "LISTENING" in l for l in netstat_lines), \
        f"裸端口匹配会把 TIME_WAIT / Foreign Address 误判成就绪: {netstat_lines}"
    assert 'findstr /C:":%V2_PORT% "' not in code


def test_hidden_vbs_is_hidden_and_does_not_wait():
    text = VBS.read_bytes().decode("ascii")
    assert "Option Explicit" in text
    assert "WScript.Arguments.Count" in text
    assert "cmd.exe /d /c" in text
    assert ", 0, False" in text, "0 = 隐藏窗口，False = 不等待（v1 已验证模式）"
    assert "sh.Run" in text


def test_both_bats_are_ascii_crlf():
    for path in (BAT, STOP_BAT):
        raw = path.read_bytes()
        raw.decode("ascii")
        assert b"\n" not in raw.replace(b"\r\n", b""), f"{path.name} 必须 CRLF"


# ---------------------------------------------------------------- 停止链路

def test_stop_services_reads_v2_state_and_only_kills_listening_tcp():
    code = _code_lines(STOP_BAT)
    assert "active_ports_v2.json" in code, "停止脚本必须读 v2 实际端口，否则自定义端口停不掉"
    assert "V2_BACKEND_PORT" in code
    assert "-p tcp" in code
    assert "LISTENING" in code
    assert 'findstr /C:":%~1 "' not in code, \
        "裸 ':port ' 匹配会误杀 Foreign Address / TIME_WAIT / UDP 行的无关进程"


def test_listen_pattern_rejects_foreign_timewait_udp_rows():
    """用真实 netstat 行格式反例验证 findstr /R 表达式的匹配边界。"""
    pattern = re.compile(r"^  TCP .*:5199 .* LISTENING")
    local_listen = "  TCP    127.0.0.1:5199    0.0.0.0:0              LISTENING       1234"
    ipv6_listen = "  TCP    [::]:5199          [::]:0                 LISTENING       4321"
    foreign = "  TCP    127.0.0.1:1092    127.0.0.1:5199        ESTABLISHED     5600"
    timewait = "  TCP    127.0.0.1:1092    127.0.0.1:5199        TIME_WAIT       0"
    udp = "  UDP    0.0.0.0:5199       *:*                                    8728"
    assert pattern.search(local_listen)
    assert pattern.search(ipv6_listen)
    for row in (foreign, timewait, udp):
        assert not pattern.search(row), f"误匹配无关行会误杀进程: {row}"


# ---------------------------------------------------------------- Python 启动器

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


def test_launcher_honesty_and_idempotency_contract():
    src = LAUNCHER.read_text(encoding="utf-8")
    assert 'BE_LOG = LOGS / "backend_v2.log"' in src
    assert 'FE_LOG = LOGS / "frontend_v2.log"' in src
    assert 'PORTS_FILE = LOGS / "active_ports_v2.json"' in src
    assert 'LOCK_FILE = LOGS / "start_v2.lock"' in src
    assert 'open(log, "a"' in src, "日志必须追加，崩溃现场不能被下一次启动截断"
    assert "SingleInstance(LOCK_FILE)" in src, "重复双击不得拉起两个 Vite"
    assert "port_in_use(backend_port)" in src
    assert "same_ports" in src and "effective_pids" in src, "重复启动不得抹掉已有真实 PID"
    assert "backend_ok" in src and "frontend_ok" in src, "状态文件必须记录真实健康结果"
    assert "SS_OPEN_BROWSER" in src, "浏览器只允许打开一次"
    assert "webbrowser.open" in src


def test_wait_http_keeps_waiting_on_5xx(monkeypatch):
    """旧实现收到 500 立即 return False；服务还在冷启动就被判失败。"""
    module = _launcher_module()

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    calls = {"n": 0}

    def fake(url, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.HTTPError(url, 500, "booting", None, None)
        return _Resp()

    monkeypatch.setattr(module.urllib.request, "urlopen", fake)
    monkeypatch.setattr(module.time, "sleep", lambda _s: None)
    assert module.wait_http("http://127.0.0.1:5199/", timeout=5) is True
    assert calls["n"] >= 3, "5xx 必须重试而不是一次判死"


def test_build_env_clears_stale_proxy_target(monkeypatch):
    """上一次自定义端口遗留的 VITE_PROXY_TARGET 必须被无条件覆盖。"""
    module = _launcher_module()
    monkeypatch.setenv("VITE_PROXY_TARGET", "http://127.0.0.1:5100")
    assert module.build_env(5050)["VITE_PROXY_TARGET"] == "http://127.0.0.1:5050"
    assert module.build_env(5100)["VITE_PROXY_TARGET"] == "http://127.0.0.1:5100"


def test_single_instance_lock_blocks_second_worker(tmp_path):
    module = _launcher_module()
    lock = tmp_path / "start_v2.lock"
    with module.SingleInstance(lock) as first:
        assert first is True
        with module.SingleInstance(lock) as second:
            assert second is False
    assert not lock.exists(), "锁必须在启动流程结束后释放"


def test_port_in_use_detects_real_listener_only():
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


# ---------------------------------------------------------------- 其它入口

def test_vite_uses_strict_port():
    assert "strictPort: true" in VITE_CFG.read_text(encoding="utf-8"), \
        "端口被占用时 Vite 静默漂移到 5174 会让整条停止/探测链路指向错误端口"


def test_sh_uses_the_same_detached_launcher():
    text = SH.read_text(encoding="utf-8")
    assert "scripts/start_v2_detached.py" in text
    assert "export VITE_ENABLE_MOCKS=false" in text
    assert "STOCKSIGNAL_USE_MOCKS" in text
    assert "nohup npm run dev" not in text
    assert "SS_OPEN_BROWSER" in text
    assert "npm.cmd" in text
    assert "The services keep running after this terminal is closed." in text
