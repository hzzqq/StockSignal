"""R11：modules/stock_analysis_helpers 纯函数单测。

#408 从 pages/2_个股分析.py 抽出纯函数簇到本模块；本测试锁定其纯函数行为，
防止后续配色/逻辑重构（如 R8 配色单一来源）引入回归。
所有函数均不依赖 streamlit / fetcher / session_state，可独立调用。
"""

from modules.colors import RED, GREEN, AMBER
from modules.stock_analysis_helpers import (
    _sentiment_tag,
    _tp_cls,
    _score_ring_html,
    _verdict_color,
    _price_color,
    _support_resistance_bar,
    _calc_trade_levels,
)


def test_sentiment_tag_mapping():
    assert _sentiment_tag("正面") == "up"
    assert _sentiment_tag("负面") == "down"
    assert _sentiment_tag("中性") == "mid"
    assert _sentiment_tag("未知") == "neu"   # 默认分支
    assert _sentiment_tag("") == "neu"


def test_tp_cls_boundaries():
    assert _tp_cls(60) == "up"
    assert _tp_cls(100) == "up"
    assert _tp_cls(40) == "down"
    assert _tp_cls(0) == "down"
    assert _tp_cls(41) == "mid"
    assert _tp_cls(59) == "mid"
    assert _tp_cls(50) == "mid"


def test_score_ring_html_clamps_and_embeds():
    # 上限夹紧
    big = _score_ring_html(150, RED)
    assert "100" in big and "150" not in big
    # 下限夹紧
    small = _score_ring_html(-20, GREEN)
    assert "0" in small
    # 颜色透传 + dasharray 比例
    mid = _score_ring_html(50, AMBER)
    assert AMBER in mid
    assert "dasharray" in mid


def test_verdict_color_thresholds():
    txt, col, cls = _verdict_color(80)
    assert txt == "看多" and col is RED and cls == "win"
    txt, col, cls = _verdict_color(70)        # 边界含等
    assert txt == "看多" and col is RED
    txt, col, cls = _verdict_color(40)
    assert txt == "看空" and col is GREEN and cls == "weak"
    txt, col, cls = _verdict_color(55)
    assert txt == "持有" and col is AMBER and cls == "mid"
    txt, col, cls = _verdict_color(41)
    assert txt == "持有"


def test_price_color_sign():
    assert _price_color(3.2) is RED       # 涨 → 文档绿
    assert _price_color(-1.5) is GREEN    # 跌 → 文档红
    assert _price_color(0.0) is AMBER     # 平 → 中性


def test_support_resistance_bar_invalid_range():
    # 压力 <= 支撑 → 返回空串（防御）
    assert _support_resistance_bar(10.0, 10.0, 10.0) == ""
    assert _support_resistance_bar(12.0, 10.0, 11.0) == ""


def test_support_resistance_bar_valid():
    html = _support_resistance_bar(8.0, 12.0, 10.0)
    assert "支撑" in html and "压力" in html
    assert "¥8.00" in html and "¥12.00" in html
    # 当前价 10 在 8~12 中点 → 约 50%
    assert "left:50.0%" in html


def test_support_resistance_bar_markers_clamp():
    # marker 超出区间应扩展 lo/hi 而不报错
    html = _support_resistance_bar(8.0, 12.0, 10.0, markers=[("MA5", 100.0, RED)])
    assert "MA5" in html


def test_calc_trade_levels_returns_tuple():
    # 构造最小 OHLC DataFrame（high=low=close=100 → ATR 退化为 current*0.025=2.5）
    import pandas as pd
    df = pd.DataFrame({"high": [100.0] * 20, "low": [100.0] * 20, "close": [100.0] * 20})
    entry, target, stop, atr = _calc_trade_levels(100.0, df, support=95.0, resistance=110.0)
    assert isinstance(entry, float) and isinstance(target, float)
    assert isinstance(stop, float) and isinstance(atr, float)
    # 目标价 > 入场价 > 0；止损 < 入场价
    assert target > entry > 0
    assert stop < entry
    # 给定固定输入，数值可复现
    assert atr == 2.5
    assert stop == 95.0
    assert entry == 98.75
    assert target == 107.5
