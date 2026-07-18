"""
modules/quantagent/agents/backtest_agent.py
-------------------------------------------
回测验证 Agent：给首席结论做「历史策略背书」。

这是投研闭环里最有说服力的一环——不只给一个看多/看空的判断，还用同一标的的
历史数据跑一遍量化策略回测，用「历史胜率 / 累计收益 / 最大回撤 / 夏普」来验证
这套多智能体的判断在过去是否站得住脚。

复用 StockSignal 的 modules.backtest.Backtester（multi_factor 策略，已内置佣金万三 /
印花税千一 / 滑点）。放在首席决策之后运行，只附加 state.backtest_report，不改动结论。

离线 / 合成数据 / 回测异常时优雅降级：产出「回测不可用」提示，绝不阻断主流程。
"""

from __future__ import annotations

import datetime as _dt

from modules.quantagent.agents.base import BaseAgent
from modules.quantagent.state import ResearchState


class BacktestAgent(BaseAgent):
    name = "backtest"
    role = "回测验证官：用历史数据检验策略胜率"

    def __init__(self, lookback_days: int = 365, strategy: str = "multi_factor"):
        self.lookback_days = lookback_days
        self.strategy = strategy

    def run(self, state: ResearchState) -> str:
        # 合成数据回测没有现实意义，直接标注跳过
        if not state.used_real_data:
            state.backtest_report = {
                "text": "回测验证：当前为离线合成行情，历史回测不适用（生产环境接真实行情后自动启用）。",
                "available": False,
            }
            return f"[{self.role}] 跳过（离线合成数据）"

        Backtester = self._safe_import("modules.backtest", "Backtester", state)
        if Backtester is None:
            state.backtest_report = {"text": "回测验证：回测引擎不可用。", "available": False}
            return f"[{self.role}] 回测引擎不可用"

        today = _dt.date.today()
        start = (today - _dt.timedelta(days=self.lookback_days)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")

        try:
            bt = Backtester()
            result = bt.run(state.ticker, start=start, end=end, strategy=self.strategy)

            def _safe(fn, default=None):
                try:
                    return fn()
                except Exception:  # noqa: BLE001
                    return default

            total_return = _safe(result.total_return, 0.0)
            win_rate = _safe(result.win_rate, 0.0)
            max_dd = _safe(result.max_drawdown, 0.0)
            sharpe = _safe(result.sharpe_ratio, 0.0)
            pf = _safe(result.profit_factor, 0.0)
            trades = _safe(result.trade_count, 0)

            verdict = state.chief_report.get("verdict", "-")
            # 历史胜率对结论的「印证/存疑」
            if trades and trades >= 2:
                if win_rate >= 55 and total_return > 0:
                    endorse = "✅ 历史回测支持该策略（胜率与收益为正）"
                elif win_rate < 45 or total_return < 0:
                    endorse = "⚠️ 历史回测偏弱，结论需谨慎（近一年策略未跑赢）"
                else:
                    endorse = "➖ 历史回测中性"
            else:
                endorse = "ℹ️ 近一年有效交易样本不足，回测参考价值有限"

            text = (
                f"回测验证（近{self.lookback_days // 30}个月 · {self.strategy} 策略）："
                f"累计收益 {total_return:+.1f}%，胜率 {win_rate:.0f}%，最大回撤 {max_dd:.1f}%，"
                f"夏普 {sharpe:.2f}，盈亏比 {pf:.2f}，交易 {trades} 次。{endorse}"
            )
            state.backtest_report = {
                "text": text,
                "available": True,
                "strategy": self.strategy,
                "total_return": round(float(total_return), 2),
                "win_rate": round(float(win_rate), 1),
                "max_drawdown": round(float(max_dd), 2),
                "sharpe": round(float(sharpe), 2),
                "profit_factor": round(float(pf), 2),
                "trade_count": int(trades),
                "endorsement": endorse,
                "verdict_checked": verdict,
            }
            return (
                f"[{self.role}] 收益 {total_return:+.1f}% / 胜率 {win_rate:.0f}% / "
                f"回撤 {max_dd:.1f}% / {trades} 笔"
            )
        except Exception as e:  # noqa: BLE001
            state.add_error(f"回测验证失败: {e}")
            state.backtest_report = {
                "text": f"回测验证：本次回测未能完成（{e}）。",
                "available": False,
            }
            return f"[{self.role}] 回测未完成：{e}"
