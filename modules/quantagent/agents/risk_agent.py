"""
modules/quantagent/agents/risk_agent.py
----------------------------------------
风控 Agent：回测验证 + 波动率风险 + 仓位建议。

优先复用 StockSignal 的 Backtester 验证策略历史表现；
离线时用行情收益率标准差估算波动率，给出风险评分与仓位上限建议。
"""

from __future__ import annotations

import datetime as _dt

import pandas as pd

from modules.quantagent.agents.base import BaseAgent
from modules.quantagent.state import ResearchState, resolve_df


def _vol_risk(df: pd.DataFrame) -> dict:
    """无回测时的波动率风险估算。"""
    if df is None or "close" not in df:
        return {"annual_vol": 0.3, "max_drawdown": 0.2, "sharpe": 0.0, "win_rate": 0.5}
    rets = df["close"].pct_change().dropna()
    daily_vol = float(rets.std()) if len(rets) else 0.02
    annual_vol = daily_vol * (252 ** 0.5)
    roll_max = df["close"].cummax()
    dd = (df["close"] - roll_max) / roll_max
    max_dd = float(dd.min()) if len(dd) else -0.2
    # 简易夏普（无风险利率≈0）
    sharpe = (rets.mean() / rets.std() * (252 ** 0.5)) if rets.std() else 0.0
    win_rate = float((rets > 0).mean()) if len(rets) else 0.5
    return {
        "annual_vol": round(annual_vol, 3),
        "max_drawdown": round(abs(max_dd), 3),
        "sharpe": round(float(sharpe), 2),
        "win_rate": round(win_rate, 3),
    }


class RiskAgent(BaseAgent):
    name = "risk"
    role = "风控官：回测验证与仓位约束"

    def run(self, state: ResearchState) -> str:
        ticker = state.ticker
        df = resolve_df(state)
        metrics = None
        Backtester = self._safe_import("modules.backtest", "Backtester", state)
        try:
            if Backtester is not None and df is not None:
                today = _dt.date.today()
                start = (today - _dt.timedelta(days=365)).strftime("%Y-%m-%d")
                end = today.strftime("%Y-%m-%d")
                bt = Backtester().run(ticker, start, end, strategy="multi_factor")
                metrics = {
                    "annual_vol": getattr(bt, "annual_vol", None),
                    "max_drawdown": getattr(bt, "max_drawdown", None),
                    "sharpe": getattr(bt, "sharpe_ratio", None),
                    "win_rate": getattr(bt, "win_rate", None),
                }
        except Exception as e:  # noqa: BLE001
            state.add_error(f"回测失败，回退波动率估算: {e}")

        if not metrics or metrics.get("annual_vol") is None:
            metrics = _vol_risk(df)

        av = float(metrics.get("annual_vol", 0.3))
        mdd = float(metrics.get("max_drawdown", 0.2))
        sharpe = float(metrics.get("sharpe", 0.0))
        # 风险评分：波动与回撤越大风险越高（0-100）
        risk_score = max(0.0, min(100.0, av * 120 + mdd * 100))
        # 仓位上限：风险越高仓位越低
        pos_cap = max(0.1, 0.8 - risk_score / 100 * 0.6)
        verdict = "高风险" if risk_score >= 60 else "中等风险" if risk_score >= 35 else "低风险"
        report = {
            "text": (
                f"风控：年化波动 {av*100:.1f}%，最大回撤 {mdd*100:.1f}%，夏普 {sharpe:.2f}；"
                f"风险评分 {risk_score:.0f}/100（{verdict}），建议单标的仓位上限 {pos_cap*100:.0f}%。"
            ),
            "annual_vol": av,
            "max_drawdown": mdd,
            "sharpe": sharpe,
            "risk_score": round(risk_score, 1),
            "position_cap": round(pos_cap, 2),
            "verdict": verdict,
        }
        state.risk_report = report
        return f"[{self.role}] {verdict}，风险 {risk_score:.0f}，仓位上限 {pos_cap*100:.0f}%"
