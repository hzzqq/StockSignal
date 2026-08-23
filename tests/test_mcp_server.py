"""StockSignal MCP Server 测试。

覆盖：
1. JSON-RPC 协议层：initialize / tools/list / tools/call（含未知方法、参数错误）。
2. 工具转发：用 monkeypatch 隔离远端网络（akshare/flask），验证 handler 真实调用到
   底层模块且返回结构化结果。
3. prompt 体系：SYSTEM_PROMPT 非空、场景模板可渲染。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from mcp_server import server as srv  # noqa: E402
from mcp_server import tools as mcp_tools  # noqa: E402  (注册副作用)
from mcp_server import prompts  # noqa: E402


# ---------------------------------------------------------------------------
# 协议层
# ---------------------------------------------------------------------------
def test_initialize():
    resp = srv._handle_initialize(1, {})
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    assert resp["result"]["serverInfo"]["name"] == "stocksignal-mcp"
    assert "tools" in resp["result"]["capabilities"]


def test_tools_list_count():
    resp = srv._handle_tools_list(2, {})
    names = [t["name"] for t in resp["result"]["tools"]]
    for expected in [
        "get_kline",
        "analyze_technical",
        "smart_pick",
        "run_backtest",
        "fund_flow",
        "stock_news",
        "risk_assess",
        "conditional_orders",
        "portfolio_query",
    ]:
        assert expected in names
    assert len(names) == 9


def test_unknown_method():
    resp = srv._handle_initialize  # placeholder
    r = asyncio.run(srv._dispatch(9, "bogus/method", {}))
    assert r["error"]["code"] == srv.METHOD_NOT_FOUND


def test_tools_call_missing_name():
    r = asyncio.run(srv._dispatch(10, "tools/call", {}))
    assert r["error"]["code"] == srv.INVALID_PARAMS


def test_tools_call_unknown_tool():
    r = asyncio.run(srv._dispatch(11, "tools/call", {"name": "nope"}))
    assert r["error"]["code"] == srv.METHOD_NOT_FOUND


def test_process_one_notification_no_reply():
    # 无 id 的通知不回包
    out = asyncio.run(srv._process_one({"method": "notifications/initialized"}))
    assert out is None


# ---------------------------------------------------------------------------
# 工具转发（隔离远端）
# ---------------------------------------------------------------------------
def test_get_kline_handles_empty_data(monkeypatch):
    """远端无数据时应返回 error 字段而非崩溃。"""
    import pandas as pd

    def fake_get_daily(*a, **k):
        return pd.DataFrame()

    monkeypatch.setattr("modules.fetcher.StockFetcher.get_daily", fake_get_daily)
    r = mcp_tools.get_kline("600519", days=10)
    assert "error" in r
    assert r["code"] == "600519"


def test_analyze_technical_empty(monkeypatch):
    import pandas as pd

    monkeypatch.setattr(
        "modules.fetcher.StockFetcher.get_daily", lambda *a, **k: pd.DataFrame()
    )
    r = mcp_tools.analyze_technical("600519")
    assert "error" in r


def test_fund_flow_market(monkeypatch):
    monkeypatch.setattr(
        "modules.fundflow.get_market_fund_flow",
        lambda *a, **k: {"sample": 1},
    )
    r = mcp_tools.fund_flow(scope="market")
    assert r["scope"] == "market"
    assert r["data"] == {"sample": 1}


def test_fund_flow_individual_requires_code():
    r = mcp_tools.fund_flow(scope="individual", code="")
    assert "error" in r


def test_conditional_orders_list_offline(monkeypatch):
    """后端不可用时应优雅返回 error，不 crash server。"""

    def boom(*a, **k):
        raise RuntimeError("no backend")

    monkeypatch.setattr("backend.app.create_app", boom)
    r = mcp_tools.conditional_orders(action="list")
    assert "error" in r


def test_conditional_orders_create_dry_run_validation(monkeypatch):
    """create + dry_run 时若参数不全应报错。"""
    r = mcp_tools.conditional_orders(action="create", dry_run=True)
    assert "error" in r  # 缺 code/side/trigger_type/quantity


def test_portfolio_query_offline(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no backend")

    monkeypatch.setattr("backend.app.create_app", boom)
    r = mcp_tools.portfolio_query()
    assert "error" in r


def test_risk_assess_empty(monkeypatch):
    import pandas as pd

    monkeypatch.setattr(
        "modules.fetcher.StockFetcher.get_daily", lambda *a, **k: pd.DataFrame()
    )
    r = mcp_tools.risk_assess("600519")
    assert "error" in r


def test_smart_pick_signature():
    # 仅验证签名可调用、参数齐全（不真正跑回测，避免远端依赖）
    import inspect

    sig = inspect.signature(mcp_tools.smart_pick)
    assert "strategy" in sig.parameters
    assert "top_k" in sig.parameters


def test_run_backtest_signature():
    import inspect

    sig = inspect.signature(mcp_tools.run_backtest)
    for p in ("code", "start", "end"):
        assert p in sig.parameters


# ---------------------------------------------------------------------------
# prompt 体系
# ---------------------------------------------------------------------------
def test_system_prompt_nonempty_and_safe():
    sp = prompts.build_system_prompt()
    assert "StockSignal" in sp
    assert "不下单" in sp or "不荐赌" in sp  # 安全约束存在
    assert "红涨绿跌" in sp


def test_scenario_render():
    s = prompts.render_scenario("诊股", code="贵州茅台")
    assert "贵州茅台" in s
    assert "analyze_technical" in s


def test_scenario_list():
    assert set(prompts.list_scenarios()) >= {
        "诊股",
        "选股",
        "回测",
        "盯盘",
        "条件单",
        "持仓体检",
    }


def test_scenario_missing_arg():
    # 缺参数时不应抛，而是返回带提示的字符串
    s = prompts.render_scenario("回测")
    assert "模板缺参数" in s
