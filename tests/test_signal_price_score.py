"""R16：SignalEngine 价格信号单测（无网依赖）。

只测可在离线环境稳定复现的纯逻辑：
1. price_score / technical_profile —— 上涨/下跌/震荡/数据不足 四种走势；
2. _clamp —— 夹紧到 [0,100] 且异常安全；
3. _score_by_return —— 分段线性映射。

SignalEngine.__init__ 会预热股票库（可能触发网络 / 较慢），但
price_score → technical_profile 仅依赖静态工具方法 (_clamp / _score_by_return)
与传入的 df，不读取任何实例属性。故用 object.__new__ 构造空实例，
规避 __init__ 副作用，专测纯算法。
"""

import numpy as np
import pandas as pd

from modules.signal import SignalEngine


def _make_engine():
    """绕过 __init__ 构造「裸」引擎，仅用于调用纯逻辑方法。"""
    return object.__new__(SignalEngine)


def _trend_df(n=65, mode="up", ticker="600519"):
    """构造带完整技术列的走势 df。
    mode: up（强上涨）/ down（强下跌）/ flat（横盘）。
    """
    idx = pd.date_range("2024-01-01", periods=n)
    if mode == "up":
        close = [100.0 + i for i in range(n)]
        r5, r20, r1 = 5.0, 15.0, 1.0
    elif mode == "down":
        close = [200.0 - i for i in range(n)]
        r5, r20, r1 = -5.0, -15.0, -1.0
    else:  # flat
        close = [100.0] * n
        r5, r20, r1 = 0.0, 0.0, 0.0
    close = np.array(close, dtype=float)
    df = pd.DataFrame({
        "date": idx,
        "ticker": [ticker] * n,
        "open": close,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "volume": [1000 + i for i in range(n)],
        "ma5": close,
        "ma20": close,
        "return_1d": [r1] * n,
        "return_5d": [r5] * n,
        "return_20d": [r20] * n,
    })
    return df


# ----------------------------------------------------------------------
# price_score 走势分档
# ----------------------------------------------------------------------
def test_price_score_uptrend_high():
    eng = _make_engine()
    df = _trend_df(n=65, mode="up")
    score = eng.price_score(df)
    assert isinstance(score, int)
    assert 0 <= score <= 100
    assert score > 65, f"强上涨应得高分，实际 {score}"


def test_price_score_downtrend_low():
    eng = _make_engine()
    df = _trend_df(n=65, mode="down")
    score = eng.price_score(df)
    assert isinstance(score, int)
    assert 0 <= score <= 100
    # 强下跌应明显低于中性 50（与上涨分形成清晰分档，留足 hash 噪声余量）
    assert score < 45, f"强下跌应得低分，实际 {score}"


def test_price_score_flat_mid():
    eng = _make_engine()
    df = _trend_df(n=65, mode="flat")
    score = eng.price_score(df)
    assert isinstance(score, int)
    assert 0 <= score <= 100
    # 横盘：趋势中性，位于中段区间
    assert 30 <= score <= 70, f"横盘应在中段，实际 {score}"


def test_price_score_insufficient_rows():
    eng = _make_engine()
    df = _trend_df(n=10, mode="up")  # 不足 20 行
    score = eng.price_score(df)
    assert score == 50, f"数据不足应返回中性 50，实际 {score}"


def test_price_score_empty_df():
    eng = _make_engine()
    df = pd.DataFrame(columns=["date", "close"])
    score = eng.price_score(df)
    assert score == 50, f"空 df 应返回中性 50，实际 {score}"


def test_price_score_none_df():
    eng = _make_engine()
    score = eng.price_score(None)
    assert score == 50, f"None 应返回中性 50，实际 {score}"


# ----------------------------------------------------------------------
# _clamp
# ----------------------------------------------------------------------
def test_clamp_bounds():
    assert SignalEngine._clamp(150) == 100
    assert SignalEngine._clamp(-20) == 0
    assert SignalEngine._clamp(73.6) == 74
    assert SignalEngine._clamp(73.4) == 73


def test_clamp_nan_safe():
    """非法输入（字符串/None）应安全回退到 50。"""
    assert SignalEngine._clamp("abc") == 50
    assert SignalEngine._clamp(None) == 50
    assert SignalEngine._clamp(float("nan")) == 50


# ----------------------------------------------------------------------
# _score_by_return
# ----------------------------------------------------------------------
def test_score_by_return_exact_breaks():
    breaks = [10, 5, 2, 0, -2, -5]
    scores = [95, 80, 68, 58, 45, 30, 15]
    assert SignalEngine._score_by_return(10, breaks, scores) == 95
    assert SignalEngine._score_by_return(0, breaks, scores) == 58
    assert SignalEngine._score_by_return(-5, breaks, scores) == 30
    # 低于最小阈值取末档
    assert SignalEngine._score_by_return(-99, breaks, scores) == 15
    # 高于最大阈值取首档
    assert SignalEngine._score_by_return(999, breaks, scores) == 95


def test_score_by_return_interpolation():
    breaks = [10, 5, 2, 0, -2, -5]
    scores = [95, 80, 68, 58, 45, 30, 15]
    # r=7.5 落在 [5,10] 之间，线性插值 = 80 + (95-80)*(7.5-5)/(10-5) = 87.5 → 88
    assert SignalEngine._score_by_return(7.5, breaks, scores) == 88
