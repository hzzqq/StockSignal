"""R18：technical.analyze_volume + detect_patterns 单测（无网依赖）。

补 whitebox 未覆盖的两块纯逻辑：
1. analyze_volume —— 量比 / 量能变化 / 连续放量天数 / 量价配合标签；
2. detect_patterns —— 单根(锤子线/十字星) / 双根(看涨吞没) / 突破 MA20。

全部用合成 K 线 DataFrame 触发具体分支，不依赖网络与 streamlit。
"""

import pandas as pd

from modules.technical import analyze_volume, detect_patterns


def _vol_df(volumes, change_pct=None, ma20=None):
    n = len(volumes)
    idx = pd.date_range("2024-01-01", periods=n)
    close = list(range(100, 100 + n))
    df = pd.DataFrame({
        "date": idx,
        "open": close,
        "high": [c + 1 for c in close],
        "low": [c - 1 for c in close],
        "close": close,
        "volume": volumes,
    })
    if change_pct is not None:
        df["change_pct"] = [change_pct] * n
    if ma20 is not None:
        df["ma20"] = ma20
    return df


# ----------------------------------------------------------------------
# analyze_volume
# ----------------------------------------------------------------------
def test_analyze_volume_error_branches():
    assert "error" in analyze_volume(None)
    assert "error" in analyze_volume(pd.DataFrame())
    # 不足 6 日
    assert "error" in analyze_volume(_vol_df([1, 2, 3, 4, 5]))
    # 缺 volume 列
    df = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=6)})
    assert "error" in analyze_volume(df)


def test_analyze_volume_ratio_and_label():
    # 前 5 日均量 100，今日 300 → vol_ratio=3.0；放量上涨
    vols = [100, 100, 100, 100, 100, 300]
    df = _vol_df(vols, change_pct=3.0)
    r = analyze_volume(df)
    assert r["vol_ratio"] == 3.0
    assert r["volume_price_label"] == "量价齐升"
    assert r["volume_price_score"] == 85


def test_analyze_volume_shrink_healthy():
    # 前 5 日均量 1000，今日 100 → vol_ratio=0.1；缩量回调(健康)
    vols = [1000, 1000, 1000, 1000, 1000, 100]
    df = _vol_df(vols, change_pct=-2.0)
    r = analyze_volume(df)
    assert r["vol_ratio"] == 0.1
    assert r["volume_price_label"] == "缩量回调(健康)"
    assert r["volume_price_score"] == 55


def test_analyze_volume_consecutive_up():
    # 连续 6 日递增量 → direction up，consecutive >= 5
    vols = [10, 20, 30, 40, 50, 60]
    df = _vol_df(vols)
    r = analyze_volume(df)
    assert r["consecutive_direction"] == "up"
    assert r["consecutive_days"] >= 5


def test_analyze_volume_change_pct():
    # 今日 200，昨日 100 → vol_change_pct = +100%
    vols = [100, 100, 100, 100, 100, 200]
    df = _vol_df(vols)
    r = analyze_volume(df)
    assert abs(r["vol_change_pct"] - 100.0) < 1e-9


# ----------------------------------------------------------------------
# detect_patterns
# ----------------------------------------------------------------------
def _candle_df(rows):
    """rows: list of (open, high, low, close)；date 自动生成。强制浮点列。"""
    idx = pd.date_range("2024-01-01", periods=len(rows))
    o, h, l, c = zip(*rows)
    return pd.DataFrame({
        "date": idx,
        "open": [float(x) for x in o],
        "high": [float(x) for x in h],
        "low": [float(x) for x in l],
        "close": [float(x) for x in c],
    })


def test_detect_patterns_empty():
    assert detect_patterns(None) == []
    assert detect_patterns(pd.DataFrame()) == []
    # 不足 3 根
    assert detect_patterns(_candle_df([(10, 10, 10, 10)] * 2)) == []


def test_detect_patterns_hammer():
    # 最后一根本质小实体、长下影、极短上影 → 锤子线
    rows = [(10, 10.5, 10.0, 9.8)] * 11  # 普通阳线，非形态
    rows[-1] = (10.0, 10.3, 8.0, 10.2)   # 锤子线：实体0.2, 下影2.0, 上影0.1
    df = _candle_df(rows)
    pats = detect_patterns(df)
    names = [p["name"] for p in pats]
    assert "锤子线" in names
    assert any(p["bias"] == "看涨" for p in pats if p["name"] == "锤子线")


def test_detect_patterns_doji():
    # 十字星：实体极小、上下影线均非零
    rows = [(10, 10.5, 10.0, 9.8)] * 11
    rows[-1] = (10.0, 11.0, 9.0, 10.05)  # 实体0.05, 上影0.95, 下影0.95
    df = _candle_df(rows)
    pats = detect_patterns(df)
    assert "十字星" in [p["name"] for p in pats]


def test_detect_patterns_bullish_engulfing():
    # 前一根阴线、后一根阳线且完全覆盖 → 看涨吞没
    rows = [(10, 10.5, 10.0, 9.8)] * 10
    rows[-2] = (10.0, 10.2, 9.0, 9.2)   # 阴线 open10 close9.2
    rows[-1] = (9.0, 10.5, 8.8, 10.3)   # 阳线 open9(<9.2) close10.3(>10)
    df = _candle_df(rows)
    pats = detect_patterns(df)
    assert "看涨吞没" in [p["name"] for p in pats]


def test_detect_patterns_breakout_ma20():
    # 倒数第二 close<=ma20，最后 close>ma20 → 突破MA20
    rows = [(10, 10.5, 9.5, 10.0)] * 10
    ma20 = [10.0] * 10
    df = _candle_df(rows)
    df["ma20"] = ma20
    # 让最后两根发生穿越
    df.loc[df.index[-2], "close"] = 9.5   # <= ma20
    df.loc[df.index[-2], "open"] = 9.6
    df.loc[df.index[-1], "close"] = 10.5  # > ma20
    df.loc[df.index[-1], "open"] = 10.2
    pats = detect_patterns(df)
    assert "突破MA20" in [p["name"] for p in pats]


def test_detect_patterns_dedup_limit():
    # 构造 6 根连续锤子线，断言返回不超过 5 个
    rows = []
    for i in range(6):
        rows.append((10.0, 10.3, 8.0, 10.2))  # 锤子线
    df = _candle_df(rows)
    pats = detect_patterns(df)
    assert len(pats) <= 5
    assert all(p["name"] == "锤子线" for p in pats)
