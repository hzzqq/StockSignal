"""
modules/quantagent/agents/fundflow_agent.py
-------------------------------------------
资金流 Agent：主力/大单/超大单资金动向研判。

复用 StockSignal 的 modules.fundflow.get_individual_fund_flow（真实 akshare 个股资金流，
不可用时内置「量价模型」估算主力净流入），把资金面折算成 0-100 的 flow_score，
供首席决策纳入综合评分（技术面之外的「聪明钱」视角）。

设计原则（与其余 Agent 一致）：
- 全部外部调用 try/except，真实数据拿不到时回退到基于 state.df 的量价 heuristic；
- 只写 state.fundflow_report，不改动其它 Agent 的字段，向后兼容。
"""

from __future__ import annotations

from modules.quantagent.agents.base import BaseAgent
from modules.quantagent.state import ResearchState, resolve_df


def _score_from_flow(main_net, main_net_pct) -> float:
    """把主力净流入折算成 0-100 评分（50 为中性）。"""
    if main_net_pct is not None:
        # 净占比（%）直接放大映射：+8% → 70，-8% → 30
        return max(0.0, min(100.0, 50.0 + float(main_net_pct) * 2.5))
    if main_net is not None:
        # 无占比时只用符号 + 量级档位
        v = float(main_net)
        if v == 0:
            return 50.0
        mag = min(abs(v) / 1e8, 3.0)  # 以亿为单位，最多 3 档
        step = 8.0 + mag * 6.0        # 8~26 分的偏移
        return max(0.0, min(100.0, 50.0 + (step if v > 0 else -step)))
    return 50.0


def _heuristic_score(df) -> tuple[float, str]:
    """无资金流数据时，用近 5 日量价关系估算「资金意愿」。"""
    try:
        tail = df.tail(6)
        ret5 = (float(tail.iloc[-1]["close"]) / float(tail.iloc[0]["close"]) - 1) * 100
        vol_now = float(df["volume"].tail(5).mean())
        vol_base = float(df["volume"].tail(20).mean()) or vol_now or 1.0
        vol_ratio = vol_now / vol_base if vol_base else 1.0
        # 放量上涨→资金流入；缩量下跌→资金流出
        score = 50.0 + ret5 * 1.8 + (vol_ratio - 1.0) * 20.0 * (1 if ret5 >= 0 else -1)
        score = max(0.0, min(100.0, score))
        note = f"近5日涨跌 {ret5:+.1f}%、量比 {vol_ratio:.2f}（量价估算）"
        return round(score, 1), note
    except Exception:
        return 50.0, "数据不足，取中性"


def _fmt_wan_yi(v) -> str:
    if v is None:
        return "—"
    v = float(v)
    if abs(v) >= 1e8:
        return f"{v / 1e8:.2f}亿"
    if abs(v) >= 1e4:
        return f"{v / 1e4:.1f}万"
    return f"{v:.0f}"


class FundFlowAgent(BaseAgent):
    name = "fundflow"
    role = "资金流分析师：主力/大单/北向资金动向"

    def run(self, state: ResearchState) -> str:
        df = resolve_df(state)
        flow = None
        getter = self._safe_import("modules.fundflow", "get_individual_fund_flow", state)
        try:
            if getter is not None:
                flow = getter(state.ticker)
        except Exception as e:  # noqa: BLE001
            state.add_error(f"资金流获取失败，回退量价估算: {e}")

        if isinstance(flow, dict) and flow.get("source") in ("akshare", "estimate"):
            main = flow.get("main_net")
            pct = flow.get("main_net_pct")
            score = round(_score_from_flow(main, pct), 1)
            src_label = "真实资金流(akshare)" if flow.get("source") == "akshare" else "量价估算"
            direction = "净流入" if (main or 0) > 0 else "净流出" if (main or 0) < 0 else "基本持平"
            pct_txt = f"，净占比 {pct:+.2f}%" if pct is not None else ""
            text = (
                f"资金面：主力{direction} {_fmt_wan_yi(main)}{pct_txt}"
                f"（超大单 {_fmt_wan_yi(flow.get('super_net'))} / 大单 {_fmt_wan_yi(flow.get('big_net'))}）；"
                f"资金评分 {score:.0f}/100（{src_label}）。"
            )
        else:
            score, note = _heuristic_score(df) if df is not None else (50.0, "无行情数据")
            main = pct = None
            src_label = "量价估算"
            direction = "偏多" if score >= 55 else "偏空" if score <= 45 else "中性"
            text = f"资金面：{note}，方向{direction}；资金评分 {score:.0f}/100（{src_label}）。"

        state.fundflow_report = {
            "text": text,
            "flow_score": score,
            "main_net": main,
            "main_net_pct": pct,
            "super_net": flow.get("super_net") if isinstance(flow, dict) else None,
            "big_net": flow.get("big_net") if isinstance(flow, dict) else None,
            "source": src_label,
            "latest_date": flow.get("latest_date") if isinstance(flow, dict) else None,
        }
        return f"[{self.role}] 资金评分 {score:.0f}/100（{src_label}）"
