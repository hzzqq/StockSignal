"""
modules/quantagent/agents/technical_agent.py
---------------------------------------------
技术面 Agent：趋势 / 动量 / 量能 / K线形态。

复用 StockSignal 的 technical.full_analysis（吃 DataAgent 产出的标准行情）；
若计算异常，回退到基于均线的轻量 heuristic，保证有产出。
"""

from __future__ import annotations

import pandas as pd

from modules.quantagent.agents.base import BaseAgent
from modules.quantagent.state import ResearchState, resolve_df


def _heuristic(df: pd.DataFrame) -> dict:
    """无 modules.technical 时的轻量技术研判。"""
    close = float(df.iloc[-1]["close"])
    ma_map = {w: float(df["close"].rolling(w).mean().iloc[-1]) for w in (5, 10, 20, 60) if len(df) >= w}
    above = sum(1 for v in ma_map.values() if close > v)
    if ma_map and ma_map.get(5, 0) > ma_map.get(20, 0) and close > ma_map.get(5, 0):
        arr, tscore = "多头排列", 80
    elif ma_map and ma_map.get(5, 0) < ma_map.get(20, 0) and close < ma_map.get(5, 0):
        arr, tscore = "空头排列", 20
    else:
        arr, tscore = "纠缠", 50
    return {"trend": {"arrangement": arr, "trend_score": tscore, "above_count": above},
            "momentum": {"label": "—"}, "volume": {"volume_price_score": 50},
            "patterns": [], "score": tscore}


class TechnicalAgent(BaseAgent):
    name = "technical"
    role = "技术分析师：解读趋势/动量/量能/形态"

    def run(self, state: ResearchState) -> str:
        df = resolve_df(state)
        tech = None
        full = self._safe_import("modules.technical", "full_analysis", state)
        try:
            if full is not None and df is not None:
                tech = full(df)
        except Exception as e:  # noqa: BLE001
            state.add_error(f"技术面计算异常，回退 heuristic: {e}")

        if not isinstance(tech, dict) or tech.get("error"):
            tech = _heuristic(df) if df is not None else {}

        trend = tech.get("trend", {})
        momentum = tech.get("momentum", {})
        volume = tech.get("volume", {})
        patterns = tech.get("patterns", []) or []
        arr = trend.get("arrangement", "—")
        tscore = self._num(trend.get("trend_score", 50))
        vol_score = self._num(volume.get("volume_price_score", 50))
        pat_txt = "、".join([p.get("name", "") for p in patterns[:3] if isinstance(p, dict)]) or "无明显形态"

        report = {
            "text": (
                f"技术面：{arr}，趋势强度 {tscore:.0f}/100；量能评分 {vol_score:.0f}/100；"
                f"近期形态：{pat_txt}。"
            ),
            "arrangement": arr,
            "trend_score": round(tscore, 1),
            "volume_score": round(vol_score, 1),
            "patterns": pat_txt,
            "momentum_label": momentum.get("label", "—"),
            "raw": tech,
        }
        state.technical_report = report
        return f"[{self.role}] {arr}，趋势 {tscore:.0f} / 量能 {vol_score:.0f}"
