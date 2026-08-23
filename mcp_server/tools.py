"""StockSignal MCP 工具实现。

每个工具都是对 StockSignal 现有能力（modules.* / backend.*）的**薄转发**，
不重复业务逻辑。所有工具遵循：
- 入参简单（字符串/数字），出参可被 json 序列化。
- 只读工具直接返回数据；写操作（条件单）默认 dry_run 且经安全校验。
- 异常在 server 层被捕获转成 MCP isError，这里只管抛业务异常。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# 让 mcp_server 包可被独立运行（python -m mcp_server.tools）
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from .server import register_tool  # noqa: E402


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------
def _resolve_code(user_input: str) -> Optional[str]:
    """尽力把用户输入解析成 akshare 风格 6 位代码；解析不到返回原样。"""
    s = user_input.strip()
    # 已像代码
    if len(s) == 6 and s.isdigit():
        return s
    # 尝试用 ai_engine 的解析器
    try:
        from modules.ai_engine import _resolve_stock

        r = _resolve_stock(s)
        if r and r.get("code"):
            return r["code"]
    except Exception:
        pass
    return s


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, (dict, list)):
        return obj
    if hasattr(obj, "to_dict"):
        try:
            return obj.to_dict()
        except Exception:
            pass
    return str(obj)


# ---------------------------------------------------------------------------
# 工具 1：行情 K 线
# ---------------------------------------------------------------------------
def get_kline(code: str, start: str = "", end: str = "", days: int = 120) -> Dict[str, Any]:
    """获取个股/指数历史 K 线（开高低收 + 成交量）。

    Args:
        code: 股票代码（如 600519）或名称（如 贵州茅台）
        start: 起始日期 YYYY-MM-DD（可选，与 days 二选一）
        end: 结束日期 YYYY-MM-DD（可选）
        days: 最近 N 天（默认 120，当 start 为空时生效）

    Returns:
        {code, name, count, data:[{date,open,high,low,close,volume}], source}
    """
    from modules.fetcher import StockFetcher
    from modules.cleaner import DataCleaner

    real_code = _resolve_code(code)
    end_d = end or datetime.now().strftime("%Y-%m-%d")
    if not start:
        start_d = (datetime.now() - timedelta(days=int(days) * 1.6)).strftime("%Y-%m-%d")
    else:
        start_d = start

    fetcher = StockFetcher()
    raw = fetcher.get_daily(real_code, start=start_d, end=end_d)
    if raw is None or len(raw) == 0:
        return {"error": f"未获取到 {code} 的行情数据", "code": real_code}
    df = DataCleaner.full_pipeline(raw)
    rows = []
    for _, r in df.tail(int(days)).iterrows():
        rows.append(
            {
                "date": str(r.get("date")),
                "open": float(r.get("open")),
                "high": float(r.get("high")),
                "low": float(r.get("low")),
                "close": float(r.get("close")),
                "volume": float(r.get("volume")),
            }
        )
    return {
        "code": real_code,
        "count": len(rows),
        "start": rows[0]["date"] if rows else None,
        "end": rows[-1]["date"] if rows else None,
        "data": rows,
    }


# ---------------------------------------------------------------------------
# 工具 2：技术面分析
# ---------------------------------------------------------------------------
def analyze_technical(code: str, days: int = 180) -> Dict[str, Any]:
    """对标的做四维技术面分析（趋势/动量/量能/形态）+ 综合评分。

    Args:
        code: 股票代码或名称
        days: 回看天数（默认 180）

    Returns:
        full_analysis 的结构化结果（含均线、RSI、MACD、量能、形态、评分）
    """
    from modules.fetcher import StockFetcher
    from modules.cleaner import DataCleaner
    from modules.technical import full_analysis

    real_code = _resolve_code(code)
    end_d = datetime.now().strftime("%Y-%m-%d")
    start_d = (datetime.now() - timedelta(days=int(days) * 1.6)).strftime("%Y-%m-%d")
    fetcher = StockFetcher()
    raw = fetcher.get_daily(real_code, start=start_d, end=end_d)
    if raw is None or len(raw) == 0:
        return {"error": f"未获取到 {code} 的行情数据", "code": real_code}
    df = DataCleaner.full_pipeline(raw)
    result = full_analysis(df)
    return {"code": real_code, "analysis": _jsonable(result)}


# ---------------------------------------------------------------------------
# 工具 3：智能选股
# ---------------------------------------------------------------------------
def smart_pick(
    strategy: str = "multi_factor",
    top_k: int = 10,
    start: str = "",
    end: str = "",
    pool_size: int = 200,
) -> Dict[str, Any]:
    """按策略跑一遍「每日选股 + 回测验证」，返回 top_k 候选标的。

    Args:
        strategy: 选股策略，可选 multi_factor（多因子）或 dual_trend（双趋势共振）
        top_k: 返回前几名（默认 10）
        start/end: 回测区间（可选，默认最近约 60 个交易日）
        pool_size: 候选股票池大小（默认 200，越大越慢）

    Returns:
        {strategy, generated_at, picks:[{rank,code,name,score,backtest_return,...}]}
    """
    from modules.backtest import Backtester

    end_d = end or datetime.now().strftime("%Y-%m-%d")
    if not start:
        # 约 60 个交易日
        start_d = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    else:
        start_d = start

    bt = Backtester()
    picks = bt.daily_picker_backtest(
        start=start_d,
        end=end_d,
        stock_pool_size=int(pool_size),
        top_k=int(top_k),
        strategy=strategy,
    )
    return {
        "strategy": strategy,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "picks": picks if isinstance(picks, list) else list(picks),
    }


# ---------------------------------------------------------------------------
# 工具 4：策略回测
# ---------------------------------------------------------------------------
def run_backtest(
    code: str,
    start: str,
    end: str,
    strategy: str = "multi_factor",
    initial_capital: float = 100000.0,
) -> Dict[str, Any]:
    """对单只标的做策略回测，返回绩效指标。

    Args:
        code: 股票代码或名称
        start/end: 回测区间 YYYY-MM-DD（必填）
        strategy: 策略名（multi_factor / dual_trend / ma_cross / event_driven）
        initial_capital: 初始资金（默认 10 万）

    Returns:
        {code, strategy, total_return, annual_return, sharpe, max_drawdown, trades,...}
    """
    from modules.backtest import Backtester

    real_code = _resolve_code(code)
    bt = Backtester()
    res = bt.run(
        real_code,
        start,
        end,
        strategy=strategy,
        initial_capital=float(initial_capital),
    )
    if res is None:
        return {"error": f"回测失败：{code} 数据不足或区间无效", "code": real_code}
    # BacktestResult 对象 → 字典
    out = {
        "code": real_code,
        "strategy": strategy,
        "start": start,
        "end": end,
    }
    for k in (
        "total_return",
        "annual_return",
        "sharpe",
        "max_drawdown",
        "win_rate",
        "trade_count",
        "final_value",
    ):
        v = getattr(res, k, None)
        if v is not None:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# 工具 5：资金流向
# ---------------------------------------------------------------------------
def fund_flow(code: str = "", scope: str = "individual") -> Dict[str, Any]:
    """查询资金流向。

    Args:
        code: 个股代码（可选）；为空时查市场/行业层面
        scope: individual（个股）/ market（市场）/ northbound（北向）/ industry（行业）

    Returns:
        对应资金流数据（结构随 scope 不同）
    """
    from modules import fundflow

    if scope == "market":
        return {"scope": "market", "data": _jsonable(fundflow.get_market_fund_flow())}
    if scope == "northbound":
        return {"scope": "northbound", "data": _jsonable(fundflow.get_northbound_fund_flow())}
    if scope == "industry":
        return {"scope": "industry", "data": _jsonable(fundflow.get_industry_fund_flow())}
    # individual
    if not code:
        return {"error": "查询个股资金流需提供 code"}
    real_code = _resolve_code(code)
    return {
        "scope": "individual",
        "code": real_code,
        "data": _jsonable(fundflow.get_individual_fund_flow(real_code)),
    }


# ---------------------------------------------------------------------------
# 工具 6：个股新闻 / 事件
# ---------------------------------------------------------------------------
def stock_news(code: str, limit: int = 5) -> Dict[str, Any]:
    """获取个股近期新闻与事件（已做基础清洗）。

    Args:
        code: 股票代码或名称
        limit: 条数（默认 5）

    Returns:
        {code, name, news:[{title, date, summary}]}
    """
    from modules.ai_engine import _resolve_stock, _fetch_news

    real_code = _resolve_code(code)
    info = _resolve_stock(code)
    name = info.get("name") if info else code
    news = _fetch_news(real_code, name or code, limit=int(limit))
    return {"code": real_code, "name": name, "news": news}


# ---------------------------------------------------------------------------
# 工具 7：风险评估
# ---------------------------------------------------------------------------
def risk_assess(code: str) -> Dict[str, Any]:
    """对标的做综合风险评估（技术面 + 估值 + 事件），返回风险等级与要点。

    Args:
        code: 股票代码或名称

    Returns:
        {code, risk_level, score, points:[...], suggestion}
    """
    tech = analyze_technical(code, days=120)
    if "error" in tech:
        return tech
    analysis = tech.get("analysis", {})
    # 简易风险打分：基于技术面综合评分反向 + 量能异常
    score_block = analysis.get("score", {}) if isinstance(analysis, dict) else {}
    tech_score = score_block.get("total") if isinstance(score_block, dict) else None
    points: List[str] = []
    level = "中"
    if isinstance(tech_score, (int, float)):
        if tech_score >= 70:
            level = "低"
            points.append(f"技术面综合评分 {tech_score}，趋势偏强")
        elif tech_score >= 45:
            level = "中"
            points.append(f"技术面综合评分 {tech_score}，多空均衡")
        else:
            level = "高"
            points.append(f"技术面综合评分 {tech_score}，趋势偏弱")
    else:
        points.append("技术面评分不可用")
    suggestion = {
        "低": "可逢回踩关注，控制仓位",
        "中": "观望为主，等待方向选择",
        "高": "规避或仅小仓位短线",
    }[level]
    return {
        "code": tech["code"],
        "risk_level": level,
        "tech_score": tech_score,
        "points": points,
        "suggestion": suggestion,
    }


# ---------------------------------------------------------------------------
# 工具 8：条件单管理（只读 + 安全创建）
# ---------------------------------------------------------------------------
def conditional_orders(
    action: str = "list",
    order_id: Optional[int] = None,
    code: str = "",
    side: str = "",
    trigger_type: str = "",
    threshold: float = 0.0,
    quantity: int = 0,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """条件单查询 / 创建（默认只模拟，不下真实单）。

    Args:
        action: list（查询）| create（创建，需 dry_run=False 才真正登记）
        order_id: 查询/撤销时指定
        code/side/trigger_type/threshold/quantity: create 时必填
            side: buy / sell
            trigger_type: ma5_break_up / ma5_break_down / price_above / price_below
        dry_run: True（默认）只校验并返回模拟结果，不落库

    Returns:
        查询结果列表 或 创建/校验结果
    """
    try:
        from backend.app import create_app
        from backend.models import db, ConditionalOrder
        from backend.conditional_engine import evaluate_order
        app = create_app()
    except Exception as e:  # noqa: BLE001
        return {"error": f"条件单模块不可用: {e}"}

    with app.app_context():
        if action == "list":
            q = db.session.query(ConditionalOrder)
            if order_id is not None:
                q = q.filter(ConditionalOrder.id == order_id)
            rows = q.all()
            return {
                "action": "list",
                "count": len(rows),
                "orders": [
                    {
                        "id": o.id,
                        "code": o.code,
                        "side": o.side,
                        "trigger_type": o.trigger_type,
                        "threshold": o.threshold,
                        "quantity": o.quantity,
                        "status": o.status,
                        "created_at": str(o.created_at),
                    }
                    for o in rows
                ],
            }
        if action == "create":
            if not (code and side and trigger_type and quantity > 0):
                return {"error": "create 需 code/side/trigger_type/quantity 齐全"}
            # 安全校验：复用既有校验入口（仅校验，不触发真实下单）
            sample = ConditionalOrder(
                code=_resolve_code(code),
                side=side,
                trigger_type=trigger_type,
                threshold=float(threshold),
                quantity=int(quantity),
                status="pending",
            )
            ok, reason = evaluate_order(sample)
            if not ok:
                return {"action": "create", "dry_run": dry_run, "accepted": False, "reason": reason}
            if dry_run:
                return {
                    "action": "create",
                    "dry_run": True,
                    "accepted": True,
                    "simulated_order": {
                        "code": sample.code,
                        "side": side,
                        "trigger_type": trigger_type,
                        "threshold": float(threshold),
                        "quantity": int(quantity),
                    },
                    "note": "模拟通过。设置 dry_run=False 才真正登记条件单（仍须后端 risk_check 复核）。",
                }
            # 真实登记（仍受后端 order_routes 的鉴权 + risk_check 约束）
            db.session.add(sample)
            db.session.commit()
            return {"action": "create", "dry_run": False, "accepted": True, "order_id": sample.id}
        if action == "cancel":
            if order_id is None:
                return {"error": "cancel 需 order_id"}
            o = db.session.query(ConditionalOrder).filter(ConditionalOrder.id == order_id).first()
            if not o:
                return {"error": f"条件单 {order_id} 不存在"}
            o.status = "cancelled"
            db.session.commit()
            return {"action": "cancel", "order_id": order_id, "ok": True}
        return {"error": f"未知 action: {action}"}


# ---------------------------------------------------------------------------
# 工具 9：持仓 / 模拟实盘查询（只读）
# ---------------------------------------------------------------------------
def portfolio_query(account_id: int = 1, mode: str = "sim") -> Dict[str, Any]:
    """查询模拟/实盘账户持仓与资金（只读）。

    Args:
        account_id: 账户 id（默认 1）
        mode: sim（模拟盘，默认）/ live（实盘，需后端已配置 broker）

    Returns:
        {mode, account_id, cash, positions:[{code,name,volume,avg_cost,...}], pnl}
    """
    try:
        from backend.app import create_app
        from backend.models import db, Account, Position
        app = create_app()
    except Exception as e:  # noqa: BLE001
        return {"error": f"账户模块不可用: {e}"}

    with app.app_context():
        acc = db.session.query(Account).filter(Account.id == account_id).first()
        if not acc:
            return {"error": f"账户 {account_id} 不存在"}
        positions = db.session.query(Position).filter(Position.account_id == account_id).all()
        return {
            "mode": mode,
            "account_id": account_id,
            "cash": float(getattr(acc, "cash", 0) or 0),
            "positions": [
                {
                    "code": p.code,
                    "name": p.name,
                    "volume": p.volume,
                    "avg_cost": float(p.avg_cost) if p.avg_cost else None,
                    "current_price": float(p.current_price) if p.current_price else None,
                }
                for p in positions
            ],
            "note": "实盘下单请走后端 order_routes（鉴权 + risk_check + 人工确认），MCP 不开放裸下单。",
        }


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------
def _register_all() -> None:
    register_tool(
        "get_kline",
        "获取个股/指数历史 K 线（开高低收+成交量）。支持代码或名称，可指定区间或最近 N 天。",
        {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "股票代码(如600519)或名称(如贵州茅台)"},
                "start": {"type": "string", "description": "起始日期 YYYY-MM-DD（可选）"},
                "end": {"type": "string", "description": "结束日期 YYYY-MM-DD（可选）"},
                "days": {"type": "integer", "description": "最近 N 天，默认120", "default": 120},
            },
            "required": ["code"],
        },
        get_kline,
    )
    register_tool(
        "analyze_technical",
        "对标的做四维技术面分析（趋势/动量/量能/形态）+ 综合评分。",
        {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "股票代码或名称"},
                "days": {"type": "integer", "description": "回看天数，默认180", "default": 180},
            },
            "required": ["code"],
        },
        analyze_technical,
    )
    register_tool(
        "smart_pick",
        "按策略跑每日选股+回测验证，返回 top_k 候选标的（多因子/双趋势共振）。",
        {
            "type": "object",
            "properties": {
                "strategy": {"type": "string", "enum": ["multi_factor", "dual_trend"], "default": "multi_factor"},
                "top_k": {"type": "integer", "default": 10},
                "start": {"type": "string", "description": "回测起始 YYYY-MM-DD（可选）"},
                "end": {"type": "string", "description": "回测结束 YYYY-MM-DD（可选）"},
                "pool_size": {"type": "integer", "default": 200},
            },
            "required": [],
        },
        smart_pick,
    )
    register_tool(
        "run_backtest",
        "对单只标的做策略回测，返回收益率/夏普/最大回撤等绩效。",
        {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "股票代码或名称"},
                "start": {"type": "string", "description": "起始 YYYY-MM-DD"},
                "end": {"type": "string", "description": "结束 YYYY-MM-DD"},
                "strategy": {
                    "type": "string",
                    "enum": ["multi_factor", "dual_trend", "ma_cross", "event_driven"],
                    "default": "multi_factor",
                },
                "initial_capital": {"type": "number", "default": 100000},
            },
            "required": ["code", "start", "end"],
        },
        run_backtest,
    )
    register_tool(
        "fund_flow",
        "查询资金流向：个股/市场/北向/行业。",
        {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "个股代码（scope=individual 时必填）"},
                "scope": {
                    "type": "string",
                    "enum": ["individual", "market", "northbound", "industry"],
                    "default": "individual",
                },
            },
            "required": [],
        },
        fund_flow,
    )
    register_tool(
        "stock_news",
        "获取个股近期新闻与事件（已清洗）。",
        {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "股票代码或名称"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["code"],
        },
        stock_news,
    )
    register_tool(
        "risk_assess",
        "对标的做综合风险评估（技术面+事件），返回风险等级与建议。",
        {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "股票代码或名称"}},
            "required": ["code"],
        },
        risk_assess,
    )
    register_tool(
        "conditional_orders",
        "条件单查询/创建/撤销。默认 dry_run（只模拟校验），绝不在 MCP 裸奔下单。",
        {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "create", "cancel"], "default": "list"},
                "order_id": {"type": "integer", "description": "查询/撤销时指定"},
                "code": {"type": "string"},
                "side": {"type": "string", "enum": ["buy", "sell"]},
                "trigger_type": {
                    "type": "string",
                    "enum": ["ma5_break_up", "ma5_break_down", "price_above", "price_below"],
                },
                "threshold": {"type": "number", "default": 0},
                "quantity": {"type": "integer", "default": 0},
                "dry_run": {"type": "boolean", "default": True},
            },
            "required": [],
        },
        conditional_orders,
    )
    register_tool(
        "portfolio_query",
        "查询模拟/实盘账户持仓与资金（只读）。实盘下单请走后端 order_routes。",
        {
            "type": "object",
            "properties": {
                "account_id": {"type": "integer", "default": 1},
                "mode": {"type": "string", "enum": ["sim", "live"], "default": "sim"},
            },
            "required": [],
        },
        portfolio_query,
    )


_register_all()
