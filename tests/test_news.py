"""test_news.py — 新闻挖掘与情感分析模块测试"""

import pytest
import pandas as pd
from modules.news import (
    NewsFetcher, KeywordExtractor, SentimentAnalyzer, EventMiner,
    POSITIVE_WORDS, NEGATIVE_WORDS
)


class TestKeywordExtractor:

    def test_extract_basic(self):
        extractor = KeywordExtractor()
        text = "煤炭价格大涨，电厂库存回升，保供政策利好煤炭板块"
        kws = extractor.extract(text, topk=5)
        assert isinstance(kws, list)
        assert len(kws) <= 5

    def test_extract_hybrid(self):
        extractor = KeywordExtractor()
        text = "半导体设备国产替代加速，MLCC涨价供需缺口扩大，景气度持续回升"
        kws = extractor.extract(text, topk=8, method="hybrid")
        assert len(kws) <= 8

    def test_extract_from_news(self):
        extractor = KeywordExtractor()
        title = "光伏装机量超预期 行业景气度高"
        content = "2025年光伏新增装机大幅增长，产业链供需两旺"
        kws = extractor.extract_from_news(title, content, topk=5)
        assert isinstance(kws, list)

    def test_clean_text(self):
        text = "<p>这<b>是</b>一段HTML文本。</p>"
        cleaned = KeywordExtractor._clean_text(text)
        assert "<" not in cleaned
        assert ">" not in cleaned


class TestSentimentAnalyzer:

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
        result = analyzer.analyze("今天天气不错")
        assert result["sentiment"] == "中性"

    def test_empty_text(self):
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze("")
        assert result["sentiment"] == "中性"
        assert result["score"] == 0

    def test_analyze_news_title_weighted(self):
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze_news("煤炭板块利好", "")
        assert result["sentiment"] == "正面"

    def test_dictionaries_not_empty(self):
        assert len(POSITIVE_WORDS) > 10
        assert len(NEGATIVE_WORDS) > 10

    def test_batch_analyze(self):
        analyzer = SentimentAnalyzer()
        df = pd.DataFrame([
            {"title": "煤炭价格大涨利好", "content": ""},
            {"title": "公司暴雷亏损", "content": ""},
            {"title": "今日天气晴朗", "content": ""},
        ])
        result = analyzer.batch_analyze(df)
        assert len(result) == 3
        assert "sentiment" in result.columns


class TestEventMiner:

    def test_extract_ticker(self, tmp_path):
        miner = EventMiner()
        assert miner._extract_ticker("贵州茅台600519创新高") == "600519"
        assert miner._extract_ticker("000858五粮液涨停") == "000858"
        assert miner._extract_ticker("300750宁德时代") == "300750"
        assert miner._extract_ticker("没有代码的新闻") == ""

    def test_save_and_load_events(self, tmp_path):
        miner = EventMiner()
        miner.event_db_path = str(tmp_path / "test_events.csv")

        events_df = pd.DataFrame([
            {"date": pd.Timestamp("2025-06-01"), "ticker": "601088",
             "title": "煤炭涨价", "type": "正面", "keywords": "煤炭,涨价",
             "sentiment_score": 0.8, "source": "eastmoney"},
            {"date": pd.Timestamp("2025-06-02"), "ticker": "",
             "title": "PMI超预期", "type": "正面", "keywords": "PMI,宏观",
             "sentiment_score": 0.6, "source": "cctv"},
        ])
        miner._save_events(events_df)

        # 验证保存
        import os
        assert os.path.exists(miner.event_db_path)

        # 验证去重追加
        dup_df = events_df.copy()
        miner._save_events(dup_df)
        loaded = pd.read_csv(miner.event_db_path, encoding="utf-8-sig")
        assert len(loaded) == 2  # 去重后仍为2条

    def test_get_hot_keywords(self, tmp_path):
        miner = EventMiner()
        miner.event_db_path = str(tmp_path / "test_events.csv")

        events_df = pd.DataFrame([
            {"date": pd.Timestamp.now(), "ticker": "601088",
             "title": "煤炭涨价", "type": "正面", "keywords": "煤炭,涨价,保供",
             "sentiment_score": 0.8, "source": "eastmoney"},
            {"date": pd.Timestamp.now(), "ticker": "",
             "title": "煤炭供需缺口", "type": "正面", "keywords": "煤炭,供需缺口",
             "sentiment_score": 0.6, "source": "cctv"},
        ])
        miner._save_events(events_df)

        hot = miner.get_hot_keywords(days=7, topk=10)
        assert len(hot) > 0
        # "煤炭"出现2次，应排第一
        assert hot[0][0] == "煤炭"
        assert hot[0][1] == 2


class TestNewsFetcher:

    def test_fetch_offline(self):
        """测试无网络时的容错。"""
        fetcher = NewsFetcher()
        try:
            df = fetcher.fetch(keyword="煤炭", source="eastmoney", limit=5)
            assert isinstance(df, pd.DataFrame)
        except Exception:
            pytest.skip("网络不可用，跳过")
