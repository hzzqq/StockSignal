"""R4 回归保护：_score_for_picker 评分逻辑。

`_score_for_picker`（backtest.py ~L433）与 `daily_picker_backtest` 内联的评分块
（backtest.py ~L824）并非真正重复：二者健康分阈值（40<=rsi14<=60 vs <=70）、
超买阈值（>75 vs >80）均不同，强行抽取共享函数会改变行为。因此按任务指引
“adapt”：对更脆弱的 `_score_for_picker` 增加输入校验 + 回归断言，锁定其输出
结构与数值有限性。

无网依赖：Backtester() 与 _score_for_picker 均为纯逻辑（不触发数据源）。
"""

import math

import numpy as np
import pandas as pd

from modules.backtest import Backtester


def _make_ohlcv(n=120, seed=42):
    """构造带 OHLCV 列的上行样本，确保评分能通过过滤、产出有限数值。"""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2023-01-02", periods=n, freq="B")
    # 温和上行 + 噪声：close 持续高于 MA20、rsi14 落在健康区间
    close = np.linspace(10.0, 25.0, n) + rng.normal(0, 0.3, n)
    close = np.maximum(close, 1.0)
    op = close + rng.normal(0, 0.1, n)
    hi = np.maximum(op, close) + np.abs(rng.normal(0.05, 0.1, n))
    lo = np.minimum(op, close) - np.abs(rng.normal(0.05, 0.1, n))
    vol = rng.integers(1_000_000, 5_000_000, n).astype(float)
    return pd.DataFrame({
        "date": dates,
        "code": "600000",
        "open": op,
        "high": hi,
        "low": lo,
        "close": close,
        "volume": vol,
    })


class TestScoreForPickerRegression:
    def setup_method(self):
        self.bt = Backtester()

    def test_returns_finite_numeric_structure(self):
        """上行样本应返回含有限数值的评分 dict。"""
        res = self.bt._score_for_picker(_make_ohlcv())
        assert res is not None, "上行样本应能通过评分过滤"

        numeric_keys = [
            "score", "raw_score", "smoothed_score",
            "rsi2", "rsi14", "trend_persistence", "vol_ratio",
        ]
        for k in numeric_keys:
            assert k in res, f"缺失数值键 {k}"
            v = res[k]
            assert isinstance(v, (int, float)) and math.isfinite(v), \
                f"键 {k} 非有限数值: {v!r}"

        # 布尔字段仍存在且为 bool
        assert isinstance(res["trend_ok"], bool)
        # 文本/序列类字段不为 None 且形态正常
        assert isinstance(res["reasons"], str)
        assert res["date"] is not None

    def test_short_df_returns_none(self):
        """数据不足 90 行应直接返回 None。"""
        assert self.bt._score_for_picker(_make_ohlcv(n=30)) is None

    def test_missing_columns_returns_none(self):
        """缺少基础列（加固点）应返回 None 而非抛 KeyError。"""
        assert self.bt._score_for_picker(_make_ohlcv().drop(columns=["volume"])) is None

    def test_nan_volume_does_not_produce_nan_vol_ratio(self):
        """末行 volume 为 NaN 时，vol_ratio 应回退为有限值（加固点）。"""
        df = _make_ohlcv()
        df.loc[df.index[-1], "volume"] = np.nan
        res = self.bt._score_for_picker(df)
        # 可能仍通过过滤；无论是否通过，只要返回就必须 vol_ratio 有限
        if res is not None:
            assert math.isfinite(res["vol_ratio"])
