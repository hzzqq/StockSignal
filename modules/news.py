"""
新闻事件抓取与智能分析模块 v2.0（半导体专项增强版）
功能：
1. 多源新闻抓取（东方财富网页搜索 + 财新数据通 + 央视新闻 + 百度股市通）
2. 半导体行业专项关键词引擎（核心词汇 + 细分公司名 + 子赛道）
3. jieba 关键词提取（TF-IDF + TextRank 双算法）
4. 中文情感分析（金融领域词典法 + 半导体领域增强 + SnowNLP 兜底）
5. 新闻去重（标题相似度 + 内容指纹）
6. 自动摘要生成
7. 结构化 SQLite 存储，支持多维度查询
8. 个股-新闻关联预警模型
"""

import os
import logging

logger = logging.getLogger(__name__)
import re
import time
import json
import hashlib
import sqlite3
from datetime import datetime, timedelta
from collections import Counter

import pandas as pd

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

# ──────────────────────────────────────────────
# 网络请求工具
# ──────────────────────────────────────────────
def _retry_request(func, max_retries=3, base_delay=2):
    """网络请求自动重试。"""
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
        except Exception as e:
            logger.warning(f"[news] 处理异常: {e}")
            raise
    raise last_err


def _fetch_url(url, headers=None, timeout=15, encoding="utf-8"):
    """
    通用 URL 抓取（urllib，无额外依赖）。
    返回 decoded text 或 None。
    """
    import urllib.request, urllib.error
    try:
        req = urllib.request.Request(
            url,
            headers=headers or {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": "https://www.eastmoney.com/",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            # 自动检测编码
            if encoding == "auto":
                ct = resp.headers.get("Content-Type", "")
                m = re.search(r"charset=([\\w-]+)", ct, re.I)
                enc = m.group(1).lower() if m else "utf-8"
            else:
                enc = encoding
            return data.decode(enc, errors="ignore")
    except Exception as e:
        logger.warning(f"[_fetch_url] {url[:60]}... failed: {e}")
        return None


# ──────────────────────────────────────────────
# 半导体行业关键词引擎
# ──────────────────────────────────────────────


# ── re-export from split sub-modules (backward compat) ──
from modules._news_io import (                       # noqa: F401
    _retry_request, _fetch_url,
    SemiconductorKeywordEngine, NewsFetcher,
    logger, POSITIVE_WORDS, NEGATIVE_WORDS, STOP_WORDS,
    _AK_OK, _JIEBA_OK, _SNOW_OK,
)
from modules._news_nlp import (                       # noqa: F401
    KeywordExtractor, SentimentAnalyzer,
    NewsDeduplicator, NewsSummarizer,
)


# ──────────────────────────────────────────────
# 新闻数据库（SQLite）
# ──────────────────────────────────────────────

class NewsDatabase:
    """
    新闻结构化数据库（SQLite）。
    支持按时间、板块、情感、股票等多维度查询。
    """

    def __init__(self, db_path="data/news.db"):
        # 跟随 SS_DATA_DIR 隔离；未设时回落到仓库 data/，生产默认行为完全不变。
        base_dir = os.environ.get("SS_DATA_DIR") or os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))
        self.db_path = os.path.join(base_dir, db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT DEFAULT '',
                url TEXT DEFAULT '',
                source TEXT DEFAULT '',
                date TEXT,
                inserted_at TEXT DEFAULT (datetime('now','localtime')),
                fingerprint TEXT UNIQUE,
                -- 分析字段
                sentiment TEXT DEFAULT '中性',
                sentiment_score REAL DEFAULT 0.0,
                is_major INTEGER DEFAULT 0,
                keywords TEXT DEFAULT '',
                related_stocks TEXT DEFAULT '',
                -- 元数据
                search_keyword TEXT DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_news_date ON news(date);
            CREATE INDEX IF NOT EXISTS idx_news_sentiment ON news(sentiment);
            CREATE INDEX IF NOT EXISTS idx_news_source ON news(source);
            CREATE INDEX IF NOT EXISTS idx_news_keyword ON news(search_keyword);
            CREATE INDEX IF NOT EXISTS idx_news_fp ON news(fingerprint);

            -- 板块配置表
            CREATE TABLE IF NOT EXISTS sectors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                keywords TEXT NOT NULL,
                stock_codes TEXT DEFAULT '',
                description TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );
        """)
        conn.commit()
        conn.close()

        # 初始化半导体板块
        self._init_sector("semiconductor")

    def _init_sector(self, sector_key):
        """预置板块数据。"""
        engine = SemiconductorKeywordEngine()
        if sector_key == "semiconductor":
            codes = ",".join(engine.get_all_semi_codes())
            names = ",".join(engine.get_search_keywords(category="companies"))
            core = ",".join(engine.get_search_keywords(category="core")[:30])
            self.upsert_sector(
                name="半导体",
                keywords=f"{core},{names}",
                stock_codes=codes,
                description="A股半导体全产业链：设计/制造/封测/设备/材料"
            )

    def save_news(self, news_df, search_keyword=""):
        """
        批量保存新闻到数据库（自动去重）。
        :return: (新增数量, 总数量)
        """
        if news_df.empty:
            return 0, 0

        conn = self._get_conn()
        new_count = 0
        try:
            for _, row in news_df.iterrows():
                title = str(row.get("title", "")).strip()
                if not title:
                    continue

                fp = hashlib.md5(title.encode()).hexdigest()[:16]

                # 检查是否已存在
                existing = conn.execute(
                    "SELECT id FROM news WHERE fingerprint = ?", (fp,)
                ).fetchone()

                if existing:
                    continue

                sentiment = row.get("type", row.get("sentiment", "中性"))
                score = row.get("sentiment_score", row.get("score", 0.0))

                # 序列化 keywords
                kws = row.get("keywords", "")
                if isinstance(kws, list):
                    kws = ",".join(str(k) for k in kws)

                conn.execute("""
                    INSERT INTO news (title, content, url, source, date,
                                      fingerprint, sentiment, sentiment_score,
                                      keywords, search_keyword)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    title,
                    str(row.get("content", ""))[:2000],
                    str(row.get("url", ""))[:500],
                    str(row.get("source", "")),
                    str(row.get("date", ""))[:19],
                    fp,
                    str(sentiment),
                    float(score) if score else 0.0,
                    kws,
                    search_keyword,
                ))
                new_count += 1

            conn.commit()
        finally:
            total = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0]
            conn.close()

        return new_count, total

    def query(self, **filters):
        """
        多维度查询新闻。
        支持 filters: keyword, sentiment, source, date_from, date_to,
                       stock_code, is_major, limit, offset, order_by
        """
        conn = self._get_conn()
        try:
            where = []
            params = []

            if filters.get("keyword"):
                where.append("(title LIKE ? OR content LIKE ? OR keywords LIKE ?)")
                kw = f"%{filters['keyword']}%"
                params.extend([kw, kw, kw])

            if filters.get("sentiment"):
                where.append("sentiment = ?")
                params.append(filters["sentiment"])

            if filters.get("source"):
                where.append("source = ?")
                params.append(filters["source"])

            if filters.get("date_from"):
                where.append("date >= ?")
                params.append(filters["date_from"])

            if filters.get("date_to"):
                where.append("date <= ?")
                params.append(filters["date_to"])

            if filters.get("is_major"):
                where.append("is_major = 1")

            if filters.get("search_keyword"):
                where.append("search_keyword = ?")
                params.append(filters["search_keyword"])

            where_clause = " AND ".join(where) if where else "1=1"

            order_by = filters.get("order_by", "inserted_at DESC")
            limit = filters.get("limit", 50)
            offset = filters.get("offset", 0)

            sql = f"""SELECT * FROM news
                      WHERE {where_clause}
                      ORDER BY {order_by}
                      LIMIT ? OFFSET ?"""
            params.extend([limit, offset])

            df = pd.read_sql_query(sql, conn, params=params)
            return df
        finally:
            conn.close()

    def get_sentiment_trend(self, days=30, keyword=None):
        """获取情感趋势（按天聚合）。"""
        conn = self._get_conn()
        try:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            where = "date >= ?"
            params = [cutoff]
            if keyword:
                where += " AND (title LIKE ? OR keywords LIKE ?)"
                kw = f"%{keyword}%"
                params.extend([kw, kw])

            sql = f"""
                SELECT date,
                       COUNT(*) as total,
                       SUM(CASE WHEN sentiment='正面' THEN 1 ELSE 0 END) as positive,
                       SUM(CASE WHEN sentiment='负面' THEN 1 ELSE 0 END) as negative,
                       SUM(CASE WHEN sentiment='中性' THEN 1 ELSE 0 END) as neutral,
                       AVG(sentiment_score) as avg_score
                FROM news
                WHERE {where}
                GROUP BY date
                ORDER BY date
            """
            return pd.read_sql_query(sql, conn, params=params)
        finally:
            conn.close()

    def get_hot_keywords(self, days=7, top_k=20):
        """热门关键词统计。"""
        conn = self._get_conn()
        try:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            rows = conn.execute(
                """SELECT keywords FROM news
                   WHERE date >= ? AND keywords != ''""",
                (cutoff,)
            ).fetchall()
            counter = Counter()
            for (kws,) in rows:
                for kw in kws.split(","):
                    kw = kw.strip()
                    if len(kw) >= 2:
                        counter[kw] += 1
            return counter.most_common(top_k)
        finally:
            conn.close()

    def upsert_sector(self, name, keywords, stock_codes="", description=""):
        """更新或插入板块配置。"""
        conn = self._get_conn()
        try:
            conn.execute("""
                INSERT INTO sectors (name, keywords, stock_codes, description)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    keywords=excluded.keywords,
                    stock_codes=excluded.stock_codes,
                    description=excluded.description
            """, (name, keywords, stock_codes, description))
            conn.commit()
        finally:
            conn.close()


# ──────────────────────────────────────────────
# 事件挖掘器 v2（集成全部能力）
# ──────────────────────────────────────────────

class EventMiner:
    """
    事件挖掘器 v2：新闻抓取 → 关键词提取 → 情感分析 → 去重 → 入库 → 摘要
    """

    def __init__(self, config_path="config.yaml"):
        self.news_fetcher = NewsFetcher()
        self.keyword_extractor = KeywordExtractor()
        self.sentiment_analyzer = SentimentAnalyzer()
        self.deduplicator = NewsDeduplicator(similarity_threshold=0.72)
        self.summarizer = NewsSummarizer()
        self.semi_engine = SemiconductorKeywordEngine()
        self.db = NewsDatabase()

        from .fetcher import load_config
        self.config = load_config(config_path)
        self.event_csv_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            self.config.get("events", {}).get("file", "data/events.csv")
        )

    def mine_events(self, keyword=None, source="auto", limit=30, auto_save=True):
        """
        完整挖掘流程：抓取 → 去重 → 分析 → 入库
        :return: DataFrame[date, ticker, title, type, keywords, sentiment_score, source, url, is_major]
        """
        # 1. 选择抓取策略
        if keyword and self.semi_engine.is_semi_related(keyword):
            news = self.news_fetcher.fetch_semi_news(keyword=keyword, limit=limit)
        else:
            news = self.news_fetcher.fetch(keyword=keyword, source=source, limit=limit)

        if news.empty:
            return pd.DataFrame()

        # 2. 去重
        original_count = len(news)
        news = self.deduplicator.deduplicate(news)
        deduped_count = len(news)

        events = []
        for _, row in news.iterrows():
            title = str(row.get("title", ""))
            content = str(row.get("content", ""))
            source_name = str(row.get("source", ""))

            # 3. 关键词提取
            kws = self.keyword_extractor.extract_from_news(title, content, topk=5)
            kw_list = [k[0] for k in kws]

            # 4. 情感分析
            sentiment = self.sentiment_analyzer.analyze_news(title, content)

            # 5. 股票代码提取（增强版：也匹配半导体龙头）
            ticker = self._extract_ticker_enhanced(title + " " + content, keyword)

            events.append({
                "date": row.get("date"),
                "ticker": ticker or "",
                "title": title,
                "type": sentiment["sentiment"],
                "keywords": ",".join(kw_list),
                "sentiment_score": sentiment["score"],
                "source": source_name,
                "url": row.get("url", ""),
                "is_major": sentiment.get("is_major", False),
                "intensity": sentiment.get("intensity", 1.0),
                "pos_words": ",".join(sentiment.get("pos_words", [])),
                "neg_words": ",".join(sentiment.get("neg_words", [])),
            })

        events_df = pd.DataFrame(events)

        # 6. 入库
        if auto_save and not events_df.empty:
            new_cnt, total = self.db.save_news(events_df, keyword)
            logger.info(f"[EventMiner] 新增 {new_cnt} 条，总计 {total} 条")

            # 同时存到旧 CSV 格式（兼容）
            self._save_events_csv(events_df)

        # 附加元信息
        if not events_df.empty:
            events_df.attrs["original_count"] = original_count
            events_df.attrs["deduped_count"] = deduped_count

        return events_df

    def _extract_ticker_enhanced(self, text, context_keyword=None):
        """增强版股票代码/名称提取。"""
        # A. 标准 6 位代码
        match = re.search(r"(?<!\d)(6\d{5}|0\d{5}|3\d{5})(?!\d)", text)
        if match:
            return match.group(1)

        # B. 半导体公司名匹配
        for code, (name, _) in self.semi_engine.SEMI_LEADERS.items():
            if name in text:
                return code

        # C. 上下文关键词匹配
        if context_keyword and context_keyword.isdigit() and len(context_keyword) == 6:
            return context_keyword

        return ""

    def _save_events_csv(self, events_df):
        """兼容旧的 CSV 存储。"""
        os.makedirs(os.path.dirname(self.event_csv_path), exist_ok=True)
        existing = pd.DataFrame()
        if os.path.exists(self.event_csv_path):
            existing = pd.read_csv(self.event_csv_path, encoding="utf-8-sig")

        csv_cols = ["date", "ticker", "title", "type", "keywords", "sentiment_score", "source"]
        to_save = events_df[[c for c in csv_cols if c in events_df.columns]].copy()

        if existing.empty:
            combined = to_save
        else:
            combined = pd.concat([existing, to_save], ignore_index=True)
            combined = combined.drop_duplicates(subset=["title"], keep="last")

        # 原子写：先写临时文件再 os.replace，避免事件页并发读取时读到半截事件 CSV
        tmp = f"{self.event_csv_path}.tmp"
        combined.to_csv(tmp, index=False, encoding="utf-8-sig")
        os.replace(tmp, self.event_csv_path)

    def auto_mine_events(self, keyword=None, source="eastmoney", limit=30):
        """兼容旧接口。"""
        return self.mine_events(keyword=keyword, source=source, limit=limit)

    def generate_report(self, keyword=None, limit=50):
        """
        生成完整的新闻分析报告。
        :return: report dict（同 NewsSummarizer.generate_summary + 更多）
        """
        news = self.news_fetcher.fetch(keyword=keyword, source="auto", limit=limit)
        if news.empty:
            return {"total": 0, "top_keywords": [], "sample_news": [],
                    "positive_pct": 0, "negative_pct": 0, "neutral_pct": 0}

        # 去重 + 分析
        news = self.deduplicator.deduplicate(news)
        analyzed = self.sentiment_analyzer.batch_analyze(news)

        # 合并回原 DataFrame
        for col in ["sentiment", "score", "is_major", "pos_words", "neg_words"]:
            if col in analyzed.columns:
                news[col] = analyzed[col].values

        # 保存
        self.db.save_news(news, keyword or "")

        # 摘要
        summary = self.summarizer.generate_summary(news)

        # 样本新闻
        sample_news = []
        major = analyzed[analyzed.get("is_major", False)] if "is_major" in analyzed.columns else pd.DataFrame()
        if not major.empty:
            for _, row in major.head(5).iterrows():
                sample_news.append({
                    "title": row.get("title", "")[:80],
                    "sentiment": row.get("sentiment", ""),
                    "score": row.get("score", 0),
                    "source": row.get("source", ""),
                })
        else:
            for _, row in analyzed.head(5).iterrows():
                sample_news.append({
                    "title": row.get("title", "")[:80],
                    "sentiment": row.get("sentiment", ""),
                    "score": row.get("score", 0),
                    "source": row.get("source", ""),
                })

        summary.update({
            "top_keywords": summary.get("hot_topics", [])[:15],
            "sample_news": sample_news,
            "positive_pct": summary.get("key_stats", {}).get("positive_pct", 0),
            "negative_pct": summary.get("key_stats", {}).get("negative_pct", 0),
            "neutral_pct": summary.get("key_stats", {}).get("neutral_pct", 0),
        })
        return summary

    def sentiment_report(self, keyword=None, limit=50):
        """兼容旧接口。"""
        return self.generate_report(keyword=keyword, limit=limit)

    def get_hot_keywords(self, days=7, topk=20):
        """获取热门关键词（从 DB）。"""
        return self.db.get_hot_keywords(days=days, top_k=topk)

    def alert_check(self, stock_code=None, hours=6):
        """
        重大新闻预警检查。
        查询最近 N 小时内的重大新闻，判断是否需要推送预警。
        :return: list of alert dicts
        """
        since = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")
        query_params = {"date_from": since, "is_major": True, "limit": 20}

        if stock_code:
            query_params["keyword"] = stock_code

        alerts = self.db.query(**query_params)

        results = []
        for _, row in alerts.iterrows():
            score = row.get("sentiment_score", 0)
            results.append({
                "title": row.get("title", ""),
                "sentiment": row.get("sentiment", ""),
                "score": float(score),
                "source": row.get("source", ""),
                "date": str(row.get("date", ""))[:16],
                "alert_level": "HIGH" if abs(score) >= 0.5 else ("MEDIUM" if abs(score) >= 0.3 else "LOW"),
                "action": "关注" if score > 0.2 else ("回避" if score < -0.2 else "观望"),
            })

        # 按紧急程度排序
        results.sort(key=lambda x: abs(x["score"]), reverse=True)
        return results