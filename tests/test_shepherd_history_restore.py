# -*- coding: utf-8 -*-
"""P1 离线恢复脚本的单测（2026-09-10 缓存截断事故的恢复路径）。

守护要点：
  * 核心广度列必须来自 v1 缓存按日求和（与健康镜像 up/down/flat 完全一致）；
  * **v1 拿不到的列必须留空，绝不能填 0**——填 0 等于把「不知道」包装成
    「当天没有任何一只股票触及跌停」，是比缺数据更坏的静默错误；
  * v1 未覆盖的近期行必须沿用现有 csv（不能因为恢复把最近的数据抹掉）；
  * 输出列必须覆盖生产聚合器的列契约（否则下游按列名读取会静默拿到 None）。
"""
import os

import numpy as np
import pandas as pd
import pytest

from modules.shepherd_reconstruct import _aggregate_frames
from scripts.restore_shepherd_history_from_v1_cache import (
    COUNT_COLS, EMPTY_COLS, OUT_COLS, aggregate_v1_cache, build_restored, load_healthy_json,
)


def _v1_rows(dates, up=1, down=0, lu=0, ld=0):
    return [{"date": d, "up_count": up, "down_count": down, "flat_count": 0,
             "limit_up": lu, "limit_down": ld} for d in dates]


def _write(cache_dir, name, rows):
    pd.DataFrame(rows).to_csv(os.path.join(cache_dir, f"{name}.csv"), index=False)


def test_aggregate_v1_cache_sums_by_date(tmp_path):
    """多只股票同一天 → 家数相加（这正是市场广度的定义）。"""
    _write(str(tmp_path), "A", _v1_rows(["2024-01-02"], up=3, lu=1))
    _write(str(tmp_path), "B", _v1_rows(["2024-01-02"], up=4, down=1, ld=1))
    _write(str(tmp_path), "C", _v1_rows(["2024-01-03"], up=1))

    out = aggregate_v1_cache(str(tmp_path))
    got = out.set_index(out["date"].dt.strftime("%Y-%m-%d"))
    assert got.loc["2024-01-02", "up_count"] == 7      # 3 + 4，跨文件求和
    assert got.loc["2024-01-02", "down_count"] == 1
    assert got.loc["2024-01-02", "limit_up"] == 1
    assert got.loc["2024-01-02", "limit_down"] == 1
    assert got.loc["2024-01-03", "up_count"] == 1
    # red_ratio 分母是 up+down（与生产 _aggregate_frames 口径一致，不含 flat）
    assert abs(got.loc["2024-01-02", "red_ratio"] - 87.5) < 1e-9


def test_red_ratio_denominator_matches_production_aggregator(tmp_path):
    """口径守卫：red_ratio 的分母必须与生产模块 _aggregate_frames 完全一致。"""
    _write(str(tmp_path), "A", _v1_rows(["2024-01-02"], up=3, down=1))
    restored = aggregate_v1_cache(str(tmp_path))

    per_stock = pd.DataFrame({
        "date": ["2024-01-02"], "up_count": [3], "down_count": [1], "flat_count": [5],
        "limit_up": [0], "limit_down": [0], "touch_down": [0], "zt_fail_count": [0],
        "hb_wave10": [0], "change_pct": [1.0], "close": [10.0],
    })
    prod = _aggregate_frames([per_stock])
    assert abs(restored["red_ratio"].iloc[0] - prod["red_ratio"].iloc[0]) < 1e-9
    # flat_count=5 不参与 red_ratio 分母（否则会得到 3/9=33.3%）
    assert abs(restored["red_ratio"].iloc[0] - 75.0) < 1e-9


def test_aggregate_v1_cache_empty_dir_raises(tmp_path):
    """空目录必须**显式报错**，不能安静地返回空表（空表落盘 = 清空全部历史）。"""
    with pytest.raises(RuntimeError):
        aggregate_v1_cache(str(tmp_path))


def test_restore_leaves_unknowable_columns_empty(tmp_path):
    """★ 诚实性守卫：v1 缓存无法支撑的列必须留 NaN，**绝不能是 0**。"""
    _write(str(tmp_path), "A", _v1_rows(["2024-01-02", "2024-01-03"], up=2, down=1))
    v1 = aggregate_v1_cache(str(tmp_path))
    out = build_restored(v1, healthy=None, existing=None)

    for c in EMPTY_COLS:
        assert out[c].isna().all(), "%s 被填了值（%s），把「不知道」伪装成了结论" % (
            c, out[c].dropna().unique()[:5])
        assert not (out[c].fillna(-1) == 0).any(), "%s 被填成 0" % c
    # 核心列必须有值
    for c in COUNT_COLS:
        assert out[c].notna().all()


def test_restore_keeps_recent_rows_from_existing_csv(tmp_path):
    """v1 只覆盖到 2026-08-21；更晚的行必须沿用现有 csv，不能被恢复动作抹掉。"""
    _write(str(tmp_path), "A", _v1_rows(["2026-08-20", "2026-08-21"], up=5))
    v1 = aggregate_v1_cache(str(tmp_path))
    existing = pd.DataFrame([{**{c: np.nan for c in OUT_COLS},
                              "date": "2026-09-02", "up_count": 1538.0, "down_count": 3898.0,
                              "limit_up": 52.0, "limit_down": 8.0}])
    out = build_restored(v1, healthy=None, existing=existing)
    assert len(out) == 3
    tail = out[out["date"] == pd.Timestamp("2026-09-02")].iloc[0]
    assert tail["up_count"] == 1538.0 and tail["down_count"] == 3898.0


def test_restore_carries_zt_columns_from_healthy_json(tmp_path):
    """connect_hl / zt_fail_ratio / zt_prev_ret 从健康镜像补齐（仅补空，不覆盖已有值）。"""
    _write(str(tmp_path), "A", _v1_rows(["2026-08-21"], up=5))
    v1 = aggregate_v1_cache(str(tmp_path))
    healthy = pd.DataFrame([{"date": "2026-08-21", "connect_hl": 7.0,
                             "zt_fail_ratio": 42.5, "zt_prev_ret": -0.31}])
    out = build_restored(v1, healthy=healthy, existing=None)
    r = out.iloc[0]
    assert r["connect_hl"] == 7.0
    assert abs(r["zt_fail_ratio"] - 42.5) < 1e-9
    assert abs(r["zt_prev_ret"] + 0.31) < 1e-9


def test_load_healthy_json_missing_returns_none():
    """健康镜像缺失要优雅降级（返回 None），不能让整条恢复链路崩掉。"""
    assert load_healthy_json("no/such/file.json") is None


def test_restored_schema_covers_production_aggregator_contract(tmp_path):
    """列契约守卫：恢复表的列必须覆盖生产聚合器产出的列，否则下游按列名读取会静默拿到 None。

    注意 ``_aggregate_frames`` 在**空输入**分支返回的是聚合前的原始列名
    （change_pct / close），非空分支才 rename 成 median_chg / avg_price，
    故这里按同一映射归一后再比对。
    """
    rename = {"change_pct": "median_chg", "close": "avg_price"}
    prod_cols = {rename.get(c, c) for c in _aggregate_frames([]).columns}
    assert prod_cols <= set(OUT_COLS), "恢复表缺列：%s" % sorted(prod_cols - set(OUT_COLS))

    _write(str(tmp_path), "A", _v1_rows(["2024-01-02"]))
    out = build_restored(aggregate_v1_cache(str(tmp_path)), healthy=None, existing=None)
    assert list(out.columns) == OUT_COLS, "列顺序漂移会破坏按位置/顺序的读取方"


def test_restore_tolerates_string_dates_in_healthy_json(tmp_path):
    """健壮性回归：健康镜像的 date 若是字符串（object dtype），合并不得抛 MergeError。"""
    _write(str(tmp_path), "A", _v1_rows(["2026-08-21"], up=5))
    v1 = aggregate_v1_cache(str(tmp_path))
    healthy = pd.DataFrame([{"date": "2026-08-21", "connect_hl": 7.0}])   # 故意用字符串日期
    out = build_restored(v1, healthy=healthy, existing=None)
    assert out["connect_hl"].iloc[0] == 7.0
