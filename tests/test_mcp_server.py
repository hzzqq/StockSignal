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
        "get_realtime_quote",
        "get_market_sentiment",
    ]:
        assert expected in names
    assert len(names) == 11


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


def test_tools_call_bad_arguments_typeerror():
    """传入 handler 不接受的关键字应被协议层捕获为 INVALID_PARAMS，不 crash server。"""
    r = asyncio.run(srv._dispatch(12, "tools/call", {"name": "get_kline", "arguments": {"foo": 1}}))
    assert r["error"]["code"] == srv.INVALID_PARAMS


def test_tools_call_non_dict_arguments():
    """arguments 为非 dict（如列表）时不应 crash，返回协议层错误。"""
    r = asyncio.run(srv._dispatch(13, "tools/call", {"name": "get_kline", "arguments": ["x"]}))
    # arguments 是 list → `or {}` 兜底为 {} → get_kline() 缺 required code → 业务 error（isError），非协议崩溃
    assert "result" in r or "error" in r


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


def test_get_kline_cache_hit(monkeypatch):
    """同一 code+days 二次调用应命中短缓存，fetcher 不被二次调用。"""
    import pandas as pd

    calls = {"n": 0}

    def fake_get_daily(*a, **k):
        calls["n"] += 1
        return pd.DataFrame({"date": ["2024-01-01"], "open": [1], "high": [2],
                              "low": [0], "close": [1], "volume": [100]})

    monkeypatch.setattr("modules.fetcher.StockFetcher.get_daily", fake_get_daily)
    monkeypatch.setattr(mcp_tools, "_TOOL_CACHE", {})
    mcp_tools.get_kline("600519", days=10)
    mcp_tools.get_kline("600519", days=10)  # 同参 → 应命中缓存
    assert calls["n"] == 1  # 仅拉取一次


def test_analyze_technical_cache_hit(monkeypatch):
    """analyze_technical 同参二次调用应命中缓存。"""
    import pandas as pd

    calls = {"n": 0}

    def fake_get_daily(*a, **k):
        calls["n"] += 1
        return pd.DataFrame({"date": ["2024-01-01"], "open": [1], "high": [2],
                              "low": [0], "close": [1], "volume": [100]})

    monkeypatch.setattr("modules.fetcher.StockFetcher.get_daily", fake_get_daily)
    monkeypatch.setattr(mcp_tools, "_TOOL_CACHE", {})
    mcp_tools.analyze_technical("600519", days=60)
    mcp_tools.analyze_technical("600519", days=60)
    assert calls["n"] == 1


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


def test_get_realtime_quote_success(monkeypatch):
    """实时盘口转发：应透出现价/涨跌/五档等字段。"""
    fake_quote = {
        "ticker": "600519",
        "name": "贵州茅台",
        "current": 1680.0,
        "prev_close": 1700.0,
        "open": 1695.0,
        "high": 1705.0,
        "low": 1680.0,
        "volume": 1234567,
        "amount": 2.1e9,
        "datetime": "2026-08-23 14:30:00",
        "bid": [{"price": 1679.0, "volume": 100}],
        "ask": [{"price": 1681.0, "volume": 200}],
    }

    def fake_get_realtime_quote(self, ticker):
        return fake_quote

    monkeypatch.setattr(
        "modules.fetcher.StockFetcher.get_realtime_quote", fake_get_realtime_quote
    )
    r = mcp_tools.get_realtime_quote("600519")
    assert r["ticker"] == "600519"
    assert r["name"] == "贵州茅台"
    assert r["current"] == 1680.0
    # 派生涨跌额/涨跌幅（change_pct 经 round(...,4) 取整）
    assert r["change"] == pytest.approx(-20.0)
    assert r["change_pct"] == pytest.approx(round(-20.0 / 1700.0 * 100, 4), rel=1e-6)
    # 五档透出
    assert r["bid"][0]["price"] == 1679.0
    assert r["ask"][0]["price"] == 1681.0


def test_get_realtime_quote_failure(monkeypatch):
    """数据源不可用时返回 error，不崩溃。"""
    monkeypatch.setattr(
        "modules.fetcher.StockFetcher.get_realtime_quote", lambda self, t: None
    )
    r = mcp_tools.get_realtime_quote("600519")
    assert "error" in r
    assert r["code"] == "600519"


def test_get_realtime_quote_market_status(monkeypatch):
    """盘口结果应透出市场时段（market_status / market_status_hint），
    让 AI / 前端正确语境化「当前价」——收盘后查到的是上一交易日快照。"""
    fake_quote = {
        "ticker": "600519", "name": "贵州茅台", "current": 1680.0, "prev_close": 1700.0,
        "open": 1695.0, "high": 1705.0, "low": 1680.0, "volume": 1234567,
        "amount": 2.1e9, "datetime": "2026-08-23 14:30:00",
        "bid": [{"price": 1679.0, "volume": 100}], "ask": [{"price": 1681.0, "volume": 200}],
    }
    monkeypatch.setattr(
        "modules.fetcher.StockFetcher.get_realtime_quote", lambda self, t: fake_quote
    )
    # 固定时段为「已收盘」，验证透出字段（不依赖测试运行时刻）
    monkeypatch.setattr(
        "modules.page_widgets.current_trading_session", lambda now=None: "after_close"
    )
    r = mcp_tools.get_realtime_quote("600519")
    assert r["market_status"] == "after_close"
    assert "上一交易日收盘快照" in r["market_status_hint"]


def test_get_realtime_quote_failure_market_status(monkeypatch):
    """即使数据源失败，也透出 market_status，便于 AI 解释「为何无行情」。"""
    monkeypatch.setattr(
        "modules.fetcher.StockFetcher.get_realtime_quote", lambda self, t: None
    )
    monkeypatch.setattr(
        "modules.page_widgets.current_trading_session", lambda now=None: "weekend"
    )
    r = mcp_tools.get_realtime_quote("600519")
    assert "error" in r
    assert r["market_status"] == "weekend"
    assert "周末休市" in r["market_status_hint"]


def test_get_market_sentiment_success(monkeypatch):
    """牧羊人情绪封装：应透出 8 项指标 + 温度（0-100）。"""
    # ⚠️ 牧羊人 v2（8→17 项）后，THRESHOLDS 已扩到 17 项；这里必须给齐，
    # 否则「仅 THRESHOLDS 指标透出」的等式断言会把「缺项」误判成「实现漏透出」。
    fake_today = ({"up_count": 4000, "down_count": 800, "limit_up": 60, "limit_down": 3,
                   "zt_prev_ret": 4.0, "red_ratio": 83.3, "connect_hl": 7, "zt_fail_ratio": 20.0,
                   "real_limit_up": 55, "median_chg": 1.2, "hb_wave10": 12,
                   "zt_fail_count": 15, "connect_2b": 18, "touch_down": 6,
                   "fc_ratio": 1.1, "avg_price": 18.6, "turnover_amt": 19000.0,
                   "flat_count": 200},  # flat_count 不应进 indicators
                  {"available": ["up_count", "down_count"], "unavailable": []})

    captured = {}
    def fake_hist(days=60):
        captured["days"] = days
        return None  # 走阈值线性打分路径
    monkeypatch.setattr("modules.shepherd.get_shepherd_today", lambda: fake_today)
    monkeypatch.setattr("modules.shepherd.get_shepherd_history", fake_hist)
    monkeypatch.setattr("modules.shepherd._CACHE", {})

    r = mcp_tools.get_market_sentiment(30)
    assert 0.0 <= r["temperature"] <= 100.0
    assert "temperature_label" in r
    # 仅 THRESHOLDS 指标透出（辅助键 flat_count 被过滤）
    assert set(r["indicators"].keys()) == set(__import__("modules.shepherd", fromlist=["THRESHOLDS"]).THRESHOLDS.keys())
    assert "flat_count" not in r["indicators"]
    assert r["meta"]["available"] == ["up_count", "down_count"]
    # days 参数必须透传给 shepherd_temperature → get_shepherd_history(hist_days)
    assert captured.get("days") == 30


def test_get_market_sentiment_network_down(monkeypatch):
    """全源失败时 indicators 为空、unavailable 标注。"""
    fake_today = ({}, {"available": [], "unavailable": [("legu", "x"), ("zt_pool", "y")]})

    monkeypatch.setattr("modules.shepherd.get_shepherd_today", lambda: fake_today)
    # shepherd_temperature({}) == 50.0 安全默认
    r = mcp_tools.get_market_sentiment(30)
    assert r["temperature"] == 50.0
    assert r["indicators"] == {}
    assert set(r["meta"]["unavailable"]) == {"legu", "zt_pool"}


def test_smart_pick_timeout_returns_error(monkeypatch):
    """回测超时应返回友好 error，而非卡死或抛异常。"""
    # 直接让超时执行器返回 None（模拟超时），隔离真实回测耗时
    monkeypatch.setattr("modules.timeout_exec.run_with_timeout", lambda fn, timeout=None: None)
    # 避免 _resolve_code 走真实 fetcher 网络
    monkeypatch.setattr(mcp_tools, "_resolve_code", lambda c: "600519")
    r = mcp_tools.smart_pick(pool_size=5)
    assert "error" in r  # 超时友好错误


def test_run_backtest_timeout_returns_error(monkeypatch):
    """单标的回测超时应返回友好 error。"""
    monkeypatch.setattr("modules.timeout_exec.run_with_timeout", lambda fn, timeout=None: None)
    monkeypatch.setattr(mcp_tools, "_resolve_code", lambda c: "600519")
    r = mcp_tools.run_backtest("600519", "2024-01-01", "2024-02-01")
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
        "实时盘口",
        "市场情绪",
    }


def test_scenario_render_realtime():
    s = prompts.render_scenario("实时盘口", code="600519")
    assert "600519" in s
    assert "get_realtime_quote" in s
    assert "红涨绿跌" in s


def test_scenario_render_sentiment():
    s = prompts.render_scenario("市场情绪", days=30)
    assert "get_market_sentiment" in s
    assert "温度计" in s


def test_system_prompt_lists_new_tools():
    sp = prompts.build_system_prompt()
    assert "get_realtime_quote" in sp
    assert "get_market_sentiment" in sp


def test_scenario_missing_arg():
    # 缺参数时不应抛，而是返回带提示的字符串
    s = prompts.render_scenario("回测")
    assert "模板缺参数" in s
