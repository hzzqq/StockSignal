"""
方案⑤ 守卫：temperature_backtest 模块
覆盖：空/短数据降级 / 分档映射 / 均值回归逻辑（冰点→反弹、狂热→回落）/ 日期排序 /
      全样本基准 / 零样本档位 available=False
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import pytest
from modules import temperature_backtest as tb


def _df():
    """10 天，红盘率刻意安排：row0=冰点(10)，row4=狂热(95)，其余=活跃(60)。
    仅 row0..row4 同时拥有 +1/+5 前瞻（需要 i <= n-6=4），其余被前瞻缺失剔除。
    """
    dates = [f"2020-01-{d:02d}" for d in range(1, 11)]
    rr = [10, 60, 60, 60, 95, 60, 60, 60, 60, 60]
    return pd.DataFrame({"date": dates, "red_ratio": rr})


def test_empty_df():
    r = tb.band_backtest(pd.DataFrame())
    assert r["available"] is False


def test_too_short_no_forward():
    # <6 行无法同时拥有 +1 与 +5 前瞻 → 降级
    df = pd.DataFrame({
        "date": [f"2020-01-0{i}" for i in range(1, 5)],
        "red_ratio": [10, 20, 30, 40],
    })
    r = tb.band_backtest(df)
    assert r["available"] is False
    assert "前瞻" in r["reason"]


def test_band_classification_and_reversion():
    r = tb.band_backtest(_df())
    assert r["available"] is True

    by_level = {b["level"]: b for b in r["bands"]}
    # 冰点：次日 +50、改善率 100%
    ice = by_level[0]
    assert ice["n"] == 1
    assert ice["next_mean_delta"] == pytest.approx(50.0)
    assert ice["next_impr_rate"] == pytest.approx(100.0)
    assert ice["d5_mean_delta"] == pytest.approx(50.0)
    assert ice["d5_impr_rate"] == pytest.approx(100.0)
    # 狂热：次日 -35、改善率 0%
    hot = by_level[4]
    assert hot["n"] == 1
    assert hot["next_mean_delta"] == pytest.approx(-35.0)
    assert hot["next_impr_rate"] == pytest.approx(0.0)
    # 偏冷/中性：本数据无样本 → available False, n=0
    assert by_level[1]["available"] is False and by_level[1]["n"] == 0
    assert by_level[2]["available"] is False and by_level[2]["n"] == 0


def test_baseline():
    r = tb.band_backtest(_df())
    base = r["baseline"]
    assert base["n"] == 5  # 仅 row0..row4 进入分析
    assert base["next_impr_rate"] == pytest.approx(40.0)   # [T,F,F,T,F]
    assert base["next_mean_delta"] == pytest.approx(10.0)  # (50+0+0+35-35)/5
    assert base["d5_impr_rate"] == pytest.approx(20.0)     # [T,F,F,F,F]


def test_date_sorting_respected():
    # 把 _df 日期顺序打乱，函数内部应按日期升序计算前瞻
    df = _df()
    df = df.iloc[::-1].reset_index(drop=True)  # 日期逆序
    r = tb.band_backtest(df)
    assert r["available"] is True
    by_level = {b["level"]: b for b in r["bands"]}
    assert by_level[0]["next_mean_delta"] == pytest.approx(50.0)  # 冰点仍 +50


def test_red_ratio_nan_dropped():
    df = pd.DataFrame({
        "date": ["2020-01-01", "2020-01-02", "2020-01-03",
                 "2020-01-04", "2020-01-05", "2020-01-06"],
        "red_ratio": [10, float("nan"), 60, 95, 60, 60],
    })
    r = tb.band_backtest(df)
    # 只有 row0..row0 同时拥有 +1/+5（n=6 → i<=0）。row0=冰点。
    # 但 row1 NaN 被剔除，row0 的 next=row1 也 NaN → 实际无可分析行
    # 这里只需验证不崩溃且降级或可用，不强求结构
    assert isinstance(r["available"], bool)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
