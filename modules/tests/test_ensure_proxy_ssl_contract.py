"""行为契约测试：modules.fundflow._ensure_proxy_and_ssl。

SDD+TDD (self-driving Cycle 73)：spec 冻结于 .workbuddy/specs/ensure_proxy_ssl_contract.md
覆盖 AC1-AC6（幂等 / 显式代理 / 直连 / 遗留代理清理 / SSL 红线默认不开 / SSL 绕过仅开发）。
重点：AC5 SSL 红线是「原来自驱模式(cycle 60-71)零行为覆盖」的安全关键路径。
mutation 实验见 spec 末段。
"""
import os

import pytest
import requests

from modules import fundflow as ff


PROXY_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """每个测试前：重置幂等标志 + 清掉代理/SSL 相关 env + 还原 requests.Session.request。"""
    monkeypatch.setattr(ff, "_patch_done", False)
    for k in PROXY_KEYS + ("STOCKSIGNAL_PROXY", "STOCKSIGNAL_SSL_BYPASS"):
        monkeypatch.delenv(k, raising=False)
    # 还原 requests.Session.request（_ensure_proxy_and_ssl 可能 patch 它）
    monkeypatch.setattr(requests.Session, "request", requests.Session.request)
    yield


def _patch_proxy_reachable(monkeypatch, reachable: bool):
    monkeypatch.setattr(ff, "_proxy_reachable", lambda *a, **k: reachable)


# ───────────────────────── AC1 幂等 ─────────────────────────
def test_ac1_idempotent_no_double_patch(monkeypatch):
    _patch_proxy_reachable(monkeypatch, False)
    ff._ensure_proxy_and_ssl()
    env_after_first = {k: os.environ.get(k) for k in PROXY_KEYS}
    # 第二次调用应为 no-op：env 不变、不抛、_patch_done 仍 True
    ff._ensure_proxy_and_ssl()
    assert ff._patch_done is True
    assert {k: os.environ.get(k) for k in PROXY_KEYS} == env_after_first


# ───────────────────────── AC2 显式代理 ─────────────────────────
def test_ac2_explicit_proxy_sets_env(monkeypatch):
    _patch_proxy_reachable(monkeypatch, False)  # 即便默认代理不可达，显式优先
    monkeypatch.setenv("STOCKSIGNAL_PROXY", "http://proxy.example:8080")
    ff._ensure_proxy_and_ssl()
    assert os.environ["HTTP_PROXY"] == "http://proxy.example:8080"
    assert os.environ["HTTPS_PROXY"] == "http://proxy.example:8080"
    assert os.environ["http_proxy"] == "http://proxy.example:8080"
    assert os.environ["https_proxy"] == "http://proxy.example:8080"


def test_ac2_explicit_proxy_does_not_override_existing(monkeypatch):
    _patch_proxy_reachable(monkeypatch, False)
    monkeypatch.setenv("STOCKSIGNAL_PROXY", "http://proxy.example:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://already-set:9999")  # 既有配置不被覆盖
    ff._ensure_proxy_and_ssl()
    assert os.environ["HTTPS_PROXY"] == "http://already-set:9999"
    assert os.environ["HTTP_PROXY"] == "http://proxy.example:8080"


# ───────────────────────── AC3 直连不设置代理 ─────────────────────────
def test_ac3_direct_no_proxy_env(monkeypatch):
    _patch_proxy_reachable(monkeypatch, False)
    ff._ensure_proxy_and_ssl()
    for k in PROXY_KEYS:
        assert os.environ.get(k) is None, f"{k} 不应被设置（走直连）"


# ───────────────────────── AC4 遗留本地代理清理 ─────────────────────────
def test_ac4_legacy_local_proxy_cleaned(monkeypatch):
    _patch_proxy_reachable(monkeypatch, False)
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:26561")
    monkeypatch.setenv("HTTPS_PROXY", "http://localhost:26561")
    ff._ensure_proxy_and_ssl()
    assert "HTTP_PROXY" not in os.environ, "遗留本地代理必须被 pop"
    assert "HTTPS_PROXY" not in os.environ, "遗留本地代理必须被 pop"


# ───────────────────────── AC5 SSL 红线(默认不开) ─────────────────────────
def test_ac5_ssl_verify_kept_by_default(monkeypatch):
    """默认（无 SSL_BYPASS）绝不 patch requests.Session.request，verify 保持默认。"""
    _patch_proxy_reachable(monkeypatch, False)
    orig = requests.Session.request
    ff._ensure_proxy_and_ssl()
    # 关键安全断言：Session.request 未被替换（没有关 TLS 校验）
    assert requests.Session.request is orig, "默认不得 patch requests.Session.request（SSL 红线）"


# ───────────────────────── AC6 SSL 绕过(仅开发) ─────────────────────────
def test_ac6_ssl_bypass_only_when_explicit(monkeypatch):
    """STOCKSIGNAL_SSL_BYPASS=1 才临时关闭 verify；且 pop 遗留代理逻辑不受影响。"""
    _patch_proxy_reachable(monkeypatch, False)
    monkeypatch.setenv("STOCKSIGNAL_SSL_BYPASS", "1")

    disable_calls = []
    import urllib3
    monkeypatch.setattr(urllib3, "disable_warnings", lambda *a, **k: disable_calls.append(1))

    # 先把 spy 设为 Session.request，让 _ensure_proxy_and_ssl 捕获 spy 作 _orig
    spy_calls = []
    def spy(self, method, url, *a, **k):
        spy_calls.append(k.get("verify"))
        return "dummy"
    monkeypatch.setattr(requests.Session, "request", spy)
    orig = requests.Session.request  # == spy

    ff._ensure_proxy_and_ssl()
    assert requests.Session.request is not orig, "SSL_BYPASS=1 应 patch Session.request"
    assert disable_calls, "SSL_BYPASS=1 应调用 urllib3.disable_warnings()"
    # 行为证明：SSL-patched 内部调 _orig(=spy)，verify 默认 False（无网络）
    requests.Session.request(object(), "GET", "http://x")
    assert spy_calls and spy_calls[0] is False, "SSL_BYPASS=1 应把 verify 默认 False"
