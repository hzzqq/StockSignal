"""T-250 缓存预热核心单测（全离线，注入 fetch）。

mutation 基线：预热参数改掉（adjust/start/end 与引擎不同步）→
test_warm_uses_engine_params 变红；失败计数谎报 → test_failed_counted_honestly 变红。
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pandas as pd
import pytest

from modules.cache_warmer import _engine_params, warm_universe  # noqa: E402
import modules.cache_warmer as cw  # noqa: E402


def _fake_fetch_ok(code, start=None, end=None, adjust=None):
    return pd.DataFrame({"date": [end], "close": [10.0]})


def test_warm_uses_engine_params(monkeypatch):
    """预热必须以与荐股引擎逐字节相同的参数调用 get_daily（键一致性铁律）。"""
    codes = ["600001", "600002", "600003"]
    calls = []

    def fetch(code, start=None, end=None, adjust=None):
        calls.append((code, start, end, adjust))
        return _fake_fetch_ok(code, start=start, end=end, adjust=adjust)

    monkeypatch.setattr(cw, "_engine_params",
                        lambda: ("2026-01-25", "2026-10-11", "qfq"))
    res = warm_universe(limit=10, fetch=fetch, get_codes=lambda limit: codes)
    assert res["ok"] is True and res["warmed"] == 3 and res["failed"] == 0
    assert calls and all(c[1:] == ("2026-01-25", "2026-10-11", "qfq") for c in calls), \
        f"参数必须与引擎一致: {calls}"


def test_engine_params_match_engine_formula():
    """_engine_params 与 recommend_engine._fetch_one 的参数公式一致。"""
    start, end, adjust = _engine_params()
    now = datetime.now()
    assert start == (now - timedelta(days=260)).strftime("%Y-%m-%d")
    assert end == now.strftime("%Y-%m-%d")
    assert adjust == "qfq"


def test_failed_counted_honestly(monkeypatch):
    """单只失败如实计数并带明细，绝不谎报全绿、也绝不中断预热。"""
    codes = ["600001", "600002", "600003"]

    def fetch(code, start=None, end=None, adjust=None):
        if code == "600002":
            raise RuntimeError("network down")
        return _fake_fetch_ok(code, start=start, end=end, adjust=adjust)

    res = warm_universe(limit=10, fetch=fetch, get_codes=lambda limit: codes)
    assert res["warmed"] == 2 and res["failed"] == 1
    assert res["failed_codes"] == ["600002"]
    assert res["ok"] is True, "部分失败仍算可用预热（诚实上报，不否决）"


def test_hard_timeout_stops_early_honestly(monkeypatch):
    """硬超时到点如实报告停在第几只，不静默截断、不无限等。"""

    def slow_fetch(code, start=None, end=None, adjust=None):
        time.sleep(0.08)
        return _fake_fetch_ok(code, start=start, end=end, adjust=adjust)

    codes = [f"6000{i:02d}" for i in range(20)]
    res = warm_universe(limit=20, fetch=slow_fetch,
                        get_codes=lambda limit: codes, timeout=0.2)
    assert res["stopped_early"] is True
    assert res["warmed"] + res["failed"] < 20, "必须在超时处停下"
    assert res["warmed"] > 0
    assert "超时" in res["reason"] and "检查点" in res["reason"]


def test_cache_warm_disabled(monkeypatch):
    """SS_CACHE_WARM=0 → 如实跳过（调度器可关开关）。"""
    monkeypatch.setenv("SS_CACHE_WARM", "0")
    res = warm_universe(limit=10, fetch=_fake_fetch_ok,
                        get_codes=lambda limit: ["600001"])
    assert res["ok"] is True and res["warmed"] == 0 and "关闭" in res["reason"]


def test_empty_codes_honest(monkeypatch):
    res = warm_universe(limit=10, fetch=_fake_fetch_ok, get_codes=lambda limit: [])
    assert res["ok"] is True and res["total"] == 0 and res["warmed"] == 0


def test_scheduler_wires_cache_warmer():
    """调度器必须在荐股生成前挂预热（接线源码守卫，防脱落）。"""
    import inspect

    import backend.recommend_scheduler as rs

    src = inspect.getsource(rs)
    assert "cache_warmer" in src and "_warm_once" in src
