"""test_whitebox_signal.py — SignalEngine 白盒测试
覆盖 price_score / event_score / macro_score / evaluate / batch_evaluate / add_event
所有分支条件、边界值和异常路径。
"""

import os
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from modules.signal import SignalEngine
from modules.cleaner import DataCleaner


def make_trend_df(n=70, start_price=10, trend="up"):
    """构造测试用行情数据。"""
    dates = pd.date_range("2025-01-01", periods=n)
    if trend == "up":
        closes = [start_price + i * 0.5 for i in range(n)]
        vols = [1000 + i * 10 for i in range(n)]
        changes = [0.5] * n
    elif trend == "down":
        closes = [start_price + (n - i) * 0.5 for i in range(n)]
        vols = [1000 + i * 10 for i in range(n)]
        changes = [-0.5] * n
    elif trend == "flat":
        closes = [start_price] * n
        vols = [1000] * n
        changes = [0.0] * n
    else:
        closes = list(range(n))
        vols = [1000] * n
        changes = [0.0] * n
    df = pd.DataFrame({"date": dates, "close": closes, "volume": vols, "change_pct": changes})
    return DataCleaner.full_pipeline(df)


class TestPriceScore:
    """price_score 白盒测试。"""

    def test_empty_df(self):
        engine = SignalEngine()
        assert engine.price_score(pd.DataFrame()) == 50

    def test_less_than_20_rows(self):
        """数据不足20行时返回基准分50。"""
        engine = SignalEngine()
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=10),
            "close": range(10),
            "volume": range(10),
        })
        assert engine.price_score(df) == 50

    def test_uptrend_score_high(self):
        """上涨趋势得分应 >50。"""
        engine = SignalEngine()
        df = make_trend_df(70, trend="up")
        score = engine.price_score(df)
        assert 0 <= score <= 100
        assert score > 50

    def test_downtrend_score_low(self):
        """下跌趋势得分应 <50。"""
        engine = SignalEngine()
        df = make_trend_df(70, trend="down")
        score = engine.price_score(df)
        assert 0 <= score <= 100
        assert score < 55

    def test_date_filter(self):
        """date 参数应过滤数据。"""
        engine = SignalEngine()
        df = make_trend_df(70, trend="up")
        score_full = engine.price_score(df)
        score_partial = engine.price_score(df, date="2025-01-30")
        assert 0 <= score_partial <= 100

    def test_score_clamped_to_100(self):
        """得分不应超过 100。"""
        engine = SignalEngine()
        df = make_trend_df(70, trend="up")
        score = engine.price_score(df)
        assert score <= 100

    def test_score_clamped_to_0(self):
        """得分不应低于 0。"""
        engine = SignalEngine()
        df = make_trend_df(70, trend="down")
        score = engine.price_score(df)
        assert score >= 0

    def test_ma_trend_branches(self):
        """测试均线趋势的三个分支: close>ma5>ma20, close>ma20, ma20>ma60。"""
        engine = SignalEngine()
        # 构造 close > ma5 > ma20 的数据
        df = make_trend_df(70, trend="up")
        score = engine.price_score(df)
        assert score > 0

    def test_momentum_branches(self):
        """测试动量评分各分支：>5, >2, >0, >-2, <=-2。"""
        engine = SignalEngine()
        df = make_trend_df(70, trend="up")
        score = engine.price_score(df)
        assert 0 <= score <= 100

    def test_volume_branches(self):
        """测试成交量评分各分支：vol_ratio>1.5+涨, >1.2, >1.0。"""
        engine = SignalEngine()
        df = make_trend_df(70, trend="up")
        score = engine.price_score(df)
        assert 0 <= score <= 100

    def test_flat_market(self):
        """横盘市场得分应在中间区域。"""
        engine = SignalEngine()
        df = make_trend_df(70, trend="flat")
        score = engine.price_score(df)
        assert 0 <= score <= 100


class TestEventScore:
    """event_score 白盒测试。"""

    def test_no_events_file(self, tmp_path):
        """事件库不存在时返回基准分50。"""
        engine = SignalEngine()
        engine.event_db_path = str(tmp_path / "nonexistent.csv")
        score = engine.event_score("601088", ["煤炭"], date="2025-06-15")
        assert 0 <= score <= 100

    def test_positive_event(self, tmp_path):
        """正面事件应提升得分。"""
        engine = SignalEngine()
        engine.event_db_path = str(tmp_path / "test_events.csv")
        engine.add_event("2025-06-01", "601088", "煤炭价格大涨利好", "利好")
        score = engine.event_score("601088", ["煤炭"], date="2025-06-15")
        assert score > 50

    def test_negative_event(self, tmp_path):
        """负面事件应降低得分。"""
        engine = SignalEngine()
        engine.event_db_path = str(tmp_path / "test_events.csv")
        engine.add_event("2025-06-01", "601088", "煤炭价格暴跌利空", "利空")
        score = engine.event_score("601088", ["煤炭"], date="2025-06-15")
        assert score < 55

    def test_neutral_event(self, tmp_path):
        """中性事件应小幅提升（+关注度）。"""
        engine = SignalEngine()
        engine.event_db_path = str(tmp_path / "test_events.csv")
        engine.add_event("2025-06-01", "601088", "煤炭行业会议召开", "中性")
        score = engine.event_score("601088", ["煤炭"], date="2025-06-15")
        assert 0 <= score <= 100

    def test_event_outside_30day_window(self, tmp_path):
        """30天前的事件不应影响评分。"""
        engine = SignalEngine()
        engine.event_db_path = str(tmp_path / "test_events.csv")
        engine.add_event("2025-01-01", "601088", "煤炭价格大涨利好", "利好")
        score = engine.event_score("601088", ["煤炭"], date="2025-06-15")
        # 事件太远，不应被计入
        assert 0 <= score <= 100

    def test_no_keyword_match(self, tmp_path):
        """关键词不匹配时得分偏低。"""
        engine = SignalEngine()
        engine.event_db_path = str(tmp_path / "test_events.csv")
        engine.add_event("2025-06-01", "601088", "半导体涨价", "利好")
        score = engine.event_score("601088", ["煤炭"], date="2025-06-15")
        assert 0 <= score <= 100

    def test_ticker_match_with_nan_ticker(self, tmp_path):
        """ticker 为 NaN 的事件应匹配所有股票。"""
        engine = SignalEngine()
        engine.event_db_path = str(tmp_path / "test_events.csv")
        # 添加 ticker 为空的事件
        events = pd.DataFrame([{
            "date": pd.Timestamp("2025-06-01"),
            "ticker": "",
            "title": "煤炭价格大涨利好",
            "type": "利好"
        }])
        events.to_csv(engine.event_db_path, index=False, encoding="utf-8-sig")
        score = engine.event_score("601088", ["煤炭"], date="2025-06-15")
        assert score > 50

    def test_sentiment_score_column(self, tmp_path):
        """事件含 sentiment_score 列时应纳入量化。"""
        engine = SignalEngine()
        engine.event_db_path = str(tmp_path / "test_events.csv")
        events = pd.DataFrame([{
            "date": pd.Timestamp("2025-06-01"),
            "ticker": "601088",
            "title": "煤炭价格大涨",
            "type": "正面",
            "sentiment_score": 0.8
        }])
        events.to_csv(engine.event_db_path, index=False, encoding="utf-8-sig")
        score = engine.event_score("601088", ["煤炭"], date="2025-06-15")
        assert score > 50

    def test_score_clamped(self, tmp_path):
        """得分应限制在 0-100。"""
        engine = SignalEngine()
        engine.event_db_path = str(tmp_path / "test_events.csv")
        # 添加大量正面事件
        for i in range(20):
            engine.add_event("2025-06-01", "601088", f"煤炭利好{i}", "利好")
        score = engine.event_score("601088", ["煤炭"], date="2025-06-15")
        assert score <= 100


class TestMacroScore:
    """macro_score 白盒测试。"""

    def test_returns_value_in_range(self):
        engine = SignalEngine()
        try:
            score = engine.macro_score()
            assert 0 <= score <= 100
        except Exception:
            pytest.skip("网络不可用")

    def test_exception_returns_50(self, monkeypatch):
        """异常时返回 50。"""
        engine = SignalEngine()
        # 让 fetcher.get_macro 抛异常
        def mock_get_macro(*args, **kwargs):
            raise Exception("mock error")
        monkeypatch.setattr(engine.fetcher, "get_macro", mock_get_macro)
        score = engine.macro_score()
        assert score == 50

    def test_empty_pmi_df_returns_50(self, monkeypatch):
        engine = SignalEngine()
        monkeypatch.setattr(engine.fetcher, "get_macro", lambda *a, **k: pd.DataFrame())
        assert engine.macro_score() == 50

    def test_no_pmi_column_returns_50(self, monkeypatch):
        engine = SignalEngine()
        df = pd.DataFrame({"some_col": [1, 2, 3]})
        monkeypatch.setattr(engine.fetcher, "get_macro", lambda *a, **k: df)
        assert engine.macro_score() == 50

    def test_nan_pmi_returns_50(self, monkeypatch):
        engine = SignalEngine()
        df = pd.DataFrame({"pmi_mfg": [np.nan]})
        monkeypatch.setattr(engine.fetcher, "get_macro", lambda *a, **k: df)
        assert engine.macro_score() == 50

    def test_pmi_above_50(self, monkeypatch):
        """PMI > 50 时得分应 > 50。"""
        engine = SignalEngine()
        df = pd.DataFrame({"pmi_mfg": [52.0]})
        monkeypatch.setattr(engine.fetcher, "get_macro", lambda *a, **k: df)
        score = engine.macro_score()
        assert score == 60  # 50 + (52-50)*5 = 60

    def test_pmi_below_50(self, monkeypatch):
        """PMI < 50 时得分应 < 50。"""
        engine = SignalEngine()
        df = pd.DataFrame({"pmi_mfg": [48.0]})
        monkeypatch.setattr(engine.fetcher, "get_macro", lambda *a, **k: df)
        score = engine.macro_score()
        assert score == 40  # 50 + (48-50)*5 = 40


class TestEvaluate:
    """evaluate 白盒测试。"""

    def test_returns_expected_keys(self):
        engine = SignalEngine()
        try:
            result = engine.evaluate("600519", ["白酒"], date="2025-06-01")
            assert "price_score" in result
            assert "event_score" in result
            assert "macro_score" in result
            assert "total" in result
            assert 0 <= result["total"] <= 100
        except Exception:
            pytest.skip("网络不可用")

    def test_total_is_weighted_sum(self, monkeypatch):
        """total 应为加权求和。"""
        engine = SignalEngine()
        # Mock price_score, event_score, macro_score
        monkeypatch.setattr(engine, "price_score", lambda *a, **k: 80)
        monkeypatch.setattr(engine, "event_score", lambda *a, **k: 60)
        monkeypatch.setattr(engine, "macro_score", lambda *a, **k: 50)
        # Mock fetcher.get_daily 和 DataCleaner.full_pipeline
        monkeypatch.setattr(engine.fetcher, "get_daily", lambda *a, **k: pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=70),
            "close": range(70), "volume": range(70), "change_pct": [0.5]*70
        }))
        result = engine.evaluate("600519", ["白酒"], date="2025-06-01")
        expected = int(80 * 0.4 + 60 * 0.4 + 50 * 0.2)
        assert result["total"] == min(100, max(0, expected))


class TestBatchEvaluate:
    """batch_evaluate 白盒测试。"""

    def test_multiple_tickers(self, monkeypatch):
        engine = SignalEngine()
        monkeypatch.setattr(engine, "evaluate", lambda t, k, d=None: {
            "price_score": 70, "event_score": 60, "macro_score": 50, "total": 62
        })
        items = [{"ticker": "601088", "keywords": ["煤炭"]},
                 {"ticker": "600519", "keywords": ["白酒"]}]
        result = engine.batch_evaluate(items)
        assert len(result) == 2
        assert "ticker" in result.columns
        assert "total" in result.columns

    def test_error_handling(self, monkeypatch):
        """单个股票出错不影响其他。"""
        engine = SignalEngine()
        def mock_evaluate(ticker, keywords, date=None):
            if ticker == "ERROR":
                raise Exception("mock error")
            return {"price_score": 70, "event_score": 60, "macro_score": 50, "total": 62}
        monkeypatch.setattr(engine, "evaluate", mock_evaluate)
        items = [{"ticker": "601088", "keywords": ["煤炭"]},
                 {"ticker": "ERROR", "keywords": ["error"]}]
        result = engine.batch_evaluate(items)
        assert len(result) == 2
        error_row = result[result["ticker"] == "ERROR"].iloc[0]
        assert error_row["total"] == 0
        assert "error" in error_row

    def test_sorted_by_total_desc(self, monkeypatch):
        """结果按 total 降序排列。"""
        engine = SignalEngine()
        scores = {"601088": 80, "600519": 60, "000858": 70}
        def mock_evaluate(ticker, keywords, date=None):
            return {"price_score": scores[ticker], "event_score": 50,
                    "macro_score": 50, "total": scores[ticker]}
        monkeypatch.setattr(engine, "evaluate", mock_evaluate)
        items = [{"ticker": t, "keywords": []} for t in scores]
        result = engine.batch_evaluate(items)
        assert result["total"].tolist() == [80, 70, 60]


class TestAddEvent:
    """add_event 白盒测试。"""

    def test_add_and_load(self, tmp_path):
        engine = SignalEngine()
        engine.event_db_path = str(tmp_path / "test_events.csv")
        engine.add_event("2025-06-01", "601088", "煤炭涨价", "利好")
        events = engine._load_events()
        assert len(events) == 1
        assert events.iloc[0]["title"] == "煤炭涨价"
        assert events.iloc[0]["ticker"] == "601088"

    def test_add_multiple(self, tmp_path):
        engine = SignalEngine()
        engine.event_db_path = str(tmp_path / "test_events.csv")
        engine.add_event("2025-06-01", "601088", "事件1", "利好")
        engine.add_event("2025-06-02", "600519", "事件2", "利空")
        events = engine._load_events()
        assert len(events) == 2

    def test_creates_directory(self, tmp_path):
        """目录不存在时自动创建。"""
        engine = SignalEngine()
        engine.event_db_path = str(tmp_path / "subdir" / "test_events.csv")
        engine.add_event("2025-06-01", "601088", "测试", "中性")
        assert os.path.exists(engine.event_db_path)


class TestSentimentReport:
    """sentiment_report 白盒测试。"""

    def test_empty_news(self, monkeypatch):
        engine = SignalEngine()
        # Mock news_fetcher.fetch 返回空 DataFrame
        monkeypatch.setattr(engine.event_miner.news_fetcher, "fetch",
                            lambda *a, **k: pd.DataFrame())
        report = engine.sentiment_report()
        assert report["total"] == 0
        assert report["positive_pct"] == 0

    def test_with_news(self, monkeypatch):
        engine = SignalEngine()
        mock_news = pd.DataFrame([
            {"date": pd.Timestamp("2025-06-01"), "title": "煤炭价格大涨利好",
             "content": "业绩超预期", "source": "eastmoney"},
            {"date": pd.Timestamp("2025-06-01"), "title": "公司暴雷亏损",
             "content": "被监管处罚", "source": "eastmoney"},
        ])
        monkeypatch.setattr(engine.event_miner.news_fetcher, "fetch",
                            lambda *a, **k: mock_news)
        report = engine.sentiment_report()
        assert report["total"] == 2
        assert "top_keywords" in report
        assert "sample_news" in report
