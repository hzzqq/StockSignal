import sys
import pathlib
import pandas as pd

ROOT = pathlib.Path(r"E:/project/ks/StockSignal")
sys.path.insert(0, str(ROOT))

from modules.backtest import _trend_persistence_ratio


def _mk(n_above, total=10):
    """构造 total 行窗口：前 n_above 行 close>ma20，其余 close<ma20。"""
    above_close = [10.0] * n_above + [5.0] * (total - n_above)
    ma20 = [9.0] * total
    return pd.DataFrame({"close": above_close, "ma20": ma20})


def test_ratio_is_true_proportion_of_window():
    # 6/10 站上 MA20 → 正确占比 0.6；旧的 min(len,5) 分母会算成 6/5=1.2（误标"持续"）
    assert _trend_persistence_ratio(_mk(6)) == 0.6


def test_ratio_bounds():
    assert _trend_persistence_ratio(_mk(0)) == 0.0
    assert _trend_persistence_ratio(_mk(10)) == 1.0
    # 7/10 → 0.7，恰好落在"强趋势"而非"持续"的边界，证明不再是 2 倍放大
    assert _trend_persistence_ratio(_mk(7)) == 0.7


def test_ratio_empty_window_safe():
    assert _trend_persistence_ratio(pd.DataFrame({"close": [], "ma20": []})) == 0.0
    assert _trend_persistence_ratio(None) == 0.0


def test_old_bug_rejected():
    # 记录旧 bug 的数值，证明修复后不再产生
    old = 6 / min(10, 5)  # = 1.2
    assert old == 1.2
    assert _trend_persistence_ratio(_mk(6)) != old
