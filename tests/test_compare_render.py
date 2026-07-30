"""多股对比渲染管线回归测试（无网依赖）。

守护「≥5 只标的」决策仪表盘渲染不回归：所有 build_* 产出器 + compare_css
都用最小 mock rows 跑一遍，断言产出非空（HTML / Plotly Figure），不抛异常。
对应需求：多股对比（≥5 只）1:1 还原星辰决策仪表盘风格。
"""
import modules.compare as C
from modules.compare import METHODS


def _row(code, name, **over):
    """与 tests/test_compare.py 同样的极小可评分行构造器。"""
    base = {
        "code": code,
        "name": name,
        "industry": "半导体",
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
        "pe_ttm": 30.0,
        "pb": 3.0,
        "ps": 5.0,
        "dv_ttm": 1.0,
        "roe": 12.0,
        "revenue_yoy": 10.0,
        "profit_yoy": 8.0,
        "fund_main_net": 1e8,
        "fund_main_net_pct": 5.0,
        "fund_big_net": 5e7,
        "support": 9.0,
        "resistance": 11.0,
        "df": None,
    }
    base.update(over)
    return base


def _five_rows():
    """构造 5 只差异化的标的，覆盖买入/持有/卖出信号与缺失字段兜底。"""
    rows = [
        _row("600667", "太极实业", scores={"trend": 80, "momentum": 75, "volume": 70, "pattern": 65, "composite": 72},
             chg_pct=4.5, elasticity=42.0, catalyst=80.0, signal="买入", pe_ttm=35.0, pb=3.4, dv_ttm=0.8,
             fund_main_net=3e8, business_corr=90.0),
        _row("601133", "B公司", scores={"trend": 55, "momentum": 50, "volume": 52, "pattern": 48, "composite": 51},
             chg_pct=-0.8, elasticity=22.0, catalyst=45.0, signal="持有", pe_ttm=22.0, pb=2.1, dv_ttm=1.5,
             fund_main_net=-5e7, business_corr=55.0),
        _row("002947", "C股份", scores={"trend": 40, "momentum": 38, "volume": 44, "pattern": 41, "composite": 41},
             chg_pct=-2.3, elasticity=15.0, catalyst=35.0, signal="卖出", pe_ttm=48.0, pb=4.2, dv_ttm=0.3,
             fund_main_net=-1e8, business_corr=30.0),
        _row("002167", "D科技", scores={"trend": 68, "momentum": 62, "volume": 60, "pattern": 58, "composite": 62},
             chg_pct=2.1, elasticity=33.0, catalyst=60.0, signal="买入", pe_ttm=28.0, pb=2.8, dv_ttm=1.1,
             fund_main_net=1.2e8, business_corr=70.0),
        # 末只故意缺部分字段，验证 .get 兜底不崩溃
        _row("600206", "E材料", scores={"composite": 48}, chg_pct=0.5, signal="持有"),
    ]
    return rows


# ── CSS ────────────────────────────────────────────────
def test_compare_css_nonempty():
    css = C.compare_css()
    assert isinstance(css, str) and len(css) > 200
    # 决策仪表盘关键结构选择器必须存在（防样式回退）
    assert ".compare-wrap" in css and ".compare-wrap .card" in css and ".compare-wrap .header" in css


# ── HTML 产出器（≥5 只）────────────────────────────────
def test_build_header_table_oneline():
    rows = _five_rows()
    assert len(rows) == 5
    for fn in (C.build_header, C.build_one_line, C.build_table):
        html = fn(rows, 120) if fn is C.build_header else fn(rows)
        assert isinstance(html, str) and html.strip(), f"{fn.__name__} 返回空"
        assert "600667" in html or "太极实业" in html  # 数据确实进入渲染


def test_build_pairwise_and_radar_right():
    rows = _five_rows()
    a, b = rows[0], rows[1]
    html = C.build_pairwise_card(a, b, 1)
    assert "太极实业" in html and "B公司" in html
    right = C.build_radar_right(rows)
    assert "风险提示" in right


def test_build_extra_method_aggregate_action_footer():
    rows = _five_rows()
    method = list(METHODS.keys())[0]
    assert C.build_extra_card(rows).strip()
    assert C.build_method_card(rows, method, "").strip()
    assert C.build_aggregate_card(rows, "").strip()
    assert C.build_action_plan(rows).strip()
    assert C.build_footer().strip()


# ── Plotly 图（≥5 只雷达）────────────────────────────
def test_build_radar_figure():
    rows = _five_rows()
    fig = C.build_radar(rows)
    assert fig is not None
    # 5 只股票 → 5 条 scatterpolar trace
    assert len(fig.data) == 5
