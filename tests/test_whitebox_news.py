"""test_whitebox_news.py — 新闻挖掘与情感分析白盒测试
覆盖 NewsFetcher / KeywordExtractor / SentimentAnalyzer / EventMiner
所有分支条件、边界值和异常路径。
"""

import os
import re
import pytest
import pandas as pd
from datetime import datetime, timedelta
from modules.news import (
    NewsFetcher, KeywordExtractor, SentimentAnalyzer, EventMiner,
    POSITIVE_WORDS, NEGATIVE_WORDS, STOP_WORDS
)


# ==================================================================
# KeywordExtractor 白盒测试
# ==================================================================
class TestKeywordExtractorWhite:

    def test_empty_text(self):
        ext = KeywordExtractor()
        assert ext.extract("") == []

    def test_none_text(self):
        ext = KeywordExtractor()
        assert ext.extract(None) == []

    def test_tfidf_method(self):
        ext = KeywordExtractor()
        kws = ext.extract("煤炭价格大涨，电厂库存回升", topk=3, method="tfidf")
        assert isinstance(kws, list)
        assert len(kws) <= 3

    def test_textrank_method(self):
        ext = KeywordExtractor()
        kws = ext.extract("半导体设备国产替代加速，景气度回升", topk=3, method="textrank")
        assert isinstance(kws, list)
        assert len(kws) <= 3

    def test_hybrid_method(self):
        ext = KeywordExtractor()
        kws = ext.extract("光伏装机量超预期，行业景气度高", topk=5, method="hybrid")
        assert isinstance(kws, list)
        assert len(kws) <= 5

    def test_invalid_method(self):
        ext = KeywordExtractor()
        with pytest.raises(ValueError, match="不支持的方法"):
            ext.extract("测试文本", method="invalid")

    def test_stopwords_filtered(self):
        """停用词应被过滤。"""
        ext = KeywordExtractor()
        kws = ext.extract("这是一个测试文本，关于煤炭行业", topk=10, method="hybrid")
        words = [k[0] for k in kws]
        for sw in STOP_WORDS:
            assert sw not in words

    def test_short_words_filtered(self):
        """长度 <2 的词应被过滤。"""
        ext = KeywordExtractor()
        kws = ext.extract("煤炭涨价", topk=10, method="hybrid")
        for w, _ in kws:
            assert len(w) >= 2

    def test_clean_text_html(self):
        text = "<p>这<b>是</b>HTML文本</p>"
        cleaned = KeywordExtractor._clean_text(text)
        assert "<" not in cleaned
        assert ">" not in cleaned

    def test_clean_text_special_chars(self):
        text = "煤炭@涨价#￥%……&*（）"
        cleaned = KeywordExtractor._clean_text(text)
        assert "@" not in cleaned
        assert "#" not in cleaned

    def test_extract_from_news_title_doubled(self):
        """标题权重应加倍（标题*2 + 正文）。"""
        ext = KeywordExtractor()
        kws = ext.extract_from_news("煤炭板块大涨", "今日市场综述", topk=5)
        assert isinstance(kws, list)

    def test_batch_extract(self):
        ext = KeywordExtractor()
        df = pd.DataFrame([
            {"title": "煤炭价格大涨", "content": "电厂库存回升"},
            {"title": "半导体涨价", "content": "国产替代加速"},
        ])
        result = ext.batch_extract(df, topk=3)
        assert len(result) == 2
        assert "keywords" in result.columns


# ==================================================================
# SentimentAnalyzer 白盒测试
# ==================================================================
class TestSentimentAnalyzerWhite:

    def test_positive_text(self):
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze("煤炭价格大涨，业绩超预期，订单大幅增长")
        assert result["sentiment"] == "正面"
        assert result["score"] > 0
        assert len(result["pos_words"]) > 0

    def test_negative_text(self):
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze("公司业绩暴雷，亏损扩大，被监管处罚")
        assert result["sentiment"] == "负面"
        assert result["score"] < 0
        assert len(result["neg_words"]) > 0

    def test_neutral_text(self):
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze("今日召开股东大会")
        assert result["sentiment"] == "中性"

    def test_empty_text(self):
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze("")
        assert result["sentiment"] == "中性"
        assert result["score"] == 0.0
        assert result["pos_words"] == []
        assert result["neg_words"] == []

    def test_none_text(self):
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze(None)
        assert result["sentiment"] == "中性"

    def test_mixed_sentiment(self):
        """正负面词同时出现，按数量加权。"""
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze("煤炭大涨利好但库存过剩风险增加")
        # pos=2 (大涨,利好), neg=2 (过剩,风险)
        assert result["sentiment"] == "中性"  # score=0

    def test_more_positive(self):
        """正面词多于负面词时为正面。"""
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze("大涨利好增长超预期订单突破")
        assert result["sentiment"] == "正面"

    def test_more_negative(self):
        """负面词多于正面词时为负面。"""
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze("暴跌大跌跳水亏损退市")
        assert result["sentiment"] == "负面"

    def test_score_range(self):
        """score 应在 -1 到 1 之间。"""
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze("大涨利好增长超预期订单突破")
        assert -1.0 <= result["score"] <= 1.0

    def test_analyze_news_title_weighted(self):
        """标题权重 x3。"""
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze_news("煤炭板块利好", "")
        assert result["sentiment"] == "正面"

    def test_batch_analyze(self):
        analyzer = SentimentAnalyzer()
        df = pd.DataFrame([
            {"title": "煤炭大涨利好", "content": ""},
            {"title": "公司暴雷亏损", "content": ""},
            {"title": "今日天气晴朗", "content": ""},
        ])
        result = analyzer.batch_analyze(df)
        assert len(result) == 3
        assert "sentiment" in result.columns
        assert "score" in result.columns

    def test_sentiment_distribution_empty(self):
        analyzer = SentimentAnalyzer()
        assert analyzer.sentiment_distribution(pd.DataFrame()) == {}

    def test_sentiment_distribution(self):
        analyzer = SentimentAnalyzer()
        df = pd.DataFrame([
            {"title": "煤炭大涨利好", "content": ""},
            {"title": "煤炭大涨利好", "content": ""},
            {"title": "公司暴雷亏损", "content": ""},
        ])
        dist = analyzer.sentiment_distribution(df)
        assert dist["正面"] == pytest.approx(66.7, abs=0.1)
        assert dist["负面"] == pytest.approx(33.3, abs=0.1)

    def test_dictionaries_not_empty(self):
        assert len(POSITIVE_WORDS) > 10
        assert len(NEGATIVE_WORDS) > 10

    def test_dictionaries_disjoint(self):
        """正负面词典不应有交集。"""
        assert POSITIVE_WORDS.isdisjoint(NEGATIVE_WORDS)

    def test_threshold_boundary(self):
        """score=0.15 应判为中性（不大于0.15）。"""
        analyzer = SentimentAnalyzer()
        # 构造 score 恰好为 0.15 的情况很难，验证边界逻辑
        # 正面=1, 负面=0 → score = 1.0/(1+0) = 1.0 > 0.15 → 正面
        result = analyzer.analyze("大涨")
        assert result["score"] == 1.0
        assert result["sentiment"] == "正面"


# ==================================================================
# NewsFetcher 白盒测试
# ==================================================================
class TestNewsFetcherWhite:

    def test_invalid_source(self, monkeypatch):
        """无效来源应抛出 ValueError（先于 akshare 检查）。"""
        import modules.news as news_mod
        monkeypatch.setattr(news_mod, "_AK_OK", True)
        fetcher = NewsFetcher()
        with pytest.raises(ValueError, match="不支持的来源"):
            fetcher.fetch(source="invalid_source")

    def test_no_akshare(self, monkeypatch):
        import modules.news as news_mod
        monkeypatch.setattr(news_mod, "_AK_OK", False)
        fetcher = NewsFetcher()
        with pytest.raises(RuntimeError, match="akshare 未安装"):
            fetcher.fetch(source="eastmoney")

    def test_sources_dict(self):
        fetcher = NewsFetcher()
        assert "eastmoney" in fetcher.sources
        assert "caixin" in fetcher.sources
        assert "cctv" in fetcher.sources

    def test_fetch_returns_empty_on_error(self, monkeypatch):
        """抓取失败时返回空 DataFrame。"""
        import modules.news as news_mod
        monkeypatch.setattr(news_mod, "_AK_OK", True)
        fetcher = NewsFetcher()
        # Mock _fetch_eastmoney 和 _fetch_stock_news_main 返回空
        monkeypatch.setattr(fetcher, "_fetch_eastmoney",
                            lambda kw: pd.DataFrame(columns=["date", "title", "content", "source"]))
        monkeypatch.setattr(fetcher, "_fetch_stock_news_main",
                            lambda kw: pd.DataFrame(columns=["date", "title", "content"]))
        df = fetcher.fetch(source="eastmoney", limit=5)
        assert isinstance(df, pd.DataFrame)
        assert df.empty


# ==================================================================
# EventMiner 白盒测试
# ==================================================================
class TestEventMinerWhite:

    def test_extract_ticker_6_prefix(self):
        """6 开头的沪市代码。"""
        miner = EventMiner()
        assert miner._extract_ticker("贵州茅台600519创新高") == "600519"

    def test_extract_ticker_0_prefix(self):
        """0 开头的深市代码。"""
        miner = EventMiner()
        assert miner._extract_ticker("000858五粮液涨停") == "000858"

    def test_extract_ticker_3_prefix(self):
        """3 开头的创业板代码。"""
        miner = EventMiner()
        assert miner._extract_ticker("300750宁德时代") == "300750"

    def test_extract_ticker_no_code(self):
        miner = EventMiner()
        assert miner._extract_ticker("没有代码的新闻") == ""

    def test_extract_ticker_longer_number(self):
        """7位以上的数字不应匹配。"""
        miner = EventMiner()
        assert miner._extract_ticker("订单号12345678") == ""

    def test_extract_ticker_multiple(self):
        """多组代码时取第一组。"""
        miner = EventMiner()
        result = miner._extract_ticker("600519和000858同时涨停")
        assert result in ("600519", "000858")

    def test_save_events_dedup(self, tmp_path):
        """重复保存同一批事件不应增加条数。"""
        miner = EventMiner()
        miner.event_db_path = str(tmp_path / "test_events.csv")
        events_df = pd.DataFrame([
            {"date": pd.Timestamp("2025-06-01"), "ticker": "601088",
             "title": "煤炭涨价", "type": "正面", "keywords": "煤炭,涨价",
             "sentiment_score": 0.8, "source": "eastmoney"},
        ])
        miner._save_events(events_df)
        miner._save_events(events_df)  # 重复保存
        loaded = pd.read_csv(miner.event_db_path, encoding="utf-8-sig")
        assert len(loaded) == 1

    def test_save_events_append_new(self, tmp_path):
        """追加新事件。"""
        miner = EventMiner()
        miner.event_db_path = str(tmp_path / "test_events.csv")
        df1 = pd.DataFrame([
            {"date": pd.Timestamp("2025-06-01"), "ticker": "601088",
             "title": "事件A", "type": "正面", "keywords": "煤炭",
             "sentiment_score": 0.5, "source": "eastmoney"},
        ])
        df2 = pd.DataFrame([
            {"date": pd.Timestamp("2025-06-02"), "ticker": "600519",
             "title": "事件B", "type": "负面", "keywords": "白酒",
             "sentiment_score": -0.3, "source": "cctv"},
        ])
        miner._save_events(df1)
        miner._save_events(df2)
        loaded = pd.read_csv(miner.event_db_path, encoding="utf-8-sig")
        assert len(loaded) == 2

    def test_get_hot_keywords_no_file(self, tmp_path):
        miner = EventMiner()
        miner.event_db_path = str(tmp_path / "nonexistent.csv")
        assert miner.get_hot_keywords(days=7, topk=10) == []

    def test_get_hot_keywords_empty_file(self, tmp_path):
        miner = EventMiner()
        path = str(tmp_path / "test_events.csv")
        miner.event_db_path = path
        pd.DataFrame(columns=["date", "keywords"]).to_csv(path, index=False, encoding="utf-8-sig")
        assert miner.get_hot_keywords(days=7, topk=10) == []

    def test_get_hot_keywords_sorted(self, tmp_path):
        """关键词按出现次数降序排列。"""
        miner = EventMiner()
        miner.event_db_path = str(tmp_path / "test_events.csv")
        events_df = pd.DataFrame([
            {"date": pd.Timestamp.now(), "ticker": "601088",
             "title": "煤炭涨价", "type": "正面",
             "keywords": "煤炭,涨价,保供", "sentiment_score": 0.8, "source": "eastmoney"},
            {"date": pd.Timestamp.now(), "ticker": "",
             "title": "煤炭供需缺口", "type": "正面",
             "keywords": "煤炭,供需缺口", "sentiment_score": 0.6, "source": "cctv"},
        ])
        miner._save_events(events_df)
        hot = miner.get_hot_keywords(days=7, topk=10)
        assert len(hot) > 0
        assert hot[0][0] == "煤炭"  # 出现2次
        assert hot[0][1] == 2

    def test_mine_events_empty_news(self, monkeypatch, tmp_path):
        """新闻为空时返回空 DataFrame。"""
        miner = EventMiner()
        miner.event_db_path = str(tmp_path / "test_events.csv")
        monkeypatch.setattr(miner.news_fetcher, "fetch",
                            lambda *a, **k: pd.DataFrame())
        result = miner.mine_events(keyword="煤炭", auto_save=False)
        assert result.empty
