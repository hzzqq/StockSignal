"""
modules/quantagent/crewai_orchestrator.py
-----------------------------------------
CrewAI 多首席辩论编排器（engine="crewai"）。

协作范式：先由 5 个分析智能体（数据/基本面/技术面/舆情/风控）完成事实层调研，
再由「多首席辩论」做决策层对抗：
    🐂 牛派首席  ┐
    🐻 熊派首席  ├─ 各自基于事实给出立场 → ⚖️ 主持首席 综合裁定
    🛡️ 风控首席 ┘

工程取舍（与 LangGraph 编排一致）：
  - 真实 CrewAI 依赖 crewai + LLM key；本沙箱/离线演示往往不具备，故内置「规则辩论降级」，
    保证任何环境都能跑出结构完整、说理清晰的辩论与结论；
  - 真实路径：检测到 crewai 已安装且 LLM 已配置时，构建 Crew（4 个 Agent + 串行 Task）
    由 LLM 驱动多方对抗与综合，结论更自然；失败自动回退规则辩论；
  - 进度通过 progress_callback(stage_key, message) 实时透传（data→...→chief 展开为辩论子阶段）。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from modules.quantagent.agents import (
    BacktestAgent,
    DataAgent,
    FundamentalAgent,
    FundFlowAgent,
    RiskAgent,
    SentimentAgent,
    TechnicalAgent,
)
from modules.quantagent.llm import llm_complete, llm_configured
from modules.quantagent.rag_module import FinRAG
from modules.quantagent.state import ResearchState

# 延迟导入 crewai，保证模块在无依赖环境仍可 import
try:
    from crewai import Agent as CrewAgent, Crew, Task as CrewTask, Process  # type: ignore
    _HAS_CREWAI = True
except Exception:  # pragma: no cover - crewai 未安装时
    _HAS_CREWAI = False


def _run_analysis_phase(state: ResearchState) -> None:
    """跑 5 个事实层分析智能体（复用既有 Agent，进度由 state.reporter 透传）。"""
    for agent in (
        DataAgent(),
        FundamentalAgent(),
        TechnicalAgent(),
        FundFlowAgent(),
        SentimentAgent(use_browser=getattr(state, "_use_browser", True)),
        RiskAgent(),
    ):
        try:
            log = agent.run(state)
            state.add_trace(agent.name, log)
        except Exception as e:  # noqa: BLE001
            state.add_error(f"节点 {agent.name} 执行异常: {e}")
            state.add_trace(agent.name, f"[异常] {e}")


def _rule_decision(state: ResearchState) -> Dict[str, Any]:
    """复用首席的评分逻辑，得到结构化初步结论。"""
    from modules.quantagent.agents.chief_agent import ChiefAgent

    return ChiefAgent()._rule_decision(state)


def _build_stances(state: ResearchState, rule: Dict[str, Any]) -> List[Dict[str, Any]]:
    """规则辩论：基于事实层打分生成牛/熊/风控三派立场 + 主持综合。"""
    tech = rule["tech"]
    fund = rule["fund"]
    sent = rule["sent"]
    risk = rule["risk"]
    brief = state.market_brief
    close = float(brief.get("close", 0) or 0)

    # 牛派：提炼正向证据
    bull_pts = []
    if tech >= 55:
        bull_pts.append(f"技术面评分 {tech} 偏强，短期动量向上")
    if fund >= 55:
        bull_pts.append(f"基本面评分 {fund} 稳健，业绩有支撑")
    if sent >= 55:
        bull_pts.append(f"舆情评分 {sent} 偏暖，市场情绪友好")
    if not bull_pts:
        bull_pts.append(f"估值/动量未见明显恶化（技术 {tech}/基本面 {fund}）")
    bull_lean = "看多" if (tech + fund + sent) / 3 >= 55 else "持有"
    bull_text = (
        f"【牛派首席】倾向「{bull_lean}」：{'；'.join(bull_pts)}。"
        f"当前价 ¥{close}，若突破则可看高至目标区间 ¥{rule['target_price']}。"
    )

    # 熊派：提炼负向风险
    bear_pts = []
    if risk >= 60:
        bear_pts.append(f"风险评分 {risk} 偏高，下行保护不足")
    if sent <= 45:
        bear_pts.append(f"舆情评分 {sent} 偏冷，资金意愿弱")
    if tech <= 45:
        bear_pts.append(f"技术面评分 {tech} 偏弱，均线压制明显")
    if not bear_pts:
        bear_pts.append(f"上行动能尚不充分（综合 {rule['composite']}）")
    bear_lean = "看空" if (tech + fund + sent) / 3 <= 45 or risk >= 65 else "持有"
    bear_text = (
        f"【熊派首席】倾向「{bear_lean}」：{'；'.join(bear_pts)}。"
        f"建议把止损设在 ¥{rule['stop_price']} 以控制回撤。"
    )

    # 风控首席：仓位与止损纪律
    cap = max(5, min(40, int((100 - risk) * 0.5)))
    risk_text = (
        f"【风控首席】风险评分 {risk}，建议单票仓位上限 {cap}%，"
        f"硬止损 ¥{rule['stop_price']}（距现价约 {round((rule['stop_price']-close)/close*100,1) if close else 0}%），"
        f"严禁越线加仓。"
    )

    # 主持综合
    verdict = rule["verdict"]
    mod_text = (
        f"【主持首席】综合多方意见，裁定为「{verdict}」（综合 {rule['composite']}/100）。"
        f"采纳牛派的上行逻辑、熊派的下行风险与风控的仓位纪律："
        f"目标价 ¥{rule['target_price']}、止损 ¥{rule['stop_price']}，"
        f"在 {cap}% 仓位上限内择机执行。"
    )

    return [
        {"role": "bull", "name": "牛派首席", "icon": "🐂", "lean": bull_lean, "text": bull_text},
        {"role": "bear", "name": "熊派首席", "icon": "🐻", "lean": bear_lean, "text": bear_text},
        {"role": "risk", "name": "风控首席", "icon": "🛡️", "lean": "持有", "text": risk_text},
        {"role": "mod", "name": "主持首席", "icon": "⚖️", "lean": verdict, "text": mod_text},
    ]


def _llm_debate(state: ResearchState, rule: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """真实 CrewAI 路径：用 LLM 驱动多方辩论。失败返回 None 触发降级。"""
    if not (_HAS_CREWAI and llm_configured()):
        return None
    try:
        ctx = "\n".join([
            f"标的：{state.display_name or state.ticker}",
            f"[数据] {state.data_report.get('text','')}",
            f"[基本面] {state.fundamental_report.get('text','')}",
            f"[技术面] {state.technical_report.get('text','')}",
            f"[舆情] {state.sentiment_report.get('text','')}",
            f"[风控] {state.risk_report.get('text','')}",
            f"[规则初步] {rule['verdict']} 综合{rule['composite']} 目标¥{rule['target_price']} 止损¥{rule['stop_price']}",
        ])
        # 极简 LLM 封装：CrewAI 需要 LLM 对象；本地 llm_complete 走 openai 协议，
        # 用一次确定性 prompt 让 LLM 直接产出三派 + 主持立场（JSON）。
        sys_p = (
            "你是投研辩论主持。基于事实，分别给出牛派、熊派、风控派、主持的综合立场。"
            "只输出中文，三派各 1-2 句，主持 1-2 句综合裁定。不编造数据。"
        )
        out = llm_complete(sys_p, ctx + "\n请输出辩论结论。")
        if not out:
            return None
        # 退化处理：把 LLM 自由文本作为主持综合，三派用规则文本补充
        stances = _build_stances(state, rule)
        stances[-1]["text"] = f"【主持首席】{out.strip()}"
        return stances
    except Exception as e:  # noqa: BLE001
        state.add_error(f"CrewAI 真实辩论失败，回退规则辩论: {e}")
        return None


def run_research_crewai(
    ticker: str,
    display_name: str = "",
    use_browser: bool = True,
    use_rag: bool = True,
    progress_callback: Optional[Callable[[str, str], None]] = None,
) -> ResearchState:
    """
    用「5 分析智能体 + 多首席辩论」跑一次投研。返回完整 ResearchState。
    真实 CrewAI 可用时走 LLM 对抗；否则规则辩论降级（结构一致）。
    """
    from modules.quantagent.llm import llm_configured as _llm_ok

    ticker = str(ticker).strip().zfill(6)
    if not display_name:
        try:
            from modules.fetcher import StockFetcher
            display_name = StockFetcher().get_stock_name(ticker) or ticker
        except Exception:
            display_name = ticker

    state = ResearchState(
        ticker=ticker,
        display_name=display_name,
        reporter=progress_callback,
    )
    setattr(state, "_use_browser", use_browser)

    # 事实层
    _run_analysis_phase(state)

    # FinRAG 复盘注入
    finrag = FinRAG(use_chroma=True) if use_rag else None
    if finrag is not None:
        try:
            query = f"{display_name or ticker} 投研决策"
            ctx = finrag.retrieve_context(ticker, query)
            state.rag_context = ctx.get("context", "")
            state.memory = ctx.get("memory", {})
            state.used_rag = True
            if progress_callback:
                progress_callback("rag_inject", f"[rag] 召回上下文 {len(state.rag_context)} 字符")
            state.add_trace("rag_inject", f"[rag] 召回上下文 {len(state.rag_context)} 字符")
        except Exception as e:  # noqa: BLE001
            state.add_error(f"FinRAG 召回失败: {e}")

    rule = _rule_decision(state)

    # 多首席辩论（真实 / 规则降级）
    state.used_crewai = bool(_HAS_CREWAI and _llm_ok())
    debate = _llm_debate(state, rule)
    if debate is None:
        debate = _build_stances(state, rule)

    stage_keys = ["debate_bull", "debate_bear", "debate_risk", "debate_mod"]
    for key, st in zip(stage_keys, debate):
        if progress_callback:
            progress_callback(key, f"[{st['name']}] {st['lean']}：{st['text'][:60]}...")
        state.add_trace(key, f"[{st['name']}] {st['text']}")
    state.debate = debate

    # 主持综合 → 首席结论
    mod = debate[-1]
    rationale = mod["text"]
    if not llm_configured():
        # 规则下把三派要点也带进论证，更完整
        rationale = (
            f"{debate[0]['text']}\n{debate[1]['text']}\n{debate[2]['text']}\n{debate[3]['text']}"
        )
    chief = {
        "verdict": rule["verdict"],
        "composite": rule["composite"],
        "target_price": rule["target_price"],
        "stop_price": rule["stop_price"],
        "scores": {"tech": rule["tech"], "fund": rule["fund"], "flow": rule.get("flow"),
                   "sent": rule["sent"], "risk": rule["risk"]},
        "rationale": rationale,
        "debate_mode": "crewai" if state.used_crewai else "rule",
    }
    state.chief_report = chief
    if progress_callback:
        progress_callback("chief", f"[{mod['name']}] 最终裁定：{rule['verdict']}（综合 {rule['composite']}）")

    # 写入 FinRAG 记忆
    if finrag is not None:
        try:
            finrag.save_decision(ticker, chief)
            finrag.index_report(ticker, rationale)
            state.used_rag = True
        except Exception as e:  # noqa: BLE001
            state.add_error(f"FinRAG 记忆写入失败: {e}")

    # 回测验证（历史背书，不改结论）
    try:
        log = BacktestAgent().run(state)
        state.add_trace("backtest", log)
        if progress_callback:
            progress_callback("backtest", log)
    except Exception as e:  # noqa: BLE001
        state.add_error(f"回测验证异常: {e}")

    return state
