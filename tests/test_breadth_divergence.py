"""
方案③ 守卫：breadth_divergence 模块
覆盖：日历缺失降级 / 分化检测逻辑 / 当前状态判定 / empty df 兜底 / 阈值语义
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import pytest
from modules import breadth_divergence as bd


def _df():
    # 构造 2 年 × 12 月、每天一条；让 2015 年普遍红、2021 年中若干天「红盘率高+跌停高」
    rows = []
    for y in (2014, 2015, 2021):
        for m in range(1, 13):
            for d in (5, 15, 25):
                rr = 75.0 if y == 2015 else 45.0
                ld = 5
                if y == 2021 and m == 6:
                    rr = 60.0  # 红盘率偏高
                    ld = 95     # 跌停数极高 → 分化
                rows.append(dict(
                    date=f"{y}-{m:02d}-{d:02d}",
                    red_ratio=rr, limit_down=float(ld),
                    up_count=800 if rr >= 50 else 400,
                    down_count=200 if rr >= 50 else 800,
                    zt_prev_ret=0.01,
                ))
    return pd.DataFrame(rows)


def test_calendar_available_and_shape():
    cal = bd.breadth_calendar(_df())
    assert cal["available"] is True
    assert cal["latest_year"] == 2021
    assert len(cal["z"]) == 3  # 3 years
    assert len(cal["z"][0]) == 12  # 12 months
    # 2015 年各月红盘率均值应≈75
    y2015_idx = cal["years"].index(2015)
    assert all(65 <= (v or 0) <= 85 for v in cal["z"][y2015_idx])


def test_calendar_missing_degrades():
    cal = bd.breadth_calendar(pd.DataFrame())
    assert cal["available"] is False
    assert cal["z"] == []


def test_divergence_flags_div_day():
    div = bd.divergence_episodes(_df(), red_thresh=50.0, ld_quantile=0.90)
    assert div["available"] is True
    # 2021-06 的 3 天应被标记（红盘率60≥50 且跌停占比处 p90）
    div_dates = {e["date"] for e in div["episodes"]}
    assert any("2021-06" in d for d in div_dates)
    assert div["ld_p90"] is not None
    assert div["n_episodes"] >= 1


def test_divergence_current_state():
    div = bd.divergence_episodes(_df(), red_thresh=50.0, ld_quantile=0.90)
    cur = div["current"]
    # 最新行是 2021-12-25 → 红盘率45(<50) → 非分化
    assert cur["is_divergent"] is False
    assert cur["red_ratio"] == 45.0


def test_divergence_empty_safe():
    div = bd.divergence_episodes(pd.DataFrame())
    assert div["available"] is False
    assert div["episodes"] == []
    assert div["current"] is None


def test_divergence_no_threshold_match():
    # 全部红盘率很低 → 无分化日
    df = _df()
    df["red_ratio"] = 10.0
    df["limit_down"] = 2.0
    div = bd.divergence_episodes(df, red_thresh=50.0, ld_quantile=0.90)
    assert div["n_episodes"] == 0
    assert div["current"]["is_divergent"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
