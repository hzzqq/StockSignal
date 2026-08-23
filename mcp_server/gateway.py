"""StockSignal MCP 工具同进程网关（in-process gateway）。

为什么需要它：
- ``mcp_server/server.py`` + ``run.py`` 是面向 **外部 AI 助手（Claude/Cursor/OpenClaw）**
  的 stdio MCP 服务，走 JSON-RPC 序列化，跨进程、适合被第三方客户端调用。
- 但 **StockSignal 站内页面（如 🌟_星辰AI.py）** 与 MCP 工具同处一个 Python 进程，
  没必要走 stdio 序列化再回来。本网关直接 import ``mcp_server.tools`` 里已注册的工具
  函数并调用，零序列化开销、零网络，返回结构化 dict。

设计红线（与 server.py 一致）：
- 行情/分析/选股/回测/资金流/新闻/风险 **全只读**；
- 条件单创建默认 dry_run 模拟，真实登记需显式 dry_run=False 且仍走后端 risk_check；
- 实盘裸下单不开放，必须走后端 order_routes（鉴权+风控+人工确认）。

本模块对所有工具调用统一包装为 ``{"ok": bool, "data": ..., "error": ...}``，
调用方无需关心每个工具的异常细节，方便页面渲染卡片或静默降级。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# 工具名 -> 实际函数（延迟导入，避免在 import 本模块时就触发重型依赖）
_TOOL_FUNCS: Dict[str, str] = {
    "get_kline": "get_kline",
    "analyze_technical": "analyze_technical",
    "smart_pick": "smart_pick",
    "run_backtest": "run_backtest",
    "fund_flow": "fund_flow",
    "stock_news": "stock_news",
    "risk_assess": "risk_assess",
    "conditional_orders": "conditional_orders",
    "portfolio_query": "portfolio_query",
    "get_realtime_quote": "get_realtime_quote",
    "get_market_sentiment": "get_market_sentiment",
}


def available_tools() -> list[str]:
    """返回当前网关支持的工具名列表。"""
    return list(_TOOL_FUNCS.keys())


def _resolve_func(name: str):
    """按工具名取真实函数（延迟 import tools 模块触发注册副作用）。"""
    if name not in _TOOL_FUNCS:
        return None
    # 导入 tools 模块会执行 @register_tool 注册（幂等），同时确保函数已定义
    from . import tools as _tools  # noqa: F401  (注册副作用)

    return getattr(_tools, _TOOL_FUNCS[name], None)


def call_tool(name: str, **kwargs: Any) -> Dict[str, Any]:
    """同进程调用一个 MCP 工具，返回统一结构。

    返回示例::

        {"ok": True, "data": {...}}          # 成功
        {"ok": False, "error": "工具不存在"}  # 工具名不合法
        {"ok": False, "error": "数据获取失败: ..."}  # 工具内部业务失败（已捕获）
        {"ok": False, "error": "工具调用超时(>12s)"}  # 总超时护栏触发
    """
    from modules.timeout_exec import run_with_timeout

    func = _resolve_func(name)
    if func is None:
        return {"ok": False, "error": f"工具不存在: {name}"}
    try:
        # 总超时护栏：任何工具内部无界阻塞（远程取数）都会在 _GATEWAY_TIMEOUT 内
        # 被强制返回 None，网关转成友好错误，避免站内 AI 页 / 外部客户端永久卡死。
        result = run_with_timeout(lambda: func(**kwargs), timeout=_GATEWAY_TIMEOUT)
    except Exception as e:  # noqa: BLE001 - 网关统一兜底，不让异常冒泡到页面
        logger.warning(f"[mcp_gateway] 工具 {name} 调用异常: {e}")
        return {"ok": False, "error": f"工具调用异常: {e}"}

    if result is None:
        return {"ok": False, "error": f"工具调用超时（>{_GATEWAY_TIMEOUT}s）或内部无返回: {name}"}

    # 工具自身已约定：出错时返回含 "error" 键的 dict
    if isinstance(result, dict) and result.get("error"):
        return {"ok": False, "error": result["error"], "data": result}
    return {"ok": True, "data": result}


# 网关总超时（秒）：与底层网络默认超时(10s) < CALL_TIMEOUT_CAP(12s) 保持一致，
# 正常阻塞路径下工具会在边界内自行返回，线程回池复用、不泄漏。
_GATEWAY_TIMEOUT = 12


# ── 意图识别：把自然语言问句映射到工具 + 参数提取 ────────────────────────────
# 这是给站内 AI 页 / 后台 AI 用的轻量路由，不依赖 LLM，纯正则+关键词，
# 命中即走工具拿真实数据；未命中则仍交给 ai_answer 走自然语言回答。

import re

# 工具 -> 触发关键词（命中其一且能抽出标的/参数即路由）
_INTENT_RULES: Dict[str, Dict[str, Any]] = {
    "smart_pick": {
        "keywords": ["选股", "找股票", "挑股票", "有什么好票", "推荐股票", "筛选", "选哪些",
                     "选几只", "选 A 股", "选几支", "帮我选", "选标的"],
        "needs_market": True,
        "needs_code": False,
    },
    "run_backtest": {
        "keywords": ["回测", "历史表现", "策略回测", "跑一下回测"],
        "needs_code": True,
    },
    "fund_flow": {
        "keywords": ["资金流", "主力", "北向", "净流入", "资金流向", "大单"],
        "needs_code": True,
    },
    "risk_assess": {
        "keywords": ["风险", "风险评估", "兜底", "会不会跌", "安不安全", "危险"],
        "needs_code": True,
    },
    "stock_news": {
        "keywords": ["新闻", "消息", "公告", "最近有什么事", "资讯"],
        "needs_code": True,
    },
    "portfolio_query": {
        "keywords": ["我的持仓", "我买了什么", "账户", "盈亏", "仓位", "资产"],
        "needs_code": False,
    },
    "conditional_orders": {
        "keywords": ["条件单", "我的条件单", "挂单", "预警单"],
        "needs_code": False,
    },
    "analyze_technical": {
        "keywords": ["技术面", "均线", "MACD", "KDJ", "趋势", "技术指标", "走势"],
        "needs_code": True,
    },
    "get_kline": {
        "keywords": ["K线", "行情", "价格", "走势图", "日线"],
        "needs_code": True,
    },
    "get_realtime_quote": {
        "keywords": ["实时", "盘口", "现在价格", "现价", "最新价", "五档", "现在多少钱", "现在涨", "现在跌"],
        "needs_code": True,
    },
    "get_market_sentiment": {
        "keywords": ["市场情绪", "情绪", "温度计", "恐慌", "贪婪", "冰点", "市场温度", "市场怎么样", "大盘情绪"],
        "needs_code": False,
    },
}


def _extract_codes(text: str) -> list[str]:
    """抽取 6 位 A 股代码；也支持中文名（由工具内部解析）。"""
    return re.findall(r"\b\d{6}\b", text)


def detect_intent(question: str) -> Dict[str, Any]:
    """识别问句意图，返回 {'tool': str|None, 'params': dict, 'confidence': float}。

    confidence 越高越应走工具；<0.5 视为未命中，交给自然语言 AI。
    """
    q = question.strip()
    codes = _extract_codes(q)
    hits: list[tuple[str, float]] = []

    for tool, rule in _INTENT_RULES.items():
        kw_hit = any(kw in q for kw in rule["keywords"])
        if not kw_hit:
            continue
        score = 0.6  # 关键词命中基线
        if rule.get("needs_code") and codes:
            score = 0.9  # 有明确标的 => 高置信
        elif rule.get("needs_code") and not codes:
            score = 0.5  # 想要但没给标的 => 低置信，仍提示补充
        elif not rule.get("needs_code"):
            score = 0.85  # 持仓/条件单类无需标的
        # 选股动作动词（选/挑/筛选/推荐）优先级高于纯技术面描述词：
        # 当同一句同时命中 smart_pick 与 analyze_technical 时，选股意图胜出。
        if tool == "smart_pick" and any(
            v in q for v in ("选", "挑", "筛选", "推荐", "找股票")
        ):
            score += 0.1
        # 实时盘口强意图词（实时/盘口/现价/五档）优先级高于泛化技术面词
        # （走势/技术面），当同一句同时命中 get_realtime_quote 与 analyze_technical 时，
        # 实时意图胜出，避免用户问「现在价格」被误判为「技术面分析」。
        if tool == "get_realtime_quote" and any(
            v in q for v in ("实时", "盘口", "现价", "最新价", "五档", "现在价格", "现在多少钱")
        ):
            score += 0.1
        hits.append((tool, score))

    if not hits:
        return {"tool": None, "params": {}, "confidence": 0.0}

    # 取置信最高的意图
    tool, score = max(hits, key=lambda x: x[1])
    params: Dict[str, Any] = {}
    if _INTENT_RULES[tool].get("needs_code") and codes:
        params["code"] = codes[0]
    if tool == "smart_pick":
        # 简单推断市场（默认 A 股）；可由后续 LLM 增强
        params.setdefault("market", "A")
    return {"tool": tool, "params": params, "confidence": score}
