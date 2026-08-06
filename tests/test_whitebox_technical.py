"""test_whitebox_technical.py — 技术面分析模块白盒测试

覆盖 modules.technical 的纯计算函数：
  - _momentum_label 全边界映射
  - analyze_momentum 动量打分与标签
  - analyze_trend 多空排列判定（多头/空头/偏多/偏空/纠缠）
  - 空数据 / 空 DataFrame 的容错分支
纯 pandas 计算，无 IO、无 streamlit、无网络依赖。
"""

import pandas as pd
import pytest

from modules.technical import (
    _momentum_label,
    analyze_momentum,
    analyze_trend,
    full_analysis,
)


class TestMomentumLabel:
    """_momentum_label 边界全覆盖。"""

    @pytest.mark.parametrize("r5,expected", [
        (10.0, "强势上攻"),
        (12.3, "强势上攻"),
        (5.0, "明显走强"),
        (7.0, "明显走强"),
        (2.0, "温和上涨"),
        (3.5, "温和上涨"),
        (1.9, "震荡整理"),
        (0.0, "震荡整理"),
        (-2.0, "震荡整理"),
        (-3.0, "弱势回调"),
        (-5.0, "弱势回调"),
        (-6.0, "加速下跌"),
        (-20.0, "加速下跌"),
    ])
    def test_boundaries(self, r5, expected):
        assert _momentum_label(r5) == expected


def _momentum_df(r5):
    return pd.DataFrame({"return_5d": [r5], "return_1d": [0.0], "return_20d": [0.0]})


class TestAnalyzeMomentum:
    """analyze_momentum 打分与标签一致性。"""

    def test_label_matches_helper(self):
        for r5 in (12.0, 6.0, 3.0, -1.0, -4.0, -8.0):
            res = analyze_momentum(_momentum_df(r5))
            assert res["momentum_label"] == _momentum_label(r5)

    def test_score_range(self):
        res = analyze_momentum(_momentum_df(7.0))
        assert isinstance(res["momentum_score"], int)
        assert 0 <= res["momentum_score"] <= 100

    def test_returns_keys_present(self):
        res = analyze_momentum(_momentum_df(3.0))
        assert set(["1日", "5日", "20日"]).issubset(res["returns"].keys())

    def test_empty_df_error(self):
        assert analyze_momentum(pd.DataFrame()) == {"error": "数据为空"}

    def test_none_error(self):
        assert analyze_momentum(None) == {"error": "数据为空"}


def _trend_df(ma5, ma10, ma20, ma60, close):
    return pd.DataFrame({
        "close": [close],
        "ma5": [ma5], "ma10": [ma10],
        "ma20": [ma20], "ma60": [ma60],
    })


class TestAnalyzeTrend:
    """analyze_trend 排列判定。"""

    def test_bull_alignment(self):
        res = analyze_trend(_trend_df(12, 11, 10, 9, 13))
        assert res["arrangement"] == "多头排列"
        assert res["trend_score"] == 85
        assert res["above_count"] == 4

    def test_bear_alignment(self):
        res = analyze_trend(_trend_df(9, 10, 11, 12, 8))
        assert res["arrangement"] == "空头排列"
        assert res["trend_score"] == 15

    def test_entangled_equal(self):
        res = analyze_trend(_trend_df(10, 10, 10, 10, 10))
        assert res["arrangement"] == "纠缠"
        assert res["trend_score"] == 50

    def test_partial_bull(self):
        # close>ma20 且 ma5>ma20，但非严格多头
        res = analyze_trend(_trend_df(11, 9, 10, 8, 12))
        assert res["arrangement"] == "偏多"
        assert res["trend_score"] == 65

    def test_trend_label_format(self):
        res = analyze_trend(_trend_df(12, 11, 10, 9, 13))
        assert "站上4条均线" in res["trend_label"]

    def test_empty_df_error(self):
        assert analyze_trend(pd.DataFrame()) == {"error": "数据为空"}

    def test_none_error(self):
        assert analyze_trend(None) == {"error": "数据为空"}


class TestFullAnalysisContract:
    """R81 契约：full_analysis 返回类型必须统一，页面消费方依赖。

    消费方（pages/1_股票选取.py 等）用 ``if "error" not in trend`` 判断，
    隐含约定 trend/momentum/volume 必为 dict、patterns 必为 list——
    若某子分析漂移为 None/str 会直接 TypeError（"error" not in None）或
    误走正常分支（字符串 in 检查）。本测试锁定四种输入下的类型契约。
    """

    def _assert_contract(self, result):
        for k in ("trend", "momentum", "volume"):
            assert isinstance(result[k], dict), f"{k} 必须是 dict，实际 {type(result[k]).__name__}"
        assert isinstance(result["patterns"], list), "patterns 必须是 list"

    def test_empty_df_contract(self):
        self._assert_contract(full_analysis(pd.DataFrame()))
        # 空数据时子分析应给 error 键（消费方据此降级展示）
        assert "error" in full_analysis(pd.DataFrame())["volume"]

    def test_incomplete_df_contract(self):
        # 只有 date/close 的残缺 DF：各子分析仍返回 dict（不崩、不漂移）
        df = pd.DataFrame({"date": ["2024-01-01", "2024-01-02"], "close": [1.0, 2.0]})
        self._assert_contract(full_analysis(df))

    def test_minimal_rows_contract(self):
        df = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "open": [1, 2, 3], "high": [2, 3, 4], "low": [0.5, 1, 2],
            "close": [1.5, 2.5, 3.5], "volume": [100, 200, 300],
        })
        self._assert_contract(full_analysis(df))

    def test_none_df_contract(self):
        self._assert_contract(full_analysis(None))
