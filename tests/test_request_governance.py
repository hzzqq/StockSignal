"""tests/test_request_governance.py — 请求治理层守卫（R91）。

覆盖三条治理能力 + 一条诚实口径红线：
  ① per-host 最小请求间隔（节流）
  ② 连续失败熔断（circuit breaker）+ 冷却后恢复
  ③ CircuitOpenError 必须是 RequestException 子类（否则会打穿调用方现有 except）
  ④ 快照回退必须如实标注 source；无快照时返回 unavailable，**绝不合成数据**

对照项目既有教训：上游限流曾把 baostock 全量刷新拖成 11h 只跑 1/3，
把腾讯行情卡在 2026-08-28 —— 这层就是为了不再被同一个坑埋第二次。
"""
import time

import pytest
import requests

import modules.request_utils as ru


class _FakeResp:
    def __init__(self, status=200):
        self.status_code = status


class _FakeSession:
    def __init__(self, status=200, exc=None):
        self.status = status
        self.exc = exc
        self.calls = 0

    def get(self, url, **kwargs):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return _FakeResp(self.status)


@pytest.fixture(autouse=True)
def _clean_governance():
    ru.reset_governance()
    yield
    ru.reset_governance()


def test_throttle_enforces_min_interval(monkeypatch):
    """同一 host 连续两次请求必须间隔 >= HOST_MIN_INTERVAL。"""
    monkeypatch.setattr(ru, "HOST_MIN_INTERVAL", 0.3)
    monkeypatch.setattr(ru, "get_session", lambda: _FakeSession())
    t0 = time.monotonic()
    ru.http_get("https://throttle.example.com/a")
    ru.http_get("https://throttle.example.com/b")
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.3, f"节流未生效，两次请求仅间隔 {elapsed:.3f}s"


def test_circuit_opens_after_consecutive_failures(monkeypatch):
    """连续失败达到阈值后熔断：第 N+1 次直接快速失败，不再硬等超时。"""
    monkeypatch.setattr(ru, "HOST_MIN_INTERVAL", 0.0)
    monkeypatch.setattr(ru, "FAIL_THRESHOLD", 3)
    monkeypatch.setattr(ru, "COOLDOWN_SECONDS", 30)
    sess = _FakeSession(exc=requests.ConnectionError("boom"))
    monkeypatch.setattr(ru, "get_session", lambda: sess)
    for _ in range(3):
        with pytest.raises(requests.ConnectionError):
            ru.http_get("https://down.example.com/x")
    with pytest.raises(ru.CircuitOpenError):
        ru.http_get("https://down.example.com/x")
    # 熔断后不应真的发出请求
    assert sess.calls == 3, "熔断后仍在打上游，失去了快速失败的意义"
    assert ru.breaker_stats()["down.example.com"]["cooling"] is True


def test_circuit_open_error_is_request_exception():
    """红线：必须是 RequestException 子类，否则调用方现有 except 兜不住。"""
    assert issubclass(ru.CircuitOpenError, requests.RequestException)


def test_success_resets_failure_counter(monkeypatch):
    """成功一次应清零连续失败计数并解除冷却。"""
    monkeypatch.setattr(ru, "HOST_MIN_INTERVAL", 0.0)
    monkeypatch.setattr(ru, "FAIL_THRESHOLD", 5)
    good = _FakeSession()
    monkeypatch.setattr(ru, "get_session", lambda: good)
    for _ in range(4):
        ru.record_failure("reset.example.com")
    assert ru.breaker_stats()["reset.example.com"]["consec_fail"] == 4
    ru.http_get("https://reset.example.com/ok")
    assert ru.breaker_stats()["reset.example.com"]["consec_fail"] == 0
    assert ru._in_cooldown("reset.example.com") is False


def test_circuit_recovers_after_cooldown(monkeypatch):
    """冷却结束后应恢复放通。"""
    monkeypatch.setattr(ru, "HOST_MIN_INTERVAL", 0.0)
    monkeypatch.setattr(ru, "FAIL_THRESHOLD", 2)
    monkeypatch.setattr(ru, "COOLDOWN_SECONDS", 0.2)
    monkeypatch.setattr(ru, "get_session",
                        lambda: _FakeSession(exc=requests.ConnectionError("boom")))
    for _ in range(2):
        with pytest.raises(requests.ConnectionError):
            ru.http_get("https://recover.example.com/x")
    assert ru._in_cooldown("recover.example.com") is True
    time.sleep(0.35)
    assert ru._in_cooldown("recover.example.com") is False


def test_fetch_with_snapshot_live_then_fallback(tmp_path):
    """成功→缓存；TTL 内复用；失败→回退真实快照并如实标注 source/as_of。"""
    d = str(tmp_path)
    calls = {"n": 0}

    def ok():
        calls["n"] += 1
        return {"v": calls["n"]}

    r1 = ru.fetch_with_snapshot("k1", ok, ttl=0, snapshot_dir=d)
    assert r1["source"] == "live" and r1["data"] == {"v": 1}

    r2 = ru.fetch_with_snapshot("k1", ok, ttl=600, snapshot_dir=d)
    assert r2["source"] == "snapshot" and r2["data"] == {"v": 1}

    def bad():
        raise RuntimeError("上游挂了")

    r3 = ru.fetch_with_snapshot("k1", bad, ttl=0, snapshot_dir=d)
    assert r3["source"] == "snapshot"
    assert r3["data"] == {"v": 1}
    assert r3["as_of"], "回退结果必须带快照时间，否则 UI 无法如实披露"
    assert "RuntimeError" in (r3["error"] or "")


def test_fetch_with_snapshot_never_fabricates(tmp_path):
    """红线：既没抓到、也无历史快照 → unavailable + data=None，绝不合成数据填充。"""
    def bad():
        raise RuntimeError("上游挂了")

    r = ru.fetch_with_snapshot("never_seen", bad, ttl=0, snapshot_dir=str(tmp_path))
    assert r["source"] == "unavailable"
    assert r["data"] is None
    assert r["as_of"] is None


def test_throttle_skips_localhost(monkeypatch):
    """本机后端不节流——给自家 Flask 加上限纯属自我伤害。"""
    monkeypatch.setattr(ru, "HOST_MIN_INTERVAL", 0.3)
    monkeypatch.setattr(ru, "get_session", lambda: _FakeSession())
    t0 = time.monotonic()
    ru.http_get("http://127.0.0.1:5050/a")
    ru.http_get("http://127.0.0.1:5050/b")
    ru.http_get("http://localhost:5050/c")
    elapsed = time.monotonic() - t0
    assert elapsed < 0.3, f"本机请求被误节流，耗时 {elapsed:.3f}s"
