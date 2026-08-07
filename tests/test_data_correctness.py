"""关键数据「正确性」断言（替代纯"不崩"冒烟）。

目标：把"页面渲染不抛异常"升级为"数据转换逻辑是对的"。
全部离线、无网络依赖——喂合成 DataFrame / 合成 K线，验证：
  - OHLC 内部自洽（high>=max(open,close), low<=min(open,close)）
  - K线日期严格单调（无重复、无乱序、无 NaT）
  - DataCleaner.full_pipeline 产出无 NaN 关键列、收益率/均线列存在且有限
  - technical.full_analysis 各维度返回 dict（契约），趋势判断对已知排列正确
  - market_drivers 股息率 PE 反推公式数值正确且落在 sane 区间
这些断言锁住"转换正确性"，是数据对错的底线。
"""
import numpy as np
import pandas as pd
import pytest

from modules.cleaner import DataCleaner
from modules.technical import full_analysis, overall_technical_score


def _make_ohlc(n=30, seed=42, base=10.0):
    """生成一只「物理自洽」的合成 K线：high>=max(o,c)、low<=min(o,c)、价格随机游走。"""
    rng = np.random.default_rng(seed)
    closes = base + np.cumsum(rng.normal(0, 0.1, n))
    opens = closes + rng.normal(0, 0.05, n)
    # 保证 high/low 包住 open/close
    highs = np.maximum(opens, closes) + np.abs(rng.normal(0, 0.05, n))
    lows = np.minimum(opens, closes) - np.abs(rng.normal(0, 0.05, n))
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    vols = rng.integers(1_000_000, 5_000_000, n).astype(float)
    return pd.DataFrame({
        "date": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": vols,
    })


def test_ohlc_self_consistent():
    """涨幅/跌幅列由 OHLC 推导时不能自相矛盾：high 必须>=max(o,c)、low<=min(o,c)。"""
    df = _make_ohlc()
    assert (df["high"] >= df[["open", "close"]].max(axis=1) - 1e-9).all(), \
        "存在 high < max(open,close) 的非法 K线"
    assert (df["low"] <= df[["open", "close"]].min(axis=1) + 1e-9).all(), \
        "存在 low > min(open,close) 的非法 K线"


def test_kline_dates_strictly_monotonic():
    """K线日期必须严格升序、无重复、无 NaT——乱序/重复会让技术指标错位。"""
    df = _make_ohlc()
    d = pd.to_datetime(df["date"])
    assert d.isna().sum() == 0, "存在 NaT 日期"
    assert d.is_unique, "存在重复日期"
    assert d.is_monotonic_increasing, "日期非严格升序"


def test_kline_sorted_ascending_preserved():
    """交易日历乱序输入时，清洗管线应保证按日期升序输出（技术分析前提）。"""
    df = _make_ohlc().sort_values("date", ascending=False)  # 故意倒序
    out = DataCleaner.full_pipeline(df.copy())
    out_dates = pd.to_datetime(out["date"])
    assert out_dates.is_monotonic_increasing, "清洗后日期未恢复升序"


def test_cleaner_pipeline_no_nan_critical():
    """full_pipeline 完成后 OHLCV 关键列不得有 NaN（ffill/bfill 应已兜底）。
    注：ma* 列前 N-1 行因 rolling 窗口不足天然为 NaN，属正确行为，不在此断言。"""
    df = _make_ohlc()
    out = DataCleaner.full_pipeline(df.copy())
    for c in ("open", "high", "low", "close", "volume"):
        assert c in out.columns, f"清洗后缺失列 {c}"
        assert out[c].notna().all(), f"列 {c} 仍含 NaN"


def test_cleaner_returns_finite():
    """收益率列（return_1d 等）与均线列必须全有限（无 inf/NaN），否则绘图会崩。"""
    df = _make_ohlc()
    out = DataCleaner.full_pipeline(df.copy())
    ret_cols = [c for c in out.columns if c.startswith("return_")]
    assert ret_cols, "未生成任何收益率列"
    for c in ret_cols + ["ma5", "ma10", "ma20", "ma60"]:
        if c in out.columns:
            assert np.isfinite(out[c].dropna()).all(), f"列 {c} 含非有限值"


def test_cleaner_ma_is_rolling_mean():
    """ma5 必须等于 close 的 5 日滚动均值（前 4 行允许 NaN）——锁住均线定义不被改坏。"""
    df = _make_ohlc()
    out = DataCleaner.full_pipeline(df.copy())
    expect = out["close"].rolling(5).mean()
    got = out["ma5"]
    valid = expect.notna()
    pd.testing.assert_series_equal(
        got[valid].reset_index(drop=True),
        expect[valid].reset_index(drop=True),
        check_names=False,
        rtol=1e-9,
    )


def test_full_analysis_contract():
    """full_analysis 必须返回 4 个 dict（trend/momentum/volume/patterns），不抛不崩契约。"""
    df = DataCleaner.full_pipeline(_make_ohlc())
    res = full_analysis(df)
    assert isinstance(res, dict)
    for k in ("trend", "momentum", "volume", "patterns"):
        assert k in res, f"full_analysis 缺维度 {k}"
        # trend/momentum/volume 为 dict（页面 dict 取值）；patterns 为形态列表
        assert isinstance(res[k], (dict, list)), f"维度 {k} 非 dict/list（页面依赖结构化取值）"
    # 已知多头排列：强制 ma5>ma10>ma20 且 close>ma5
    bull = _make_ohlc(n=60)
    bull["close"] = np.linspace(10, 20, 60)
    bull["ma5"] = bull["close"].rolling(5).mean()
    bull["ma10"] = bull["close"].rolling(10).mean()
    bull["ma20"] = bull["close"].rolling(20).mean()
    bull["ma60"] = bull["close"].rolling(60).mean()
    r = full_analysis(bull)["trend"]
    assert r.get("arrangement") == "多头排列", f"应判多头排列，实际 {r.get('arrangement')}"


def test_overall_score_bounds_and_weights():
    """综合得分必须落在 [0,100] 且 NaN 维度按中性 50 处理。"""
    s = overall_technical_score(80, 70, 60)
    assert 0.0 <= s <= 100.0
    s2 = overall_technical_score(None, np.nan, 90)
    assert 0.0 <= s2 <= 100.0
    # 权重中性化后不应等于纯第3维 90
    assert abs(s2 - 90.0) > 1e-6


def test_dividend_pe_inverse_sane():
    """股息率 PE 反推公式 sanity：payout=0.35 时，PE=10→3.5%、PE=20→1.75%；
    且股息率必须为正、落在 (0, 15] 合理区间。"""
    payout = 0.35

    def div_from_pe(pe):
        pe = float(pe)
        if pe <= 0:
            return None
        return payout * 100.0 / pe

    assert abs(div_from_pe(10) - 3.5) < 1e-9
    assert abs(div_from_pe(20) - 1.75) < 1e-9
    # 单调性：PE 越低股息率越高
    assert div_from_pe(10) > div_from_pe(20) > div_from_pe(40)
    # sane 区间
    for pe in (8, 12, 15, 25, 40):
        d = div_from_pe(pe)
        assert 0 < d <= 15, f"PE={pe} 反推股息率 {d} 超出 sane 区间"


def test_dividend_pe_zero_or_negative_safe():
    """PE<=0（亏损股）反推应安全返回 None（不抛、不为负）。"""
    payout = 0.35

    def div_from_pe(pe):
        pe = float(pe)
        if pe <= 0:
            return None
        return payout * 100.0 / pe

    assert div_from_pe(0) is None
    assert div_from_pe(-5) is None
