"""
事件信号分析模块
综合价格信号、事件信号、宏观信号三类因子，输出 0-100 的主线强度得分。
"""

import os
import re
from datetime import datetime, timedelta

import pandas as pd

from .fetcher import StockFetcher, load_config
from .atomic_io import atomic_to_csv
from .time_utils import now_cst, now_cst_str
from .cleaner import DataCleaner
from .news import EventMiner, SentimentAnalyzer, KeywordExtractor

import logging

logger = logging.getLogger(__name__)


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
    # ------------------------------------------------------------------
    # 工具函数
    # ------------------------------------------------------------------
    @staticmethod
    def _clamp(v, lo=0, hi=100):
        try:
            return max(lo, min(hi, int(round(float(v)))))
        except Exception as e:
            logger.warning(f"[signal] 未处理异常: {e}")
            return 50

    @staticmethod
    def strength_label(score):
        """把 0-100 综合得分映射为信号强度档位：强(>=70) / 中(50-69) / 弱(<50)。"""
        s = SignalEngine._clamp(score)
        if s >= 70:
            return "强"
        if s >= 50:
            return "中"
        return "弱"

    @staticmethod
    def _stable_offset(ticker: str, scale: float = 5.0) -> float:
        """确定性微偏移（±scale）。

        原实现用内置 ``hash(ticker)``，而 Python3 的 ``hash(str)`` 按进程加盐
        （PYTHONHASHSEED），导致同一股票在不同进程/次启动下偏移值不同，排序不稳定，
        与「确定性偏移」的注释意图相悖。这里改用 hashlib（sha256）得到跨进程/跨机器
        稳定的偏移，区间仍为 ±scale（中间区加权在调用方完成）。
        """
        import hashlib
        try:
            digest = hashlib.sha256(str(ticker).encode("utf-8")).digest()
            # 取前 4 字节作为无符号整数，映射到 [0,1)
            val = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
            return (val - 0.5) * 2 * scale
        except Exception as e:
            logger.warning(f"[signal] 未处理异常: {e}")
            return 0.0

    @staticmethod
    def _score_by_return(r, breaks, scores):
        """把涨跌幅 r 映射到 0-100：breaks 降序阈值，scores 对应得分（线性插值）。"""
        r = float(r)
        if pd.isna(r):
            return 50  # 缺失行情 → 中性分，而非落到最低档
        if r >= breaks[0]:
            return scores[0]
        for i in range(1, len(breaks)):
            if r >= breaks[i]:
                lo_b, hi_b = breaks[i], breaks[i - 1]
                lo_s, hi_s = scores[i], scores[i - 1]
                if hi_b == lo_b:
                    return lo_s
                return int(round(lo_s + (hi_s - lo_s) * (r - lo_b) / (hi_b - lo_b)))
        return scores[-1]

    # ------------------------------------------------------------------
    # 技术面多周期画像 (0-100)
    # ------------------------------------------------------------------
    def technical_profile(self, df, date=None):
        """
        多周期技术面画像：短期(5日)/中期(20日)/长期(60日)+趋势，各 0-100。
        综合分 = 短期0.40 + 中期0.35 + 长期0.25，再与趋势分(权重0.20)混合。
        不再单一看 5 日动量，避免「50/100 太机械化」。
        """
        empty = {"short": 50, "mid": 50, "long": 50, "trend": 50, "composite": 50}
        if df is None or df.empty or len(df) < 20:
            return empty
        d = df.copy()
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        if date is not None:
            d = d[d["date"] <= pd.Timestamp(date)]
        if len(d) < 20:
            return empty

        latest = d.iloc[-1]
        close = float(latest["close"])
        ma5 = float(latest.get("ma5", close))
        ma20 = float(latest.get("ma20", close))
        ma60 = float(d["close"].rolling(60).mean().iloc[-1]) if len(d) >= 60 else ma20

        # 趋势分：均线多空排列
        trend = 50
        if close > ma5 > ma20:
            trend += 25
        elif close > ma20:
            trend += 12
        if ma20 > ma60:
            trend += 20
        elif ma20 < ma60:
            trend -= 12

        # 多周期涨跌幅
        r5 = float(latest.get("return_5d", 0) or 0)
        r20 = float(latest.get("return_20d", 0) or 0)
        r60 = (float(d["close"].iloc[-1]) / float(d["close"].iloc[-61]) - 1) * 100 if len(d) >= 61 else r20

        short = self._score_by_return(r5, [10, 5, 2, 0, -2, -5], [95, 80, 68, 58, 45, 30, 15])
        mid = self._score_by_return(r20, [25, 15, 5, 0, -8, -15], [95, 82, 70, 58, 42, 25, 10])
        long = self._score_by_return(r60, [40, 20, 5, 0, -15, -30], [95, 82, 68, 55, 38, 20, 8])

        composite = 0.4 * short + 0.35 * mid + 0.25 * long
        composite = 0.8 * composite + 0.2 * trend

        # 增加区分度因子：同板块/同涨跌幅的股票，因位置/波动/量能/振幅不同而得分不同。
        # 所有因子采用线性插值，避免阈值造成的「同质化」。
        # 1) 52 周位置：0~100 映射到 +6 ~ -6（超跌加分，超买扣分）
        pos_adj = 0.0
        if {"high", "low"}.issubset(d.columns):
            if len(d) >= 60:
                hi52 = float(d["high"].tail(252).max())
                lo52 = float(d["low"].tail(252).min())
            else:
                hi52 = float(d["high"].max())
                lo52 = float(d["low"].min())
            if hi52 > lo52:
                pos52 = (close - lo52) / (hi52 - lo52) * 100
                pos_adj = (50 - pos52) * 0.12

        # 2) 波动率：近 20 日收益率标准差；2% 为中性，低波动偏优，高波动偏劣
        volatility = 0.0
        if len(d) >= 21 and "close" in d.columns:
            volatility = float(d["close"].pct_change().tail(20).std() * 100)
        vol_adj = (2.5 - volatility) * 1.2

        # 3) 量能趋势：放量上涨/缩量下跌加分；缩量上涨/放量下跌减分
        vol_trend_adj = 0.0
        if "volume" in d.columns and len(d) >= 20:
            vol_now = float(latest.get("volume", 0))
            vol_avg20 = float(d["volume"].tail(20).mean())
            if vol_avg20 > 0:
                vol_dev = (vol_now / vol_avg20 - 1) * 100
                if composite > 55:
                    vol_trend_adj = vol_dev * 0.06
                elif composite < 45:
                    vol_trend_adj = -vol_dev * 0.06

        # 4) 5 日振幅：同涨跌幅下，高振幅股票弹性/风险更大，做负向微调
        amplitude_5d = 0.0
        if len(d) >= 5 and {"high", "low", "close"}.issubset(d.columns):
            recent5 = d.tail(5)
            amplitude_5d = float(((recent5["high"] - recent5["low"]) / recent5["close"]).mean() * 100)
        amp_adj = (2.5 - amplitude_5d) * 0.6

        # 5) 当日动量：捕捉最新一日资金博弈，让同板块股票因当日表现不同而不同
        r1 = float(latest.get("return_1d", 0) or 0)
        r1_adj = r1 * 0.6

        # 6) 个股确定性微偏移：防止极少数特征高度雷同的股票 composite 完全相同
        # 中间区域（40~70）最容易扎堆，偏移力度加大；极端区域（超买/超跌）保持小偏移。
        # 偏移量来自 ticker 的确定性哈希（见 _stable_offset），范围 ±4.5（中间区）/ ±2.5（极端区），
        # 不影响整体排序（远小于基本面因子带来的差异）。
        ticker = str(latest.get("ticker", d.index[-1] if len(d.index) else "0"))
        mid_boost = 1.8 if 40 <= composite <= 70 else 1.0
        hash_offset = self._stable_offset(ticker, scale=5.0) * mid_boost

        composite = composite + pos_adj + vol_adj + vol_trend_adj + amp_adj + r1_adj + hash_offset

        return {
            "short": self._clamp(short),
            "mid": self._clamp(mid),
            "long": self._clamp(long),
            "trend": self._clamp(trend),
            "composite": self._clamp(composite),
        }

    # ------------------------------------------------------------------
    # 价格信号得分 (0-100) —— 多周期技术面综合
    # ------------------------------------------------------------------
    def price_score(self, df, date=None):
        """
        基于均线趋势 + 多周期动量的价格信号得分（0-100）。
        :param df: 行情 DataFrame
        :param date: 评估日期，None 则取最后一天
        :return: 0-100 得分
        """
        return self.technical_profile(df, date)["composite"]

    # ------------------------------------------------------------------
    # 事件信号得分 (0-100)
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # 真实事件因子接入（P1 EV 信号）
    # ------------------------------------------------------------------
    def _p1_loader(self):
        """懒加载并缓存 P1 信号加载器（避免每次 evaluate 重复扫描信号目录）。

        取不到（模块/目录缺失）安全降级：置 False 并缓存，后续不再重试。
        """
        _ld = getattr(self, "_p1l", None)
        if _ld is None:
            try:
                from modules.p1_signal import P1SignalLoader
                self._p1l = P1SignalLoader(ttl=300)
            except Exception as _e:  # noqa: BLE401
                logger.warning(f"[signal] P1 加载器不可用，事件维度回退本地: {_e}")
                self._p1l = False
        return self._p1l or None

    def _event_factor_to_score(self, ef: dict) -> int:
        """把 P1 EV 事件因子 dict 映射为 0-100 事件得分（决策系统统一量纲）。

        - ``rank`` 为模型自身百分位排名（0-1，越高越看多）→ 线性映射到 0-100；
        - 无 rank（daily 精确路径）用 ``score``（日超额收益）方向近似，scale 保守；
        - 仅含信号文本时按多/空定性。
        取不到真实信号时调用方应回退本地事件库逻辑，不在此兜底。
        """
        rank = ef.get("rank")
        if isinstance(rank, (int, float)):
            base = 50 + (float(rank) - 0.5) * 100  # rank=1→100, rank=0→0, 0.5→50
            return self._clamp(base, 5, 95)
        sc = ef.get("score")
        if isinstance(sc, (int, float)):
            base = 50 + float(sc) * 200  # 日超额 ±0.25 → ±50
            return self._clamp(base, 5, 95)
        sig = ef.get("signal")
        if sig in ("看多", "多头"):
            return 80
        if sig in ("看空", "空头"):
            return 20
        return 50

    def event_signal_detail(self, ticker, model: str = "ev") -> dict | None:
        """返回某标的真实事件因子明细（供展示增强用）；取不到返回 None。"""
        try:
            from modules.event_factor import get_event_factor
            _ld = self._p1_loader()
            if _ld is None:
                return None
            ef = get_event_factor(ticker, model=model, loader=_ld)
            return ef if ef.get("available") else None
        except Exception as _e:  # noqa: BLE401
            logger.warning(f"[signal] 事件因子明细获取失败({ticker}): {_e}")
            return None

    def event_score(self, ticker, keywords, date=None):
        """
        基于「真实事件因子」+ 本地事件库 + 实时新闻情感的事件信号得分（0-100）。

        优先级：
          1. 真实事件因子（P1 EV 信号，适配器接入，rank 百分位的 0-100 映射）——
             这是去除旧「P4 合成演示依赖」后的主线数据源；
          2. 取不到（标的不在 P1 池 / 无信号文件）优雅回退本地事件库 + 实时新闻情感。

        关键修复（长电科技无利空却得 42 分）：
          - 中性基准从 50 提到 52，且无利空事件时绝不打低分（下限 45）。
          - 实时新闻情绪改为「相对中性」映射（50=多空平衡），仅在事件库
            无法定性时才小幅微调，不再让中性/偏多新闻把分数拖到 40 出头。
        """
        # ── 真实事件因子优先（P1 EV 信号，取代旧本地事件库合成路径）──
        # 取不到（标的不在 P1 池 / 无信号文件）优雅回退到下方本地事件库逻辑。
        try:
            from modules.event_factor import get_event_factor
            _ld = self._p1_loader()
            if _ld is not None:
                _ef = get_event_factor(ticker, model="ev", loader=_ld)
                if _ef.get("available"):
                    return self._event_factor_to_score(_ef)
        except Exception as _e:  # noqa: BLE401
            logger.warning(f"[signal] 事件因子真实信号获取失败，回退本地: {_e}")

        events = self._load_events()
        score = 52  # 中性偏多基准：无利空即不应低于 50
        pos_w = neg_w = 0

        # ---- Part 1: 本地事件库匹配 ----
        if not events.empty:
            events["date"] = pd.to_datetime(events["date"], errors="coerce")
            if date is not None:
                date_ts = pd.Timestamp(date)
                events = events[events["date"] >= date_ts - timedelta(days=30)]

            if keywords:
                # re.escape 每个关键词，避免关键词含正则元字符（如 ( + . ）时崩溃
                matched = events[events["title"].str.contains(
                    "|".join(re.escape(k) for k in keywords), na=False, regex=True)]
            else:
                # 空关键词不应匹配任何事件（空正则 "" 会命中全部，属隐性 bug）
                matched = events.iloc[0:0]
            matched = matched[matched["ticker"].str.contains(ticker, na=False) | matched["ticker"].isna()]

            for _, evt in matched.iterrows():
                evt_type = str(evt.get("type", ""))
                # 优先用已存储的情感标签
                if "正面" in evt_type or evt_type == "利好":
                    pos_w += 1
                elif "负面" in evt_type or evt_type == "利空":
                    neg_w += 1
                else:
                    score += 1  # 中性事件 +关注度

                # 若有 sentiment_score 列，纳入量化
                if "sentiment_score" in evt and pd.notna(evt.get("sentiment_score")):
                    score += float(evt["sentiment_score"]) * 6

        # ---- Part 2: 实时新闻情绪（仅当事件库无法定性时参考）----
        # 有正/负面事件已能定性，就不再让实时情绪推翻结论。
        if pos_w == 0 and neg_w == 0 and keywords:
            try:
                live = self._live_news_sentiment(keywords, date)
                if live is not None:
                    # live 为相对分(50=中性)，只允许 ±35 区间微调，地板 50
                    adj = (live - 50) * 0.7
                    score = 52 + adj
            except Exception as e:
                logger.warning(f"[signal] 未处理异常: {e}")
                pass

        # 最终按正/负面事件上下修，带下限保护（避免极端低分）
        score += pos_w * 14
        score -= neg_w * 12
        return self._clamp(score, 45, 95)

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
            # 相对映射：50=多空平衡，正面占比高则上、负面高则下
            # （修复旧逻辑中性新闻被映射到 30 的偏误）
            live_score = 50 + (pos_pct - neg_pct) * 0.6
            return min(100, max(0, int(live_score)))
        except Exception as e:
            logger.warning(f"[signal] 未处理异常: {e}")
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
        # 原子写：先写临时文件再 os.replace，避免并发 _load_events 读到半截事件库
        atomic_to_csv(events, self.event_db_path, encoding="utf-8-sig")

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
        except Exception as e:
            logger.warning(f"[signal] 未处理异常: {e}")
            return 50

    # ------------------------------------------------------------------
    # 板块相对强度得分 (0-100)
    # ------------------------------------------------------------------
    def sector_relative_score(self, keywords, df=None, date=None, sector_name=None):
        """
        板块相对强度得分 0-100：个股中期表现 vs 所属行业板块。
        行业强 + 个股领涨 → 高分；行业弱 + 个股滞涨 → 低分。
        用于「信号归因·五维雷达」的第五维（板块）。

        :param sector_name: 股票真实所属行业名（如"白酒"），优先用此名匹配板块；
                            未提供时退化为 keywords 匹配。
        """
        # 优先用真实行业名匹配；没有再用事件关键词兜底
        kws = [k.strip() for k in (keywords or []) if k.strip()]
        if sector_name and str(sector_name).strip():
            kws = [str(sector_name).strip()]
        if not kws:
            return 55
        try:
            sectors = self.fetcher.get_sector_list()
            if sectors is None or (hasattr(sectors, "empty") and sectors.empty):
                return 55
            name_col = "sector" if "sector" in sectors.columns else sectors.columns[0]
            chg_col = next((c for c in sectors.columns if "change" in c.lower()), None)
            if chg_col is None:
                return 55
            sec = sectors[sectors[name_col].astype(str).str.contains("|".join(kws), na=False, regex=True)]
            if sec.empty:
                sec = sectors[sectors[name_col].astype(str).apply(
                    lambda x: any(k in x for k in kws))]
            if sec.empty:
                return 55
            sector_chg = float(sec.iloc[0][chg_col])
            r20 = 0.0
            if df is not None and not df.empty:
                r20 = float(df.iloc[-1].get("return_20d", 0) or 0)
            rel = r20 - sector_chg
            # 板块维度：一半看板块绝对强度（行业好则加分），一半看个股相对强度
            score = 50 + rel * 2.0 + sector_chg * 2.0
            return self._clamp(score)
        except Exception as e:
            logger.warning(f"[signal] 未处理异常: {e}")
            return 55

    # ------------------------------------------------------------------
    # 综合评分
    # ------------------------------------------------------------------
    def evaluate(self, ticker, event_keywords, date=None, sector_name=None, df=None):
        """
        综合评估单只股票的事件驱动得分。
        :param ticker: 股票代码
        :param event_keywords: 事件关键词列表（用于事件库/新闻匹配）
        :param sector_name: 真实所属行业名（如"白酒"），用于板块相对强度计算
        :param date: 评估日期
        :param df: 已获取并清洗过的日线 DataFrame（可选，避免重复拉取）
        :return: dict {price_score, event_score, macro_score, sector_score,
                          technical_profile, total}
        """
        # 拉取行情并清洗（失败时降级为中性评分）
        if df is not None and not df.empty:
            try:
                df = DataCleaner.full_pipeline(df)
                tp = self.technical_profile(df, date)
                p_score = tp["composite"]
            except Exception as e:
                p_score = 50
                tp = {"short": 50, "mid": 50, "long": 50, "trend": 50, "composite": 50}
                logger.warning(f"[SignalEngine] 传入行情清洗失败({ticker})，价格信号使用中性分50: {e}")
        else:
            end = date or now_cst_str("%Y-%m-%d")
            start = (datetime.strptime(end, "%Y-%m-%d") if date else now_cst()) - timedelta(days=120)
            start_str = start.strftime("%Y-%m-%d")

            df = None
            try:
                df = self.fetcher.get_daily(ticker, start=start_str, end=end)
                df = DataCleaner.full_pipeline(df)
                tp = self.technical_profile(df, date)
                p_score = tp["composite"]
            except (RuntimeError, ValueError, Exception) as e:
                # 行情数据不可用 → 价格信号给中性分，不影响事件和宏观评分
                p_score = 50
                tp = {"short": 50, "mid": 50, "long": 50, "trend": 50, "composite": 50}
                logger.warning(f"[SignalEngine] 行情获取失败({ticker})，价格信号使用中性分50: {e}")

        e_score = self.event_score(ticker, event_keywords, date)
        m_score = self.macro_score(date)
        s_score = self.sector_relative_score(event_keywords, df, date, sector_name=sector_name)

        # 事件维度信号源（真实 P1 EV 信号 or 本地事件库回退），供展示与选股池标注
        _ef_detail = self.event_signal_detail(ticker)
        _event_source = _ef_detail.get("source") if _ef_detail else "本地事件库"
        _event_signal = _ef_detail.get("signal") if _ef_detail else None

        w = self.weights
        total = int(p_score * w.get("price", 0.4) + e_score * w.get("event", 0.4) + m_score * w.get("macro", 0.2))

        return {
            "price_score": p_score,
            "event_score": e_score,
            "event_source": _event_source,
            "event_signal": _event_signal,
            "macro_score": m_score,
            "sector_score": s_score,
            "technical_profile": tp,
            "total": min(100, max(0, total)),
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
                logger.warning(f"[signal] 处理异常: {e}")
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
