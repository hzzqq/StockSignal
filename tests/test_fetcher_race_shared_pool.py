# -*- coding: utf-8 -*-
"""tests/test_fetcher_race_shared_pool.py — T-383 四源竞速复用共享池守卫。

背景：``get_daily`` 的四源竞速原先每次调用自建
``ThreadPoolExecutor(max_workers=4)``，用完 ``shutdown(cancel_futures=True)``。
改为复用 ``modules.timeout_exec._pool()``（进程级 16 worker 单例）后，必须钉住：

1. 竞速语义不变——先成功者胜出，**不等慢源**（不能退回串行降级）；
2. 共享池**绝不能被 shutdown**（它是进程级单例，shutdown 会连带废掉其他页面的取数）；
3. 全部源失败时仍诚实抛 RuntimeError（降级语义零变化）；
4. 源码层面禁止自建池回潮（AST/文本守卫）。

mutation 基线：
  - 把 ``_shared_pool()`` 换成自建 ``ThreadPoolExecutor`` → test_no_local_pool_in_race 变红；
  - 在 finally 里加 ``_shared_pool().shutdown()`` → test_shared_pool_survives_get_daily 变红；
  - 竞速退回串行（等慢源） → test_fastest_source_wins_without_waiting_slow_ones 变红。
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import threading
import time
from pathlib import Path

import pandas as pd
import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import modules.fetcher as fetcher_mod  # noqa: E402
import modules.timeout_exec as timeout_exec  # noqa: E402
from modules.fetcher import StockFetcher  # noqa: E402

_DATES = pd.date_range("2026-01-01", "2026-02-10").strftime("%Y-%m-%d")
KLINE_SRC = Path(_ROOT) / "modules" / "fetcher_kline.py"


def _df():
    n = len(_DATES)
    return pd.DataFrame({"date": pd.to_datetime(_DATES),
                         "open": [10.0] * n, "high": [11.0] * n,
                         "low": [9.0] * n, "close": [10.0] * n,
                         "volume": [1e6] * n})


def _empty_db(tmp_path):
    db = os.path.join(str(tmp_path), "cache.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE daily_cache (cache_key TEXT PRIMARY KEY, "
                 "data_json TEXT, updated_at TEXT)")
    conn.commit()
    conn.close()
    return db


def _instance(db):
    """最小可用的 StockFetcher 实例（复用 test_fetcher_speedups 的构造范式）。"""
    f = StockFetcher.__new__(StockFetcher)
    f._code_to_name = {}
    f.cache_days = 7
    f._get_conn = lambda: sqlite3.connect(db)  # type: ignore[method-assign]
    return f


@pytest.fixture(autouse=True)
def _clean_l0():
    fetcher_mod._L0_CACHE.clear()
    yield
    fetcher_mod._L0_CACHE.clear()


# ───────────────────── 1. 源码守卫：禁自建池回潮 ─────────────────────

def test_no_local_pool_in_race():
    """四源竞速不得再自建 ThreadPoolExecutor（必须复用 timeout_exec._pool）。"""
    src = KLINE_SRC.read_text(encoding="utf-8")
    offenders = []
    for m in re.finditer(r"ThreadPoolExecutor\s*\(", src):
        line = src[:m.start()].count("\n") + 1
        offenders.append(f"L{line}")
    assert not offenders, (
        "fetcher_kline.py 出现自建 ThreadPoolExecutor（T-383 已改共享池）：" + ",".join(offenders)
    )
    assert "_shared_pool()" in src, "四源竞速必须复用 modules.timeout_exec._pool()"


def test_shared_pool_never_shutdown():
    """共享池是进程级单例，源码里禁止 shutdown（会废掉其他页面的取数）。"""
    src = KLINE_SRC.read_text(encoding="utf-8")
    assert ".shutdown(" not in src, (
        "fetcher_kline.py 不得调用 shutdown()：共享池被 shutdown 会让全站取数一起失效"
    )


def test_race_keeps_first_completed_two_rounds():
    """竞速语义保留：FIRST_COMPLETED + 两轮 10s 硬边界。"""
    src = KLINE_SRC.read_text(encoding="utf-8")
    assert "FIRST_COMPLETED" in src, "先成功者胜出的语义不得丢失"
    assert src.count("timeout=10") >= 2, "两轮各 10s 硬边界不得减少"


# ───────────────────── 2. 行为：先成功者胜出，不等慢源 ─────────────────────

def test_fastest_source_wins_without_waiting_slow_ones(tmp_path):
    """L3 秒回、其余源阻塞 → get_daily 必须秒级返回 L3 数据，而非等满 10s。"""
    db = _empty_db(tmp_path)
    f = _instance(db)
    gate = threading.Event()
    calls = []

    def _level(self, level, symbol, start, end, adjust):
        calls.append(level)
        if level == "L3":
            return _df(), None
        gate.wait(timeout=5)  # 模拟被墙挂起的慢源
        return None, f"{level}: slow"

    f._fetch_level = _level.__get__(f, StockFetcher)  # type: ignore[method-assign]
    t0 = time.monotonic()
    try:
        out = f.get_daily("600519", start="2026-01-01", end="2026-02-10", adjust="qfq")
    finally:
        gate.set()  # 释放仍在阻塞的慢源线程

    elapsed = time.monotonic() - t0
    assert out is not None and len(out) == len(_DATES), "应拿到 L3 的即时结果"
    assert elapsed < 3.0, f"竞速等了慢源（耗时 {elapsed:.1f}s，应远小于第一轮 10s 上限）"
    assert set(calls) == {"L1", "L2", "L3", "L4"}, f"四源应并发提交，实际只跑了 {calls}"


# ───────────────────── 3. 行为：全失败仍诚实抛错 ─────────────────────

def test_all_sources_fail_still_raises(tmp_path):
    """四源全失败 + 无缓存 → 仍抛 RuntimeError（降级语义零变化）。"""
    db = _empty_db(tmp_path)
    f = _instance(db)
    f._fetch_level = (lambda self, level, symbol, start, end, adjust:
                      (None, f"{level}: offline")).__get__(f, StockFetcher)  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        f.get_daily("600519", start="2026-01-01", end="2026-02-10", adjust="qfq")


# ───────────────────── 4. 行为：共享池不得被本次调用废掉 ─────────────────────

def test_shared_pool_survives_get_daily(tmp_path):
    """get_daily 结束后共享池仍可用（证明 finally 没有 shutdown 它）。"""
    db = _empty_db(tmp_path)
    f = _instance(db)
    f._fetch_level = (lambda self, level, symbol, start, end, adjust:
                      (_df(), None) if level == "L3" else (None, f"{level}: offline")
                      ).__get__(f, StockFetcher)  # type: ignore[method-assign]
    f.get_daily("600519", start="2026-01-01", end="2026-02-10", adjust="qfq")

    pool = timeout_exec._pool()
    assert pool is timeout_exec._pool(), "共享池必须是同一单例"
    fut = pool.submit(lambda: 42)  # 若池已被 shutdown 会抛 RuntimeError
    assert fut.result(timeout=5) == 42, "get_daily 之后共享池仍须可提交任务"
