"""
modules/quantagent/agents/chief_agent.py
-----------------------------------------
首席决策 Agent：汇总共识，产出最终投研结论。

输入：数据/基本面/技术面/舆情/风控 五个 Agent 的报告 + FinRAG 注入的上下文。
输出：verdict（看多/看空/持有）、目标价、止损价、综合评分、论证理由。
策略：
  - 有 LLM 时：把结构化结论交给 LLM 生成自然语言论证（更专业、更像真人首席）；
  - 无 LLM 时：规则引擎合成论证，骨架永远可跑；
  - 决策后写入 FinRAG 记忆层，供下次复盘（episodic memory）。
"""

from __future__ import annotations

from modules.quantagent.agents.base import BaseAgent
from modules.quantagent.llm import llm_complete, llm_configured
from modules.quantagent.state import ResearchState


class ChiefAgent(BaseAgent):
    name = "chief"
    role = "首席投研官：综合决策"

    def __init__(self, use_rag: bool = True, finrag=None):
        self.use_rag = use_rag
        self.finrag = finrag

    # -------- 规则合成结构化结论 --------
    def _rule_decision(self, state: ResearchState) -> dict:
        tech = state.technical_report.get("trend_score", 50)
        fund = state.fundamental_report.get("score", 50)
        sent = state.sentiment_report.get("score", 50)
        risk = state.risk_report.get("risk_score", 50)
        # 资金流评分（新增维度）：有则纳入综合，无则退回原四维权重（向后兼容）
        flow = state.fundflow_report.get("flow_score") if state.fundflow_report else None
        if flow is not None:
            # 五维权重：技术 0.25 / 基本面 0.20 / 资金流 0.15 / 舆情 0.20 / 风险 0.20
            composite = (tech * 0.25 + fund * 0.20 + float(flow) * 0.15
                         + sent * 0.20 + (100 - risk) * 0.20)
        else:
            # 原四维权重
            composite = tech * 0.30 + fund * 0.25 + sent * 0.25 + (100 - risk) * 0.20
        composite = max(0.0, min(100.0, composite))
        verdict = "看多" if composite >= 65 else "看空" if composite <= 40 else "持有"

        brief = state.market_brief
        close = float(brief.get("close", 0) or 0)
        low20 = float(brief.get("low_20", close * 0.95) or close * 0.95)
        high20 = float(brief.get("high_20", close * 1.05) or close * 1.05)
        target = round(max(close * 1.10, high20 * 1.02), 2) if close else 0.0
        stop = round(min(close * 0.93, low20 * 0.98), 2) if close else 0.0
        return {
            "verdict": verdict,
            "composite": round(composite, 1),
            "target_price": target,
            "stop_price": stop,
            "tech": round(tech, 1),
            "fund": round(fund, 1),
            "flow": round(float(flow), 1) if flow is not None else None,
            "sent": round(sent, 1),
            "risk": round(risk, 1),
        }

    def _build_prompt(self, state: ResearchState, rule: dict) -> str:
        parts = [
            f"标的：{state.display_name or state.ticker}",
            f"[数据] {state.data_report.get('text','')}",
            f"[基本面] {state.fundamental_report.get('text','')}",
            f"[技术面] {state.technical_report.get('text','')}",
            f"[资金流] {state.fundflow_report.get('text','')}",
            f"[舆情] {state.sentiment_report.get('text','')}",
            f"[风控] {state.risk_report.get('text','')}",
        ]
        if self.use_rag and state.rag_context:
            parts.append(f"[复盘记忆]\n{state.rag_context}")
        parts.append(
            f"规则初步结论：{rule['verdict']}（综合{rule['composite']}，技术{rule['tech']}/基本面{rule['fund']}"
            f"/舆情{rule['sent']}/风险{rule['risk']}），目标价≈{rule['target_price']}，止损≈{rule['stop_price']}。"
        )
        parts.append("请以首席投研官口吻，用 3-4 句话给出最终论证（结论须与规则一致）。")
        return "\n".join(parts)

    def run(self, state: ResearchState) -> str:
        rule = self._rule_decision(state)

        rationale = ""
        if llm_configured():
            try:
                sys_p = (
                    "你是资深首席投研官，风格严谨、数据驱动。只基于提供的事实论证，"
                    "不做无依据承诺，明确提示风险。"
                )
                user_p = self._build_prompt(state, rule)
                out = llm_complete(sys_p, user_p)
                if out:
                    rationale = out.strip()
                    state.used_llm = True
            except Exception as e:  # noqa: BLE001
                state.add_error(f"LLM 决策失败，回退规则论证: {e}")

        if not rationale:
            rationale = (
                f"综合研判为「{rule['verdict']}」（综合评分 {rule['composite']}/100）。"
                f"技术面 {rule['tech']}、基本面 {rule['fund']}、舆情 {rule['sent']}、风险 {rule['risk']}。"
                f"建议目标价 ¥{rule['target_price']}，止损 ¥{rule['stop_price']}，"
                f"请结合仓位上限控制风险，本结论为模型辅助、非投资建议。"
            )

        decision = {
            "verdict": rule["verdict"],
            "composite": rule["composite"],
            "target_price": rule["target_price"],
            "stop_price": rule["stop_price"],
            "scores": {"tech": rule["tech"], "fund": rule["fund"], "flow": rule["flow"],
                       "sent": rule["sent"], "risk": rule["risk"]},
            "rationale": rationale,
        }
        state.chief_report = decision

        # 写入 FinRAG 记忆层（复盘）
        if self.use_rag and self.finrag is not None:
            try:
                self.finrag.save_decision(state.ticker, decision)
                self.finrag.index_report(state.ticker, rationale)
                state.used_rag = True
            except Exception as e:  # noqa: BLE001
                state.add_error(f"FinRAG 记忆写入失败: {e}")

        return f"[{self.role}] 最终结论：{rule['verdict']}（综合 {rule['composite']}）目标¥{rule['target_price']}/止损¥{rule['stop_price']}"
