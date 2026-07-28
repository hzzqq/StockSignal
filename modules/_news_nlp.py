# ── 依赖 _news_io 中定义的标志/常量/日志器 ──
from modules._news_io import (                  # noqa: F401
    logger, _JIEBA_OK, _SNOW_OK,
    POSITIVE_WORDS, NEGATIVE_WORDS, STOP_WORDS,
)

# ── NLP 库（仅本文件内的分析类使用）──
import hashlib
import re
from collections import Counter

import pandas as pd

try:
    import jieba
    import jieba.analyse
except ImportError:
    jieba = None  # type: ignore[assignment]

try:
    from snownlp import SnowNLP
except ImportError:
    SnowNLP = None  # type: ignore[assignment]

class KeywordExtractor:
    """关键词提取器（jieba TF-IDF + TextRank 融合）。"""

    DOMAIN_WORDS = [
        "事件驱动", "主线", "顺周期", "景气度", "供需缺口", "产能利用率",
        "渗透率", "国产替代", "专精特新", "碳中和", "新能源", "半导体",
        "光伏", "储能", "锂电", "煤炭", "有色", "化工", "军工", "消费",
        "医药", "房地产", "银行", "券商", "保险", "MLCC", "存储芯片",
        "动力电池", "稀土", "螺纹钢", "原油", "天然气",
        # 补充半导体领域词
        "晶圆代工", "先进封装", "Chiplet", "HBM", "CPO",
        "光刻机", "刻蚀机", "薄膜沉积", "CMP", "国产化率",
        "功率半导体", "碳化硅", "氮化镓", "IGBT", "MOSFET",
        "存储芯片", "MCU", "GPU", "FPGA", "SoC",
        "模拟芯片", "射频芯片", "电源管理", "CIS", "MEMS",
    ]

    def __init__(self):
        if _JIEBA_OK:
            for w in self.DOMAIN_WORDS:
                jieba.add_word(w)

    def extract(self, text, topk=8, method="hybrid"):
        if not text or not _JIEBA_OK:
            return []
        text = self._clean_text(text)
        if method == "tfidf":
            return jieba.analyse.extract_tags(text, topK=topk, withWeight=True)
        elif method == "textrank":
            return jieba.analyse.textrank(text, topK=topk, withWeight=True)
        elif method == "hybrid":
            tfidf = dict(jieba.analyse.extract_tags(text, topK=topk * 2, withWeight=True))
            textrank = dict(jieba.analyse.textrank(text, topK=topk * 2, withWeight=True))
            merged = {}
            all_words = set(tfidf.keys()) | set(textrank.keys())
            for w in all_words:
                score = tfidf.get(w, 0) * 0.6 + textrank.get(w, 0) * 0.4
                if w not in STOP_WORDS and len(w) >= 2:
                    merged[w] = score
            ranked = sorted(merged.items(), key=lambda x: x[1], reverse=True)
            return ranked[:topk]
        else:
            raise ValueError(f"不支持的方法: {method}")

    def extract_from_news(self, title, content="", topk=5):
        full_text = (title * 2) + " " + (content or "")
        return self.extract(full_text, topk=topk, method="hybrid")

    @staticmethod
    def _clean_text(text):
        text = re.sub(r"<[^>]+>", "", str(text))
        text = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def batch_extract(self, news_df, topk=5):
        results = []
        for _, row in news_df.iterrows():
            kws = self.extract_from_news(row.get("title", ""), row.get("content", ""), topk)
            results.append({
                "date": row.get("date"),
                "title": row.get("title"),
                "keywords": [k[0] for k in kws],
                "keyword_weights": [round(k[1], 4) for k in kws],
            })
        return pd.DataFrame(results)


# ──────────────────────────────────────────────
# 情感分析器 v2（半导体增强版）
# ──────────────────────────────────────────────

class SentimentAnalyzer:
    """中文金融情感分析器 v2（增强半导体领域情感词典）。"""

    def __init__(self):
        self.positive = POSITIVE_WORDS
        self.negative = NEGATIVE_WORDS

    def analyze(self, text):
        """
        情感分析。
        :return: dict {sentiment, score(-1~1), pos_words[], neg_words[], intensity}
        """
        if not text:
            return self._default_result()

        text = str(text)

        pos_hits = [w for w in self.positive if w in text]
        neg_hits = [w for w in self.negative if w in text]
        pos_count = len(pos_hits)
        neg_count = len(neg_hits)

        snownlp_score = 0.5
        if _SNOW_OK and pos_count == 0 and neg_count == 0:
            try:
                s = SnowNLP(text)
                snownlp_score = s.sentiments
            except Exception as e:
                logger.warning(f"[news] SnowNLP 情感分析失败: {e}")

        # 计算强度修饰词（非常/极度/显著/大幅）
        intensifiers = re.findall(r"(非常|极其|显著|大幅|急剧|持续|严重|深度)(?=的?[^\w])?", text)
        intensity_mod = 1.0 + min(len(intensifiers) * 0.15, 0.5) if intensifiers else 1.0

        if pos_count + neg_count > 0:
            raw = (pos_count - neg_count) / (pos_count + neg_count) * intensity_mod
        else:
            raw = (snownlp_score - 0.5) * 0.3

        score = round(max(-1.0, min(1.0, raw)), 3)

        if score > 0.15:
            sentiment = "正面"
        elif score < -0.15:
            sentiment = "负面"
        else:
            sentiment = "中性"

        # 判断是否为重大新闻（高绝对值分数）
        is_major = abs(score) >= 0.4

        return {
            "sentiment": sentiment,
            "score": score,
            "pos_words": pos_hits,
            "neg_words": neg_hits,
            "is_major": is_major,
            "intensity": round(intensity_mod, 2),
        }

    def analyze_news(self, title, content=""):
        """分析单条新闻情感（标题权重高）。"""
        full_text = (title * 3) + " " + (content or "")
        return self.analyze(full_text)

    def batch_analyze(self, news_df):
        results = []
        for _, row in news_df.iterrows():
            r = self.analyze_news(row.get("title", ""), row.get("content", ""))
            r["date"] = row.get("date")
            r["title"] = row.get("title")
            results.append(r)
        return pd.DataFrame(results)

    @staticmethod
    def _default_result():
        return {
            "sentiment": "中性", "score": 0.0,
            "pos_words": [], "neg_words": [],
            "is_major": False, "intensity": 1.0,
        }

    def sentiment_distribution(self, news_df):
        if news_df.empty:
            return {}
        analyzed = self.batch_analyze(news_df)
        dist = analyzed["sentiment"].value_counts().to_dict()
        total = len(analyzed)
        return {k: round(v / total * 100, 1) for k, v in dist.items()}


# ──────────────────────────────────────────────
# 新闻去重器
# ──────────────────────────────────────────────

class NewsDeduplicator:
    """
    新闻去重器。
    使用标题相似度（编辑距离/Jaccard）+ 内容指纹（SimHash思想）进行去重。
    """

    def __init__(self, similarity_threshold=0.75):
        self.threshold = similarity_threshold

    @staticmethod
    def _fingerprint(text):
        """生成文本的简化 MD5 指纹。"""
        clean = re.sub(r"\s+", "", str(text).lower())[:200]
        return hashlib.md5(clean.encode()).hexdigest()[:16]

    @staticmethod
    def _jaccard_similarity(s1, s2):
        """计算两个字符串的 Jaccard 相似度（基于字符级别 shingle）。"""
        if not s1 or not s2:
            return 0.0
        shingle_size = 3
        s1_set = set(s1[i:i + shingle_size] for i in range(len(s1) - shingle_size + 1))
        s2_set = set(s2[i:i + shingle_size] for i in range(len(s2) - shingle_size + 1))
        if not s1_set or not s2_set:
            return 0.0
        intersection = s1_set & s2_set
        union = s1_set | s2_set
        return len(intersection) / len(union)

    def deduplicate(self, news_df):
        """
        对新闻 DataFrame 进行去重。
        保留最早发布的版本。
        返回去重后的 DataFrame。
        """
        if news_df.empty or "title" not in news_df.columns:
            return news_df

        seen_fingerprints = set()
        seen_titles_similar = []  # [(fingerprint, title), ...]
        keep_indices = []

        for idx, row in news_df.iterrows():
            title = str(row.get("title", ""))

            # 快速路径：完全相同的标题
            fp = self._fingerprint(title)
            if fp in seen_fingerprints:
                continue

            # 慢速路径：相似标题
            is_dup = False
            for prev_fp, prev_title in seen_titles_similar:
                sim = self._jaccard_similarity(title, prev_title)
                if sim >= self.threshold:
                    is_dup = True
                    break

            if not is_dup:
                seen_fingerprints.add(fp)
                seen_titles_similar.append((fp, title))
                # 只保留最近的 N 个做比较（避免 O(N^2)）
                if len(seen_titles_similar) > 200:
                    seen_titles_similar.pop(0)
                keep_indices.append(idx)

        return news_df.loc[keep_indices].reset_index(drop=True)

    def deduplicate_with_merge(self, news_df):
        """
        去重 + 合并同质新闻。
        对于相似新闻，保留信息量最大的那条（标题最长），并在 content 中标记合并来源数。
        """
        deduped = self.deduplicate(news_df)
        deduped["_merge_count"] = 1
        deduped["_original_count"] = len(news_df)
        return deduped


# ──────────────────────────────────────────────
# 新闻摘要生成器
# ──────────────────────────────────────────────

class NewsSummarizer:
    """
    新闻摘要生成器。
    从多条新闻中提取关键信息，生成结构化摘要报告。
    """

    @staticmethod
    def generate_summary(news_df, top_k=10):
        """
        生成新闻摘要。
        :return: dict {
            total, date_range, sentiment_summary,
            major_events: [{title, sentiment, score, keywords}],
            hot_topics: [(topic, count)],
            key_stats: {positive_pct, negative_pct, neutral_pct, major_count}
        }
        """
        if news_df.empty:
            return {"total": 0, "major_events": [], "hot_topics": [], "key_stats": {}}

        total = len(news_df)

        # 时间范围
        dates = pd.to_datetime(news_df["date"], errors="coerce").dropna()
        date_range = f"{dates.min().strftime('%Y-%m-%d')} ~ {dates.max().strftime('%Y-%m-%d')}" if not dates.empty else "未知"

        # 情感统计（如果还没算过）
        analyzer = SentimentAnalyzer()
        if "sentiment" not in news_df.columns:
            analyzed = analyzer.batch_analyze(news_df)
            sentiments = analyzed["sentiment"].tolist()
            scores = analyzed["score"].tolist()
            is_major = analyzed.get("is_major", [False] * total).tolist()
        else:
            sentiments = news_df["sentiment"].tolist()
            scores = news_df.get("sentiment_score", [0.0] * total).tolist()
            is_major = news_df.get("is_major", [False] * total).tolist()

        pos_count = sum(1 for s in sentiments if s == "正面")
        neg_count = sum(1 for s in sentiments if s == "负面")
        neu_count = total - pos_count - neg_count

        # 重大事件（高绝对值分数或 is_major 标记）
        major_events = []
        for i, row in news_df.iterrows():
            sc = scores[i] if i < len(scores) else 0
            major = is_major[i] if i < len(is_major) else (abs(sc) >= 0.4)
            if major or abs(sc) >= 0.25:
                major_events.append({
                    "title": row.get("title", ""),
                    "sentiment": sentiments[i] if i < len(sentiments) else "中性",
                    "score": round(sc, 3),
                    "source": row.get("source", ""),
                    "date": str(row.get("date", ""))[:10],
                })

        # 排序：按情绪强度降序
        major_events.sort(key=lambda x: abs(x["score"]), reverse=True)
        major_events = major_events[:top_k]

        # 热门话题
        extractor = KeywordExtractor() if _JIEBA_OK else None
        topic_counter = Counter()
        if extractor and "content" in news_df.columns:
            for _, row in news_df.iterrows():
                kws = extractor.extract_from_news(
                    row.get("title", ""),
                    row.get("content", ""),
                    topk=3
                )
                for kw, _ in kws:
                    topic_counter[kw] += 1

        hot_topics = topic_counter.most_common(10)

        return {
            "total": total,
            "date_range": date_range,
            "key_stats": {
                "positive": pos_count,
                "negative": neg_count,
                "neutral": neu_count,
                "positive_pct": round(pos_count / total * 100, 1) if total > 0 else 0,
                "negative_pct": round(neg_count / total * 100, 1) if total > 0 else 0,
                "neutral_pct": round(neu_count / total * 100, 1) if total > 0 else 0,
                "major_count": len(major_events),
            },
            "major_events": major_events,
            "hot_topics": hot_topics,
        }
