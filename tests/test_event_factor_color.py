import sys
import pathlib

ROOT = pathlib.Path(r"E:/project/ks/StockSignal")
sys.path.insert(0, str(ROOT))

from modules.colors import RED, GREEN, AMBER
from modules.stock_analysis_helpers import event_factor_color


def test_positive_score_is_green_render():
    # 正分=利好，绿涨红跌约定下应渲染绿=RED 常量（与价格行 426 一致）
    assert event_factor_color(0.05) == RED
    assert event_factor_color(0.0) == RED


def test_negative_score_is_red_render():
    # 负分=利空，应渲染红=GREEN 常量
    assert event_factor_color(-0.05) == GREEN


def test_none_is_amber():
    assert event_factor_color(None) == AMBER


def test_old_inversion_rejected():
    # 旧实现 `GREEN if _sc>=0 else RED` 会让正分落到 GREEN(红)，与价格行 426 矛盾
    assert event_factor_color(0.05) != GREEN
