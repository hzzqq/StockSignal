"""R14：backend.monitor 监控指标修复 + 新能力。

- record_request 对 NaN / inf / 负数延迟做防护，不再污染 avg 聚合；
- 新增 reset() 清空指标；
- 新增 get_error_endpoints(top_n) 定位错误最多的端点。
"""
import math

from backend.monitor import (
    record_request,
    get_stats,
    reset,
    get_error_endpoints,
    get_active_users,
)


def setup_function(_fn):
    reset()


def test_reset_clears_metrics():
    record_request("/api/quote", 10.0, False, user_id=1)
    reset()
    stats = get_stats()
    assert stats["total_requests"] == 0
    assert stats["total_errors"] == 0
    assert stats["error_rate_pct"] == 0.0
    assert stats["endpoints"] == []


def test_nan_latency_does_not_poison_avg():
    record_request("/api/quote", float("nan"), False, user_id=1)
    record_request("/api/quote", 20.0, False, user_id=1)
    stats = get_stats()
    # 两次请求：1 次 NaN(回落0) + 1 次 20 → avg 应为 10，绝不为 nan
    assert math.isfinite(stats["avg_latency_ms"])
    assert stats["avg_latency_ms"] == 10.0
    assert stats["total_requests"] == 2


def test_inf_and_negative_latency_clamped_to_zero():
    record_request("/a", math.inf, False, user_id=1)
    record_request("/a", -5.0, False, user_id=1)
    record_request("/a", 30.0, False, user_id=1)
    stats = get_stats()
    assert math.isfinite(stats["avg_latency_ms"])
    # (0 + 0 + 30) / 3 == 10
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
    # /api/ok 无错误，不应出现
    assert all(e["endpoint"] != "/api/ok" for e in errs)


def test_active_users_window():
    record_request("/x", 1.0, False, user_id=10)
    record_request("/x", 1.0, False, user_id=11)
    # 同一个 user 去重
    record_request("/x", 1.0, False, user_id=10)
    assert get_active_users(300) == 2
