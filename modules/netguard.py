"""
统一网络韧性护栏（项目级兜底，根治「akshare 取数卡死」）。

问题根因：akshare 底层（requests 与 urllib 两条路径）默认都不设 timeout。
当代理/上游挂起、或东方财富接口无响应时，调用会**无限阻塞**，表现为页面
spinner 一直转、「资金流向模块卡住」这类现象。此前的修复只在 fundflow 一处
打补丁，覆盖不全。

本模块一次性给两条传输层都注入默认超时：
- requests 层：给 Session.request 注入默认 timeout（覆盖 akshare 走 requests 的接口）。
- socket 层：socket.setdefaulttimeout 覆盖 akshare 走 **urllib**（东方财富）的接口——
  这类调用不经过 requests，上面那层拦不住，是「卡死」的主要来源。

在 modules/__init__.py 中调用 install_network_guard()，使任意页面首次
import modules.* 时即生效，覆盖全部 40+ 页面与所有取数模块，无需逐处手动加补丁。
幂等，重复调用无副作用。
"""
import os
import socket
import logging

from modules.site_config import REQUEST_TIMEOUT as _TIMEOUT

logger = logging.getLogger(__name__)

_installed = False


def install_network_guard():
    """安装 requests + socket 双层默认超时。幂等。"""
    global _installed
    if _installed:
        return

    # ── requests 层 ──
    try:
        import requests

        if not getattr(requests.Session.request, "_ss_timeout_patched", False):
            _orig = requests.Session.request

            def _patched(self, *a, **k):
                k.setdefault("timeout", _TIMEOUT)
                return _orig(self, *a, **k)

            _patched._ss_timeout_patched = True
            requests.Session.request = _patched
    except Exception as e:  # pragma: no cover - 防御性
        logger.warning(f"[netguard] requests 超时补丁安装失败：{e}")

    # ── socket 层（覆盖 urllib / 东方财富路径）──
    # 仅当尚无更严格的全局默认超时时设置，避免覆盖用户显式配置
    try:
        cur = socket.getdefaulttimeout()
        if cur is None or cur > _TIMEOUT:
            socket.setdefaulttimeout(_TIMEOUT)
    except Exception as e:  # pragma: no cover - 防御性
        logger.warning(f"[netguard] socket 超时补丁安装失败：{e}")

    _installed = True
    logger.info(f"[netguard] 已安装网络韧性护栏（默认超时 {_TIMEOUT}s，覆盖 requests + urllib 路径）")
