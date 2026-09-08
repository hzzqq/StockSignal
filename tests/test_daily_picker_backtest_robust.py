"""回归测试：daily_picker_backtest 不应因 reasons[-1] 越界而崩溃。

复现 StockSignal 选股回测「list index out of range」：
原 daily_picker_backtest 的 multi_factor 内联评分分支在 trend_persist>=0.9
但 trend_score<20 时，reasons 仍为空，却执行 reasons[-1] += "(持续)" 触发
IndexError。修复后改为在 reason 创建时按 _score_for_picker 的口径写入。
"""

import numpy as np
import pandas as pd
import modules.backtest as bt_mod
import modules.fetch_parallel as fetch_parallel


def _sync_fetch_many(tasks, max_workers=8, timeout=12):
    """把并行取数降级为同步，避免线程/网络依赖。"""
    out = {}
    for code, fn in tasks:
        try:
            out[code] = fn()
        except Exception:
            out[code] = None
    return out


class _FakeFetcher:
    def get_all_codes(self, limit=None, random_seed=None):
        codes = [f"60000{i}" for i in range(8)]
        if random_seed is not None:
            import random
            rng = random.Random(random_seed)
            rng.shuffle(codes)
        return codes[:limit] if limit else codes

    def get_name_only(self, code):
        return f"NAME{code}"

    def get_daily(self, symbol, start, end, adjust="qfq"):
        n = 130
        idx = pd.date_range(end="2024-06-30", periods=n, freq="B")
        np.random.seed(abs(hash(symbol)) % 1000)
        price = np.maximum(100 + np.cumsum(np.random.randn(n) * 1.5), 5)
        return pd.DataFrame({
            "date": idx,
            "open": price + np.random.randn(n) * 0.5,
            "high": price + np.abs(np.random.randn(n)) * 1,
            "low": price - np.abs(np.random.randn(n)) * 1,
            "close": price,
            "volume": 1000 + np.random.rand(n) * 500,
        })


def _make_bt():
    bt = bt_mod.Backtester.__new__(bt_mod.Backtester)
    bt.fetcher = _FakeFetcher()
    bt.config = {}
    return bt


def test_daily_picker_multi_factor_no_indexerror(monkeypatch):
    monkeypatch.setattr(fetch_parallel, "fetch_many", _sync_fetch_many)
    bt = _make_bt()
    res = bt.daily_picker_backtest(
        start="2024-05-01", end="2024-06-30",
        stock_pool_size=8, top_k=3, hold_days=1, max_workers=2,
        strategy="multi_factor",
    )
    assert isinstance(res, bt_mod.DailyPickerResult)
    s = res.summary()
    assert "total_return_pct" in s and "win_pick_pct" in s


def test_daily_picker_dual_trend_no_indexerror(monkeypatch):
    monkeypatch.setattr(fetch_parallel, "fetch_many", _sync_fetch_many)
    bt = _make_bt()
    res = bt.daily_picker_backtest(
        start="2024-05-01", end="2024-06-30",
        stock_pool_size=8, top_k=3, hold_days=1, max_workers=2,
        strategy="dual_trend",
    )
    assert isinstance(res, bt_mod.DailyPickerResult)
    s = res.summary()
    assert "total_return_pct" in s and "win_pick_pct" in s
