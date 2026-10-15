"""T-249 缓存加固 P2：_safe_urlopen 接入 per-host 节流（全离线，urlopen 打桩）。

背景（docs/data_cache_hardening.md §1.2/§三 P2）：fetcher 日线链路走
_feed_io._safe_urlopen 直连 urllib，此前**无 per-host 节流也无熔断**——荐股一轮
对新浪约 300+ 次请求（8 并发×每股 L3 竞速+失败重试 2 次），新浪 RemoteDisconnected
限流相当程度是「自己打自己」。P2 把 request_utils._throttle 语义延伸到该路径：
同一 host 两次请求（含重试尝试）之间至少间隔 SS_HOST_MIN_INTERVAL 秒，本机后端不节流。

mutation 基线：去掉 _throttle 接线 → test_same_host_second_call_delayed 变红。

T-285 密封桩：fake urlopen 打在进程级 urllib.request 模块上，全量回归时其它测试
泄漏的后台拉取线程会穿过补丁污染计数（曾实测 4 次≠2、时间戳簇状成对，负载态偶发）。
桩只认本测试 URL：外来流量返回哑对象、不记录、不消耗失败预算。
"""
from __future__ import annotations

import os
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

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


def _install_fake_urlopen(monkeypatch, fail_first=0, match="sina.example.com"):
    """打桩 urllib.request.urlopen：**只认 match 命中的调用**（T-285 密封契约）。

    补丁打在进程级 urllib.request 模块上，全量回归时其它测试泄漏的后台拉取线程
    也会调进来——外来流量返回哑对象、不记录时刻、不消耗 fail_first 失败预算
    （否则计数 4≠2 / 重试用例首调预算被抢，负载态偶发红）。
    """
    calls = {"t": [], "n": 0}
    lock = threading.Lock()

    def fake_urlopen(req, timeout=None):
        url = req if isinstance(req, str) else getattr(req, "full_url", "")
        if match in str(url):
            with lock:
                calls["n"] += 1
                n = calls["n"]
                calls["t"].append(time.monotonic())
        else:
            n = fail_first + 1  # 外来流量：不触发失败预算
        if n <= fail_first:
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
    """本机后端（127.0.0.1）不节流——给自家 Flask 加间隔属自我伤害。

    T-285：interval 取 1.0、阈值 0.5——「未节流」上界断言留足负载余量
    （全量回归时调度毛刺可到几十 ms），仍保留判别力（误节流则 delta≥1.0 必红）。
    """
    _reset_gov(monkeypatch, interval="1.0")
    calls = _install_fake_urlopen(monkeypatch, match="127.0.0.1:5050")
    _safe_urlopen("http://127.0.0.1:5050/api/x", timeout=1, retries=0)
    _safe_urlopen("http://127.0.0.1:5050/api/x", timeout=1, retries=0)
    delta = calls["t"][1] - calls["t"][0]
    assert delta < 0.5, f"本机后端不得节流（实测 {delta:.3f}s）"


def test_different_hosts_independent(monkeypatch):
    """不同 host 互不节流（T-285：interval 1.0 / 阈值 0.5 留负载余量，同上）。"""
    _reset_gov(monkeypatch, interval="1.0")
    calls = _install_fake_urlopen(monkeypatch, match="example.com")
    _safe_urlopen("http://a.example.com/x", timeout=1, retries=0)
    _safe_urlopen("http://b.example.com/x", timeout=1, retries=0)
    delta = calls["t"][1] - calls["t"][0]
    assert delta < 0.5, f"不同 host 互不节流（实测 {delta:.3f}s）"


def test_fake_ignores_foreign_traffic(monkeypatch):
    """T-285 密封契约钉子：外来流量（泄漏线程穿进程级补丁）不得进计数/预算。

    直接以真实域名形态的异 URL 调 fake（与后台线程同路径同属性检查），确定性
    复现「污染」场景：无过滤时外来调用会计入 calls——既撑爆 4≠2 类计数、又提前
    耗尽 fail_first 失败预算。fail_first=2 结构让预算窃取可观测：若外来流量被计，
    本域第 2 调 n=4>2 会误成功 → pytest.raises 落空 → 红。
    """
    _reset_gov(monkeypatch, interval="0.25")
    calls = _install_fake_urlopen(monkeypatch, fail_first=2)
    # 本域第 1 调：消耗失败预算 1（retries=0 不重试，URLError 直接冒泡）
    with pytest.raises(urllib.error.URLError):
        _safe_urlopen("http://sina.example.com/json_v2", timeout=1, retries=0)
    assert calls["n"] == 1 and len(calls["t"]) == 1
    # 模拟泄漏线程：真实域名形态异 URL（含 "sina" 但不含 "sina.example.com"）
    r1 = urllib.request.urlopen("http://finance.sina.com.cn/real/leaked", timeout=1)
    r2 = urllib.request.urlopen("http://hq.sinajs.cn/leaked", timeout=1)
    assert r1 is not None and r2 is not None  # 外来流量拿哑对象、不抛错
    assert calls["n"] == 1, f"外来流量不得计数（实测 {calls['n']}）"
    assert len(calls["t"]) == 1
    # 本域第 2 调：n=2 ≤ fail_first=2 → 仍失败，证明失败预算未被外来流量抢走
    with pytest.raises(urllib.error.URLError):
        _safe_urlopen("http://sina.example.com/json_v2", timeout=1, retries=0)
    assert calls["n"] == 2 and len(calls["t"]) == 2
    # 预算耗尽后 → 成功
    assert _safe_urlopen("http://sina.example.com/json_v2", timeout=1, retries=0) \
        is not None
    assert calls["n"] == 3 and len(calls["t"]) == 3
