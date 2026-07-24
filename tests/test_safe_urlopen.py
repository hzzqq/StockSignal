"""test_safe_urlopen.py — _safe_urlopen 重试/退避的回归测试

背景：修复前 _safe_urlopen 在循环体内错误地递归调用了自身（而非 urllib.request.urlopen），
一旦遇到瞬时网络错误（URLError/timeout 等）会无限递归直到 RecursionError，
且 retries/backoff 退避逻辑从未真正生效。本文件锁定该行为。
"""

import urllib.request
import urllib.error

import pytest

from modules import fetcher


class TestSafeUrlopenRetry:
    """验证瞬时错误重试、HTTPError 不重试、无限递归已修复。"""

    def test_transient_error_raises_original_not_recursion(self, monkeypatch):
        """瞬时失败应抛出原始异常，而非 RecursionError（无限递归）。"""
        calls = {"n": 0}

        def fake_urlopen(req, timeout=None):
            calls["n"] += 1
            raise urllib.error.URLError("simulated transient failure")

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(urllib.error.URLError):
            fetcher._safe_urlopen("req", timeout=5, retries=1, backoff=0)
        # 重试 1 次 + 首次，最多 2 次调用；绝不无限递归
        assert calls["n"] == 2

    def test_retries_then_succeeds(self, monkeypatch):
        """第 1 次瞬时失败、第 2 次成功 → 返回成功结果并记录了 2 次调用。"""
        calls = {"n": 0}

        def fake_urlopen(req, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise urllib.error.URLError("t1")
            return "OK"

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        assert fetcher._safe_urlopen("req", timeout=5, retries=2, backoff=0) == "OK"
        assert calls["n"] == 2

    def test_exhausts_retries_then_raises(self, monkeypatch):
        """重试耗尽后抛出最后的瞬时异常（不静默吞掉）。"""
        calls = {"n": 0}

        def fake_urlopen(req, timeout=None):
            calls["n"] += 1
            raise urllib.error.URLError("always fail")

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(urllib.error.URLError):
            fetcher._safe_urlopen("req", timeout=5, retries=2, backoff=0)
        assert calls["n"] == 3  # 首次 + 2 次重试

    def test_http_error_not_retried(self, monkeypatch):
        """业务层 HTTPError 不重试，立即抛出（避免对 4xx/5xx 无意义重试）。"""
        calls = {"n": 0}

        def fake_urlopen(req, timeout=None):
            calls["n"] += 1
            raise urllib.error.HTTPError(None, 503, "service unavailable", None, None)

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(urllib.error.HTTPError):
            fetcher._safe_urlopen("req", timeout=5, retries=3, backoff=0)
        assert calls["n"] == 1  # 不重试
