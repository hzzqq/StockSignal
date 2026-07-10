"""
事件信号分析模块
综合价格信号、事件信号、宏观信号三类因子，输出 0-100 的主线强度得分。
"""

import os
from datetime import datetime, timedelta

import pandas as pd

from .fetcher import StockFetcher, load_config
from .cleaner import DataCleaner
from .news import EventMiner, NewsFetcher, SentimentAnalyzer, KeywordExtractor


class SignalEngine:
    """事件驱动信号引擎（集成新闻挖掘 + 情感分析）。"""

    def __init__(self, config_path="config.yaml"):
        self.config = load_config(config_path)
        self.fetcher = StockFetcher(config_path)
        self.weights = self.config.get("signal", {}).get("weights", {
            "price": 0.4, "event": 0.4, "macro": 0.2
        })
        self.event_db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            self.config.get("events", {}).get("file", "data/events.csv")
        )
        # 新闻挖掘与情感分析组件
        self.event_miner = EventMiner(config_path)
        self.sentiment_analyzer = SentimentAnalyzer()
        self.keyword_extractor = KeywordExtractor()

    # ------------------------------------------------------------------
    # 价格信号得分 (0-100)
    # ------------------------------------------------------------------
    def price_score(self, df, date=None):
        """
        基于均线趋势、动量、成交量变化计算价格信号得分。
        :param df: 行情 DataFrame，需含 close, volume, ma5, ma20 列
        :param date: 评估日期，None 则取最后一天
        :return: 0-100 得分
        """
        if df.empty:
            return 50

        df = df.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

        if date is not None:
            df = df[df["date"] <= pd.Timestamp(date)]
        if len(df) < 20:
            return 50

        latest = df.iloc[-1]
        score = 0

        # 1) 均线趋势 (40分): close > ma20 > ma60 偏多
        close = latest["close"]
        ma5 = latest.get("ma5", close)
        ma20 = latest.get("ma20", close)
        ma60 = df["close"].rolling(60).mean().iloc[-1] if len(df) >= 60 else ma20

        if close > ma5 > ma20:
            score += 25
        elif close > ma20:
            score += 15
        if ma20 > ma60:
            score += 15

        # 2) 动量 (30分): 5日涨幅
        if "return_5d" in df.columns:
            ret_5d = latest.get("return_5d", 0)
            if ret_5d > 5:
                score += 30
            elif ret_5d > 2:
                score += 20
            elif ret_5d > 0:
                score += 10
            elif ret_5d > -2:
                score += 5

        # 3) 成交量 (30分): 量价齐升加分
        if "volume" in df.columns and len(df) >= 5:
            vol_today = latest["volume"]
            vol_avg5 = df["volume"].tail(5).mean()
            if vol_avg5 > 0:
                vol_ratio = vol_today / vol_avg5
                if vol_ratio > 1.5 and latest.get("change_pct", 0) > 0:
                    score += 30
                elif vol_ratio > 1.2:
                    score += 15
                elif vol_ratio > 1.0:
                    score += 5

        return min(100, max(0, int(score)))

    # ------------------------------------------------------------------
    # 事件信号得分 (0-100)
    # ------------------------------------------------------------------
    def event_score(self, ticker, keywords, date=None):
        """
        基于关键词匹配事件库 + 实时新闻情感分析，计算事件信号得分。
        :param ticker: 股票代码
        :param keywords: 关键词列表，如 ["煤炭", "保供"]
        :param date: 评估日期
        :return: 0-100 得分
        """
        events = self._load_events()
        score = 50  # 基准分

        # ---- Part 1: 本地事件库匹配 ----
        if not events.empty:
            events["date"] = pd.to_datetime(events["date"], errors="coerce")
            if date is not None:
                date_ts = pd.Timestamp(date)
                events = events[events["date"] >= date_ts - timedelta(days=30)]

            matched = events[events["title"].str.contains("|".join(keywords), na=False, regex=True)]
            matched = matched[matched["ticker"].str.contains(ticker, na=False) | matched["ticker"].isna()]

            for _, evt in matched.iterrows():
                evt_type = str(evt.get("type", ""))
                # 优先用已存储的情感标签
                if "正面" in evt_type or evt_type == "利好":
                    score += 18
                elif "负面" in evt_type or evt_type == "利空":
                    score -= 14
                else:
                    score += 2  # 中性事件 +关注度

                # 若有 sentiment_score 列，纳入量化
                if "sentiment_score" in evt and pd.notna(evt.get("sentiment_score")):
                    score += float(evt["sentiment_score"]) * 10

        # ---- Part 2: 实时新闻情感（如果事件库匹配不足）----
        if score <= 52 and keywords:
            try:
                live_score = self._live_news_sentiment(keywords, date)
                if live_score is not None:
                    # 本地 + 实时取加权平均
                    score = score * 0.5 + live_score * 0.5
            except Exception:
                pass

        return min(100, max(0, int(score)))

    def _live_news_sentiment(self, keywords, date=None):
        """抓取最新新闻做实时情感打分（0-100）。"""
        try:
            keyword = keywords[0] if keywords else None
            news = self.event_miner.news_fetcher.fetch(keyword=keyword, source="eastmoney", limit=15)
            if news.empty:
                return None

            # 批量情感分析
            dist = self.sentiment_analyzer.sentiment_distribution(news)
            pos_pct = dist.get("正面", 0)
            neg_pct = dist.get("负面", 0)
            # 正面占比映射到 30-90，负面越多越低
            live_score = 30 + pos_pct * 0.6 - neg_pct * 0.4
            return min(100, max(0, int(live_score)))
        except Exception:
            return None

    def _load_events(self):
        """加载事件库 CSV。"""
        if not os.path.exists(self.event_db_path):
            return pd.DataFrame(columns=["date", "ticker", "title", "type"])
        df = pd.read_csv(self.event_db_path, parse_dates=["date"])
        # 强制 ticker 为字符串，避免纯数字列被推断为 int64 导致 .str 访问器失效
        df["ticker"] = df["ticker"].astype(str).str.strip()
        return df

    def add_event(self, date, ticker, title, event_type="中性"):
        """手动添加一条事件记录。"""
        events = self._load_events()
        new_row = pd.DataFrame([{
            "date": pd.Timestamp(date),
            "ticker": ticker,
            "title": title,
            "type": event_type
        }])
        events = pd.concat([events, new_row], ignore_index=True)
        os.makedirs(os.path.dirname(self.event_db_path), exist_ok=True)
        events.to_csv(self.event_db_path, index=False, encoding="utf-8-sig")

    # ------------------------------------------------------------------
    # 宏观信号得分 (0-100)
    # ------------------------------------------------------------------
    def macro_score(self, date=None):
        """
        基于制造业 PMI 计算宏观信号得分。
        PMI > 50 扩张 → 偏多，PMI < 50 收缩 → 偏空。
        """
        try:
            pmi_df = self.fetcher.get_macro("pmi_mfg")
            if pmi_df.empty:
                return 50

            # 取最近一期 PMI
            pmi_col = [c for c in pmi_df.columns if "pmi" in c.lower()]
            if not pmi_col:
                return 50
            latest_pmi = pmi_df[pmi_col[0]].iloc[-1]

            if pd.isna(latest_pmi):
                return 50

            # PMI 50 为中线，每偏离 1 点 → 评分变动 5 分
            score = 50 + (latest_pmi - 50) * 5
            return min(100, max(0, int(score)))
        except Exception:
            return 50

    # ------------------------------------------------------------------
    # 综合评分
    # ------------------------------------------------------------------
    def evaluate(self, ticker, event_keywords, date=None):
        """
        综合评估单只股票的事件驱动得分。
        :param ticker: 股票代码
        :param event_keywords: 事件关键词列表
        :param date: 评估日期
        :return: dict {price_score, event_score, macro_score, total}
        """
        # 拉取行情并清洗（失败时降级为中性评分）
        end = date or datetime.now().strftime("%Y-%m-%d")
        start = (datetime.strptime(end, "%Y-%m-%d") if date else datetime.now()) - timedelta(days=120)
        start_str = start.strftime("%Y-%m-%d")

        try:
            df = self.fetcher.get_daily(ticker, start=start_str, end=end)
            df = DataCleaner.full_pipeline(df)
            p_score = self.price_score(df, date)
        except (RuntimeError, ValueError, Exception) as e:
            # 行情数据不可用 → 价格信号给中性分，不影响事件和宏观评分
            p_score = 50
            print(f"[SignalEngine] 行情获取失败({ticker})，价格信号使用中性分50: {e}")

        e_score = self.event_score(ticker, event_keywords, date)
        m_score = self.macro_score(date)

        w = self.weights
        total = int(p_score * w["price"] + e_score * w["event"] + m_score * w["macro"])

        return {
            "price_score": p_score,
            "event_score": e_score,
            "macro_score": m_score,
            "total": min(100, max(0, total))
        }

    # ------------------------------------------------------------------
    # 批量评分
    # ------------------------------------------------------------------
    def batch_evaluate(self, tickers_keywords, date=None):
        """
        批量评估多只股票。
        :param tickers_keywords: [{"ticker": "601088", "keywords": ["煤炭"]}, ...]
        :return: DataFrame[ticker, price_score, event_score, macro_score, total]
        """
        results = []
        for item in tickers_keywords:
            try:
                r = self.evaluate(item["ticker"], item.get("keywords", []), date)
                r["ticker"] = item["ticker"]
                results.append(r)
            except Exception as e:
                results.append({
                    "ticker": item["ticker"], "price_score": 0,
                    "event_score": 0, "macro_score": 0, "total": 0, "error": str(e)
                })
        return pd.DataFrame(results).sort_values("total", ascending=False).reset_index(drop=True)

    # ------------------------------------------------------------------
    # 新闻事件自动挖掘（新增）
    # ------------------------------------------------------------------
    def auto_mine_events(self, keyword=None, source="eastmoney", limit=30):
        """
        一键抓取新闻 → 提取关键词 → 情感分析 → 自动入库。
        :param keyword: 关键词过滤，None 则抓取财经要闻
        :return: DataFrame[date, ticker, title, type, keywords, sentiment_score]
        """
        return self.event_miner.mine_events(keyword=keyword, source=source, limit=limit, auto_save=True)

    def get_hot_keywords(self, days=7, topk=20):
        """获取近 N 天热门关键词排行。"""
        return self.event_miner.get_hot_keywords(days=days, topk=topk)

    def sentiment_report(self, keyword=None, limit=50):
        """
        生成新闻情感分析报告。
        :return: dict {total, positive_pct, negative_pct, neutral_pct, top_keywords, sample_news}
        """
        news = self.event_miner.news_fetcher.fetch(keyword=keyword, source="eastmoney", limit=limit)
        if news.empty:
            return {"total": 0, "positive_pct": 0, "negative_pct": 0, "neutral_pct": 0,
                    "top_keywords": [], "sample_news": []}

        # 情感分布
        dist = self.sentiment_analyzer.sentiment_distribution(news)

        # 关键词
        kw_df = self.keyword_extractor.batch_extract(news, topk=5)
        from collections import Counter
        all_kws = []
        for kws in kw_df["keywords"]:
            all_kws.extend(kws)
        top_kws = Counter(all_kws).most_common(15)

        # 样本新闻（取正负面各3条）
        analyzed = self.sentiment_analyzer.batch_analyze(news)
        samples = []
        for sentiment in ["正面", "负面"]:
            subset = analyzed[analyzed["sentiment"] == sentiment].head(3)
            for _, row in subset.iterrows():
                samples.append({
                    "sentiment": row["sentiment"],
                    "title": row.get("title", ""),
                    "score": row.get("score", 0),
                    "pos_words": row.get("pos_words", []),
                    "neg_words": row.get("neg_words", [])
                })

        return {
            "total": len(news),
            "positive_pct": dist.get("正面", 0),
            "negative_pct": dist.get("负面", 0),
            "neutral_pct": dist.get("中性", 0),
            "top_keywords": top_kws,
            "sample_news": samples
        }
