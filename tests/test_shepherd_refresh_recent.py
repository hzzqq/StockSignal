# -*- coding: utf-8 -*-
"""P2 增量刷新脚本的单测（离线，不联网）：核心是「刷新只能加/改最近的行，绝不缩短历史」。"""
import numpy as np
import pandas as pd

from scripts.refresh_shepherd_history_recent import merge_recent

COLS = ["date", "up_count", "down_count", "flat_count", "limit_up", "limit_down",
        "red_ratio", "touch_down", "hb_wave10", "median_chg"]


def _frame(rows):
    out = pd.DataFrame(rows)
    for c in COLS:
        if c not in out.columns:
            out[c] = np.nan
    return out[COLS]


def test_merge_recent_prefers_new_value_and_keeps_history():
    """同日取新值；历史行原样保留。"""
    base = _frame([{"date": "2026-08-20", "up_count": 2504, "red_ratio": 46.7},
                   {"date": "2026-08-21", "up_count": 999, "red_ratio": 1.0}])
    recent = _frame([{"date": "2026-08-21", "up_count": 1000, "red_ratio": 50.0},
                     {"date": "2026-09-10", "up_count": 1200, "red_ratio": 60.0}])
    out = merge_recent(base, recent).set_index("date")
    assert len(out) == 3
    assert out.loc["2026-08-20", "up_count"] == 2504        # 历史未被触碰
    assert out.loc["2026-08-21", "up_count"] == 1000        # 同日被新值覆盖
    assert out.loc["2026-09-10", "up_count"] == 1200
    assert out.index.is_monotonic_increasing


def test_merge_recent_keeps_old_value_when_refresh_is_null():
    """刷新值缺失（NaN）时不得把已有值抹成 NaN——这是「刷新反而毁数据」的静默失败。"""
    base = _frame([{"date": "2026-08-21", "up_count": 2504}])
    base["hb_wave10"] = 7.0
    recent = _frame([{"date": "2026-08-21", "up_count": 2504}])   # hb_wave10 为 NaN
    out = merge_recent(base, recent).set_index("date")
    assert out.loc["2026-08-21", "hb_wave10"] == 7.0


def test_merge_recent_never_shrinks_history():
    """★ 不变量：合并结果行数必须 >= 基表行数（刷新不许缩短历史）。"""
    base = _frame([{"date": "2026-08-%02d" % d, "up_count": d} for d in range(1, 11)])
    recent = _frame([{"date": "2026-08-%02d" % d, "up_count": 100 + d} for d in (9, 10, 11)])
    out = merge_recent(base, recent)
    assert len(out) == 11
    assert len(out) >= len(base)


def test_merge_recent_empty_recent_returns_base():
    base = _frame([{"date": "2026-08-01", "up_count": 1}])
    out = merge_recent(base, _frame([]))
    assert len(out) == 1 and out["up_count"].iloc[0] == 1


def test_merge_recent_adds_columns_present_only_in_recent():
    """recent 多出来的列（如 v2 专有列）应被补进结果，而不是被丢弃。"""
    base = _frame([{"date": "2026-08-01", "up_count": 1}])
    recent = _frame([{"date": "2026-08-01", "up_count": 2}])
    recent["brand_new_col"] = 42.0
    out = merge_recent(base, recent)
    assert "brand_new_col" in out.columns
    assert out["brand_new_col"].iloc[0] == 42.0


def test_drop_breadthless_new_dates_removes_premarket_empty_row():
    """★ 盘前跑 zt_pool 会带出「当天」空白行（广度全 NaN），必须丢掉。"""
    from scripts.refresh_shepherd_history_recent import drop_breadthless_new_dates

    base = pd.DataFrame({"date": ["2026-09-09", "2026-09-10"],
                         "up_count": [1.0, 2.0]})
    recent = pd.DataFrame({
        "date": ["2026-09-10", "2026-09-11"],
        "up_count": [2.0, np.nan], "down_count": [3.0, np.nan], "flat_count": [0.0, np.nan],
        "limit_up": [35.0, 35.0],
    })
    out = drop_breadthless_new_dates(recent, base)
    got = [str(d)[:10] for d in out["date"]]
    assert got == ["2026-09-10"], "空白未来行未被丢弃，实得 %s" % got


def test_drop_breadthless_new_dates_keeps_known_rows_even_if_empty():
    """基表里已有的日期即使广度为空也要保留（广度可能由别的路径补）。"""
    from scripts.refresh_shepherd_history_recent import drop_breadthless_new_dates

    base = pd.DataFrame({"date": ["2026-09-04"], "up_count": [np.nan]})
    recent = pd.DataFrame({"date": ["2026-09-04"], "up_count": [np.nan],
                           "down_count": [np.nan], "flat_count": [np.nan],
                           "limit_up": [39.0]})
    out = drop_breadthless_new_dates(recent, base)
    assert len(out) == 1, "基表已有日期被误删"
