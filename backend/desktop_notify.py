"""
backend/desktop_notify.py
=========================
智能条件单触发时的本机桌面弹窗通知（Windows）。

设计约束：
- 仅在 Windows 生效；非 Windows 仅打印日志，绝不抛错、绝不影响调度/下单。
- 通知在独立守护线程中弹出，绝不阻塞条件单调度器线程。
- 任何异常都被吞掉并记日志，保证下单与调度逻辑不受影响。
- 可用环境变量 STOCKSIGNAL_COND_NOTIFY=0 关闭（如不需要弹窗时）。
- MessageBoxW 是模态窗口，用户不关闭就一直存在；为避免短时多次触发导致
  模态弹窗/线程无上限堆积，用 _MAX_ACTIVE 限制同时存在的弹窗数，超限则丢弃并记日志。
"""
from __future__ import annotations

import logging
import os
import platform
import threading

logger = logging.getLogger("stocksignal.desktop_notify")

# 同时最多允许存在的模态弹窗数（防止连环触发时弹窗/线程无上限堆积）
_MAX_ACTIVE = 5
# 标题/正文长度上限（MessageBoxW 能显示超长文本但体验差，且防御异常超长输入）
_TITLE_MAX = 120
_MESSAGE_MAX = 1000

_active_lock = threading.Lock()
_active_count = 0


def _active_popups() -> int:
    """当前正在显示的模态弹窗数（供测试/诊断用）。"""
    with _active_lock:
        return _active_count


def notify(title: str, message: str) -> None:
    """触发一次本机桌面弹窗（异步、非阻塞）。

    调用方无需关心平台 / 是否成功：失败只记日志。
    """
    if os.environ.get("STOCKSIGNAL_COND_NOTIFY", "1") == "0":
        return
    if platform.system().lower() != "windows":
        logger.info("[桌面通知-非Windows跳过] %s | %s", title, message)
        return

    title = str(title)[:_TITLE_MAX]
    message = str(message)[:_MESSAGE_MAX]

    global _active_count
    with _active_lock:
        if _active_count >= _MAX_ACTIVE:
            logger.warning(
                "桌面弹窗已达并发上限 %d，丢弃本次通知: %s", _MAX_ACTIVE, title
            )
            return
        _active_count += 1

    t = threading.Thread(
        target=_worker, args=(title, message),
        name="desktop-notify", daemon=True,
    )
    t.start()


def _worker(title: str, message: str) -> None:
    global _active_count
    try:
        _popup(title, message)
    except Exception as e:  # noqa: BLE001 - 任何异常都不该影响主流程
        logger.warning("桌面弹窗失败（不影响下单/调度）: %s", e)
    finally:
        with _active_lock:
            _active_count -= 1


def _popup(title: str, message: str) -> None:
    """通过 Win32 MessageBoxW 弹出一个系统级置顶窗口（零依赖）。"""
    import ctypes

    MB_OK = 0x0
    MB_ICONINFORMATION = 0x40
    MB_TOPMOST = 0x40000
    ctypes.windll.user32.MessageBoxW(
        0, message, title, MB_OK | MB_ICONINFORMATION | MB_TOPMOST
    )
