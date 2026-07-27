"""ssl_helper.ssl_bypass 行为测试。

验证 P0 整改后的安全红线：
- 默认（无 STOCKSIGNAL_SSL_BYPASS）不 patch requests，TLS 校验保持开启；
- 仅 STOCKSIGNAL_SSL_BYPASS=1 时局部 patch，退出后恢复；
- patch 后的请求强制注入 verify=False（绕过本机代理 TLS 拦截）。
"""
import os

import pytest
import requests
from modules.ssl_helper import ssl_bypass

# 保存 requests 库自带的原函数，任何测试结束后强制恢复，避免污染全局 Session.request
TRUE_ORIG = requests.Session.request


@pytest.fixture(autouse=True)
def _restore_request_after_test():
    yield
    requests.Session.request = TRUE_ORIG


def test_default_does_not_patch(monkeypatch):
    """默认无 env 时，requests.Session.request 不应被替换，TLS 校验保持开启。"""
    monkeypatch.delenv("STOCKSIGNAL_SSL_BYPASS", raising=False)
    with ssl_bypass():
        assert requests.Session.request is TRUE_ORIG, "默认不应 patch requests"
    assert requests.Session.request is TRUE_ORIG, "退出后应恢复原函数"


def test_env_triggers_patch_and_restores(monkeypatch):
    """设 STOCKSIGNAL_SSL_BYPASS=1 时，with 块内 patch、退出后恢复。"""
    monkeypatch.setenv("STOCKSIGNAL_SSL_BYPASS", "1")
    with ssl_bypass():
        assert requests.Session.request is not TRUE_ORIG, "env=1 时应 patch requests"
    assert requests.Session.request is TRUE_ORIG, "退出后必须恢复原函数"


def test_patched_injects_verify_false(monkeypatch):
    """patch 后的请求强制注入 verify=False（绕过本机代理 TLS 拦截）。"""
    monkeypatch.setenv("STOCKSIGNAL_SSL_BYPASS", "1")
    captured = {}

    def spy(self, *args, **kwargs):
        captured.update(kwargs)
        return None

    # 在 with 进入前替换为 spy，ssl_bypass 会把 spy 当作 _orig 捕获
    requests.Session.request = spy
    with ssl_bypass():
        session = requests.Session()
        session.request("GET", "https://example.com")
    assert captured.get("verify") is False, "patch 后必须注入 verify=False"


def test_default_with_env_unset_does_not_patch(monkeypatch):
    """即便其他测试改过 env，delenv 后默认仍不 patch。"""
    monkeypatch.setenv("STOCKSIGNAL_SSL_BYPASS", "0")
    with ssl_bypass():
        assert requests.Session.request is TRUE_ORIG, "env!=1 时不应 patch"
