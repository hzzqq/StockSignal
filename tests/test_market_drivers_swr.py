"""
tests/test_market_drivers_swr.py
================================
T-272④：慢源 stale-while-revalidate——_cached_swr 单测（过期旧值立即返回 + 后台
单飞刷新 + 冷启动不变 + 刷新失败留痕可重试）+ get_market_drivers 接线契约。

诚实语义：SWR 返回旧值必须可辨（meta 注入 _swr_stale/_swr_age_s，绝不冒充新鲜）。
红线：仅慢档（21 指标）；实时行情 fast 路径不走本函数。
"""
import threading
import time
from pathlib import Path

import modules.market_drivers as md

_PROJECT = Path(__file__).resolve().parents[1]


def _cleanup(key):
    with md._CACHE_LOCK:
        md._CACHE.pop(key, None)
    with md._SWR_LOCK:
        md._SWR_INFLIGHT.discard(key)


def test_fresh_hit_no_swr():
    """未过期命中：原样返回、不触发刷新（swr_info=None）。"""
    key = "swr_fresh_probe"
    try:
        with md._CACHE_LOCK:
            md._CACHE[key] = (time.time(), "v1")
        calls = {"n": 0}

        def _fn():
            calls["n"] += 1
            return "v2"

        val, swr = md._cached_swr(600, key, _fn)
        assert val == "v1" and swr is None
        assert calls["n"] == 0, "新鲜命中不应触发 fn"
    finally:
        _cleanup(key)


def test_expired_returns_stale_then_background_refresh():
    """过期有旧值：立即返回旧值 + swr 标注；后台刷新完成后下次调用拿新值。"""
    key = "swr_expired_probe"
    try:
        with md._CACHE_LOCK:
            md._CACHE[key] = (time.time() - 700, "old")

        def _fn():
            return "new"

        t0 = time.time()
        val, swr = md._cached_swr(600, key, _fn)
        elapsed = time.time() - t0
        assert val == "old", "SWR 应立即返回旧值"
        assert swr is not None and 690 <= swr["age_s"] <= 710
        assert elapsed < 1.0, "SWR 路径不应阻塞等网络（应亚秒返回）"

        # 等后台刷新完成（inflight 清空 + 缓存换新）
        for _ in range(200):
            if key not in md._SWR_INFLIGHT:
                break
            time.sleep(0.02)
        assert key not in md._SWR_INFLIGHT, "后台刷新应结束并释放 inflight"
        with md._CACHE_LOCK:
            assert md._CACHE[key][1] == "new", "刷新完成后缓存应换新值"

        val2, swr2 = md._cached_swr(600, key, _fn)
        assert val2 == "new" and swr2 is None, "刷新后再次调用应拿新值且无 SWR 标注"
    finally:
        _cleanup(key)


def test_cold_start_sync_unchanged():
    """冷启动无旧值：同步执行 fn（行为与原 _cached 一致），swr_info=None。"""
    key = "swr_cold_probe"
    try:
        calls = {"n": 0}

        def _fn():
            calls["n"] += 1
            return "computed"

        val, swr = md._cached_swr(600, key, _fn)
        assert val == "computed" and swr is None and calls["n"] == 1
        with md._CACHE_LOCK:
            assert key in md._CACHE, "冷启动结果应写入缓存"
    finally:
        _cleanup(key)


def test_singleflight_dedup():
    """单飞：同一 key 并发触发多次刷新，fn 只执行一次（防并发风暴）。"""
    key = "swr_singleflight_probe"
    try:
        with md._CACHE_LOCK:
            md._CACHE[key] = (time.time() - 700, "old")
        release = threading.Event()
        calls = {"n": 0}

        def _fn():
            calls["n"] += 1
            release.wait(timeout=5)
            return "new"

        # 手动 kick 两次（模拟两个用户同时打到过期缓存）
        md._kick_refresh(key, _fn)
        md._kick_refresh(key, _fn)
        time.sleep(0.2)  # 让 worker 进入 fn
        assert calls["n"] == 1, "单飞去重失败：同一 key 刷新被并发执行"

        release.set()
        for _ in range(200):
            if key not in md._SWR_INFLIGHT:
                break
            time.sleep(0.02)
        assert calls["n"] == 1
    finally:
        release.set()
        _cleanup(key)


def test_refresh_failure_keeps_stale_and_releases_inflight():
    """刷新失败：旧值保留、inflight 释放（下次调用可重试）、不静默（异常上抛到 logger）。"""
    key = "swr_fail_probe"
    try:
        with md._CACHE_LOCK:
            md._CACHE[key] = (time.time() - 700, "old")

        def _boom():
            raise RuntimeError("网络全断")

        val, swr = md._cached_swr(600, key, _boom)
        assert val == "old" and swr is not None, "刷新失败不影响本次旧值返回"
        for _ in range(200):
            if key not in md._SWR_INFLIGHT:
                break
            time.sleep(0.02)
        assert key not in md._SWR_INFLIGHT, "失败后必须释放 inflight（否则永不重试）"
        with md._CACHE_LOCK:
            assert md._CACHE[key][1] == "old", "失败后旧值必须保留"
    finally:
        _cleanup(key)


def test_tuple_value_passthrough():
    """元组值透传契约：fn 返回 (df, meta) 元组时，value 必须原样整体透传。

    根因钉子（T-272④）：get_market_drivers 的 fn 返回元组，若调用方写成
    `df, meta, swr = _cached_swr(...)` 会把 value 元组错误解包（全量回归抓到的真 bug）。
    """
    key = "swr_tuple_probe"
    try:
        sentinel = ("fake_df", {"dim": "meta"})

        def _fn():
            return sentinel

        val, swr = md._cached_swr(600, key, _fn)
        assert val is sentinel and swr is None, "冷启动元组值必须整体透传"

        # 过期路径同样整体透传（SWR 旧值 = 元组）
        with md._CACHE_LOCK:
            md._CACHE[key] = (time.time() - 700, sentinel)
        val2, swr2 = md._cached_swr(600, key, _fn)
        assert val2 is sentinel and swr2 is not None, "SWR 旧值元组必须整体透传且带标注"
    finally:
        _cleanup(key)


def test_get_market_drivers_carries_swr_meta_contract():
    """源码契约：get_market_drivers 对 SWR 旧值注入 _swr_* 诚实标注（不回退）。"""
    src = (_PROJECT / "modules" / "market_drivers.py").read_text(encoding="utf-8")
    assert "_swr_stale" in src and "_swr_age_s" in src and "_swr_note" in src, \
        "SWR 诚实标注缺失——旧值冒充新鲜（T-272④ 语义回退）"
    assert "_cached_swr" in src, "get_market_drivers 应走 _cached_swr（SWR 回潮）"
    assert "dict(meta)" in src, "注入标注前必须浅拷贝 meta（防污染缓存内共享 dict）"
    # 接线形态守卫：必须 res, swr = _cached_swr(...) + df, meta = res 整体接收——
    # 写成 df, meta, swr = _cached_swr(...) 会触发元组错解包（全量回归抓到的真 bug）
    assert "res, swr = _cached_swr" in src and "df, meta = res" in src, \
        "SWR 接线形态回潮（直接三变量解包）——将复发元组错解包缺陷"
