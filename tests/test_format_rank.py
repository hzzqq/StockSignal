import sys
import pathlib

ROOT = pathlib.Path(r"E:/project/ks/StockSignal")
sys.path.insert(0, str(ROOT))

from modules.p1_signal import format_rank


def test_ordinal_rank_not_multiplied():
    # 看多榜 rank 是序数（1,2,3），不应乘 100 → 否则出现 100%/200%/300% 荒谬值
    assert format_rank(1.0, as_percent=False) == "1"
    assert format_rank(3.0, as_percent=False) == "3"


def test_percentile_rank_shows_pct():
    # 看空榜 rank 是百分位，才显示为百分比
    assert format_rank(0.0007, as_percent=True) == "0.07%"


def test_invalid_safe():
    assert format_rank(None, as_percent=False) == "—"
    assert format_rank("x", as_percent=False) == "—"


def test_old_bug_rejected():
    # 旧实现 rank*100 对序数 3 会得到 "300%"，修复后 ordinal 应显示 "3"
    assert format_rank(3.0, as_percent=False) != "300%"
