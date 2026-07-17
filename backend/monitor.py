"""
backend/monitor.py
------------------
轻量级后端运行监控（进程内，零外部依赖）。

跟踪指标：
  - 总请求数、各端点请求数
  - 错误数、错误率
  - 平均/最大响应延迟（毫秒）
  - 活跃会话数（基于最近 5 分钟内有请求的 JWT 用户）
  - 启动时间、运行时长

数据存于进程内存（dict + deque），重启清零；对单实例部署足够。
前端管理界面通过 /api/admin/monitor 读取展示。
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import datetime
from threading import RLock

_lock = RLock()
_start_time = time.time()

# 各端点统计：{endpoint: {"count": int, "errors": int, "total_ms": float, "max_ms": float}}
_endpoint_stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "errors": 0, "total_ms": 0.0, "max_ms": 0.0})

# 最近请求时间戳（用于 QPS / 活跃会话）
_recent_requests: deque = deque()  # (ts, user_id)

# 全局累计
_total_requests = 0
_total_errors = 0
_total_latency_ms = 0.0


def record_request(endpoint: str, latency_ms: float, is_error: bool, user_id: int | None = None) -> None:
    """记录一次 API 请求（在 after_request 中调用）。"""
    global _total_requests, _total_errors, _total_latency_ms
    now = time.time()
    with _lock:
        _total_requests += 1
        _total_latency_ms += latency_ms
        if is_error:
            _total_errors += 1
        es = _endpoint_stats[endpoint]
        es["count"] += 1
        es["total_ms"] += latency_ms
        es["max_ms"] = max(es["max_ms"], latency_ms)
        if is_error:
            es["errors"] += 1
        _recent_requests.append((now, user_id))
        # 清理 10 分钟前的记录
        _cutoff = now - 600
        while _recent_requests and _recent_requests[0][0] < _cutoff:
            _recent_requests.popleft()


def get_active_users(window_sec: int = 300) -> int:
    """返回最近 window_sec 秒内有活动的去重用户数。"""
    now = time.time()
    cut = now - window_sec
    with _lock:
        uids = {uid for ts, uid in _recent_requests if ts >= cut and uid}
        return len(uids)


def get_stats() -> dict:
    """返回汇总监控数据。"""
    now = time.time()
    uptime_sec = int(now - _start_time)
    with _lock:
        avg_latency = (_total_latency_ms / _total_requests) if _total_requests else 0.0
        error_rate = (_total_errors / _total_requests) if _total_requests else 0.0
        top_endpoints = sorted(
            _endpoint_stats.items(),
            key=lambda kv: kv[1]["count"],
            reverse=True,
        )[:12]
        endpoints = []
        for ep, s in top_endpoints:
            ep_avg = (s["total_ms"] / s["count"]) if s["count"] else 0.0
            ep_err_rate = (s["errors"] / s["count"]) if s["count"] else 0.0
            endpoints.append({
                "endpoint": ep,
                "count": s["count"],
                "errors": s["errors"],
                "avg_ms": round(ep_avg, 1),
                "max_ms": round(s["max_ms"], 1),
                "error_rate": round(ep_err_rate * 100, 2),
            })
        return {
            "start_time": datetime.fromtimestamp(_start_time).strftime("%Y-%m-%d %H:%M:%S"),
            "uptime_sec": uptime_sec,
            "uptime_text": _fmt_uptime(uptime_sec),
            "total_requests": _total_requests,
            "total_errors": _total_errors,
            "avg_latency_ms": round(avg_latency, 1),
            "error_rate_pct": round(error_rate * 100, 2),
            "active_users_5m": get_active_users(300),
            "active_users_1m": get_active_users(60),
            "endpoints": endpoints,
        }


def _fmt_uptime(sec: int) -> str:
    d, r = divmod(sec, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    if d:
        return f"{d}天{h}时{m}分"
    if h:
        return f"{h}时{m}分{s}秒"
    if m:
        return f"{m}分{s}秒"
    return f"{s}秒"
