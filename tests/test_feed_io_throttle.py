"""T-249 缓存加固 P2：_safe_urlopen 接入 per-host 节流（全离线，urlopen 打桩）。

背景（docs/data_cache_hardening.md §1.2/§三 P2）：fetcher 日线链路走
_feed_io._safe_urlopen 直连 urllib，此前**无 per-host 节流也无熔断**——荐股一轮
对新浪约 300+ 次请求（8 并发×每股 L3 竞速+失败重试 2 次），新浪 RemoteDisconnected
限流相当程度是「自己打自己」。P2 把 request_utils._throttle 语义延伸到该路径：
同一 host 两次请求（含重试尝试）之间至少间隔 SS_HOST_MIN_INTERVAL 秒，本机后端不节流。

mutation 基线：去掉 _throttle 接线 → test_same_host_second_call_delayed 变红。
"""
from __future__ import annotations

import os
import sys
import time
import urllib.error

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import modules._feed_io as feed_io  # noqa: E402
import modules.request_utils as ru  # noqa: E402
from modules._feed_io import _safe_urlopen  # noqa: E402


def _reset_gov(monkeypatch, interval="0.25"):
    """隔离治理状态：间隔改可测值、清空 per-host 时钟/熔断表。"""
    monkeypatch.setattr(ru, "HOST_MIN_INTERVAL", float(interval))
    monkeypatch.setattr(ru, "_last_call_at", {})
    monkeypatch.setattr(ru, "_consec_fail", {})
    monkeypatch.setattr(ru, "_cooldown_until", {})


def _install_fake_urlopen(monkeypatch, fail_first=0):
    """打桩 urllib.request.urlopen：记录调用时刻；可选前 N 次抛 URLError。"""
    calls = {"t": [], "n": 0}

    def fake_urlopen(req, timeout=None):
        calls["t"].append(time.monotonic())
        calls["n"] += 1
        if calls["n"] <= fail_first:
            raise urllib.error.URLError("simulated transient failure")
        return object()

    monkeypatch.setattr(feed_io.urllib.request, "urlopen", fake_urlopen)
    return calls


def test_same_host_second_call_delayed(monkeypatch):
    _reset_gov(monkeypatch, interval="0.25")
    calls = _install_fake_urlopen(monkeypatch)
    _safe_urlopen("http://sina.example.com/json_v2", timeout=1, retries=0)
    _safe_urlopen("http://sina.example.com/json_v2", timeout=1, retries=0)
    assert len(calls["t"]) == 2
    delta = calls["t"][1] - calls["t"][0]
    assert delta >= 0.24, f"同 host 第二次请求必须被节流（实测 {delta:.3f}s）"


def test_retry_attempts_also_throttled(monkeypatch):
    """重试尝试同样节流（新浪限流正是被「瞬时失败×重试」打出来的）。"""
    _reset_gov(monkeypatch, interval="0.2")
    calls = _install_fake_urlopen(monkeypatch, fail_first=1)
    out = _safe_urlopen("http://sina.example.com/json_v2", timeout=1,
                        retries=1, backoff=0.0)
    assert out is not None and calls["n"] == 2
    delta = calls["t"][1] - calls["t"][0]
    assert delta >= 0.19, f"重试尝试必须同样节流（实测 {delta:.3f}s，backoff=0 隔离）"


def test_local_host_not_throttled(monkeypatch):
    """本机后端（127.0.0.1）不节流——给自家 Flask 加间隔属自我伤害。"""
    _reset_gov(monkeypatch, interval="0.25")
    calls = _install_fake_urlopen(monkeypatch)
    _safe_urlopen("http://127.0.0.1:5050/api/x", timeout=1, retries=0)
    _safe_urlopen("http://127.0.0.1:5050/api/x", timeout=1, retries=0)
    delta = calls["t"][1] - calls["t"][0]
    assert delta < 0.2, f"本机后端不得节流（实测 {delta:.3f}s）"


def test_different_hosts_independent(monkeypatch):
    _reset_gov(monkeypatch, interval="0.25")
    calls = _install_fake_urlopen(monkeypatch)
    _safe_urlopen("http://a.example.com/x", timeout=1, retries=0)
    _safe_urlopen("http://b.example.com/x", timeout=1, retries=0)
    delta = calls["t"][1] - calls["t"][0]
    assert delta < 0.2, f"不同 host 互不节流（实测 {delta:.3f}s）"
