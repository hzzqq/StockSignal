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

from modules.backtest import Backtester, _clamp100, _final_picker_score


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


# ───────────────────────── 评分收束纯函数（R8） ─────────────────────────
def test_clamp100_bounds():
    """任意评分收束到 [0,100]，多因子分段上限合计 125 的历史债不再泄漏。"""
    assert _clamp100(125) == 100.0
    assert _clamp100(200) == 100.0
    assert _clamp100(-5) == 0.0
    assert _clamp100(62.5) == 62.5
    assert _clamp100(0) == 0.0
    assert _clamp100(100) == 100.0


def test_clamp100_non_numeric_safe():
    """非数值兜底中性分，不抛。"""
    assert _clamp100("坏") == 50.0


def test_final_picker_score_clamp_overflow():
    """分段上限合计 125，曾可溢出到 ~125，违反 0-100 契约。"""
    # 多日平滑分支：score/smoothed 都满格 → 仍须封顶 100
    assert _final_picker_score(125, 125, True) == 100.0
    assert _final_picker_score(200, 0, True) == 100.0
    # 单日分支（日评分不足 3 天）：直接用 score，仍须封顶
    assert _final_picker_score(-10, -10, False) == 0.0
    # 正常值不受影响
    assert _final_picker_score(80, 80, True) == 80.0
    assert _final_picker_score(40, 40, False) == 40.0


def test_daily_picker_candidate_score_clamped():
    """R9：daily_picker_backtest 的候选 score 分段上限合计 125，
    落盘为 candidate['score'] 并参与排序/展示，曾可出现「评分 125/100」。
    修复后所有候选评分必须落在 [0,100]。"""
    import pandas as pd

    bt = Backtester()
    n = 60
    dates = pd.date_range("2023-01-02", periods=n, freq="B")
    # 全行恒定工程化：趋势满(50)+超跌满(40)+健康满(20)+量能满(15)=125 → 触发溢出
    df = pd.DataFrame({
        "date": dates, "code": "600000",
        "open": 100.0, "high": 105.0, "low": 95.0, "close": 100.0,
        "volume": 150.0,
        "ma20": 90.0, "ma60": 80.0,
        "ma20_rising": True, "ma60_rising": True,
        "rsi2": 3.0, "rsi14": 50.0, "vol_ma20": 100.0,
    })

    def fake_fetch(code, start, end):
        return {"df": df, "code": code, "name": "测试", "score": 100.0}

    class FakeFetcher:
        def get_all_codes(self, limit=200, random_seed=None):
            return ["600000"]

    bt._fetch_single_for_picker = fake_fetch
    bt.fetcher = FakeFetcher()

    res = bt.daily_picker_backtest(
        "2023-01-02", "2023-04-01", stock_pool_size=1, top_k=1,
        hold_days=1, min_score=0, max_workers=1,
        use_smart_exit=False, strategy="multi_factor",
    )
    picks = res.picks_df
    assert not picks.empty, "应至少产出一条候选"
    # 修复前 raw 达 125，修复后必须 [0,100]
    assert (picks["score"] <= 100).all(), f"候选评分越界: {picks['score'].tolist()}"
    assert (picks["score"] >= 0).all()
