"""
网络韧性护栏回归测试（离线可跑）。

验证 install_network_guard() 在任意 modules.* 首次导入时自动生效：
- socket 默认超时被设置（覆盖 akshare urllib / 东方财富路径，根治「卡死」）
- requests.Session.request 被注入默认超时（覆盖 akshare requests 路径）
- 幂等：重复调用不产生副作用或报错
- 即使导入的是「不依赖 fundflow」的模块（如 fetcher/compare），护栏也应生效
  （这是此前只在 fundflow 一处打补丁时的盲区）
"""
import importlib
import socket
import sys

import pytest


def _drop_modules():
    """卸载所有已加载的 modules.* 子模块，模拟「首个 modules.* 导入」场景。"""
    for name in [k for k in sys.modules if k == "modules" or k.startswith("modules.")]:
        sys.modules.pop(name, None)


def test_netguard_applies_without_fundflow():
    """导入一个不依赖 fundflow 的模块也应触发网络护栏。"""
    _drop_modules()
    import modules.fetcher  # 该模块不导入 fundflow
    after = socket.getdefaulttimeout()
    assert after == 15.0, f"socket 默认超时未生效: {after}"

    import requests
    assert getattr(requests.Session.request, "_ss_timeout_patched", False) is True


def test_netguard_idempotent():
    """重复调用 install_network_guard 不报错、不产生多重包装。"""
    from modules.netguard import install_network_guard
    install_network_guard()
    import requests
    wrapped = requests.Session.request
    install_network_guard()  # 第二次应直接 return，不重复包装
    assert requests.Session.request is wrapped


def test_netguard_respects_stricter_existing_timeout():
    """若已存在更严格的全局 socket 超时（<15s），护栏不应放宽它。"""
    socket.setdefaulttimeout(5.0)
    from modules.netguard import install_network_guard
    install_network_guard()
    assert socket.getdefaulttimeout() == 5.0
