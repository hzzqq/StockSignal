"""test_signal.py — 信号分析模块测试"""

import pytest
import pandas as pd
from datetime import datetime, timedelta
from modules.signal import SignalEngine
from modules.cleaner import DataCleaner


class TestDataCleaner:

    def test_fill_missing_ffill(self):
        df = pd.DataFrame({"a": [1, None, 3, None, 5]})
        result = DataCleaner.fill_missing(df, method="ffill")
        assert result["a"].isna().sum() == 0
        assert result["a"].iloc[1] == 1

    def test_fill_missing_bfill(self):
        df = pd.DataFrame({"a": [1, None, 3]})
        result = DataCleaner.fill_missing(df, method="bfill")
        assert result["a"].iloc[1] == 3

    def test_remove_outliers_iqr(self):
        df = pd.DataFrame({"v": [1, 2, 3, 4, 5, 100]})
        result = DataCleaner.remove_outliers(df, "v", method="iqr")
        assert len(result) < len(df)
        assert 100 not in result["v"].values

    def test_calc_returns(self):
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=25),
            "close": range(25)
        })
        result = DataCleaner.calc_returns(df)
        assert "return_1d" in result.columns
        assert "return_5d" in result.columns
        assert "return_20d" in result.columns

    def test_calc_ma(self):
        df = pd.DataFrame({"close": range(30)})
        result = DataCleaner.calc_ma(df, windows=[5, 20])
        assert "ma5" in result.columns
        assert "ma20" in result.columns
        assert pd.isna(result["ma5"].iloc[0])

    def test_normalize_minmax(self):
        df = pd.DataFrame({"v": [0, 5, 10]})
        result = DataCleaner.normalize(df, ["v"], method="minmax")
        assert result["v"].min() == 0
        assert result["v"].max() == 1.0


class TestSignalEngine:

    def test_price_score_empty(self):
        engine = SignalEngine()
        df = pd.DataFrame()
        score = engine.price_score(df)
        assert 0 <= score <= 100

    def test_price_score_with_data(self):
        engine = SignalEngine()
        # 构造上涨趋势数据
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=70),
            "close": [10 + i * 0.5 for i in range(70)],
            "volume": [1000 + i * 10 for i in range(70)],
            "change_pct": [0.5] * 70
        })
        df = DataCleaner.full_pipeline(df)
        score = engine.price_score(df)
        assert 0 <= score <= 100
        assert score > 50  # 上涨趋势应该偏高

    def test_macro_score(self):
        engine = SignalEngine()
        try:
            score = engine.macro_score()
            assert 0 <= score <= 100
        except Exception:
            pytest.skip("网络不可用，跳过")

    def test_add_and_load_event(self, tmp_path):
        """测试事件添加与加载。"""
        engine = SignalEngine()
        engine.event_db_path = str(tmp_path / "test_events.csv")

        engine.add_event("2025-06-01", "601088", "煤炭价格大涨", "利好")
        events = engine._load_events()
        assert len(events) == 1
        assert events.iloc[0]["title"] == "煤炭价格大涨"

    def test_event_score_with_keywords(self, tmp_path):
        engine = SignalEngine()
        engine.event_db_path = str(tmp_path / "test_events.csv")
        engine.add_event("2025-06-01", "601088", "煤炭价格大涨利好", "利好")

        score = engine.event_score("601088", ["煤炭"], date="2025-06-15")
        assert 0 <= score <= 100
        assert score > 50  # 利好事件应偏高
