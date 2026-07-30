"""screener_indicators 边界健壮性回归测试。

修复前：calculate_macd / analyze_trend / calculate_rsi 等函数仅检查 len(series) < X，
未守卫 None 输入；上游取数失败返回 None 时调用会抛 TypeError: object of type
'NoneType' has no len()，拖垮选股/分析链路。
"""
import pandas as pd

import modules.screener_indicators as SI


def test_none_input_no_crash():
    # 全部指标函数传入 None 必须优雅返回默认值，不得抛 TypeError
    assert SI.calculate_macd(None) == (None, None, None)
    assert SI.calculate_sma(None, 5) is None
    assert SI.calculate_ema(None, 5) is None
    assert SI.analyze_trend(None) == (None, None)
    assert SI.detect_bottom_divergence(None, None) is False
    assert SI.detect_top_divergence(None, None) is False
    assert SI.check_volume_surge(None) == (False, None)
    assert SI.calculate_rsi(None) is None
    assert SI.calculate_bollinger_bands(None) == (None, None, None)


def test_empty_series_returns_graceful():
    empty = pd.Series(dtype=float)
    assert SI.calculate_macd(empty) == (None, None, None)
    assert SI.calculate_sma(empty, 5) is None
    assert SI.calculate_rsi(empty) is None
    assert SI.calculate_bollinger_bands(empty) == (None, None, None)


def test_normal_series_still_works():
    s = pd.Series([float(i) for i in range(1, 31)])  # 30 点：RSI(>=15) 与 MACD(slow=26) 均满足
    rsi = SI.calculate_rsi(s)
    assert rsi is not None and len(rsi) == len(s)
    macd = SI.calculate_macd(s)
    assert macd[0] is not None
