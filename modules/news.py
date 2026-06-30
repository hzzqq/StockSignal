"""
新闻事件抓取与智能分析模块
功能：
1. 多源新闻抓取（AKShare 东方财富/财新/央视）
2. jieba 关键词提取（TF-IDF + TextRank 双算法）
3. 中文情感分析（金融领域词典法 + SnowNLP 兜底）
4. 事件自动结构化入库
"""

import os
import re
import time
from datetime import datetime, timedelta
from collections import Counter

import pandas as pd
import numpy as np

try:
    import akshare as ak
    _AK_OK = True
except ImportError:
    _AK_OK = False

try:
    import jieba
    import jieba.analyse
    _JIEBA_OK = True
except ImportError:
    _JIEBA_OK = False

try:
    from snownlp import SnowNLP
    _SNOW_OK = True
except ImportError:
    _SNOW_OK = False


def _retry_request(func, max_retries=3, base_delay=2):
    """网络请求自动重试（与 fetcher.py 同构）。"""
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except (ConnectionError, TimeoutError, OSError) as e:
            last_err = e
            err_msg = str(e).lower()
            is_transient = any(kw in err_msg for kw in [
                "remote disconnected", "connection aborted", "reset by peer",
                "timed out", "connection refused", "broken pipe",
                "remote end closed", "temporary failure"
            ])
            if not is_transient or attempt == max_retries:
                raise
            delay = base_delay * (2 ** (attempt - 1))
            time.sleep(delay)
        except Exception:
            raise
    raise last_err


# ------------------------------------------------------------------
# 金融领域情感词典
# ------------------------------------------------------------------
POSITIVE_WORDS = {
    "利好", "增长", "超预期", "订单", "突破", "涨价", "补贴", "支持", "回升",
    "增持", "回购", "业绩大增", "涨停", "大涨", "暴涨", "创新高", "丰收",
    "盈利", "翻倍", "强劲", "繁荣", "刺激", "宽松", "降息", "减税", "复苏",
    "扩张", "加速", "强劲增长", "供不应求", "紧缺", "高速增长", "大幅提升",
    "景气回升", "景气度", "高景气", "需求旺盛", "产销两旺", "量价齐升",
}

NEGATIVE_WORDS = {
    "利空", "下降", "亏损", "违规", "处罚", "下跌", "停产", "风险", "预警",
    "减持", "质押", "爆雷", "退市", "暴跌", "大跌", "跳水", "创新低", "萧条",
    "收缩", "放缓", "滞销", "过剩", "库存积压", "裁员", "停产限产", "限产",
    "违约", "诉讼", "调查", "问询", "监管", "收紧", "加息", "通胀", "滞胀",
    "产能过剩", "价格战", "恶性竞争", "需求疲软", "景气下行", "业绩暴雷",
}

# 停用词
STOP_WORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有",
    "看", "好", "自己", "这", "那", "它", "被", "从", "把", "对", "为", "与",
    "及", "或", "等", "但", "而", "则", "其", "此", "以", "可", "将", "已",
    "该", "某", "多", "少", "大", "小", "中", "后", "前", "年", "月", "日",
    "时", "分", "点", "个", "只", "量", "项", "家", "位", "名", "号",
}


class NewsFetcher:
    """多源新闻抓取器（适配 akshare 1.18.64 API 变更）。"""

    def __init__(self):
        self.sources = {
            "eastmoney": self._fetch_eastmoney,
            "caixin": self._fetch_caixin,
            "cctv": self._fetch_cctv,
        }
        self._today_news_cache = None  # 缓存当天的通用新闻，避免重复请求

    def fetch(self, keyword=None, source="eastmoney", limit=50):
        """
        抓取新闻。
        :param keyword: 关键词过滤，None 则抓取全部
        :param source: eastmoney / caixin / cctv
        :param limit: 最多返回条数
        :return: DataFrame[date, title, content, source]
        """
        func = self.sources.get(source)
        if func is None:
            raise ValueError(f"不支持的来源: {source}，可选: {list(self.sources.keys())}")

        if not _AK_OK:
            return pd.DataFrame(columns=["date", "title", "content", "source"])

        df = func(keyword)
        if df is not None and not df.empty:
            df = df.head(limit).reset_index(drop=True)
            return df
        return pd.DataFrame(columns=["date", "title", "content", "source"])

    # ------------------------------------------------------------------
    # 内部：通用快讯抓取 + 关键词过滤
    # ------------------------------------------------------------------
    def _fetch_stock_news_main(self, keyword):
        """
        抓取财新数据通-股票新闻（支持关键词过滤）。
        stock_news_main_cx 返回 [tag, summary, url]（akshare 1.18.64 实测列名）。
        """
        try:
            df = _retry_request(lambda: ak.stock_news_main_cx(), max_retries=3, base_delay=2)

            # 适配 API 返回的列名（实测为 tag/summary/url）
            # summary 字段同时包含标题和摘要，取第一行作为 title
            df = df.rename(columns={
                "summary": "content",
                "tag": "category",
            })

            # 从 summary 中提取首句作为 title（summary 可能很长）
            df["title"] = df["content"].str.split(r"[\n。，；]", n=1).str[0].str.strip()
            # 截断过长的标题
            df["title"] = df["title"].str.slice(0, 80)

            # 日期：API 不直接返回日期，使用今天
            df["date"] = datetime.now().strftime("%Y-%m-%d")

            # 关键词过滤
            if keyword:
                mask = (df["category"].str.contains(keyword, na=False) |
                        df["title"].str.contains(keyword, na=False) |
                        df["content"].str.contains(keyword, na=False))
                df = df[mask]

            df["date"] = pd.to_datetime(df["date"])
            return df[["date", "title", "content"]].dropna(subset=["title"])
        except Exception as e:
            print(f"[NewsFetcher] 股票新闻抓取失败: {e}")
            return pd.DataFrame(columns=["date", "title", "content", "source"])

    def _fetch_eastmoney(self, keyword):
        """
        东方财富来源。
        stock_news_em 在 akshare 1.18.64 有 ArrowInvalid bug，
        退化为 stock_news_main_cx + 关键词过滤；无关键词时用 news_cctv。
        """
        try:
            if keyword:
                # 有关键词 → 用财新数据通 + 关键词过滤
                df = self._fetch_stock_news_main(keyword)
                df["source"] = "eastmoney"
                return df
            else:
                # 无关键词 → 央视新闻联播
                df = _retry_request(
                    lambda: ak.news_cctv(date=datetime.now().strftime("%Y%m%d")),
                    max_retries=3, base_delay=2
                )
                df = df.rename(columns={"date": "date", "title": "title", "content": "content"})
                df["source"] = "eastmoney"
                df["date"] = pd.to_datetime(df["date"], errors="coerce")
                return df[["date", "title", "content", "source"]].dropna(subset=["date"])
        except Exception as e:
            print(f"[NewsFetcher] 东方财富抓取失败: {e}")
            return pd.DataFrame(columns=["date", "title", "content", "source"])

    def _fetch_caixin(self, keyword):
        """财新数据通来源：直接调用 stock_news_main_cx。"""
        try:
            df = self._fetch_stock_news_main(keyword)
            df["source"] = "caixin"
            return df
        except Exception:
            return pd.DataFrame(columns=["date", "title", "content", "source"])

    def _fetch_cctv(self, keyword):
        """央视新闻联播来源。"""
        try:
            date_str = datetime.now().strftime("%Y%m%d")
            df = _retry_request(
                lambda: ak.news_cctv(date=date_str),
                max_retries=3, base_delay=2
            )
            df = df.rename(columns={"date": "date", "title": "title", "content": "content"})
            df["source"] = "cctv"
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            if keyword:
                df = df[df["title"].str.contains(keyword, na=False) |
                        df["content"].str.contains(keyword, na=False)]
            return df[["date", "title", "content", "source"]].dropna(subset=["date"])
        except Exception:
            return pd.DataFrame(columns=["date", "title", "content", "source"])

    def fetch_all(self, keyword=None, limit_per_source=30):
        """聚合所有来源的新闻。"""
        frames = []
        for source in self.sources:
            try:
                df = self.fetch(keyword=keyword, source=source, limit=limit_per_source)
                if not df.empty:
                    frames.append(df)
            except Exception:
                pass
        if frames:
            return pd.concat(frames, ignore_index=True).sort_values("date", ascending=False)
        return pd.DataFrame(columns=["date", "title", "content", "source"])


class KeywordExtractor:
    """关键词提取器（jieba TF-IDF + TextRank 融合）。"""

    # 金融领域自定义词典（提升行业术语权重）
    DOMAIN_WORDS = [
        "事件驱动", "主线", "顺周期", "景气度", "供需缺口", "产能利用率",
        "渗透率", "国产替代", "专精特新", "碳中和", "新能源", "半导体",
        "光伏", "储能", "锂电", "煤炭", "有色", "化工", "军工", "消费",
        "医药", "房地产", "银行", "券商", "保险", "MLCC", "存储芯片",
        "动力电池", "稀土", "螺纹钢", "原油", "天然气",
    ]

    def __init__(self):
        if _JIEBA_OK:
            for w in self.DOMAIN_WORDS:
                jieba.add_word(w)

    def extract(self, text, topk=8, method="hybrid"):
        """
        提取关键词。
        :param text: 文本
        :param topk: 返回前 K 个
        :param method: tfidf / textrank / hybrid(融合两者)
        :return: [(word, weight), ...]
        """
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
            # 融合：两个算法都命中的词权重加权
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
        """从新闻标题+正文提取关键词（标题权重加倍）。"""
        full_text = (title * 2) + " " + (content or "")
        return self.extract(full_text, topk=topk, method="hybrid")

    @staticmethod
    def _clean_text(text):
        """清洗文本：去 HTML 标签、特殊字符。"""
        text = re.sub(r"<[^>]+>", "", str(text))
        text = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def batch_extract(self, news_df, topk=5):
        """批量提取新闻关键词。"""
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


class SentimentAnalyzer:
    """中文金融情感分析器。"""

    def __init__(self):
        self.positive = POSITIVE_WORDS
        self.negative = NEGATIVE_WORDS

    def analyze(self, text):
        """
        情感分析。
        :return: dict {sentiment: 正面/负面/中性, score: -1.0~1.0, pos_words: [], neg_words: []}
        """
        if not text:
            return self._default_result()

        text = str(text)

        # 1. 词典法：统计正负面词数
        pos_hits = [w for w in self.positive if w in text]
        neg_hits = [w for w in self.negative if w in text]
        pos_count = len(pos_hits)
        neg_count = len(neg_hits)

        # 2. SnowNLP 兜底（词典未命中时）
        snownlp_score = 0.5
        if _SNOW_OK and pos_count == 0 and neg_count == 0:
            try:
                s = SnowNLP(text)
                snownlp_score = s.sentiments  # 0~1
            except Exception:
                pass

        # 3. 综合打分
        if pos_count + neg_count > 0:
            # 词典法：pos/(pos+neg) 映射到 -1~1
            raw = (pos_count - neg_count) / (pos_count + neg_count)
        else:
            # SnowNLP 兜底：训练于电商评论，对正式金融文本偏乐观
            # 压缩映射范围至 ±0.15，使其无法独立判定为正面/负面
            raw = (snownlp_score - 0.5) * 0.3

        score = round(max(-1.0, min(1.0, raw)), 3)

        if score > 0.15:
            sentiment = "正面"
        elif score < -0.15:
            sentiment = "负面"
        else:
            sentiment = "中性"

        return {
            "sentiment": sentiment,
            "score": score,
            "pos_words": pos_hits,
            "neg_words": neg_hits,
        }

    def analyze_news(self, title, content=""):
        """分析单条新闻情感（标题权重高）。"""
        full_text = (title * 3) + " " + (content or "")
        return self.analyze(full_text)

    def batch_analyze(self, news_df):
        """批量情感分析。"""
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
            "pos_words": [], "neg_words": []
        }

    def sentiment_distribution(self, news_df):
        """统计情感分布。"""
        if news_df.empty:
            return {}
        analyzed = self.batch_analyze(news_df)
        dist = analyzed["sentiment"].value_counts().to_dict()
        total = len(analyzed)
        return {k: round(v / total * 100, 1) for k, v in dist.items()}


class EventMiner:
    """事件挖掘器：新闻 → 结构化事件 → 自动入库。"""

    def __init__(self, config_path="config.yaml"):
        self.news_fetcher = NewsFetcher()
        self.keyword_extractor = KeywordExtractor()
        self.sentiment_analyzer = SentimentAnalyzer()

        # 复用 SignalEngine 的事件库路径
        import yaml
        from .fetcher import load_config
        self.config = load_config(config_path)
        self.event_db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            self.config.get("events", {}).get("file", "data/events.csv")
        )

    def mine_events(self, keyword=None, source="eastmoney", limit=30, auto_save=True):
        """
        从新闻中挖掘结构化事件并入库。
        :param keyword: 关键词过滤，None 则抓全部
        :return: DataFrame[date, ticker, title, type, keywords, sentiment_score]
        """
        # 1. 抓取新闻
        news = self.news_fetcher.fetch(keyword=keyword, source=source, limit=limit)
        if news.empty:
            return pd.DataFrame()

        events = []
        for _, row in news.iterrows():
            title = str(row.get("title", ""))
            content = str(row.get("content", ""))

            # 2. 关键词提取
            kws = self.keyword_extractor.extract_from_news(title, content, topk=5)
            kw_list = [k[0] for k in kws]

            # 3. 情感分析
            sentiment = self.sentiment_analyzer.analyze_news(title, content)

            # 4. 股票代码提取（从标题/正文）
            ticker = self._extract_ticker(title + content)

            events.append({
                "date": row.get("date"),
                "ticker": ticker or "",
                "title": title,
                "type": sentiment["sentiment"],
                "keywords": ",".join(kw_list),
                "sentiment_score": sentiment["score"],
                "source": row.get("source", ""),
            })

        events_df = pd.DataFrame(events)

        # 5. 自动入库
        if auto_save and not events_df.empty:
            self._save_events(events_df)

        return events_df

    def _extract_ticker(self, text):
        """从文本中提取 A 股代码（6位数字，以6/0/3开头）。"""
        match = re.search(r"(?<!\d)(6\d{5}|0\d{5}|3\d{5})(?!\d)", str(text))
        return match.group(1) if match else ""

    def _save_events(self, events_df):
        """保存到事件库 CSV（追加模式）。"""
        os.makedirs(os.path.dirname(self.event_db_path), exist_ok=True)

        # 读取现有事件
        existing = pd.DataFrame()
        if os.path.exists(self.event_db_path):
            existing = pd.read_csv(self.event_db_path, encoding="utf-8-sig")

        # 去重（按 title 去重）
        new_events = events_df[~events_df["title"].isin(existing["title"])] if not existing.empty else events_df

        if not new_events.empty:
            combined = pd.concat([existing, new_events], ignore_index=True)
            combined["date"] = pd.to_datetime(combined["date"], errors="coerce")
            combined = combined.sort_values("date", ascending=False).reset_index(drop=True)
            combined.to_csv(self.event_db_path, index=False, encoding="utf-8-sig")

    def get_hot_keywords(self, days=7, topk=20):
        """获取近 N 天热门关键词。"""
        if not os.path.exists(self.event_db_path):
            return []
        df = pd.read_csv(self.event_db_path, encoding="utf-8-sig", parse_dates=["date"])
        cutoff = datetime.now() - timedelta(days=days)
        df = df[df["date"] >= cutoff]
        if df.empty:
            return []

        all_kws = []
        for kws in df["keywords"].dropna():
            all_kws.extend([k.strip() for k in kws.split(",")])
        counter = Counter(all_kws)
        return counter.most_common(topk)
