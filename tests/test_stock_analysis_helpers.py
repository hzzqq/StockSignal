"""R11：modules/stock_analysis_helpers 纯函数单测。

#408 从 pages/2_个股分析.py 抽出纯函数簇到本模块；本测试锁定其纯函数行为，
防止后续配色/逻辑重构（如 R8 配色单一来源）引入回归。
所有函数均不依赖 streamlit / fetcher / session_state，可独立调用。
"""

from modules.colors import RED, GREEN, AMBER
from modules.stock_analysis_helpers import (
    _safe_float,
    _sentiment_tag,
    _tp_cls,
    _score_ring_html,
    _verdict_color,
    _price_color,
    _pattern_name,
    _support_resistance_bar,
    _battle_plan_scale,
    _build_risk_iron_rules,
    _build_plan_rows,
    _build_rise_fall_factors,
    _factor_list_html,
    _build_logic_lists,
    _logic_list_html,
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


# ---------------------------------------------------------------------------
# 健壮性测试（R1/R2/R3/R5/R6）：脏输入不崩、缺失键安全、零/None 分母不出 NaN。
# 全部为纯离线构造，无任何网络依赖。
# ---------------------------------------------------------------------------


def test_safe_float_normal_and_degenerate():
    # 正常值不变
    assert _safe_float(3.5) == 3.5
    assert _safe_float("2.25") == 2.25
    assert _safe_float(10, 99) == 10
    # None / 空串 / 非数字 / NaN / inf → 回退 default
    assert _safe_float(None, 7.0) == 7.0
    assert _safe_float("", 7.0) == 7.0
    assert _safe_float("abc", 7.0) == 7.0
    assert _safe_float(float("nan"), 7.0) == 7.0
    assert _safe_float(float("inf"), 7.0) == 7.0
    assert _safe_float(float("-inf"), 7.0) == 7.0


def test_tp_cls_degenerate():
    assert _tp_cls(None) == "mid"
    assert _tp_cls(float("nan")) == "mid"
    assert _tp_cls("") == "mid"
    # 正常值不受影响
    assert _tp_cls(80) == "up"
    assert _tp_cls(20) == "down"


def test_verdict_color_degenerate():
    # None / NaN → 中性默认
    txt, col, cls = _verdict_color(None)
    assert txt == "持有" and col is AMBER and cls == "mid"
    txt, col, cls = _verdict_color(float("nan"))
    assert txt == "持有"
    # 正常值不受影响
    assert _verdict_color(85)[0] == "看多"


def test_price_color_degenerate():
    assert _price_color(None) is AMBER
    assert _price_color(float("nan")) is AMBER
    assert _price_color("") is AMBER
    assert _price_color(1.0) is RED
    assert _price_color(-1.0) is GREEN


def test_score_ring_html_degenerate():
    # None / NaN → 夹紧到 0，不抛异常
    assert "0" in _score_ring_html(None, AMBER)
    assert "0" in _score_ring_html(float("nan"), AMBER)
    # 正常值不受影响
    assert "100" in _score_ring_html(150, RED)


def test_pattern_name_degenerate():
    # dict / str / None / 空 都安全
    assert _pattern_name({"name": "金叉"}) == "金叉"
    assert _pattern_name("底背离") == "底背离"
    assert _pattern_name(None) == ""
    assert _pattern_name("") == ""


def test_support_resistance_bar_none_inputs():
    # None 输入转为 0 → 压力<=支撑 → 返回空串，不崩
    assert _support_resistance_bar(None, None, None) == ""
    # 正常值含合理位置（分母 span 已守卫，无 NaN）
    html = _support_resistance_bar(8.0, 12.0, 10.0)
    assert "left:50.0%" in html
    assert "nan" not in html.lower()


def test_battle_plan_scale_none_inputs():
    # None 当前价 → 转换为 0，函数不崩且返回字符串
    out = _battle_plan_scale(None, None, None, None, None, None, "持有")
    assert isinstance(out, str)
    assert "nan" not in out.lower()


def test_build_risk_iron_rules_degenerate():
    # None / 空 dict → 返回非空列表，且文本无 NaN
    items = _build_risk_iron_rules(None)
    assert isinstance(items, list) and len(items) >= 1
    items = _build_risk_iron_rules({})
    assert isinstance(items, list) and len(items) >= 1
    blob = " ".join(it.get("desc", "") for it in items)
    assert "nan" not in blob.lower()


def test_build_plan_rows_none_inputs():
    # None 数值 → 不崩，返回两方案元组
    rows = _build_plan_rows("持有", None, None, None, None, None, None, None)
    assert len(rows) == 2
    for r in rows:
        assert isinstance(r, tuple)
        assert "nan" not in " ".join(str(x) for x in r).lower()


def test_build_rise_fall_factors_degenerate():
    # None / 空 dict → 不崩，且每侧至少补一条默认因素
    rise, fall = _build_rise_fall_factors(None)
    assert isinstance(rise, list) and isinstance(fall, list)
    assert len(rise) >= 1 and len(fall) >= 1
    # current_price=0 时分母被守卫，不应出现 NaN
    rise, fall = _build_rise_fall_factors({"current_price": 0, "resistance": 0})
    blob = " ".join(f.get("desc", "") for f in rise + fall)
    assert "nan" not in blob.lower()


def test_build_logic_lists_degenerate():
    # None / 空 dict → 返回 (rise, fall, fatal) 三元组，每侧至少一条
    rise, fall, fatal = _build_logic_lists(None)
    assert len(rise) >= 1 and len(fall) >= 1 and len(fatal) >= 1
    blob = " ".join(
        it.get("desc", "") for it in rise + fall + fatal
    )
    assert "nan" not in blob.lower()


def test_factor_list_html_missing_keys():
    # 缺 stars/title/desc 的因子不崩
    html = _factor_list_html("上涨因素", [{"foo": "bar"}])
    assert isinstance(html, str)
    assert "nan" not in html.lower()


def test_logic_list_html_missing_keys():
    # 缺 title/desc 的条目不崩
    html = _logic_list_html("利好逻辑", [{"core": True}], RED, "")
    assert isinstance(html, str)
    assert "nan" not in html.lower()


def test_calc_trade_levels_nan_current_price():
    # NaN 当前价 → 安全返回，不抛异常、不传播 NaN
    res = _calc_trade_levels(float("nan"), None, None, None)
    assert isinstance(res, tuple)
    assert len(res) == 4

