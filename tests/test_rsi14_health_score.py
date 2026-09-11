import sys
import pathlib
import pandas as pd

ROOT = pathlib.Path(r"E:/project/ks/StockSignal")
sys.path.insert(0, str(ROOT))

from modules.backtest import _rsi14_health_score, _rsi14_overbought


def test_rsi14_health_matches_main_reference_path():
    # _score_for_picker 是既定参考分段；批量路径必须与之完全一致（锐评 R6 修复前会分歧）
    assert _rsi14_health_score(55) == 20
    assert _rsi14_health_score(70) == 12   # 主路径 60<70<=70 -> 12
    assert _rsi14_health_score(75) == 10
    assert _rsi14_health_score(85) == 10   # 修复前批量路径落入 else -> 0
    assert _rsi14_health_score(90) == 10   # 修复前批量路径 -> 0
    assert _rsi14_health_score(35) == 15
    assert _rsi14_health_score(27) == 8
    assert _rsi14_health_score(95) == 0


def test_rsi14_health_invalid_safe():
    assert _rsi14_health_score(None) == 0
    assert _rsi14_health_score("x") == 0


def test_rsi14_overbought_counts_threshold_75():
    df = pd.DataFrame({"rsi14": [80, 80, 30, 30, 30, 30, 30, 30, 30, 30]})  # 2 天 >75
    assert _rsi14_overbought(df) == 2
    df2 = pd.DataFrame({"rsi14": [70, 70, 70, 70, 70, 70, 70, 70, 70, 70]})  # 0 天 >75
    assert _rsi14_overbought(df2) == 0
    assert _rsi14_overbought(None) == 0


def test_old_batch_divergence_rejected():
    # 旧批量路径对 85 落入 else 给 0；修复后统一为 10
    assert _rsi14_health_score(85) == 10
