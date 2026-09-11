"""tests/test_request_utils.py — R89 共享 requests.Session 守卫。

验证：
1. ``get_session()`` 返回单例（连接池复用）。
2. 共享会话挂载了重试适配器（仅幂等 GET 重试）且继承代理环境变量。
3. ``http_get`` 默认带 site_config.REQUEST_TIMEOUT，且经共享会话发出。
4. POST 不在重试白名单（避免非幂等副作用）。
"""

import requests

import modules.request_utils as ru
from modules.site_config import REQUEST_TIMEOUT


def test_get_session_is_singleton():
    assert ru.get_session() is ru.get_session()


def test_session_has_retry_adapter_and_trust_env():
    s = ru.get_session()
    assert s.trust_env is True
    adapter = s.get_adapter("https://example.com")
    assert isinstance(adapter, requests.adapters.HTTPAdapter)
    assert adapter.max_retries.total == 3
    assert "GET" in adapter.max_retries.allowed_methods
    # POST 不重试（非幂等）
    assert "POST" not in adapter.max_retries.allowed_methods


def test_http_get_applies_default_timeout_via_shared_session():
    captured = {}

    class _FakeResp:
        status_code = 200

        def json(self):
            return {}

    s = ru.get_session()
    orig = s.request

    def _spy(method, url, **kw):
        captured.update(kw)
        captured["method"] = method
        captured["url"] = url
        return _FakeResp()

    s.request = _spy
    try:
        ru.http_get("https://example.test/api/x")
    finally:
        s.request = orig

    assert captured["method"] == "GET"
    assert captured["url"] == "https://example.test/api/x"
    assert captured["timeout"] == REQUEST_TIMEOUT  # 默认超时已注入
