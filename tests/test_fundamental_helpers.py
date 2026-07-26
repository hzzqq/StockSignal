"""test_fundamental_helpers.py — 纯函数簇单测（无网依赖）。

覆盖 modules/fundamental_helpers 中的数值解析、比率、成长/环比计算、统计与综合评分等
纯逻辑，确保拆分 (#408) 后行为不变，并加固对「除零 / None / 缺失字段 / NaN」的鲁棒性。
所有测试均为离线构造最小数据，不触发任何网络请求。
"""

import math

import pandas as pd

from modules.fundamental_helpers import (
    _to_num, _to_float, _percentile, _pe_status, _period_label,
    _compute_yoy, _compute_qoq, _normalize_industry,
    _fmt_fin_value, _fmt_fin_yoy, _composite_score,
    calc_alr, _alr_status, _roe_status,
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

    def test_nan_float_collapses_to_none(self):
        # R1/R2: NaN 浮点输入应安全收敛为 None，而非泄漏 NaN
        assert _to_num(float("nan")) is None


class TestToFloat:
    def test_sentinels(self):
        assert _to_float(None) is None
        assert _to_float("") is None
        assert _to_float("—") is None

    def test_numeric(self):
        assert _to_float("1.5") == 1.5
        assert _to_float(2) == 2.0

    def test_nan_float_collapses_to_none(self):
        assert _to_float(float("nan")) is None


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

    def test_nan_value_is_safe(self):
        # R2: NaN 作为 value 入参不应泄漏为 0.0
        assert _percentile(pd.Series([1, 2, 3]), float("nan")) is None


class TestPeStatus:
    def test_thresholds(self):
        assert _pe_status(None) == "—"
        assert _pe_status(-5) == "—"
        assert _pe_status(10) == "低估区间"
        assert _pe_status(20) == "合理区间"
        assert _pe_status(40) == "偏高区间"
        assert _pe_status(60) == "高估区间"


class TestAlrStatus:
    def test_low_leverage(self):
        assert _alr_status(30.0) == "低杠杆"

    def test_mid_leverage(self):
        assert _alr_status(50.0) == "中杠杆"

    def test_high_leverage(self):
        assert _alr_status(70.0) == "高杠杆"

    def test_none_is_dash(self):
        assert _alr_status(None) == "—"

    def test_negative_out_of_range_is_dash(self):
        assert _alr_status(-5.0) == "—"

    def test_over_100_out_of_range_is_dash(self):
        assert _alr_status(150.0) == "—"


class TestRoeStatus:
    def test_levels(self):
        assert _roe_status(None) == "—"
        assert _roe_status(float("nan")) == "—"
        assert _roe_status(-1.0) == "亏损"
        assert _roe_status(2.0) == "偏弱"
        assert _roe_status(8.0) == "一般"
        assert _roe_status(12.0) == "良好"
        assert _roe_status(20.0) == "优秀"


class TestPeriodLabel:
    def test_annual(self):
        assert _period_label(pd.Timestamp("2024-03-15"), "年度") == "2024年报"

    def test_quarter(self):
        assert _period_label(pd.Timestamp("2024-01-15"), "季度") == "2024Q1"
        assert _period_label(pd.Timestamp("2024-07-15"), "季度") == "2024Q3"


class TestYoYQoQ:
    def test_yoy_normal(self):
        # R3: 正常比率正确计算
        s = pd.Series(
            [100.0, 110.0],
            index=[pd.Timestamp("2023-01-01"), pd.Timestamp("2024-01-01")],
        )
        yoy = _compute_yoy(s)
        assert yoy.iloc[0] == 10.0

    def test_qoq_normal(self):
        s = pd.Series(
            [100.0, 110.0],
            index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-04-01")],
        )
        qoq = _compute_qoq(s)
        assert qoq.iloc[0] == 10.0

    def test_yoy_zero_denominator_safe(self):
        # R2: 前期为 0 不应触发除零，应安全跳过（空结果）
        s = pd.Series(
            [0.0, 5.0],
            index=[pd.Timestamp("2023-01-01"), pd.Timestamp("2024-01-01")],
        )
        yoy = _compute_yoy(s)
        assert yoy.empty

    def test_qoq_zero_denominator_safe(self):
        s = pd.Series(
            [0.0, 5.0],
            index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-04-01")],
        )
        qoq = _compute_qoq(s)
        assert qoq.empty

    def test_yoy_nan_denominator_no_leak(self):
        # R2: 前期为 NaN 不应泄漏 NaN 到结果
        s = pd.Series(
            [float("nan"), 5.0],
            index=[pd.Timestamp("2023-01-01"), pd.Timestamp("2024-01-01")],
        )
        yoy = _compute_yoy(s)
        assert yoy.empty

    def test_qoq_nan_denominator_no_leak(self):
        s = pd.Series(
            [float("nan"), 5.0],
            index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-04-01")],
        )
        qoq = _compute_qoq(s)
        assert qoq.empty

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
        # R5: 缺字段 perf={} 应安全给出 0-100 评分
        score, text = _composite_score(
            price=100, pe=12, hist_pct_5y=50,
            sector_rank=None, sector_total=0,
            market_cap=1500, perf={},
        )
        assert isinstance(score, int)
        assert 0 <= score <= 100
        assert isinstance(text, str)
        assert "低估" in text

    def test_high_pe_flagged(self):
        score, text = _composite_score(
            price=100, pe=80, hist_pct_5y=95,
            sector_rank=60, sector_total=60,
            market_cap=30, perf={"revenue_yoy": -5.0, "profit_yoy": -10.0},
        )
        assert isinstance(score, int)
        assert 0 <= score <= 100
        assert ("偏高" in text) or ("承压" in text)

    def test_clip_upper_bound(self):
        score, _ = _composite_score(
            price=100, pe=10, hist_pct_5y=50,
            sector_rank=1, sector_total=100,
            market_cap=5000,
            perf={"revenue_yoy": 50.0, "profit_yoy": 50.0,
                  "alr": 20.0, "current_ratio": 3.0},
        )
        assert score <= 100

    def test_all_none_inputs_safe(self):
        # R6: 全部为 None / 缺字段不应崩溃
        score, text = _composite_score(
            price=None, pe=None, hist_pct_5y=None,
            sector_rank=None, sector_total=0,
            market_cap=None, perf={},
        )
        assert isinstance(score, int)
        assert 0 <= score <= 100


class FakeBalanceFetcher:
    def __init__(self, df):
        self._df = df

    def get_financial(self, code, sheet):
        return self._df


class TestCalcAlr:
    def test_normal_ratio(self):
        # R3: 正常比率正确计算 = 负债/资产*100
        df = pd.DataFrame({"资产总计": [200.0], "负债合计": [80.0]})
        assert calc_alr("000001", FakeBalanceFetcher(df)) == 40.0

    def test_zero_debt_returns_zero(self):
        # 0 负债应得 ALR=0.0（真实 0，而非误判缺失 None）
        df = pd.DataFrame({"资产总计": [100.0], "负债合计": [0.0]})
        assert calc_alr("000001", FakeBalanceFetcher(df)) == 0.0

    def test_zero_asset_safe(self):
        # R2: 资产为 0（分母为 0）不应除零崩溃，应安全返回 None
        df = pd.DataFrame({"资产总计": [0.0], "负债合计": [80.0]})
        assert calc_alr("000001", FakeBalanceFetcher(df)) is None

    def test_missing_columns_returns_none(self):
        # R5: 缺失字段应安全返回 None
        df = pd.DataFrame({"其他": [1.0]})
        assert calc_alr("000001", FakeBalanceFetcher(df)) is None

    def test_all_nan_safe(self):
        # R6: 全 NaN 输入不应泄漏 NaN，应安全返回 None
        df = pd.DataFrame({"资产总计": [float("nan")], "负债合计": [float("nan")]})
        res = calc_alr("000001", FakeBalanceFetcher(df))
        assert res is None

    def test_nan_denominator_no_leak(self):
        # R2: 分母为 NaN 不得泄漏 NaN 结果
        df = pd.DataFrame({"资产总计": [float("nan")], "负债合计": [50.0]})
        res = calc_alr("000001", FakeBalanceFetcher(df))
        assert res is None or not math.isnan(res)
