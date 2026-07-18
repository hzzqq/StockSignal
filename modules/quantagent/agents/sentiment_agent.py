"""
modules/quantagent/agents/sentiment_agent.py
---------------------------------------------
舆情 Agent：新闻情感 + FinBrowser 网页舆情。

复用 StockSignal 的 NewsFetcher + SentimentAnalyzer（jieba + snownlp）；
并调用 FinBrowser 采集外挂补充网页端舆情，体现「多源融合」。
"""

from __future__ import annotations

from modules.quantagent.agents.base import BaseAgent
from modules.quantagent.browser_plugin import BrowserAgent
from modules.quantagent.state import ResearchState


class SentimentAgent(BaseAgent):
    name = "sentiment"
    role = "舆情分析师：新闻+网页情绪"

    def __init__(self, use_browser: bool = True):
        self.use_browser = use_browser

    def run(self, state: ResearchState) -> str:
        name = state.display_name or state.ticker
        pos_pct = neg_pct = 0.0
        headlines = []
        NewsFetcher = self._safe_import("modules.news", "NewsFetcher", state)
        SentimentAnalyzer = self._safe_import("modules.news", "SentimentAnalyzer", state)
        try:
            if NewsFetcher is not None and SentimentAnalyzer is not None:
                nf = NewsFetcher()
                df = nf.fetch(keyword=name, source="auto", limit=50)
                sa = SentimentAnalyzer()
                if df is not None and not getattr(df, "empty", True):
                    pos = neg = neu = 0
                    for _, row in df.head(12).iterrows():
                        s = sa.analyze_news(str(row.get("title", "")), str(row.get("content", "")))
                        lab = s.get("sentiment", "中性")
                        if lab == "正面":
                            pos += 1
                        elif lab == "负面":
                            neg += 1
                        else:
                            neu += 1
                        headlines.append(str(row.get("title", ""))[:40])
                    total = max(1, pos + neg + neu)
                    pos_pct = pos / total * 100
                    neg_pct = neg / total * 100
        except Exception as e:  # noqa: BLE001
            state.add_error(f"新闻舆情获取失败: {e}")

        web_signal = 0.0
        web_sample = ""
        if self.use_browser:
            try:
                bc = BrowserAgent()
                web = bc.fetch_web_sentiment(state.ticker)
                web_signal = float(web.get("signal", 0.0))
                web_sample = web.get("sample", "")
                state.used_browser = True
            except Exception as e:  # noqa: BLE001
                state.add_error(f"FinBrowser 调用失败: {e}")

        # 综合舆情分（0-100，50 中性）
        score = 50.0 + (pos_pct - neg_pct) * 0.3 + web_signal * 10
        score = max(0.0, min(100.0, score))
        label = "偏多" if score >= 60 else "偏空" if score <= 40 else "中性"
        report = {
            "text": (
                f"舆情：新闻正面 {pos_pct:.0f}% / 负面 {neg_pct:.0f}%，网页信号 {web_signal:+.1f}；"
                f"综合舆情分 {score:.0f}/100（{label}）。{web_sample}"
            ),
            "pos_pct": round(pos_pct, 1),
            "neg_pct": round(neg_pct, 1),
            "web_signal": web_signal,
            "score": round(score, 1),
            "label": label,
            "headlines": headlines[:5],
        }
        state.sentiment_report = report
        return f"[{self.role}] 舆情 {label}，得分 {score:.0f}（新闻±{pos_pct:.0f}/{neg_pct:.0f}，网页 {web_signal:+.1f}）"
