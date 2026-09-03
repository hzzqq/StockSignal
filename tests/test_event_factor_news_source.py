# -*- coding: utf-8 -*-
"""事件因子「第二真实源：东方财富新闻」单元测试。

锁死：event_factor.news_event_signal 用真实 NewsFetcher + SentimentAnalyzer，
绝不造数；get_event_factor 在 P1 无信号时优雅回退到该真实新闻源。
全部用例用假 fetcher/analyzer 注入，**不触网**，保证离线可回归。
"""
import pandas as pd
import pytest

import modules.news as news_mod
import modules.event_factor as ef


class FakeNewsFetcher:
    """可注入：按构造时给定的「新闻」DataFrame 返回。"""

    def __init__(self, df):
        self._df = df

    def fetch(self, keyword=None, source="eastmoney", limit=15):
        return self._df


class FakeSentiment:
    def __init__(self, dist):
        self._dist = dist

    def sentiment_distribution(self, news):
        return self._dist


SOME_NEWS = pd.DataFrame({
    "title": ["利好公告A", "利空公告B", "中性报道C"],
    "content": ["", "", ""],
})


@pytest.fixture
def patch_news(monkeypatch):
    """默认注入「有新闻 + 80% 正面」的假源。返回可直接改的引用。"""
    fetcher = FakeNewsFetcher(SOME_NEWS)
    analyzer = FakeSentiment({"正面": 80.0, "负面": 20.0, "中性": 0.0})
    monkeypatch.setattr(news_mod, "NewsFetcher", lambda: fetcher)
    monkeypatch.setattr(news_mod, "SentimentAnalyzer", lambda: analyzer)
    return fetcher, analyzer


def test_news_event_signal_available(patch_news):
    out = ef.news_event_signal("sh600519")
    assert out["available"] is True
    # 50 + (80-20)*0.6 = 86
    assert out["score"] == 86.0
    assert out["rank"] == pytest.approx(0.86)
    assert out["signal"] == "看多"
    assert out["source"] == "eastmoney-news"


def test_news_event_signal_empty(patch_news, monkeypatch):
    monkeypatch.setattr(news_mod, "NewsFetcher",
                        lambda: FakeNewsFetcher(pd.DataFrame(columns=["title"])))
    out = ef.news_event_signal("sh600519")
    assert out["available"] is False
    assert "无相关东方财富新闻" in out["reason"]


def test_news_event_signal_fetch_error(patch_news, monkeypatch):
    class Boom:
        def fetch(self, *a, **k):
            raise RuntimeError("network down")
    monkeypatch.setattr(news_mod, "NewsFetcher", Boom)
    out = ef.news_event_signal("sh600519")
    assert out["available"] is False
    assert "新闻抓取失败" in out["reason"]


def test_news_event_signal_sentiment_error(patch_news, monkeypatch):
    class BoomSA:
        def sentiment_distribution(self, news):
            raise RuntimeError("analyze fail")
    monkeypatch.setattr(news_mod, "SentimentAnalyzer", BoomSA)
    out = ef.news_event_signal("sh600519")
    assert out["available"] is False
    assert "情感分析失败" in out["reason"]


def test_news_event_signal_empty_ticker(patch_news):
    out = ef.news_event_signal("")
    assert out["available"] is False
    assert "未提供标的代码" in out["reason"]


# ── get_event_factor 回退到新闻源 的接线测试 ──
class FakeP1Loader:
    """available_models 有 ev，但该 symbol 不在任何榜 / daily 也为空 → 触发新闻回退。"""

    def available_models(self):
        return ["ev"]

    def top_long(self, model, top_n=None):
        return []

    def top_short(self, model, top_n=None):
        return []

    def daily_df(self, model):
        # 空 DataFrame（无该 symbol）→ sub 为空，跳过精确路径
        return pd.DataFrame(columns=["symbol", "date", "score", "signal"])


def test_get_event_factor_falls_back_to_news(patch_news, monkeypatch):
    import modules.p1_signal as p1
    monkeypatch.setattr(p1, "P1SignalLoader", lambda *a, **k: FakeP1Loader())
    out = ef.get_event_factor("sh600519")
    assert out["available"] is True
    assert out["source"] == "eastmoney-news"
    assert out["score"] == 86.0


def test_get_event_factor_no_p1_no_news(monkeypatch):
    """P1 无信号且新闻也为空 → available=False（绝不造数）。"""
    import modules.p1_signal as p1
    monkeypatch.setattr(p1, "P1SignalLoader", lambda *a, **k: FakeP1Loader())
    monkeypatch.setattr(news_mod, "NewsFetcher",
                        lambda: FakeNewsFetcher(pd.DataFrame(columns=["title"])))
    monkeypatch.setattr(news_mod, "SentimentAnalyzer",
                        lambda: FakeSentiment({"正面": 0, "负面": 0, "中性": 0}))
    out = ef.get_event_factor("sh600519")
    assert out["available"] is False
    assert "无 P1 事件因子信号" in out["reason"]
