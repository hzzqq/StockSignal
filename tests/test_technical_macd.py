"""technical 新增 MACD / EMA 原语 + NaN 守卫回归（无网依赖）。

覆盖：
- compute_ema：普通序列 / 含 NaN 点不向后污染 / 非法输入→None
- compute_macd：
  - 单调上涨 → dif>0, dea>0, macd>0
  - 数据不足（< slow）→ None
  - 缺 close 列 → None
  - 含 NaN 收盘价 → 先 dropna 仍能给出有效值（隐性健壮化，不污染整条）
"""
import math

import pandas as pd

import modules.technical as T


def _df(closes):
    n = len(closes)
    return pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=n, freq="D"),
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": [1000] * n,
    })


def test_compute_ema_basic():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    e = T.compute_ema(s, span=3)
    assert e is not None
    assert len(e) == 5
    # 最后值应接近末项
    assert e.iloc[-1] > 4.0


def test_compute_ema_nan_no_poison():
    s = pd.Series([1.0, 2.0, float("nan"), 4.0, 5.0])
    e = T.compute_ema(s, span=2)
    # NaN 行被剔除，其余点得到有限值
    assert e is not None
    assert math.isfinite(float(e.iloc[-1]))


def test_compute_ema_invalid():
    assert T.compute_ema(None, 3) is None
    assert T.compute_ema(pd.Series([float("nan")] * 3), 3) is None


def test_compute_macd_uptrend_positive():
    closes = [10 + i for i in range(40)]
    out = T.compute_macd(_df(closes))
    assert out is not None
    assert out["dif"] > 0 and out["dea"] > 0 and out["macd"] > 0


def test_compute_macd_insufficient_data():
    closes = [10, 11, 12]
    assert T.compute_macd(_df(closes)) is None


def test_compute_macd_missing_close():
    df = pd.DataFrame({"open": [1, 2], "high": [1, 2]})
    assert T.compute_macd(df) is None


def test_compute_macd_with_nan_close():
    closes = [10 + i for i in range(40)]
    closes[20] = float("nan")  # 单点 NaN
    out = T.compute_macd(_df(closes))
    # 隐性健壮化：dropna 后仍能给出有限 MACD，而非整条 NaN
    assert out is not None
    assert all(math.isfinite(v) for v in out.values())
