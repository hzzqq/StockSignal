"""R15：数据清洗器纯函数单测（无网依赖）。

覆盖 modules/cleaner.py 的 DataCleaner 静态方法簇：
1. fill_missing  —— ffill/bfill/mean/median 四种缺失值填充；
2. remove_outliers —— iqr / zscore 两种异常值剔除；
3. normalize      —— minmax / zscore 归一化；
4. calc_returns    —— periods=[1,5,20] 收益率；
5. calc_ma        —— windows=[5,10,20,60] 均线；
6. align_dates    —— 多 DataFrame 按 date 取交集对齐；
7. full_pipeline  —— 一键流水线自检。

全部走合成 DataFrame，不触碰网络 / 不依赖 streamlit。
"""

import numpy as np
import pandas as pd

from modules.cleaner import DataCleaner


# ----------------------------------------------------------------------
# 构造工具
# ----------------------------------------------------------------------
def _price_df(n=30, start=100.0, step=1.0):
    """单调递增的收盘价序列，附带少量 NaN 用于填充测试。"""
    idx = pd.date_range("2024-01-01", periods=n)
    close = [start + step * i for i in range(n)]
    return pd.DataFrame({
        "date": idx,
        "open": close,
        "high": [c + 1 for c in close],
        "low": [c - 1 for c in close],
        "close": close,
        "volume": [1000 + i for i in range(n)],
    })


# ----------------------------------------------------------------------
# fill_missing
# ----------------------------------------------------------------------
def test_fill_missing_ffill():
    df = _price_df()
    df.loc[5, "close"] = np.nan
    df.loc[6, "close"] = np.nan
    out = DataCleaner.fill_missing(df, method="ffill")
    # 前向填充取上一行（第 4 行）的值：close[4]=104
    assert out.loc[5, "close"] == 104.0
    assert out.loc[6, "close"] == 104.0
    assert out.isna().sum().sum() == 0


def test_fill_missing_bfill():
    df = _price_df()
    df.loc[0, "close"] = np.nan
    out = DataCleaner.fill_missing(df, method="bfill")
    # 第 0 行后向填充为第 1 行的值（101）
    assert out.loc[0, "close"] == 101.0


def test_fill_missing_mean():
    df = _price_df(n=10)
    df.loc[3, "close"] = np.nan
    out = DataCleaner.fill_missing(df, method="mean")
    expected = df["close"].mean()  # 含 NaN 的均值
    assert abs(out.loc[3, "close"] - expected) < 1e-9


def test_fill_missing_median():
    df = _price_df(n=10)
    df.loc[3, "close"] = np.nan
    out = DataCleaner.fill_missing(df, method="median")
    expected = df["close"].median()
    assert abs(out.loc[3, "close"] - expected) < 1e-9


def test_fill_missing_invalid_method():
    df = _price_df(n=5)
    try:
        DataCleaner.fill_missing(df, method="nope")
        assert False, "应当抛出 ValueError"
    except ValueError:
        pass


def test_fill_missing_columns_subset():
    df = _price_df(n=6)
    df.loc[2, "close"] = np.nan
    df.loc[2, "volume"] = np.nan
    out = DataCleaner.fill_missing(df, method="ffill", columns=["close"])
    # 仅 close 被填充（取上一行第 1 行=101），volume 仍 NaN
    assert out.loc[2, "close"] == 101.0
    assert pd.isna(out.loc[2, "volume"])


# ----------------------------------------------------------------------
# remove_outliers
# ----------------------------------------------------------------------
def test_remove_outliers_iqr():
    df = _price_df(n=20)
    df.loc[10, "close"] = 99999.0  # 极端离群点
    out = DataCleaner.remove_outliers(df, column="close", method="iqr")
    assert 99999.0 not in out["close"].values
    assert len(out) < len(df)


def test_remove_outliers_iqr_no_drop_normal():
    df = _price_df(n=20)
    out = DataCleaner.remove_outliers(df, column="close", method="iqr")
    # 正常单调递增数据不应丢失任何行
    assert len(out) == len(df)


def test_remove_outliers_missing_column():
    df = _price_df(n=10)
    out = DataCleaner.remove_outliers(df, column="not_exist")
    # 列不存在时原样返回
    assert len(out) == len(df)


def test_remove_outliers_zscore():
    df = _price_df(n=20)
    df.loc[5, "close"] = 88888.0
    out = DataCleaner.remove_outliers(df, column="close", method="zscore", threshold=3.0)
    assert 88888.0 not in out["close"].values


def test_remove_outliers_invalid_method():
    df = _price_df(n=5)
    try:
        DataCleaner.remove_outliers(df, column="close", method="bad")
        assert False, "应当抛出 ValueError"
    except ValueError:
        pass


# ----------------------------------------------------------------------
# normalize
# ----------------------------------------------------------------------
def test_normalize_minmax():
    df = _price_df(n=11)  # close 100..110
    out = DataCleaner.normalize(df, columns=["close"], method="minmax")
    assert abs(out["close"].min()) < 1e-9
    assert abs(out["close"].max() - 1.0) < 1e-9


def test_normalize_zscore():
    df = _price_df(n=20)
    out = DataCleaner.normalize(df, columns=["close"], method="zscore")
    # 标准分均值接近 0
    assert abs(out["close"].mean()) < 1e-9


def test_normalize_skip_missing_col():
    df = _price_df(n=10)
    out = DataCleaner.normalize(df, columns=["not_exist"], method="minmax")
    # 不存在的列被跳过，原 DataFrame 结构不变
    assert "close" in out.columns


# ----------------------------------------------------------------------
# calc_returns
# ----------------------------------------------------------------------
def test_calc_returns_periods():
    df = _price_df(n=30, start=100.0, step=1.0)
    out = DataCleaner.calc_returns(df, periods=[1, 5, 20])
    assert "return_1d" in out.columns
    assert "return_5d" in out.columns
    assert "return_20d" in out.columns
    # step=1 时 1 日收益率 = (101-100)/100*100 = 1.0（自第 2 行起）
    assert abs(out.loc[1, "return_1d"] - 1.0) < 1e-9
    # 前 period-1 行应为 NaN
    assert pd.isna(out.loc[0, "return_1d"])
    assert pd.isna(out.loc[4, "return_5d"])


# ----------------------------------------------------------------------
# calc_ma
# ----------------------------------------------------------------------
def test_calc_ma_windows():
    df = _price_df(n=70)
    out = DataCleaner.calc_ma(df, windows=[5, 10, 20, 60])
    for w in [5, 10, 20, 60]:
        assert f"ma{w}" in out.columns
    # ma5 第 4 行起等于前 5 行均值（100..104 → 102）
    assert abs(out.loc[4, "ma5"] - 102.0) < 1e-9
    # 前窗口-1 行应为 NaN
    assert pd.isna(out.loc[3, "ma5"])
    assert pd.isna(out.loc[58, "ma60"])


# ----------------------------------------------------------------------
# align_dates
# ----------------------------------------------------------------------
def test_align_dates_intersection():
    d1 = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
        "a": [1, 2, 3],
    })
    d2 = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
        "b": [20, 30, 40],
    })
    a, b = DataCleaner.align_dates(d1, d2)
    # 交集为 01-02 / 01-03
    assert len(a) == 2
    assert len(b) == 2
    assert pd.Timestamp("2024-01-02") in a["date"].values
    assert pd.Timestamp("2024-01-03") in b["date"].values
    # 01-01 / 01-04 已被剔除
    assert pd.Timestamp("2024-01-01") not in a["date"].values
    assert pd.Timestamp("2024-01-04") not in b["date"].values


def test_align_dates_string_columns():
    """非 datetime 列的 date 也能对齐（防御实现的分支）。"""
    d1 = pd.DataFrame({"date": ["2024-01-01", "2024-01-02"], "a": [1, 2]})
    d2 = pd.DataFrame({"date": ["2024-01-02", "2024-01-03"], "b": [3, 4]})
    a, b = DataCleaner.align_dates(d1, d2)
    assert list(a["date"]) == ["2024-01-02"]
    assert list(b["date"]) == ["2024-01-02"]


# ----------------------------------------------------------------------
# full_pipeline
# ----------------------------------------------------------------------
def test_full_pipeline():
    df = _price_df(n=70, start=100.0, step=1.0)
    out = DataCleaner.full_pipeline(df.copy())
    # 流水线应产出收益率与均线列
    assert "return_1d" in out.columns
    assert "ma5" in out.columns
    assert "ma20" in out.columns
    assert "ma60" in out.columns


# ----------------------------------------------------------------------
# 边界：空 / 单值
# ----------------------------------------------------------------------
def test_fill_missing_empty_df():
    df = pd.DataFrame(columns=["close"])
    out = DataCleaner.fill_missing(df, method="ffill")
    assert out.empty


def test_calc_returns_single_row():
    df = pd.DataFrame({"date": [pd.Timestamp("2024-01-01")], "close": [100.0]})
    out = DataCleaner.calc_returns(df)
    # 单行为 NaN，但不抛异常
    assert pd.isna(out.loc[0, "return_1d"])


def test_calc_ma_insufficient_rows():
    df = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=3), "close": [1, 2, 3]})
    out = DataCleaner.calc_ma(df, windows=[5, 10, 20])
    for w in [5, 10, 20]:
        assert f"ma{w}" in out.columns
        # 行数不足，全部 NaN
        assert out[f"ma{w}"].isna().all()
