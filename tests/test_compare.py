"""compare.py 纯函数 / 边界回归测试（无网依赖）。

覆盖：
- 评分原语 _safe / _norm / _pattern_score / _catalyst_score
- 行业相似度 _biz_similarity
- 事件立场 _event_stance
- 多维度评分 compute_method_scores（空 / 单只 / 含 NaN）
- 新能力 rank_methods（结构化赢家映射）
- 隐式 bug 修复：build_method_card 早返回不再残留字面 {method}；空 rows 不崩溃
"""
import math

import numpy as np
import pytest

import modules.compare as C


def _row(code="600000", name="测试股", **over):
    """构造最小可评分行，便于纯函数测试。"""
    base = {
        "code": code,
        "name": name,
        "industry": "银行",
        "scores": {
            "trend": 60.0, "momentum": 55.0, "volume": 50.0,
            "pattern": 50.0, "composite": 60.0,
        },
        "chg_pct": 1.2,
        "elasticity": 30.0,
        "business_corr": 40.0,
        "catalyst": 55.0,
        "signal": "持有",
        "market_cap": 1000.0,
        "pe_ttm": 8.0,
        "pb": 1.0,
        "ps": 2.0,
        "dv_ttm": 3.0,
        "roe": 12.0,
        "revenue_yoy": 10.0,
        "profit_yoy": 8.0,
        "fund_main_net": 1e8,
        "fund_main_net_pct": 5.0,
        "fund_big_net": 5e7,
        "support": 9.0,
        "resistance": 11.0,
    }
    base.update(over)
    return base


def _two_rows():
    a = _row("600000", "A行", scores={"trend": 80, "momentum": 75, "volume": 70, "pattern": 65, "composite": 72},
             industry="银行", chg_pct=3.0, elasticity=40.0, catalyst=80.0, signal="买入",
             pe_ttm=6.0, pb=0.9, dv_ttm=4.0, fund_main_net=3e8, business_corr=90.0)
    b = _row("600001", "B行", scores={"trend": 40, "momentum": 45, "volume": 50, "pattern": 48, "composite": 45},
             industry="银行", chg_pct=-1.0, elasticity=20.0, catalyst=40.0, signal="卖出",
             pe_ttm=12.0, pb=1.4, dv_ttm=2.0, fund_main_net=-1e8, business_corr=30.0)
    return [a, b]


# ── 评分原语 ──────────────────────────────────────────────
def test_safe_basics():
    assert C._safe(None) == 0.0
    assert C._safe("3.5") == 3.5
    assert C._safe(float("nan"), 9.0) == 9.0
    assert C._safe("not-a-number", 5.0) == 5.0
    assert C._safe("", 2.0) == 2.0


def test_norm_all_equal():
    assert C._norm([5.0, 5.0, 5.0]) == [50.0, 50.0, 50.0]


def test_norm_range_maps_to_50_100():
    out = C._norm([0.0, 10.0, 20.0])
    assert out[0] == 50.0
    assert out[-1] == 100.0
    assert all(50.0 <= v <= 100.0 for v in out)


def test_pattern_score_clamps():
    assert C._pattern_score([]) == 50.0
    assert C._pattern_score([{"bias": "看涨"}]) == 62.0
    assert C._pattern_score([{"bias": "看跌"}]) == 38.0
    # 封顶 100
    many = [{"bias": "看涨"}] * 10
    assert C._pattern_score(many) == 100.0


def test_catalyst_score_deterministic():
    ta = {"momentum": {"momentum_score": 80}, "volume": {"volume_price_score": 70},
          "patterns": [{"bias": "看涨"}]}
    s = C._catalyst_score(ta)
    assert 0.0 <= s <= 100.0
    assert C._catalyst_score(ta) == s  # 幂等


# ── 行业相似度 ────────────────────────────────────────────
def test_biz_similarity():
    a = {"industry": "半导体"}
    b = {"industry": "半导体"}
    c = {"industry": "半导体制造"}
    d = {"industry": "白酒"}
    assert C._biz_similarity(a, b) == 90.0        # 完全相同
    assert C._biz_similarity(a, c) == 60.0        # 包含
    assert C._biz_similarity(a, d) == 12.0        # 弱相关
    assert C._biz_similarity({"industry": ""}, a) == 0.0  # 缺行业


# ── 事件立场 ──────────────────────────────────────────────
def test_event_stance_chip():
    stock = {"industry": "电子半导体"}
    rel, stance = C._event_stance(stock, "AI 芯片 扩产 利好")
    assert rel == 85.0
    assert stance == "利好"


def test_event_stance_bear():
    stock = {"industry": "医药生物"}
    rel, stance = C._event_stance(stock, "医药 处罚 减持 利空")
    # 事件含「医药」→ 与医药生物行业高关联(85)；看空词决定立场为利空
    assert rel == 85.0
    assert stance == "利空"


# ── 多维度评分 ───────────────────────────────────────────
def test_compute_method_scores_empty():
    assert C.compute_method_scores([], "短期") == {}


def test_compute_method_scores_single_row():
    rows = [_row()]
    for m in C.METHODS:
        sc = C.compute_method_scores(rows, m)
        assert list(sc.keys()) == ["600000"]
        assert all(0.0 <= v <= 100.0 for v in sc.values())


def test_compute_method_scores_with_nan_chg():
    rows = [_row(chg_pct=float("nan")), _row("600001", "B", chg_pct=2.0)]
    sc = C.compute_method_scores(rows, "短期")
    # NaN 经 _safe 退化为 0，不应产生 nan
    assert not any(math.isnan(v) for v in sc.values())


def test_compute_method_scores_event_requires_event():
    rows = _two_rows()
    # 不传 event 时「事件」维度无匹配关键词，关联度 0
    sc = C.compute_method_scores(rows, "事件")
    assert sc["600000"] == 0.0
    sc2 = C.compute_method_scores(rows, "事件", event="芯片 半导体 利好")
    # A/B 行业均为银行，与芯片无重叠 → 仍偏弱，但不崩溃
    assert all(0.0 <= v <= 100.0 for v in sc2.values())


# ── 新能力 rank_methods ──────────────────────────────────
def test_rank_methods_structure():
    rows = _two_rows()
    out = C.rank_methods(rows)
    assert set(out.keys()) == set(C.METHODS)
    short = C.rank_methods(rows, event="芯片 利好")
    assert short["短期"]["winner_code"] == "600000"
    assert short["短期"]["winner_name"] == "A行"
    assert 0.0 <= short["短期"]["score"] <= 100.0


def test_rank_methods_empty():
    assert C.rank_methods([]) == {}


# ── 隐式 bug 修复 ───────────────────────────────────────
def test_build_method_card_single_row_no_literal_method():
    html = C.build_method_card(_two_rows()[:1], "短期")
    assert isinstance(html, str)
    assert "{method}" not in html        # 早返回的 f-string 必须已格式化
    assert "短期" in html


def test_build_method_card_literal_fix_various_methods():
    # 任意 method 早返回都不应残留占位符
    for m in ["长期", "价值", "资金", "事件", "宏观"]:
        html = C.build_method_card(_two_rows()[:1], m)
        assert "{method}" not in html


def test_hex_to_rgba():
    assert C._hex_to_rgba("#ff4d4f", 0.2) == "rgba(255,77,79,0.2)"
    assert C._hex_to_rgba("#fff", 1.0) == "rgba(255,255,255,1.0)"


def test_build_one_line_empty():
    assert C.build_one_line([]) == ""


def test_aggregate_card_empty_does_not_crash():
    # 空 rows：各方法 summary 退化为「暂无对比标的」，但不抛 IndexError
    html = C.build_aggregate_card([])
    assert isinstance(html, str)


# ── 需求 R1/R2：部分缺失 / None / NaN / 除零 / 空输入 健壮性 ──
def test_row_score_helper_safe_when_missing():
    # scores 缺失 / 为 None / 子项缺失 都安全返回 default
    assert C._row_score({"code": "X"}, "composite") == 50.0
    assert C._row_score({"code": "X", "scores": None}, "composite") == 50.0
    assert C._row_score({"code": "X", "scores": {}}, "momentum") == 50.0
    assert C._row_score({"code": "X", "scores": {"composite": 80}}, "composite") == 80.0


def test_partial_metric_missing_scores_no_crash():
    # 一只股票完全缺失 scores，另一只完整 —— 不应崩溃，且结果均为有限值
    full = _row("600000", "A行", scores={"trend": 80, "momentum": 75, "volume": 70,
                                          "pattern": 65, "composite": 72}, chg_pct=3.0)
    partial = {"code": "600001", "name": "B行(缺数据)", "scores": None}
    rows = [full, partial]
    for m in C.METHODS:
        sc = C.compute_method_scores(rows, m)
        assert set(sc.keys()) == {"600000", "600001"}
        assert not any(math.isnan(v) for v in sc.values())
        # 缺数据那只退化为有限值、落在 [0,100]，不会污染另一只
        assert 0.0 <= sc["600001"] <= 100.0
    out = C.rank_methods(rows)
    assert set(out.keys()) == set(C.METHODS)
    # 完整股票在「价值」维度应当胜出（缺数据那只退化为中性）
    assert out["价值"]["winner_code"] == "600000"


def test_normal_comparison_expected_ordering():
    a = _row("600000", "A行", scores={"trend": 80, "momentum": 75, "volume": 70,
                                      "pattern": 65, "composite": 72})
    b = _row("600001", "B行", scores={"trend": 40, "momentum": 45, "volume": 50,
                                      "pattern": 48, "composite": 45})
    rows = [a, b]
    sc = C.compute_method_scores(rows, "综合")
    assert sc["600000"] == 72.0 and sc["600001"] == 45.0
    ranked = C._ranked(rows, sc)
    assert ranked[0]["code"] == "600000"
    # METHODS 中无「综合」键；用「短期」维度验证完整股票(A)胜出
    assert C.rank_methods(rows)["短期"]["winner_code"] == "600000"


def test_zero_and_none_denominator_safe():
    # 1) 规范化除零（全部相等）→ 全部 50
    assert C._norm([5.0, 5.0, 5.0]) == [50.0, 50.0, 50.0]
    # 2) 输入含 None / NaN → 退化为有限值，不抛错、不产生 NaN
    out = C._norm([None, 10.0, 20.0, float("nan")])
    assert len(out) == 4
    assert not any(math.isnan(v) for v in out)
    # 3) 含 None / NaN 指标的评分不崩溃
    a = _row("600000", "A", chg_pct=None, elasticity=float("nan"), pe_ttm=None, pb=None, dv_ttm=None)
    b = _row("600001", "B", chg_pct=2.0, elasticity=20.0, pe_ttm=10.0, pb=1.0, dv_ttm=2.0)
    for m in ("短期", "长期", "价值", "宏观"):
        sc = C.compute_method_scores([a, b], m)
        assert not any(math.isnan(v) for v in sc.values())


def test_empty_input_safe_empty_result():
    # 所有方法对空输入返回 {}
    for m in C.METHODS:
        assert C.compute_method_scores([], m) == {}
    assert C.rank_methods([]) == {}
    assert C._norm([]) == []          # 空列表规范化安全返回 []
    assert C._ranked([], {}) == []


def test_render_partial_scores_does_not_crash():
    # 渲染层（R1）：部分股票缺失 scores 时，表格/一句话结论不抛异常
    full = _row("600000", "A行", scores={"trend": 80, "momentum": 75, "volume": 70,
                                         "pattern": 65, "composite": 72})
    partial = {"code": "600001", "name": "B行(缺数据)", "scores": None, "signal": "持有"}
    rows = [full, partial]
    assert isinstance(C.build_one_line(rows), str)
    assert isinstance(C.build_table(rows), str)
    assert isinstance(C.build_vs_cards(rows), str)
