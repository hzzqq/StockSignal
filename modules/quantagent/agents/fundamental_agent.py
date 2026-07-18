"""
modules/quantagent/agents/fundamental_agent.py
------------------------------------------------
基本面 Agent：分析公司质地（行业、估值、盈利、成长）。

优先复用 StockSignal 的 fetcher.get_fundamentals；离线时给出占位说明，
保证报告完整、不中断。
"""

from __future__ import annotations

from modules.quantagent.agents.base import BaseAgent
from modules.quantagent.state import ResearchState


class FundamentalAgent(BaseAgent):
    name = "fundamental"
    role = "基本面分析师：评估公司质地与估值"

    def run(self, state: ResearchState) -> str:
        ticker = state.ticker
        fundamentals = None
        fetcher = self._safe_import("modules.fetcher", "StockFetcher", state)
        try:
            if fetcher is not None:
                f = fetcher()
                fundamentals = f.get_fundamentals(ticker)
        except Exception as e:  # noqa: BLE001
            state.add_error(f"基本面获取失败: {e}")

        if not fundamentals:
            report = {
                "text": "基本面：离线演示模式下未拉取财务数据；上线后由 fetcher.get_fundamentals 提供行业/PE/PB/ROE 等。",
                "industry": "—",
                "pe": None,
                "pb": None,
                "roe": None,
                "summary": "质地待评估",
            }
            state.fundamental_report = report
            return f"[{self.role}] 离线占位：未获取财务数据"

        ind = fundamentals.get("industry") or "—"
        pe = fundamentals.get("pe")
        pb = fundamentals.get("pb")
        roe = fundamentals.get("roe")
        # 简单质地评分：ROE 高 + 估值合理 → 偏好
        score = 50.0
        try:
            if roe is not None:
                score += min(20.0, float(roe) * 0.4)
            if pe is not None:
                pe_f = float(pe)
                if pe_f < 15:
                    score += 10
                elif pe_f > 60:
                    score -= 10
        except Exception:
            pass
        score = max(0.0, min(100.0, score))
        summary = "质地优良" if score >= 65 else "质地中性" if score >= 45 else "质地偏弱"
        report = {
            "text": f"基本面：行业「{ind}」，PE={pe}，PB={pb}，ROE={roe}；质地评分 {score:.0f}/100（{summary}）。",
            "industry": ind,
            "pe": pe,
            "pb": pb,
            "roe": roe,
            "score": round(score, 1),
            "summary": summary,
        }
        state.fundamental_report = report
        return f"[{self.role}] 行业 {ind}，质地评分 {score:.0f}（{summary}）"
