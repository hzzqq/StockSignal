"""锁定 site_config 配置单源 + 不变量校验（REQUEST_TIMEOUT < CALL_TIMEOUT_CAP）。

确保换机器 / 改环境变量时：
- 默认配置满足「底层网络超时 < 单次调用硬边界」的防泄漏不变量
- 错误的 env 配置（CALL_TIMEOUT_CAP 过小）会被自动纠正并告警，而非静默留雷
"""
import importlib

import modules.site_config as sc


def _reload():
    return importlib.reload(sc)


def test_default_invariant():
    # 无 env 干预时默认满足不变量
    assert sc.REQUEST_TIMEOUT < sc.CALL_TIMEOUT_CAP


def test_invariant_enforced(monkeypatch):
    # 模拟错误的窄边界配置 -> 自动纠正
    monkeypatch.setenv("STOCKSIGNAL_REQ_TIMEOUT", "10")
    monkeypatch.setenv("STOCKSIGNAL_CALL_TIMEOUT", "5")  # 5 <= 10 错误
    try:
        mod = _reload()
        assert mod.CALL_TIMEOUT_CAP > mod.REQUEST_TIMEOUT
        assert mod.CALL_TIMEOUT_CAP == 12  # 10 + 2
    finally:
        monkeypatch.undo()
        _reload()  # 还原为默认，避免污染其他测试


def test_env_override_normal(monkeypatch):
    monkeypatch.setenv("STOCKSIGNAL_REQ_TIMEOUT", "8")
    monkeypatch.setenv("STOCKSIGNAL_CALL_TIMEOUT", "20")
    try:
        mod = _reload()
        assert mod.REQUEST_TIMEOUT == 8
        assert mod.CALL_TIMEOUT_CAP == 20
    finally:
        monkeypatch.undo()
        _reload()
