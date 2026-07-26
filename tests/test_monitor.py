"""Unit tests for backend.monitor.record_request (R14 修复 + 端点到聚合防护).

- record_request 对 NaN / inf / 负数延迟做防护，不再污染 avg 聚合；
- 端点级 total_ms / max_ms 同样使用已校验的 lat，绝不出现 NaN/inf/负数；
- 新增 reset() 清空指标；
- 新增 get_error_endpoints(top_n) 定位错误最多的端点。
"""
import math

import pytest

import backend.monitor as monitor
from backend.monitor import (
    record_request,
    get_stats,
    reset,
    get_error_endpoints,
    get_active_users,
)


@pytest.fixture(autouse=True)
def _reset_state():
    reset()
    yield
    reset()


def _assert_finite_nonneg(*values):
    for v in values:
        assert isinstance(v, (int, float))
        assert math.isfinite(v), f"value is not finite: {v!r}"
        assert v >= 0, f"value is negative: {v!r}"


def _assert_endpoint_ok(endpoint):
    s = monitor._endpoint_stats[endpoint]
    _assert_finite_nonneg(s["total_ms"], s["max_ms"], s["count"], s["errors"])


def _assert_global_ok():
    _assert_finite_nonneg(
        monitor._total_latency_ms,
        monitor._total_requests,
        monitor._total_errors,
    )


def test_reset_clears_metrics():
    record_request("/api/quote", 10.0, False, user_id=1)
    reset()
    stats = get_stats()
    assert stats["total_requests"] == 0
    assert stats["total_errors"] == 0
    assert stats["error_rate_pct"] == 0.0
    assert stats["endpoints"] == []


def test_normal_latency():
    record_request("/api/test", 123.4, False, user_id=1)
    _assert_endpoint_ok("/api/test")
    _assert_global_ok()
    s = monitor._endpoint_stats["/api/test"]
    assert s["total_ms"] == 123.4
    assert s["max_ms"] == 123.4


def test_nan_latency():
    record_request("/api/test", float("nan"), False, user_id=1)
    _assert_endpoint_ok("/api/test")
    _assert_global_ok()
    s = monitor._endpoint_stats["/api/test"]
    assert s["total_ms"] == 0.0
    assert s["max_ms"] == 0.0


def test_inf_latency():
    record_request("/api/test", float("inf"), False, user_id=1)
    _assert_endpoint_ok("/api/test")
    _assert_global_ok()
    s = monitor._endpoint_stats["/api/test"]
    assert s["total_ms"] == 0.0
    assert s["max_ms"] == 0.0


def test_negative_latency():
    record_request("/api/test", -50.0, False, user_id=1)
    _assert_endpoint_ok("/api/test")
    _assert_global_ok()
    s = monitor._endpoint_stats["/api/test"]
    assert s["total_ms"] == 0.0
    assert s["max_ms"] == 0.0


def test_large_latency():
    record_request("/api/test", 1e9, False, user_id=1)
    _assert_endpoint_ok("/api/test")
    _assert_global_ok()
    s = monitor._endpoint_stats["/api/test"]
    assert s["total_ms"] == 1e9
    assert s["max_ms"] == 1e9


def test_nan_latency_does_not_poison_avg():
    record_request("/api/quote", float("nan"), False, user_id=1)
    record_request("/api/quote", 20.0, False, user_id=1)
    stats = get_stats()
    assert math.isfinite(stats["avg_latency_ms"])
    assert stats["avg_latency_ms"] == 10.0
    assert stats["total_requests"] == 2


def test_inf_and_negative_latency_clamped_to_zero():
    record_request("/a", math.inf, False, user_id=1)
    record_request("/a", -5.0, False, user_id=1)
    record_request("/a", 30.0, False, user_id=1)
    stats = get_stats()
    assert math.isfinite(stats["avg_latency_ms"])
    assert stats["avg_latency_ms"] == 10.0


def test_error_endpoints_ranked():
    record_request("/api/ok", 5.0, False, user_id=1)
    record_request("/api/bad", 5.0, True, user_id=2)
    record_request("/api/bad", 5.0, True, user_id=3)
    record_request("/api/worse", 5.0, True, user_id=4)
    record_request("/api/worse", 5.0, True, user_id=5)
    record_request("/api/worse", 5.0, True, user_id=6)
    errs = get_error_endpoints(top_n=5)
    assert errs[0]["endpoint"] == "/api/worse"
    assert errs[0]["errors"] == 3
    assert errs[1]["endpoint"] == "/api/bad"
    assert errs[1]["errors"] == 2
    assert all(e["endpoint"] != "/api/ok" for e in errs)


def test_active_users_window():
    record_request("/x", 1.0, False, user_id=10)
    record_request("/x", 1.0, False, user_id=11)
    record_request("/x", 1.0, False, user_id=10)
    assert get_active_users(300) == 2
