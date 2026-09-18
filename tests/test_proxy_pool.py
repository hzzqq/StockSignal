"""tests/test_proxy_pool.py — 代理 IP 池（离线 mock，不触网）。

覆盖：
- 默认关闭 / 显式启用
- 静态代理列表解析
- 候选采集解析（含脏数据过滤）
- 校验 + 轮换 + 全死回退
- request_utils 接入：封了换 IP、池空回退直连、本机不走代理
"""

import os
import time

import pytest

import modules.proxy_pool as pp
import modules.request_utils as ru


# ───────── 网络 mock 辅助 ─────────
class _FakeResp:
    def __init__(self, status=200, text=None, json_data=None):
        self.status_code = status
        self.text = text if text is not None else "{}"
        self._json = json_data if json_data is not None else {}

    def json(self):
        return self._json


class _FakeSession:
    def __init__(self, ok=True):
        self.ok = ok
        self.last_proxies = None

    def get(self, url, **kwargs):
        self.last_proxies = kwargs.get("proxies")
        if self.ok:
            return _FakeResp(status=200, json_data={"ip": "9.9.9.9"})
        raise RuntimeError("proxy dead")


@pytest.fixture
def fake_net(monkeypatch):
    """让 pool.validate / _collect 走假网络。"""
    sess = _FakeSession(ok=True)

    class _S:
        trust_env = False

        def get(self, url, **kwargs):
            return sess.get(url, **kwargs)

    monkeypatch.setattr(pp.requests, "Session", lambda: _S())
    # collect 源返回含脏数据 + 合法行的文本
    monkeypatch.setattr(
        pp.requests, "get",
        lambda url, timeout=10: _FakeResp(
            status=200,
            text="1.2.3.4:8080\n  garbage line \n8.8.8.8:3128\nhttp://bad\n",
        ),
    )
    return sess


# ───────── 池单元 ─────────
def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SS_PROXY_POOL", raising=False)
    assert pp.ProxyPool().enabled is False


def test_static_proxies_parsed(monkeypatch):
    monkeypatch.setenv("SS_PROXIES", "http://1.2.3.4:8080, 5.6.7.8:8888 ")
    pool = pp.ProxyPool(enabled=True)
    assert pool._static_provided is True
    assert "http://1.2.3.4:8080" in pool._candidates
    assert "http://5.6.7.8:8888" in pool._candidates


def test_collect_filters_garbage(fake_net):
    pool = pp.ProxyPool(enabled=True)
    pool._static_provided = False  # 强制走采集
    cands = pool._collect()
    assert "http://1.2.3.4:8080" in cands
    assert "http://8.8.8.8:3128" in cands
    assert all(c.startswith("http://") for c in cands)
    assert "http://bad" not in cands  # 无端口的脏行被过滤


def test_validate_and_apply_to_env(fake_net, monkeypatch):
    pool = pp.ProxyPool(enabled=True)
    pool._static_provided = False
    pool._candidates = ["http://1.2.3.4:8080", "http://5.6.7.8:8888"]
    pool._last_collect = time.time()  # 防止 ensure_fresh 重新采集覆盖手动候选
    cur = pool.apply_to_env()
    assert cur == "http://1.2.3.4:8080"
    assert os.environ.get("HTTPS_PROXY") == "http://1.2.3.4:8080"
    assert "http://1.2.3.4:8080" in pool._validated_ok


def test_rotation_on_failure(fake_net, monkeypatch):
    pool = pp.ProxyPool(enabled=True)
    pool._static_provided = False
    pool._candidates = ["http://1.2.3.4:8080", "http://5.6.7.8:8888"]
    pool._last_collect = time.time()
    pool.apply_to_env()
    assert pool._current == "http://1.2.3.4:8080"
    # 当前代理连续失败 3 次 → 标记死亡并轮换到下一个
    pool.report_failure(pool._current)
    pool.report_failure(pool._current)
    pool.report_failure(pool._current)
    pool.rotate_on_failure()
    assert pool._current == "http://5.6.7.8:8888"
    assert "http://1.2.3.4:8080" in pool._dead


def test_all_dead_clears_env(fake_net, monkeypatch):
    pool = pp.ProxyPool(enabled=True)
    pool._static_provided = False
    pool._candidates = ["http://1.2.3.4:8080"]
    pool._last_collect = time.time()
    pool.apply_to_env()
    pool.report_failure(pool._current)
    pool.report_failure(pool._current)
    pool.report_failure(pool._current)
    pool.rotate_on_failure()
    assert pool._current is None
    assert "HTTPS_PROXY" not in os.environ


# ───────── request_utils 接入 ─────────
class _FakeReqSession:
    def __init__(self):
        self.calls = []
        self._proxied_attempts = 0

    def get(self, url, **kwargs):
        proxies = kwargs.get("proxies")
        self.calls.append(proxies)
        # 仅第一次「带代理」的请求失败（模拟出口 IP 被封），其余（轮换后 / 直连）成功
        if proxies is not None:
            self._proxied_attempts += 1
            if self._proxied_attempts == 1:
                raise ConnectionError("egress blocked")
        r = _FakeResp(status=200, json_data={})
        return r

    def post(self, url, **kwargs):
        self.calls.append(kwargs.get("proxies"))
        return _FakeResp(status=200)


class _FakePool:
    def __init__(self, sequence):
        self.enabled = True
        self._seq = list(sequence)
        self._i = 0

    def acquire_for_request(self):
        if self._i < len(self._seq):
            return self._seq[self._i]
        return None

    def rotate_on_failure(self):
        self._i += 1


@pytest.fixture
def wire(monkeypatch):
    monkeypatch.setenv("SS_PROXY_POOL", "1")
    # T-128：本文件只应验证代理轮换逻辑本身。ru 的熔断/节流状态是模块级全局，
    # 其他测试（页面冒烟经 _verify_token 真打 127.0.0.1:5050）记账的冷却会泄漏进来，
    # 令本文件测试撞 CircuitOpenError。前后各清一次，与 test_request_governance 同范式。
    ru.reset_governance()
    fs = _FakeReqSession()
    monkeypatch.setattr(ru, "get_session", lambda: fs)
    yield fs
    ru.reset_governance()


def test_request_utils_rotates_proxy_on_failure(wire, monkeypatch):
    fake_pool = _FakePool([{"http": "http://p1", "https": "http://p1"},
                           {"http": "http://p2", "https": "http://p2"}])
    monkeypatch.setattr(pp, "get_proxy_pool", lambda: fake_pool)
    resp = ru.http_get("https://push2.eastmoney.com/api")
    assert resp.status_code == 200
    # 第一调用带代理1，第二调用（轮换后）带代理2
    assert wire.calls == [{"http": "http://p1", "https": "http://p1"},
                          {"http": "http://p2", "https": "http://p2"}]


def test_request_utils_fallback_direct_when_pool_empty(wire, monkeypatch):
    fake_pool = _FakePool([None])  # 无可用代理
    monkeypatch.setattr(pp, "get_proxy_pool", lambda: fake_pool)
    resp = ru.http_get("https://push2.eastmoney.com/api")
    assert resp.status_code == 200
    # 回退直连：最后一次调用不带 proxies
    assert wire.calls[-1] is None


def test_request_utils_local_host_not_proxied(wire, monkeypatch):
    fake_pool = _FakePool([{"http": "http://p1", "https": "http://p1"}])
    monkeypatch.setattr(pp, "get_proxy_pool", lambda: fake_pool)
    ru.http_get("http://127.0.0.1:5050/health")
    # 本机目标不应带代理
    assert wire.calls == [None]
