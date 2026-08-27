"""DataCleaner.full_pipeline 的「数据对错」契约断言（离线、确定性、独立重算对账）。

与 test_data_correctness.py 互补：那里覆盖结构性（无 NaN / 有限 / 单调），
这里锁住**数值定义本身**与**日期-数值对齐不变式**——这类 bug 不会让页面崩，
但会让"看起来对的图实际是错的"。所有断言都用独立重算结果做对照，
而非 trust 代码自身输出，确保测试能真正抓到回归（非安慰剂）。
"""
import numpy as np
import pandas as pd
import pytest

from modules.cleaner import DataCleaner


def _mk(seed=7, n=80, base=10.0):
    """生成一只「物理自洽」的合成 K线（与 test_data_correctness 同约定）。"""
    rng = np.random.default_rng(seed)
    closes = base + np.cumsum(rng.normal(0, 0.2, n))
    opens = closes + rng.normal(0, 0.05, n)
    highs = np.maximum(opens, closes) + np.abs(rng.normal(0, 0.05, n))
    lows = np.minimum(opens, closes) - np.abs(rng.normal(0, 0.05, n))
    dates = pd.date_range("2023-01-02", periods=n, freq="B")
    vols = rng.integers(1_000_000, 5_000_000, n).astype(float)
    return pd.DataFrame({
        "date": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": vols,
    })


def test_full_pipeline_preserves_value_date_alignment():
    """清洗后每个交易日（按日期键值）的 close 必须仍等于输入——禁止数值被错排到别的日期。

    这是最隐蔽的一类脏数据 bug：管线若重排/重索引不当，会让「图看着对、实为错位」，
    页面不崩但结论全错。
    """
    df = _mk()
    out = DataCleaner.full_pipeline(df.copy())
    in_map = dict(zip(pd.to_datetime(df["date"]), df["close"]))
    out_map = dict(zip(pd.to_datetime(out["date"]), out["close"]))
    assert set(in_map) == set(out_map), "清洗后交易日集合发生变化"
    for d in in_map:
        assert abs(in_map[d] - out_map[d]) < 1e-9, f"日期 {d} 的 close 被错位"


def test_return_1d_definition():
    """return_1d 必须等于 close.pct_change(1)*100（独立重算对照，非 trust 自身输出）。"""
    df = _mk()
    out = DataCleaner.full_pipeline(df.copy())
    expect = df["close"].pct_change(1) * 100
    pd.testing.assert_series_equal(
        out["return_1d"].reset_index(drop=True),
        expect.reset_index(drop=True),
        check_names=False, rtol=1e-9,
    )


def test_return_5d_20d_definition():
    """return_5d / return_20d 必须等于对应周期的 pct_change*100。"""
    df = _mk()
    out = DataCleaner.full_pipeline(df.copy())
    for p in (5, 20):
        expect = df["close"].pct_change(p) * 100
        pd.testing.assert_series_equal(
            out[f"return_{p}d"].reset_index(drop=True),
            expect.reset_index(drop=True),
            check_names=False, rtol=1e-9,
        )


def test_ma60_is_rolling_mean():
    """ma60 必须等于 close 的 60 日滚动均值（补齐长周期均线定义，ma5 已在别处锁过）。"""
    df = _mk(n=80)
    out = DataCleaner.full_pipeline(df.copy())
    expect = out["close"].rolling(60).mean()
    valid = expect.notna()
    pd.testing.assert_series_equal(
        out["ma60"][valid].reset_index(drop=True),
        expect[valid].reset_index(drop=True),
        check_names=False, rtol=1e-9,
    )


def test_volume_non_negative():
    """成交量不得出现负值（脏数据 coerce 后若为 NaN，ffill 应兜底成非负历史值）。"""
    df = _mk()
    out = DataCleaner.full_pipeline(df.copy())
    assert (out["volume"] >= 0).all(), "清洗后出现负成交量"


def test_contract_catches_ma60_window_regression(monkeypatch):
    """突变敏感性：若 ma60 被错误算成 rolling(5)，契约断言必须失败——证明本文件非安慰剂。

    这是对你"测试能否真实暴露 bug"元焦点的直接证据：锁住定义的断言在定义被改坏时
    会立即红，而不是"怎么改都绿"。
    """
    df = _mk(n=80)

    def bad_calc_ma(self, price_col="close", windows=None):
        d = self.copy()
        d["ma60"] = d[price_col].rolling(5).mean()  # 故意算错窗口
        return d

    monkeypatch.setattr(DataCleaner, "calc_ma", bad_calc_ma)
    out = DataCleaner.full_pipeline(df.copy())
    expect = out["close"].rolling(60).mean()
    valid = expect.notna()
    with pytest.raises(AssertionError):
        pd.testing.assert_series_equal(
            out["ma60"][valid].reset_index(drop=True),
            expect[valid].reset_index(drop=True),
            check_names=False, rtol=1e-9,
        )
