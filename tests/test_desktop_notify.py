"""
tests/test_desktop_notify.py
============================
校验 backend.desktop_notify 的通知调度不影响主流程且防止模态弹窗堆积：
- STOCKSIGNAL_COND_NOTIFY=0 时不弹窗、不起线程；
- 非 Windows 平台只记日志、不起线程；
- 并发上限：达到 _MAX_ACTIVE 后丢弃后续通知（防止连环触发堆积）；
- 标题/正文超长时被截断。
"""
from __future__ import annotations

import threading

from backend import desktop_notify


def test_disabled_env_no_thread(monkeypatch):
    monkeypatch.setenv("STOCKSIGNAL_COND_NOTIFY", "0")
    started = []
    monkeypatch.setattr(desktop_notify.threading, "Thread",
                        lambda *a, **k: started.append(1))
    desktop_notify.notify("t", "m")
    assert started == []


def test_non_windows_no_thread(monkeypatch):
    monkeypatch.delenv("STOCKSIGNAL_COND_NOTIFY", raising=False)
    monkeypatch.setattr(desktop_notify.platform, "system", lambda: "Linux")
    started = []
    monkeypatch.setattr(desktop_notify.threading, "Thread",
                        lambda *a, **k: started.append(1))
    desktop_notify.notify("t", "m")
    assert started == []


def test_concurrency_cap(monkeypatch):
    """模拟 Windows：达到并发上限后应丢弃后续通知，避免模态弹窗无限堆积。"""
    monkeypatch.delenv("STOCKSIGNAL_COND_NOTIFY", raising=False)
    monkeypatch.setattr(desktop_notify.platform, "system", lambda: "Windows")

    # 用一个不会真正启动/弹窗的假线程：记录创建次数
    created = []

    class _FakeThread:
        def __init__(self, *a, **k):
            created.append(1)

        def start(self):
            pass  # 不启动真实 worker → _active_count 不会被 finally 递减

    monkeypatch.setattr(desktop_notify.threading, "Thread", _FakeThread)

    # 复位计数
    with desktop_notify._active_lock:
        desktop_notify._active_count = 0

    for _ in range(desktop_notify._MAX_ACTIVE + 3):
        desktop_notify.notify("标题", "正文")

    # 只应创建 _MAX_ACTIVE 个线程，其余被丢弃
    assert len(created) == desktop_notify._MAX_ACTIVE
    assert desktop_notify._active_popups() == desktop_notify._MAX_ACTIVE

    # 清理
    with desktop_notify._active_lock:
        desktop_notify._active_count = 0


def test_truncation(monkeypatch):
    """标题/正文超长时被截断到上限。"""
    monkeypatch.delenv("STOCKSIGNAL_COND_NOTIFY", raising=False)
    monkeypatch.setattr(desktop_notify.platform, "system", lambda: "Windows")

    captured = {}

    class _FakeThread:
        def __init__(self, *a, **k):
            captured["args"] = k.get("args") or (a[1] if len(a) > 1 else None)

        def start(self):
            pass

    monkeypatch.setattr(desktop_notify.threading, "Thread", _FakeThread)
    with desktop_notify._active_lock:
        desktop_notify._active_count = 0

    desktop_notify.notify("T" * 500, "M" * 5000)
    title, message = captured["args"]
    assert len(title) == desktop_notify._TITLE_MAX
    assert len(message) == desktop_notify._MESSAGE_MAX

    with desktop_notify._active_lock:
        desktop_notify._active_count = 0
