"""test_fundamental_helpers.py — #408 拆出的纯函数簇单测（无网依赖）。

覆盖 modules/fundamental_helpers 中的数值解析、格式化、统计与综合评分等纯逻辑，
确保拆分超大文件 (#408) 后行为不变、且后续改动有回归护栏。
"""

import pandas as pd

from modules.fundamental_helpers import (
    _to_num, _to_float, _percentile, _pe_status, _period_label,
    _compute_yoy, _compute_qoq, _normalize_industry,
    _fmt_fin_value, _fmt_fin_yoy, _composite_score,
)


class TestToNum:
    def test_int_float_pass_through(self):
        assert _to_num(5) == 5.0
        assert _to_num(3.14) == 3.14

    def test_string_cleaning(self):
        assert _to_num("1,234.5") == 1234.5
        assert _to_num("12%") == 12.0
        assert _to_num("  8  ") == 8.0

    def test_empty_and_garbage(self):
        assert _to_num("") is None
        assert _to_num("-") is None
        assert _to_num("--") is None
        assert _to_num("nan") is None
        assert _to_num("abc") is None
        assert _to_num(None) is None


class TestToFloat:
    def test_sentinels(self):
        assert _to_float(None) is None
        assert _to_float("") is None
        assert _to_float("—") is None

    def test_numeric(self):
        assert _to_float("1.5") == 1.5
        assert _to_float(2) == 2.0


class TestPercentile:
    def test_basic(self):
        s = pd.Series([1, 2, 3, 4, 5])
        assert _percentile(s, 3) == 60.0
        assert _percentile(s, 10) == 100.0
        assert _percentile(s, 0) == 0.0

    def test_edge(self):
        assert _percentile(None, 3) is None
        assert _percentile(pd.Series([], dtype=float), 3) is None
        assert _percentile(pd.Series([1, 2, 3]), None) is None


class TestPeStatus:
    def test_thresholds(self):
        assert _pe_status(None) == "—"
        assert _pe_status(-5) == "—"
        assert _pe_status(10) == "低估区间"
        assert _pe_status(20) == "合理区间"
        assert _pe_status(40) == "偏高区间"
        assert _pe_status(60) == "高估区间"


class TestPeriodLabel:
    def test_annual(self):
        assert _period_label(pd.Timestamp("2024-03-15"), "年度") == "2024年报"

    def test_quarter(self):
        assert _period_label(pd.Timestamp("2024-01-15"), "季度") == "2024Q1"
        assert _period_label(pd.Timestamp("2024-07-15"), "季度") == "2024Q3"


class TestYoYQoQ:
    def test_yoy(self):
        s = pd.Series(
            [100.0, 110.0],
            index=[pd.Timestamp("2023-01-01"), pd.Timestamp("2024-01-01")],
        )
        yoy = _compute_yoy(s)
        assert yoy.iloc[0] == 10.0

    def test_qoq(self):
        s = pd.Series(
            [100.0, 110.0],
            index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-04-01")],
        )
        qoq = _compute_qoq(s)
        assert qoq.iloc[0] == 10.0

    def test_empty(self):
        assert _compute_yoy(None).empty
        assert _compute_qoq(pd.Series(dtype=float)).empty


class TestNormalizeIndustry:
    def test_roman_suffix(self):
        assert _normalize_industry("白酒Ⅱ") == "白酒"
        assert _normalize_industry("白酒III") == "白酒"

    def test_whitespace(self):
        assert _normalize_industry(" 银行 II ") == "银行"

    def test_empty(self):
        assert _normalize_industry("") == ""


class TestFmtFin:
    def test_value_none(self):
        assert _fmt_fin_value(None, "归母净利润") == "—"
        assert _fmt_fin_yoy(None, "归母净利润") == "—"

    def test_value_format(self):
        assert _fmt_fin_value(12.345, "归母净利润") == "12.35亿"
        assert _fmt_fin_yoy(5.0, "归母净利润") == "+5.00%"


class TestCompositeScore:
    def test_low_pe_bluechip(self):
        score, text = _composite_score(
            price=100, pe=12, hist_pct_5y=50,
            sector_rank=None, sector_total=0,
            market_cap=1500, perf={},
        )
        assert isinstance(score, int)
        assert 0 <= score <= 100
        assert isinstance(text, str)
        # PE<15 应贡献高估分理由
        assert "低估" in text

    def test_high_pe_flagged(self):
        score, text = _composite_score(
            price=100, pe=80, hist_pct_5y=95,
            sector_rank=60, sector_total=60,
            market_cap=30, perf={"revenue_yoy": -5.0, "profit_yoy": -10.0},
        )
        assert isinstance(score, int)
        assert 0 <= score <= 100
        # 高 PE + 业绩承压应有负面提示
        assert ("偏高" in text) or ("承压" in text)

    def test_clip_upper_bound(self):
        # 全满分不应溢出 100
        score, _ = _composite_score(
            price=100, pe=10, hist_pct_5y=50,
            sector_rank=1, sector_total=100,
            market_cap=5000,
            perf={"revenue_yoy": 50.0, "profit_yoy": 50.0,
                  "alr": 20.0, "current_ratio": 3.0},
        )
        assert score <= 100
