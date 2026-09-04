# -*- coding: utf-8 -*-
"""牧羊人指标历史重构：_enrich_zt_from_cache 反推 zt_pool 指标的单元测试。

核心防护：回测历史上 zt_prev_ret / zt_fail_ratio / connect_hl 只来自近 ~30 天 zt_pool
接口（稀疏），导致 analyze_history 全期坍缩成「修复试探」。本模块从已落盘的 per-stock
缓存（含 limit_up/zt_fail_count/change_pct）反推这三个指标，覆盖全历史。

测试不联网：用合成缓存验证反推口径正确。
"""
import os
import tempfile

import pandas as pd
import pytest

from modules.shepherd_reconstruct import _enrich_zt_from_cache, _board_limit_pct


def _write_cache(cache_dir, name, rows):
    pd.DataFrame(rows).to_csv(os.path.join(cache_dir, f"{name}.csv"), index=False)


def _make_cache(cache_dir):
    # 股A：01-01/01-02 连板（limit_up 连续），01-03 炸板（触板未封）
    _write_cache(cache_dir, "A", [
        {"date": "2024-01-01", "up_count": 1, "down_count": 0, "flat_count": 0,
         "limit_up": 1, "limit_down": 0, "touch_up": 1, "touch_down": 0,
         "zt_fail_count": 0, "hb_wave10": 0, "change_pct": 10.0, "close": 11},
        {"date": "2024-01-02", "up_count": 1, "down_count": 0, "flat_count": 0,
         "limit_up": 1, "limit_down": 0, "touch_up": 1, "touch_down": 0,
         "zt_fail_count": 0, "hb_wave10": 0, "change_pct": 5.0, "close": 12},
        {"date": "2024-01-03", "up_count": 0, "down_count": 1, "flat_count": 0,
         "limit_up": 0, "limit_down": 0, "touch_up": 1, "touch_down": 0,
         "zt_fail_count": 1, "hb_wave10": 0, "change_pct": -2.0, "close": 11},
    ])
    # 股B：01-02 炸板 2 只（这里用单股模拟炸板家数累加）
    _write_cache(cache_dir, "B", [
        {"date": "2024-01-01", "up_count": 0, "down_count": 0, "flat_count": 1,
         "limit_up": 0, "limit_down": 0, "touch_up": 0, "touch_down": 0,
         "zt_fail_count": 0, "hb_wave10": 0, "change_pct": 1.0, "close": 10},
        {"date": "2024-01-02", "up_count": 0, "down_count": 0, "flat_count": 1,
         "limit_up": 0, "limit_down": 0, "touch_up": 1, "touch_down": 0,
         "zt_fail_count": 2, "hb_wave10": 0, "change_pct": 2.0, "close": 10},
        {"date": "2024-01-03", "up_count": 0, "down_count": 0, "flat_count": 1,
         "limit_up": 0, "limit_down": 0, "touch_up": 0, "touch_down": 0,
         "zt_fail_count": 0, "hb_wave10": 0, "change_pct": 3.0, "close": 10},
    ])


def test_enrich_zt_fail_ratio():
    """炸板率 = Σ炸板 / (Σ涨停 + Σ炸板) × 100。"""
    with tempfile.TemporaryDirectory() as d:
        _make_cache(d)
        breadth = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "limit_up": [1.0, 1.0, 0.0], "limit_down": [0.0, 0.0, 0.0],
        })
        out = _enrich_zt_from_cache(breadth, d)
        zfr = out["zt_fail_ratio"].tolist()
        assert zfr[0] == 0.0          # 01-01: 0/(1+0)
        assert abs(zfr[1] - 66.67) < 0.01   # 01-02: 2/(1+2)
        assert zfr[2] == 100.0        # 01-03: 1/(0+1)


def test_enrich_zt_prev_ret():
    """昨板溢价 = 昨日涨停股今日平均涨跌幅。"""
    with tempfile.TemporaryDirectory() as d:
        _make_cache(d)
        breadth = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "limit_up": [1.0, 1.0, 0.0], "limit_down": [0.0, 0.0, 0.0],
        })
        out = _enrich_zt_from_cache(breadth, d)
        zpr = out["zt_prev_ret"].tolist()
        assert pd.isna(zpr[0])              # 首日前无「昨日涨停」
        assert abs(zpr[1] - 5.0) < 1e-6     # 01-01 涨停的 A，01-02 涨 5%
        assert abs(zpr[2] - (-2.0)) < 1e-6  # 01-02 涨停的 A，01-03 跌 -2%


def test_enrich_connect_hl():
    """最高连板数 = 逐股连板天数取最大。"""
    with tempfile.TemporaryDirectory() as d:
        _make_cache(d)
        breadth = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "limit_up": [1.0, 1.0, 0.0], "limit_down": [0.0, 0.0, 0.0],
        })
        out = _enrich_zt_from_cache(breadth, d)
        chl = out["connect_hl"].tolist()
        assert chl[0] == 1   # A 单板
        assert chl[1] == 2   # A 两连板
        assert chl[2] == 0   # A 断板，无连板


def test_enrich_preserves_existing_zt_pool():
    """近期 zt_pool 已有真实值时不被反推值覆盖（仅 fillna）。"""
    with tempfile.TemporaryDirectory() as d:
        _make_cache(d)
        breadth = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "limit_up": [1.0, 1.0, 0.0], "limit_down": [0.0, 0.0, 0.0],
            # 近期 zt_pool 真实值（如 01-02 真实炸板率 40%）
            "zt_fail_ratio": [None, 40.0, None],
            "zt_prev_ret": [None, 8.8, None],
            "connect_hl": [None, 7, None],
        })
        out = _enrich_zt_from_cache(breadth, d)
        # 01-02 保留真实值
        assert out["zt_fail_ratio"].iloc[1] == 40.0
        assert out["zt_prev_ret"].iloc[1] == 8.8
        assert out["connect_hl"].iloc[1] == 7
        # 01-01/01-03 由反推补齐
        assert out["zt_fail_ratio"].iloc[0] == 0.0
        assert out["connect_hl"].iloc[2] == 0


def test_enrich_empty_cache_is_noop():
    with tempfile.TemporaryDirectory() as d:
        breadth = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01"]),
            "limit_up": [1.0], "limit_down": [0.0],
            "zt_fail_ratio": [None], "zt_prev_ret": [None], "connect_hl": [None],
        })
        out = _enrich_zt_from_cache(breadth, d)
        assert out["zt_fail_ratio"].isna().all()
        assert out["zt_prev_ret"].isna().all()


def test_board_limit_pct_bare_and_prefixed():
    # 带前缀（原口径）
    assert _board_limit_pct("sh600000") == 0.10   # 沪主板
    assert _board_limit_pct("sz000001") == 0.10   # 深主板
    assert _board_limit_pct("sh688981") == 0.20   # 科创板
    assert _board_limit_pct("sz300750") == 0.20   # 创业板
    assert _board_limit_pct("bj920001") == 0.30   # 北交所
    # 裸代码（修复前裸 688/300 被前缀逻辑漏掉 → 误判 10%）
    assert _board_limit_pct("600000") == 0.10     # 裸主板
    assert _board_limit_pct("688001") == 0.20     # 裸科创板
    assert _board_limit_pct("300750") == 0.20     # 裸创业板
    assert _board_limit_pct("830799") == 0.30     # 裸北交所 8 段
    assert _board_limit_pct("920002") == 0.30     # 裸北交所 920 段
