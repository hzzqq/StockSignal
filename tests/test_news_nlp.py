"""锁定 _news_nlp 的清洗 / 去重 / 情感 / 摘要纯逻辑（防回归）。

聚焦不依赖外部 NLP 库（jieba/snownlp 装否都不影响）的确定性逻辑：
文本清洗、Jaccard 相似度、指纹、去重、情感词典判定、摘要统计。
此前无单测。
"""
import pandas as pd

import modules._news_nlp as nlp


def test_clean_text():
    assert nlp.KeywordExtractor._clean_text("<b>苹果</b>大涨!") == "苹果大涨"
    assert "  " not in nlp.KeywordExtractor._clean_text("a   b\nc")


def test_jaccard():
    assert nlp.NewsDeduplicator._jaccard_similarity("abc", "abc") == 1.0
    assert nlp.NewsDeduplicator._jaccard_similarity("abc", "xyz") == 0.0
    assert nlp.NewsDeduplicator._jaccard_similarity("", "abc") == 0.0


def test_fingerprint_distinct():
    a = nlp.NewsDeduplicator._fingerprint("公司A发布新品")
    b = nlp.NewsDeduplicator._fingerprint("公司B发布新品")
    assert a != b
    assert nlp.NewsDeduplicator._fingerprint("同一标题") == \
        nlp.NewsDeduplicator._fingerprint("同一标题")


def test_deduplicate_identical():
    df = pd.DataFrame({"title": ["新闻A", "新闻A", "新闻B"], "date": ["d1", "d2", "d3"]})
    out = nlp.NewsDeduplicator().deduplicate(df)
    assert len(out) == 2
    assert set(out["title"]) == {"新闻A", "新闻B"}


def test_deduplicate_empty():
    df = pd.DataFrame(columns=["title", "date"])
    out = nlp.NewsDeduplicator().deduplicate(df)
    assert out.equals(df)


def test_sentiment_analyze_empty():
    r = nlp.SentimentAnalyzer().analyze("")
    assert r["sentiment"] == "中性"
    assert r["score"] == 0.0
    assert r["level"] == "中性"          # T-287：空文本五档归中性


def test_sentiment_positive_negative():
    pos = nlp.SentimentAnalyzer().analyze("公司净利润大幅增长，业绩亮眼")
    assert pos["sentiment"] == "正面"
    neg = nlp.SentimentAnalyzer().analyze("业绩暴雷，股价暴跌，巨亏")
    assert neg["sentiment"] == "负面"
    # T-287 五档：单边净差拉满 → 「大」
    assert pos["level"] == "大利好"
    assert neg["level"] == "大利空"


def test_sentiment_level_grades():
    """T-287 五档判定：混合情绪净差小 → 「小」档（score 落 ±0.15~±0.4 带）。"""
    small_pos = nlp.SentimentAnalyzer().analyze("公司获得大单，产品涨价，但库存积压")
    assert small_pos["sentiment"] == "正面"
    assert small_pos["level"] == "小利好"     # 2 好 1 坏 → raw≈0.33
    small_neg = nlp.SentimentAnalyzer().analyze("公司获得订单，但库存积压，需求疲软")
    assert small_neg["sentiment"] == "负面"
    assert small_neg["level"] == "小利空"     # 1 好 2 坏 → raw≈-0.33


def test_batch_analyze_carries_level():
    """batch_analyze DataFrame 自动携带 level 列（下游展示直接可用）。"""
    df = pd.DataFrame({"title": ["业绩暴雷，股价暴跌"], "date": ["2026-10-15"]})
    out = nlp.SentimentAnalyzer().batch_analyze(df)
    assert "level" in out.columns
    assert out.iloc[0]["level"] == "大利空"


def test_sentiment_intensity():
    base = nlp.SentimentAnalyzer().analyze("公司增长")
    strong = nlp.SentimentAnalyzer().analyze("公司大幅增长")
    assert abs(strong["score"]) >= abs(base["score"])


def test_generate_summary_empty():
    r = nlp.NewsSummarizer.generate_summary(pd.DataFrame(columns=["title", "date"]))
    assert r["total"] == 0
    assert r["major_events"] == []


def test_generate_summary_stats():
    df = pd.DataFrame({
        "title": ["净利润大幅增长", "业绩暴雷暴跌", "公司宣布分红计划"],
        "date": ["2026-08-01", "2026-08-02", "2026-08-03"],
    })
    r = nlp.NewsSummarizer.generate_summary(df)
    assert r["total"] == 3
    assert r["key_stats"]["positive"] == 1
    assert r["key_stats"]["negative"] == 1
    assert r["key_stats"]["neutral"] == 1
