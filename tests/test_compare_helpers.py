"""R19：compare.py 纯函数单测（无网依赖）。

覆盖多股对比模块中可离线复现的纯函数：
1. _hex_to_rgba      —— #rrggbb / #rgb 转 rgba；
2. _pattern_score    —— 看涨+12 / 看跌-12，夹紧 0-100；
3. _catalyst_score   —— 动量+量能+形态 加权代理分；
4. _signal_from      —— composite + 动量标签 → 买入/持有/卖出；
5. _biz_groups       —— 行业大类关键词映射；
6. _biz_similarity   —— 同行业/包含/同大类/弱相关 四档；
7. _fmt / _fmt_pct   —— 数值与百分比格式化（含 None/NaN 防御）。

全部纯 Python / pandas，不触发 streamlit 与网络。
"""

from modules.compare import (
    _hex_to_rgba,
    _pattern_score,
    _catalyst_score,
    _signal_from,
    _biz_groups,
    _biz_similarity,
    _fmt,
    _fmt_pct,
)


# ----------------------------------------------------------------------
# _hex_to_rgba
# ----------------------------------------------------------------------
def test_hex_to_rgba_6digit():
    assert _hex_to_rgba("#ff0000", 0.5) == "rgba(255,0,0,0.5)"


def test_hex_to_rgba_3digit():
    assert _hex_to_rgba("#0f0", 1.0) == "rgba(0,255,0,1.0)"


def test_hex_to_rgba_no_hash():
    assert _hex_to_rgba("0000ff", 0.2) == "rgba(0,0,255,0.2)"


# ----------------------------------------------------------------------
# _pattern_score
# ----------------------------------------------------------------------
def test_pattern_score_neutral():
    assert _pattern_score([]) == 50.0


def test_pattern_score_bullish():
    pats = [{"bias": "看涨"}, {"bias": "看涨"}]
    assert _pattern_score(pats) == 74.0


def test_pattern_score_bearish_clamp():
    pats = [{"bias": "看跌"}] * 10  # 50 - 120 → 夹紧到 0
    assert _pattern_score(pats) == 0.0


def test_pattern_score_mixed():
    pats = [{"bias": "看涨"}, {"bias": "看跌"}, {"bias": "中性"}]
    assert _pattern_score(pats) == 50.0


# ----------------------------------------------------------------------
# _catalyst_score
# ----------------------------------------------------------------------
def _ta(mom=50, vol=50, patterns=None):
    return {
        "momentum": {"momentum_score": mom},
        "volume": {"volume_price_score": vol},
        "patterns": patterns or [],
    }


def test_catalyst_score_neutral():
    assert _catalyst_score(_ta(50, 50, [])) == 50.0


def test_catalyst_score_bullish():
    s = _catalyst_score(_ta(80, 85, [{"bias": "看涨"}]))
    assert 50 < s <= 100
    # 50 + (80-50)*0.45 + (85-50)*0.30 + (62-50)*0.35 = 50+13.5+10.5+4.2 = 78.2
    assert s == 78.2


def test_catalyst_score_clamp():
    s = _catalyst_score(_ta(100, 100, [{"bias": "看涨"}] * 5))
    assert 0 <= s <= 100


# ----------------------------------------------------------------------
# _signal_from
# ----------------------------------------------------------------------
def _ta_label(label):
    return {"momentum": {"momentum_label": label}}


def test_signal_from_buy():
    assert _signal_from(70, _ta_label("强势上攻")) == "买入"


def test_signal_from_buy_needs_strong():
    # 高分但动量标签不含「上攻/走强/上涨」→ 持有而非买入
    assert _signal_from(70, _ta_label("横盘整理")) == "持有"


def test_signal_from_hold():
    assert _signal_from(60, _ta_label("震荡")) == "持有"


def test_signal_from_sell():
    assert _signal_from(40, _ta_label("明显走弱")) == "卖出"


# ----------------------------------------------------------------------
# _biz_groups / _biz_similarity
# ----------------------------------------------------------------------
def test_biz_groups_match():
    assert "电子半导体" in _biz_groups("半导体")
    assert "消费" in _biz_groups("白酒")
    assert "金融" in _biz_groups("证券")


def test_biz_groups_no_match():
    assert _biz_groups("未知行业") == []


def test_biz_similarity_same():
    a = {"industry": "半导体"}
    b = {"industry": "半导体"}
    assert _biz_similarity(a, b) == 90.0


def test_biz_similarity_substring():
    a = {"industry": "半导体"}
    b = {"industry": "半导体设备"}
    assert _biz_similarity(a, b) == 60.0


def test_biz_similarity_group_overlap():
    a = {"industry": "半导体"}
    b = {"industry": "消费电子"}  # 不同行业但同属「电子半导体」大类
    assert _biz_similarity(a, b) == 55.0


def test_biz_similarity_weak():
    a = {"industry": "半导体"}
    b = {"industry": "医药"}
    assert _biz_similarity(a, b) == 12.0


def test_biz_similarity_empty():
    assert _biz_similarity({"industry": ""}, {"industry": "白酒"}) == 0.0


# ----------------------------------------------------------------------
# _fmt / _fmt_pct
# ----------------------------------------------------------------------
def test_fmt_none_and_nan():
    assert _fmt(None) == "—"
    assert _fmt(float("nan")) == "—"


def test_fmt_num():
    assert _fmt(12.345, is_num=True) == "12.3"


def test_fmt_str():
    assert _fmt("hello") == "hello"


def test_fmt_pct_percent_input():
    # 已是百分比数字
    assert _fmt_pct(12.5) == "12.50%"


def test_fmt_pct_decimal_input():
    # 小数 0.1234 → 12.34%
    assert _fmt_pct(0.1234) == "12.34%"


def test_fmt_pct_none():
    assert _fmt_pct(None) == "—"
