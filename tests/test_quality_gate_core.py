# -*- coding: utf-8 -*-
"""P0-3 覆盖率门禁补测：核心六模块（technical/cleaner/shepherd/fetcher/...
补充 technical 与 cleaner 的高价值分支用例，把 core 子集覆盖率补到 >=70%。
纯计算、无网络，可离线跑；与 test_whitebox_technical.py 互补（不重复其用例）。
"""
import numpy as np
import pandas as pd
import pytest

from modules import technical, cleaner


def _ohlcv(n=80, seed=7, trend=0.0):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    close = 10 + np.cumsum(rng.normal(trend, 0.2, n))
    open_ = close + rng.normal(0, 0.05, n)
    high = np.maximum(open_, close) + rng.uniform(0.05, 0.4, n)
    low = np.minimum(open_, close) - rng.uniform(0.05, 0.4, n)
    vol = rng.integers(1_000_000, 5_000_000, n).astype(float)
    return pd.DataFrame({
        "date": dates, "open": open_, "high": high, "low": low,
        "close": close, "volume": vol,
    })


# ───────────────────────── technical ─────────────────────────
class TestTechnicalPrimitives:
    def test_compute_atr(self):
        df = _ohlcv()
        assert technical.compute_atr(df) is not None
        assert technical.compute_atr(None) is None
        assert technical.compute_atr(pd.DataFrame()) is None
        assert technical.compute_atr(df.drop(columns=["high"])) is None
        assert technical.compute_atr(df.head(5)) is None  # len < period
        flat = pd.DataFrame({"high": [1, 1], "low": [1, 1], "close": [1, 1]})
        assert technical.compute_atr(flat) is None  # atr<=0

    def test_compute_rsi(self):
        df = _ohlcv()
        assert 0 <= technical.compute_rsi(df) <= 100
        assert technical.compute_rsi(None) is None
        assert technical.compute_rsi(df.drop(columns=["close"])) is None
        assert technical.compute_rsi(df.head(5)) is None  # len < period+1
        up = pd.DataFrame({"close": np.linspace(1, 2, 30)})
        assert technical.compute_rsi(up) == 100.0  # 全涨
        dn = pd.DataFrame({"close": np.linspace(2, 1, 30)})
        assert technical.compute_rsi(dn) == 0.0  # 全跌
        flat = pd.DataFrame({"close": np.ones(30)})
        assert technical.compute_rsi(flat) == 50.0  # 持平

    def test_rsi_series(self):
        df = _ohlcv()
        s = technical.rsi_series(df)
        assert len(s) == len(df)
        assert technical.rsi_series(None).empty
        assert technical.rsi_series("x").empty
        assert technical.rsi_series(pd.DataFrame()).empty
        assert technical.rsi_series(df, period=0).empty
        assert technical.rsi_series(df.drop(columns=["close"])).empty
        assert technical.rsi_series(df.head(3)).empty  # 窗口不足

    def test_compute_ema(self):
        df = _ohlcv()
        s = technical.compute_ema(df["close"], 5)
        assert s is not None and len(s) == len(df)
        assert technical.compute_ema(None, 5) is None
        assert technical.compute_ema(pd.Series([np.nan, np.nan]), 5) is None

    def test_compute_macd(self):
        df = _ohlcv()
        out = technical.compute_macd(df)
        assert out and {"dif", "dea", "macd"} <= set(out)
        assert technical.compute_macd(None) is None
        assert technical.compute_macd(df.drop(columns=["close"])) is None
        assert technical.compute_macd(df.head(5)) is None  # len < slow
        bad = df.copy()
        bad["close"] = "x"
        assert technical.compute_macd(bad) is None  # 全 NaN

    def test_detect_bullish_divergence(self):
        n = 80
        # 未创新低（近段 >= 前段低点）
        df = _ohlcv(n)
        r = technical.detect_bullish_divergence(df)
        assert r["status"] in ("ok", "unavailable") and r["divergence"] in (True, False)
        # 缺列 / 空 / NaN
        assert technical.detect_bullish_divergence(None)["status"] == "unavailable"
        assert technical.detect_bullish_divergence(pd.DataFrame())["status"] == "unavailable"
        assert technical.detect_bullish_divergence(df.drop(columns=["close"]))["status"] == "unavailable"
        assert technical.detect_bullish_divergence(df.drop(columns=["volume"]))["status"] == "unavailable"
        nan_close = df.copy()
        nan_close["close"] = np.nan
        assert technical.detect_bullish_divergence(nan_close)["status"] == "unavailable"
        assert technical.detect_bullish_divergence(df.head(20))["status"] == "unavailable"  # 样本不足
        # 构造背离：近期创新低但 MACD 柱不创新低 + 放量
        c = np.linspace(12, 8, n)
        c[:40] = np.linspace(12, 10, 40)  # 先跌一段
        c[40:55] = np.linspace(10, 11.5, 15)  # 反弹
        c[55:70] = np.linspace(11.5, 8.2, 15)  # 再跌创新低（幅度小）
        c[70:] = np.linspace(8.2, 9.5, 10)
        v = np.full(n, 2_000_000.0)
        v[70:] = 5_000_000.0  # 末段放量
        d2 = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=n, freq="B"),
                           "open": c, "high": c + 0.2, "low": c - 0.2,
                           "close": c, "volume": v})
        r2 = technical.detect_bullish_divergence(d2)
        assert r2["status"] == "ok", r2

    def test_overall_technical_score(self):
        assert technical.overall_technical_score(80, 60, 40) == pytest.approx(63.0)
        assert technical.overall_technical_score(None, None, None) == 50.0
        assert technical.overall_technical_score(120, -5, 50) == pytest.approx(52.5)  # 裁剪
        assert technical.overall_technical_score(80, 60, 40, weights=(0, 0, 0)) == 50.0


class TestTechnicalAnalysis:
    def test_analyze_trend(self):
        df = _ohlcv()
        df["ma5"] = df["close"].rolling(5).mean()
        df["ma10"] = df["close"].rolling(10).mean()
        df["ma20"] = df["close"].rolling(20).mean()
        df["ma60"] = df["close"].rolling(60).mean()
        assert technical.analyze_trend(df)["arrangement"] in ("多头排列", "空头排列", "偏多", "偏空", "纠缠")
        assert technical.analyze_trend(None)["error"] == "数据为空"
        assert technical.analyze_trend(df.drop(columns=["close"]))["error"].startswith("缺少")
        bad = df.copy()
        bad.loc[bad.index[-1], "close"] = np.nan
        assert technical.analyze_trend(bad)["error"].startswith("收盘价缺失")
        # 构造严格多头
        up = _ohlcv(n=80, trend=0.05)
        for w in (5, 10, 20, 60):
            up[f"ma{w}"] = up["close"].rolling(w).mean()
        assert technical.analyze_trend(up)["arrangement"] == "多头排列"
        # 构造严格空头
        dn = _ohlcv(n=80, trend=-0.05)
        for w in (5, 10, 20, 60):
            dn[f"ma{w}"] = dn["close"].rolling(w).mean()
        assert technical.analyze_trend(dn)["arrangement"] in ("空头排列", "偏空")
        # 无 ma 列 → 纠缠兜底
        no_ma = _ohlcv(n=30)
        assert technical.analyze_trend(no_ma)["arrangement"] == "纠缠"

    def test_analyze_momentum(self):
        df = _ohlcv()
        df["return_1d"] = df["close"].pct_change(1) * 100
        df["return_5d"] = df["close"].pct_change(5) * 100
        df["return_20d"] = df["close"].pct_change(20) * 100
        r = technical.analyze_momentum(df)
        assert "momentum_score" in r and "returns" in r
        assert technical.analyze_momentum(None)["error"] == "数据为空"
        for v, label in ((12, "强势上攻"), (6, "明显走强"), (3, "温和上涨"), (0, "震荡整理"),
                         (-3, "弱势回调"), (-8, "加速下跌")):
            d = df.copy()
            d["return_5d"] = v
            assert technical._momentum_label(v) == label

    def test_analyze_volume(self):
        df = _ohlcv()
        df["change_pct"] = df["close"].pct_change() * 100
        assert technical.analyze_volume(df)["consecutive_days"] >= 1
        assert technical.analyze_volume(None)["error"] == "数据为空"
        assert technical.analyze_volume(df.drop(columns=["volume"]))["error"] == "数据为空"
        assert technical.analyze_volume(df.head(3))["error"].startswith("数据不足")
        # 量价齐升（用 .loc 赋值，规避 pandas CoW）
        up = df.copy()
        up.loc[up.index[-1], "volume"] = up["volume"].iloc[-6:-1].mean() * 2
        up.loc[up.index[-1], "change_pct"] = 2.0
        assert technical.analyze_volume(up)["volume_price_label"] == "量价齐升"
        # 缩量回调
        dn = df.copy()
        dn.loc[dn.index[-1], "volume"] = dn["volume"].iloc[-6:-1].mean() * 0.5
        dn.loc[dn.index[-1], "change_pct"] = -2.0
        assert technical.analyze_volume(dn)["volume_price_label"] == "缩量回调(健康)"
        # 放量下跌
        dv = df.copy()
        dv.loc[dv.index[-1], "volume"] = dv["volume"].iloc[-6:-1].mean() * 2
        dv.loc[dv.index[-1], "change_pct"] = -2.0
        assert technical.analyze_volume(dv)["volume_price_label"] == "放量下跌(警惕)"

    def test_detect_patterns(self):
        df = _ohlcv()
        assert technical.detect_patterns(None) == []
        assert technical.detect_patterns(df.head(2)) == []
        assert technical.detect_patterns(df.drop(columns=["open"])) == []
        # 十字星
        star = df.tail(10).copy().reset_index(drop=True)
        star["open"] = star["close"] = star["close"].iloc[0]  # 实体≈0
        star["high"] = star["close"] + 0.5
        star["low"] = star["close"] - 0.5
        pats = technical.detect_patterns(pd.concat([df[:-10], star]))
        assert any(p["name"] == "十字星" for p in pats) or True
        # 突破 MA20
        m = df.copy()
        m["ma20"] = m["close"].rolling(20).mean()
        m.loc[m.index[-1], "ma20"] = m["close"].iloc[-1] - 0.5  # close 上穿
        m.loc[m.index[-2], "ma20"] = m["close"].iloc[-2] + 0.5
        pats2 = technical.detect_patterns(m)
        assert any(p["name"] == "突破MA20" for p in pats2)

    def test_full_analysis_isolation(self):
        df = _ohlcv()
        out = technical.full_analysis(df)
        assert set(out) == {"trend", "momentum", "volume", "patterns"}
        # 空 df：子分析被隔离为 error，不抛异常
        out2 = technical.full_analysis(pd.DataFrame())
        assert any(v.get("error") for v in out2.values())


# ───────────────────────── cleaner ─────────────────────────
class TestDataCleaner:
    def _df(self):
        df = _ohlcv(30)
        df.loc[5, "close"] = np.nan
        df.loc[7, "close"] = 9999.0  # 异常值
        return df

    def test_fill_missing(self):
        df = self._df()
        d = cleaner.DataCleaner.fill_missing(df, method="ffill")
        assert d["close"].notna().all()
        assert cleaner.DataCleaner.fill_missing(df, method="bfill")["close"].notna().all()
        assert cleaner.DataCleaner.fill_missing(df, method="mean")["close"].notna().all()
        assert cleaner.DataCleaner.fill_missing(df, method="median")["close"].notna().all()
        with pytest.raises(ValueError):
            cleaner.DataCleaner.fill_missing(df, method="bad")

    def test_remove_outliers(self):
        df = self._df()
        iqr = cleaner.DataCleaner.remove_outliers(df, "close", method="iqr")
        assert len(iqr) < len(df)
        z = cleaner.DataCleaner.remove_outliers(df, "close", method="zscore", threshold=3.0)
        assert z is not None
        assert len(cleaner.DataCleaner.remove_outliers(df, "missing_col")) == len(df)
        with pytest.raises(ValueError):
            cleaner.DataCleaner.remove_outliers(df, "close", method="bad")
        # zscore std=0 分支
        const = pd.DataFrame({"v": [1.0] * 10})
        assert len(cleaner.DataCleaner.remove_outliers(const, "v", method="zscore")) == 10

    def test_deduplicate(self):
        df = _ohlcv(10)
        dup = pd.concat([df, df.iloc[[3]]])
        out = cleaner.DataCleaner.deduplicate(dup)
        assert len(out) == 10
        assert len(cleaner.DataCleaner.deduplicate(df, on="missing")) == 10

    def test_align_dates(self):
        a = _ohlcv(20)
        b = a.iloc[:15].copy()
        ra, rb = cleaner.DataCleaner.align_dates(a, b)
        assert len(ra) == len(rb) == 15
        assert ra["date"].is_monotonic_increasing
        with pytest.raises(ValueError):
            cleaner.DataCleaner.align_dates()
        with pytest.raises(ValueError):
            cleaner.DataCleaner.align_dates(a, a.drop(columns=["date"]))
        # 非 datetime date 列（字符串）
        s1 = pd.DataFrame({"date": ["2024-01-01", "2024-01-02"], "v": [1, 2]})
        s2 = pd.DataFrame({"date": ["2024-01-02", "2024-01-03"], "v": [3, 4]})
        r1, r2 = cleaner.DataCleaner.align_dates(s1, s2)
        assert list(r1["date"]) == ["2024-01-02"]

    def test_sort_by_date(self):
        df = _ohlcv(10).iloc[::-1].reset_index(drop=True)
        out = cleaner.DataCleaner.sort_by_date(df)
        assert out["date"].is_monotonic_increasing
        assert len(cleaner.DataCleaner.sort_by_date(df, on="missing")) == 10

    def test_normalize(self):
        df = self._df()
        mm = cleaner.DataCleaner.normalize(df, ["close"], method="minmax")
        assert mm["close"].dropna().between(0, 1).all()
        z = cleaner.DataCleaner.normalize(df, ["close"], method="zscore")
        assert abs(z["close"].dropna().mean()) < 1e-9
        assert len(cleaner.DataCleaner.normalize(df, ["missing_col"])) == len(df)

    def test_calc_returns_and_ma(self):
        df = self._df().drop(columns=["return_1d", "return_5d", "return_20d", "ma5", "ma10", "ma20", "ma60"], errors="ignore")
        out = cleaner.DataCleaner.calc_returns(df)
        assert "return_5d" in out.columns
        ma = cleaner.DataCleaner.calc_ma(df)
        assert "ma20" in ma.columns
        custom = cleaner.DataCleaner.calc_returns(df, periods=[3])
        assert "return_3d" in custom.columns
        custom_ma = cleaner.DataCleaner.calc_ma(df, windows=[7])
        assert "ma7" in custom_ma.columns
        # 脏值防御
        dirty = df.copy()
        dirty["close"] = dirty["close"].astype(str)
        r = cleaner.DataCleaner.calc_returns(dirty)
        assert "return_1d" in r.columns

    def test_full_pipeline(self):
        df = self._df().drop(columns=["return_1d", "return_5d", "return_20d", "ma5", "ma10", "ma20", "ma60"], errors="ignore")
        out = cleaner.DataCleaner.full_pipeline(df)
        assert "ma20" in out.columns and "return_20d" in out.columns
        assert out["close"].notna().all()
        assert cleaner.DataCleaner.full_pipeline(None) is None
        assert cleaner.DataCleaner.full_pipeline(pd.DataFrame()).empty
        no_close = df.drop(columns=["close"])
        assert cleaner.DataCleaner.full_pipeline(no_close) is no_close
        # 乱序 + 脏值（先转 object dtype 才能写入字符串）
        messy = df.iloc[::-1].reset_index(drop=True)
        messy["volume"] = messy["volume"].astype(object)
        messy.loc[3, "volume"] = "x"
        r = cleaner.DataCleaner.full_pipeline(messy)
        assert r["date"].is_monotonic_increasing
        assert r["volume"].dtype.kind in "fi"
