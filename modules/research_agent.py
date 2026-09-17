"""H1 AI 研究智能体（research_agent）。

把「星辰 AI」从单轮问答升级为**多步工具调用研究智能体**：
用户问题 → 规划工具调用（LLM 可用则 LLM 规划，否则确定性规划器）→ 逐工具执行
（真实数据，经 mcp_server.gateway 的统一超时护栏）→ 带引用的综合回答。

核心差异化（对标报告 H1，老板 2026-09-17 批准）：
- **引用溯源**：每个数据要点都带 [S#] 引用，可追溯到具体工具调用与数据时点（as_of）；
  这是「诚实数据治理」的产品化——别的工具告诉你结论，我们还能告诉你结论怎么来的、可不可信。
- **诚实降级**：工具失败/超时绝不编造数据补位；全失败 → status="unavailable" 并如实说明。
- **有界执行**：max_steps clamp 1..8 + budget_s 时间预算，绝不永久挂死。
- **只读红线**：conditional_orders 仅允许 action="list"，任何写操作直接拒绝执行。

Spec：``.workbuddy/specs/ai_research_agent_contract.md``（AC1–AC8）。
测试：``tests/test_research_agent.py``（tools/planner/synthesizer 全依赖注入，离线零网络）。

与 modules/quantagent/（单标的深度研报流水线）互补不重叠：本模块面向任意问题的
轻量工具调用编排，复用 MCP 16 工具注册表，不重复角色流水线。
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量 / 红线
# ---------------------------------------------------------------------------
_MAX_STEPS_CAP = 8
_DEFAULT_MAX_STEPS = 6

# 只读红线：智能体对 conditional_orders 唯一放行的 action（写操作禁入）
_ALLOWED_CONDITIONAL_ACTIONS = {"list"}

# 数据时点提取键（按优先级取首个非空，AC7）
_AS_OF_KEYS = ("as_of", "generated_at", "datetime", "date", "end", "latest_date")

# 治理词：命中即首步强制 get_data_health（先知道数据多旧，再谈结论，AC7/AC8）
_GOVERNANCE_WORDS = (
    "情绪", "温度", "恐慌", "贪婪", "冰点",
    "宏观", "PMI", "CPI", "PPI", "GDP", "M2", "LPR",
    "龙虎榜", "事件因子", "数据源", "新鲜",
)

_ROUTE_WORDS: List[tuple] = [
    # (工具, 触发词, 是否需要代码)
    ("get_realtime_quote", ("实时", "现价", "盘口", "最新价", "五档", "现在多少钱",
                            "现在涨", "现在跌", "现在价格"), True),
    ("analyze_technical", ("技术", "均线", "MACD", "KDJ", "趋势", "技术指标", "走势"), True),
    ("stock_news", ("新闻", "消息", "公告", "资讯", "最近有什么事"), True),
    ("fund_flow", ("资金流", "主力", "北向", "净流入", "资金", "大单"), True),
    ("risk_assess", ("风险", "会不会跌", "安不安全", "危险", "兜底"), True),
    ("get_market_sentiment", ("市场情绪", "温度计", "市场温度", "大盘情绪", "市场怎么样"), False),
    ("get_macro_indicators", ("宏观", "PMI", "CPI", "PPI", "GDP", "M2", "LPR"), False),
    ("get_lhb", ("龙虎榜",), False),
    ("portfolio_query", ("持仓", "账户", "我买了什么", "仓位", "资产", "盈亏"), False),
]

_PICK_WORDS = ("选股", "挑股票", "找股票", "推荐股票", "筛选", "选几只", "选几支", "帮我选")

_CODE_RE = re.compile(r"\b\d{6}\b")


# ---------------------------------------------------------------------------
# 确定性规划器（AC8，纯正则关键词，零 LLM / 零网络）
# ---------------------------------------------------------------------------
def plan_steps(question: str) -> List[Dict[str, Any]]:
    """把自然语言问题映射为工具调用计划 [{tool, args, why}]。

    规则（spec AC8 钉死，mutation 目标）：
    - 治理词命中 → 首步固定 ``get_data_health``（先看数据健康再取数）；
    - 各路由词按表命中；「仅代码无关键词」→ 研究三件套（quote+tech+news）；
    - 选股词 → ``smart_pick`` 置末位（慢任务）；
    - 全未命中 → 诚实兜底 ``[get_data_health, get_market_sentiment]``；
    - 工具去重、总量 ≤8。
    """
    q = str(question or "")
    codes = _CODE_RE.findall(q)
    code = codes[0] if codes else ""
    plan: List[Dict[str, Any]] = []

    def _add(tool: str, args: Optional[Dict[str, Any]] = None, why: str = "") -> None:
        if any(p["tool"] == tool for p in plan):
            return
        plan.append({"tool": tool, "args": dict(args or {}), "why": why})

    lowered_hit = False
    if any(w in q for w in _GOVERNANCE_WORDS):
        _add("get_data_health", {}, "治理词命中：先查数据源时效，避免基于陈旧数据下结论")
        lowered_hit = True

    for tool, words, needs_code in _ROUTE_WORDS:
        if not any(w in q for w in words):
            continue
        if needs_code and not code:
            continue
        args = {"code": code} if needs_code else {}
        _add(tool, args, f"关键词命中：{tool}")
        lowered_hit = True

    if any(w in q for w in _PICK_WORDS):
        _add("smart_pick", {"top_k": 5}, "选股意图：慢任务置末位")
        lowered_hit = True

    if not plan:
        if code:
            # 仅代码、无关键词 → 默认研究三件套
            _add("get_realtime_quote", {"code": code}, "默认三件套：实时盘口")
            _add("analyze_technical", {"code": code}, "默认三件套：技术面")
            _add("stock_news", {"code": code}, "默认三件套：近期消息")
        else:
            # 全未命中 → 诚实兜底：给市场现状 + 数据健康，不硬答
            _add("get_data_health", {}, "兜底：数据健康")
            _add("get_market_sentiment", {}, "兜底：市场情绪")
    return plan[:_MAX_STEPS_CAP]


# ---------------------------------------------------------------------------
# 工具结果摘要（AC4：溯源用结构化摘要，防巨型 payload）
# ---------------------------------------------------------------------------
def summarize_tool_result(
    result: Any, max_items: int = 5, max_scalar_len: int = 120
) -> Optional[Dict[str, Any]]:
    """把工具原始结果压成可溯源、可渲染的摘要 dict。

    - 标量键全保留（str 截断到 max_scalar_len）；
    - 列表截断到前 max_items 条，并注 ``_total_<key>`` 总数；
    - 嵌套 dict → 压缩 JSON 字符串（≤300 字符）；
    - 非 dict 结果 → ``{"_repr": ...}``。
    """
    if result is None:
        return None
    if not isinstance(result, dict):
        try:
            return {"_repr": str(result)[:300]}
        except Exception:  # noqa: BLE001
            return {"_repr": "<不可序列化结果>"}
    out: Dict[str, Any] = {}
    for k, v in result.items():
        if v is None or isinstance(v, (int, float, bool)):
            out[str(k)] = v
        elif isinstance(v, str):
            s = v
            if len(s) > max_scalar_len:
                s = s[:max_scalar_len] + "…"
            out[str(k)] = s
        elif isinstance(v, list):
            out[str(k)] = v[:max_items]
            if len(v) > max_items:
                out[f"_total_{k}"] = len(v)
        elif isinstance(v, dict):
            try:
                out[str(k)] = json.dumps(v, ensure_ascii=False, default=str)[:300]
            except Exception:  # noqa: BLE001
                out[str(k)] = "<不可序列化>"
        else:
            out[str(k)] = str(v)[:max_scalar_len]
    return out


def _extract_as_of(data: Any) -> Optional[str]:
    """从工具结果提取数据时点（AC7：按 _AS_OF_KEYS 优先级取首个非空）。"""
    if not isinstance(data, dict):
        return None
    for key in _AS_OF_KEYS:
        v = data.get(key)
        if v:
            return str(v)
    return None


def _safe_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """步骤留痕用的 args 快照（长字符串截断，防溯源记录本身巨型化）。"""
    out: Dict[str, Any] = {}
    for k, v in (args or {}).items():
        if isinstance(v, str) and len(v) > 120:
            out[str(k)] = v[:120] + "…"
        else:
            out[str(k)] = v
    return out


# ---------------------------------------------------------------------------
# LLM 可插拔层（AC6：零 LLM 也必须可用）
# ---------------------------------------------------------------------------
def _resolve_llm(use_llm: Any):
    """use_llm: False=强制关 / True=强制用 / None=自动探测 / 模块对象=注入（测试）。"""
    if use_llm is False:
        return None
    if isinstance(use_llm, bool) or use_llm is None:
        try:
            import modules.llm_client as llm_client

            if use_llm is True or llm_client.is_configured():
                return llm_client
        except Exception:  # noqa: BLE001
            return None
        return None
    return use_llm  # 注入点


def _plan_with_llm(question: str, available: List[str], llm: Any) -> Optional[List[Dict[str, Any]]]:
    """LLM 规划：问题 + 工具目录 → 计划 JSON。任何失败返回 None（回退确定性规划器）。"""
    if llm is None:
        return None
    try:
        catalog = "\n".join(f"- {n}" for n in available)
        prompt = (
            "你是 A 股研究助手。根据用户问题，从下列工具中挑选 ≤6 个做一次研究：\n"
            f"{catalog}\n"
            '只输出 JSON：{"steps":[{"tool":"工具名","args":{...},"why":"一句话"}]}，'
            "不要输出其它文字。args 只能用工具支持的简单参数（code 为 6 位代码）。\n"
            f"用户问题：{question}"
        )
        parsed = llm.chat_completion_json(
            [{"role": "user", "content": prompt}], temperature=0.2, max_tokens=600, timeout=20
        )
        if not isinstance(parsed, dict):
            return None
        raw_steps = parsed.get("steps")
        if not isinstance(raw_steps, list):
            return None
        plan: List[Dict[str, Any]] = []
        for s in raw_steps:
            if not isinstance(s, dict):
                continue
            tool = s.get("tool")
            if not isinstance(tool, str) or tool not in available:
                continue
            args = s.get("args")
            plan.append({
                "tool": tool,
                "args": args if isinstance(args, dict) else {},
                "why": str(s.get("why") or "")[:100],
            })
        return plan or None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[research_agent] LLM 规划失败，回退确定性规划器: {e}")
        return None


def _synthesize_with_llm(
    question: str, steps: List[Dict[str, Any]], citations: List[Dict[str, Any]], llm: Any
) -> Optional[str]:
    """LLM 合成：只许基于步骤摘要措辞，数据事实必须带 [S#] 引用。失败返回 None。"""
    if llm is None or not citations:
        return None
    try:
        digest_lines = []
        for s in steps:
            if s.get("status") != "ok":
                continue
            digest_lines.append(
                f"[S{s['idx']}] {s['tool']}（数据截至 {s.get('data_as_of') or '未知'}）："
                f"{json.dumps(s.get('summary') or {}, ensure_ascii=False, default=str)[:400]}"
            )
        prompt = (
            "你是严谨的 A 股研究员。只依据下列工具返回的真实数据回答用户问题，"
            "每个数据点必须标注 [S#] 引用（S 编号见各条目前缀）；数据没覆盖的部分如实说明，"
            "禁止编造或外推。\n\n"
            f"用户问题：{question}\n\n工具数据：\n" + "\n".join(digest_lines)
        )
        text = llm.chat_completion(
            [{"role": "user", "content": prompt}], temperature=0.4, max_tokens=900, timeout=30
        )
        return text or None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[research_agent] LLM 合成失败，回退规则合成器: {e}")
        return None


# ---------------------------------------------------------------------------
# 规则合成器（AC4：每条数据要点必须带 [S#] 引用）
# ---------------------------------------------------------------------------
_STATUS_LABEL = {"ok": "完成", "partial": "部分完成", "unavailable": "数据不可用"}


def _rule_synthesize(
    question: str, steps: List[Dict[str, Any]], citations: List[Dict[str, Any]],
    limitations: List[str],
) -> str:
    ok_steps = [s for s in steps if s.get("status") == "ok"]
    if not ok_steps:
        reason = "；".join(limitations[:4]) if limitations else "全部工具调用失败"
        return (
            f"⚠️ **未能获取任何有效数据**，无法回答「{question}」。\n\n"
            f"原因：{reason}\n\n"
            "本智能体只基于工具真实返回作答，取不到数据时不会编造结论。请稍后重试，"
            "或换个问法（例如带上 6 位股票代码）。"
        )
    lines = [f"### 研究结论（{_STATUS_LABEL.get('ok', '完成')}，共 {len(ok_steps)} 项有效数据）", ""]
    for s in ok_steps:
        core = json.dumps(s.get("summary") or {}, ensure_ascii=False, default=str)
        if len(core) > 200:
            core = core[:200] + "…"
        as_of = f"（数据截至 {s['data_as_of']}）" if s.get("data_as_of") else ""
        lines.append(f"- [S{s['idx']}] `{s['tool']}`：{core}{as_of}")
    if limitations:
        lines.append("")
        lines.append("> ⚠️ " + "；".join(limitations[:5]))
    lines.append("")
    lines.append("### 引用溯源")
    for c in citations:
        lines.append(f"- [S{c['step']}] `{c['tool']}` — 数据时点 {c.get('as_of') or '未知'}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 工具调用通道（真实路径走 gateway，测试路径注入 tools 表）
# ---------------------------------------------------------------------------
def _available_tool_names(tools: Optional[Dict[str, Callable]]) -> List[str]:
    if tools is not None:
        return list(tools.keys())
    try:
        from mcp_server.gateway import available_tools

        return available_tools()
    except Exception:  # noqa: BLE001
        return []


def _call_tool(
    name: str, args: Dict[str, Any], tools: Optional[Dict[str, Callable]]
) -> Dict[str, Any]:
    """统一调用入口：tools=None 走 gateway（12s 超时护栏）；否则调注入表。"""
    if tools is not None:
        fn = tools.get(name)
        if fn is None:
            return {"ok": False, "error": f"未知工具: {name}"}
        try:
            return {"ok": True, "data": fn(**args)}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    try:
        from mcp_server.gateway import call_tool

        res = call_tool(name, **args)
        if res.get("ok"):
            return {"ok": True, "data": res.get("data")}
        return {"ok": False, "error": str(res.get("error") or "工具调用失败")}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _tool_exists(name: str, tools: Optional[Dict[str, Callable]]) -> bool:
    if tools is not None:
        return name in tools
    return name in _available_tool_names(None)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def run_research(
    question: str,
    *,
    tools: Optional[Dict[str, Callable]] = None,
    planner: Optional[Callable[[str, List[str]], List[Dict[str, Any]]]] = None,
    synthesizer: Optional[
        Callable[[str, List[Dict[str, Any]], List[Dict[str, Any]], List[str]], str]
    ] = None,
    max_steps: int = _DEFAULT_MAX_STEPS,
    budget_s: float = 90.0,
    use_llm: Any = None,
    on_step: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """执行一轮研究：规划 → 有界执行 → 带引用综合。契约见 spec AC1–AC8。"""
    t0 = time.time()
    question = str(question or "").strip()
    limitations: List[str] = []

    def _emit(msg: str) -> None:
        if on_step is None:
            return
        try:
            on_step(msg)
        except Exception:  # noqa: BLE001
            pass

    def _envelope(status: str, steps: List[Dict[str, Any]],
                  answer: str, citations: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "question": question,
            "status": status,
            "steps": steps,
            "answer": answer,
            "citations": citations,
            "limitations": limitations,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_s": round(time.time() - t0, 2),
        }

    if not question:
        limitations.append("问题为空")
        return _envelope("unavailable", [], "问题为空，无法开展研究。", [])

    max_steps = max(1, min(int(max_steps or _DEFAULT_MAX_STEPS), _MAX_STEPS_CAP))
    llm = _resolve_llm(use_llm)
    available = _available_tool_names(tools)

    # ── 1) 规划 ──
    plan: Optional[List[Dict[str, Any]]] = None
    if planner is not None:
        try:
            plan = planner(question, available)
        except Exception as e:  # noqa: BLE001
            limitations.append(f"注入规划器失败（{e}），已回退确定性规划器")
            plan = None
    if plan is None:
        plan = _plan_with_llm(question, available, llm) or plan_steps(question)

    # 规范化 + 截断（AC2）
    norm: List[Dict[str, Any]] = []
    for s in plan or []:
        if isinstance(s, dict) and isinstance(s.get("tool"), str) and s["tool"]:
            norm.append({
                "tool": s["tool"],
                "args": s.get("args") if isinstance(s.get("args"), dict) else {},
                "why": str(s.get("why") or ""),
            })
    if len(norm) > max_steps:
        limitations.append(
            f"计划包含 {len(norm)} 个步骤，超出 max_steps={max_steps}，已截断"
        )
        norm = norm[:max_steps]
    if not norm:
        limitations.append("未生成任何可用研究步骤")
        synth = synthesizer or _rule_synthesize
        return _envelope("unavailable", [], synth(question, [], [], limitations), [])

    # ── 2) 有界执行（AC2 预算 / AC3 红线 / AC5 隔离）──
    steps: List[Dict[str, Any]] = []
    stopped_by_budget = False
    for i, entry in enumerate(norm, start=1):
        if time.time() - t0 > budget_s:
            remain = len(norm) - i + 1
            limitations.append(
                f"已达时间预算 {budget_s:.0f}s，剩余 {remain} 步未执行"
            )
            stopped_by_budget = True
            break
        tool = entry["tool"]
        args = entry["args"]
        step: Dict[str, Any] = {
            "idx": i,
            "tool": tool,
            "args": _safe_args(args),
            "status": "ok",
            "duration_ms": 0,
            "summary": None,
            "data_as_of": None,
            "reason": "",
        }
        s0 = time.time()
        # 只读红线（AC3）：写操作禁入，不执行
        if tool == "conditional_orders" and \
                str(args.get("action", "list")).lower() not in _ALLOWED_CONDITIONAL_ACTIONS:
            step["status"] = "rejected"
            step["reason"] = "智能体只读红线：conditional_orders 仅允许 action=list"
        elif not _tool_exists(tool, tools):
            step["status"] = "rejected"
            step["reason"] = f"未知工具: {tool}"
        else:
            res = _call_tool(tool, args, tools)
            if res.get("ok"):
                data = res.get("data")
                step["summary"] = summarize_tool_result(data)
                step["data_as_of"] = _extract_as_of(data)
                # 工具自身约定的业务失败：返回 dict 含 error 键
                if isinstance(data, dict) and data.get("error"):
                    step["status"] = "error"
                    step["reason"] = str(data.get("error"))[:200]
            else:
                step["status"] = "error"
                step["reason"] = str(res.get("error"))[:200]
        step["duration_ms"] = int((time.time() - s0) * 1000)
        steps.append(step)
        _emit(f"步骤 {i}/{len(norm)} · {tool} → {step['status']}")

    # ── 3) 汇总状态（AC1/AC5）──
    ok_steps = [s for s in steps if s["status"] == "ok"]
    citations = [
        {"step": s["idx"], "tool": s["tool"], "as_of": s.get("data_as_of")}
        for s in ok_steps
    ]

    # 数据健康溯源（AC7）：health 结果中的劣化源 → limitations
    for s in steps:
        if s["tool"] == "get_data_health" and s["status"] == "ok" \
                and isinstance(s.get("summary"), dict):
            for src in s["summary"].get("sources") or []:
                if not isinstance(src, dict):
                    continue
                st_val = src.get("status")
                if st_val in ("warn", "stale") or src.get("stalled"):
                    # 源名兼容真实 data_health 行（name/key）与早期假设（source）
                    src_name = src.get("source") or src.get("name") or src.get("key") or "?"
                    limitations.append(
                        f"数据源 {src_name} 状态 {st_val or 'stalled'}"
                    )

    if not ok_steps:
        status = "unavailable"
    elif stopped_by_budget or len(ok_steps) < len(steps):
        status = "partial"
    else:
        status = "ok"

    # ── 4) 合成（AC4/AC6：LLM 优先措辞、规则兜底，数据只来自工具真实返回）──
    if synthesizer is not None:
        try:
            answer = synthesizer(question, steps, citations, limitations)
        except Exception as e:  # noqa: BLE001
            limitations.append(f"注入合成器失败（{e}），已回退规则合成器")
            answer = _rule_synthesize(question, steps, citations, limitations)
    else:
        answer = (
            _synthesize_with_llm(question, steps, citations, llm)
            or _rule_synthesize(question, steps, citations, limitations)
        )
    if status == "unavailable" and not limitations:
        limitations.append("全部工具调用失败")

    return _envelope(status, steps, answer, citations)
