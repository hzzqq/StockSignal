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


def _drop_modules(monkeypatch):
    """卸载所有已加载的 modules.* 子模块，模拟「首个 modules.* 导入」场景。

    R71 修复：旧实现直接 ``sys.modules.pop`` 且不恢复——被弹模块重新导入后
    产生**新对象**，而其他测试文件在收集期已绑定旧引用（如 test_whitebox_fetcher
    顶层的 ``StockFetcher`` 类），导致后续 monkeypatch 打在新模块上、旧类方法
    读旧模块全局 ``_AK_OK``，出现顺序性 ``NameError: name 'ak' is not defined``。
    改用 ``monkeypatch.delitem``：测试结束由 pytest 自动把旧模块引用写回，
    保证 sys.modules 全局零污染。
    """
    for name in [k for k in sys.modules if k == "modules" or k.startswith("modules.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)


def test_netguard_applies_without_fundflow(monkeypatch):
    """导入一个不依赖 fundflow 的模块也应触发网络护栏。"""
    _drop_modules(monkeypatch)
    import modules.fetcher  # 该模块不导入 fundflow
    after = socket.getdefaulttimeout()
    from modules.site_config import REQUEST_TIMEOUT
    assert after == REQUEST_TIMEOUT, f"socket 默认超时未生效: {after}"

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
    prev = socket.getdefaulttimeout()
    socket.setdefaulttimeout(5.0)
    try:
        from modules.netguard import install_network_guard
        install_network_guard()
        assert socket.getdefaulttimeout() == 5.0
    finally:
        # R74 修复：恢复原全局默认超时，避免 5.0 污染后续网络相关测试
        socket.setdefaulttimeout(prev)


def test_drop_modules_leaves_no_residue():
    """R72 回归：_drop_modules 后 sys.modules 中 modules.* 必须完整恢复。

    旧实现直接 pop 不恢复，重载产生的新模块对象残留，导致其他测试文件
    收集期绑定的旧类引用失效（顺序性 NameError）。monkeypatch.delitem
    应确保测试结束后 modules.* 与测试前完全一致。
    """
    import sys as _sys
    from _pytest.monkeypatch import MonkeyPatch

    before = {k: v for k, v in _sys.modules.items() if k == "modules" or k.startswith("modules.")}
    import modules.fetcher  # noqa: F401 确保已加载

    mp = MonkeyPatch()
    # 模拟 _drop_modules 的行为（测试函数内执行）
    for name in list(_sys.modules):
        if name == "modules" or name.startswith("modules."):
            mp.delitem(_sys.modules, name, raising=False)
    # 弹掉后重新导入（产生新对象，模拟 netguard 测试）
    import importlib
    importlib.import_module("modules.fetcher")
    # 测试结束：monkeypatch 还原
    mp.undo()

    after = {k: v for k, v in _sys.modules.items() if k == "modules" or k.startswith("modules.")}
    # 关键：还原后模块对象应与测试前完全一致（引用相等）
    for k in before:
        assert k in after, f"缺失 {k}"
        assert after[k] is before[k], f"{k} 被替换为新对象（污染残留）"
