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

    def test_add_event_is_atomic_no_tmp_lingering(self, tmp_path):
        """事件库写入须为原子写：写完后无 .tmp 残留，且可完整 reload。"""
        import os
        engine = SignalEngine()
        engine.event_db_path = str(tmp_path / "test_events.csv")

        engine.add_event("2025-06-01", "601088", "煤炭价格大涨", "利好")
        engine.add_event("2025-06-02", "600519", "白酒提价", "利好")

        assert os.path.exists(engine.event_db_path)
        assert not os.path.exists(engine.event_db_path + ".tmp")
        events = engine._load_events()
        assert len(events) == 2
        assert set(events["ticker"]) == {"601088", "600519"}

    def test_event_score_with_keywords(self, tmp_path):
        engine = SignalEngine()
        engine.event_db_path = str(tmp_path / "test_events.csv")
        engine.add_event("2025-06-01", "601088", "煤炭价格大涨利好", "利好")

        score = engine.event_score("601088", ["煤炭"], date="2025-06-15")
        assert 0 <= score <= 100
        assert score > 50  # 利好事件应偏高


class TestSignalRobustness:
    """针对三处脆弱点的纯逻辑单测（无网络）。"""

    def test_macro_score_empty_pmi_col_returns_50(self):
        """空 pmi_col 列表不得抛 IndexError，应返回中性 50。"""
        engine = SignalEngine()

        class FakeFetcher:
            def get_macro(self, name):
                # 不含任何 pmi 列的 DataFrame → pmi_col 为空
                return pd.DataFrame({
                    "date": pd.to_datetime(["2025-01-01"]),
                    "value": [51.0],
                })

        engine.fetcher = FakeFetcher()
        score = engine.macro_score(date=None)
        assert score == 50

    def test_macro_score_with_pmi_col_computes(self):
        """正常有 pmi 列时按公式计分，证明上一例走的是空列分支而非异常兜底。"""
        engine = SignalEngine()

        class FakeFetcher:
            def get_macro(self, name):
                return pd.DataFrame({
                    "date": pd.to_datetime(["2025-01-01"]),
                    "pmi_mfg": [52.0],
                })

        engine.fetcher = FakeFetcher()
        assert engine.macro_score(date=None) == 60  # 50 + (52-50)*5

    def test_event_score_regex_metachar_keywords(self):
        """关键词含正则元字符 (+ ( .) 不应抛错，且能正常匹配。"""
        engine = SignalEngine()

        def fake_load_events():
            return pd.DataFrame({
                "date": pd.to_datetime(["2025-06-01"]),
                "ticker": [None],  # isna() 命中，使 ticker 过滤通过
                "title": ["利好 A+B(C. 公告"],  # 含 + ( . 三种元字符
                "type": ["利好"],
            })

        engine._load_events = fake_load_events
        score = engine.event_score("601088", ["A+B(C."], date=None)
        assert 0 <= score <= 100
        assert score == 66  # 命中利好 → 52 + 14

    def test_evaluate_missing_weight_keys_fallback(self):
        """weights 缺 event/macro 键时回落默认 0.4/0.2，不 KeyError。"""
        engine = SignalEngine()
        engine.weights = {"price": 0.5}  # 缺 event、macro

        class FakeFetcher:
            def get_daily(self, *a, **k):
                raise RuntimeError("no network")

        engine.fetcher = FakeFetcher()
        engine.event_score = lambda *a, **k: 80
        engine.macro_score = lambda *a, **k: 60
        engine.sector_relative_score = lambda *a, **k: 40

        result = engine.evaluate("601088", ["煤炭"], df=None)
        # 50*0.5 + 80*0.4 + 60*0.2 = 25 + 32 + 12 = 69
        assert result["total"] == 69

    def test_evaluate_all_weight_keys_missing(self):
        """weights 全缺时全部回落默认权重。"""
        engine = SignalEngine()
        engine.weights = {}  # 全缺

        class FakeFetcher:
            def get_daily(self, *a, **k):
                raise RuntimeError("no network")

        engine.fetcher = FakeFetcher()
        engine.event_score = lambda *a, **k: 80
        engine.macro_score = lambda *a, **k: 60
        engine.sector_relative_score = lambda *a, **k: 40

        result = engine.evaluate("601088", ["煤炭"], df=None)
        # 50*0.4 + 80*0.4 + 60*0.2 = 20 + 32 + 12 = 64
        assert result["total"] == 64

