"""mcp_server.gateway 同进程网关 + 意图识别测试。"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from mcp_server import gateway as gw


def test_available_tools_nonempty():
    tools = gw.available_tools()
    assert isinstance(tools, list)
    assert len(tools) >= 11
    for t in ("get_kline", "analyze_technical", "smart_pick", "run_backtest",
              "fund_flow", "stock_news", "risk_assess", "conditional_orders",
              "portfolio_query", "get_realtime_quote", "get_market_sentiment"):
        assert t in tools


def test_call_tool_unknown():
    r = gw.call_tool("not_a_tool")
    assert r["ok"] is False
    assert "工具不存在" in r["error"]


def test_call_tool_runs_without_crash():
    # 调用一个只读工具（smart_pick 走本地评分，不应崩溃；网络失败返回 error dict）
    r = gw.call_tool("smart_pick", market="A", limit=3)
    assert isinstance(r, dict)
    assert "ok" in r  # 统一结构
    # 要么成功要么友好错误，绝不应抛异常冒泡


def test_detect_intent_high_confidence_with_code():
    intent = gw.detect_intent("帮我回测一下 600519 的多因子策略")
    assert intent["tool"] == "run_backtest"
    assert intent["params"].get("code") == "600519"
    assert intent["confidence"] >= 0.85


def test_detect_intent_pick_with_code():
    intent = gw.detect_intent("用双趋势策略选几只 A 股，比如 600519")
    assert intent["tool"] == "smart_pick"
    # 选股是批量行为，code 仅作举例不约束参数（smart_pick 无 code 形参）
    assert intent["confidence"] >= 0.85


def test_detect_intent_portfolio_no_code():
    intent = gw.detect_intent("查一下我的持仓和盈亏")
    assert intent["tool"] == "portfolio_query"
    assert intent["confidence"] >= 0.85


def test_detect_intent_low_confidence_falls_through():
    # 无关键词 => 不命中，交给自然语言 AI
    intent = gw.detect_intent("今天天气怎么样")
    assert intent["tool"] is None
    assert intent["confidence"] == 0.0


def test_detect_intent_needs_code_but_missing_is_low():
    # 想要资金流但没给代码 => 低置信，不拦截
    intent = gw.detect_intent("这只股票资金流怎么样")
    assert intent["tool"] == "fund_flow"
    assert intent["confidence"] < 0.85


def test_call_tool_is_idempotent_import():
    # 多次调用不应重复注册或抛异常
    gw.call_tool("smart_pick", market="A", limit=1)
    gw.call_tool("run_backtest", code="600519")
    assert True


def test_detect_intent_realtime_quote_with_code():
    intent = gw.detect_intent("600519 现在价格多少，实时盘口怎么样")
    assert intent["tool"] == "get_realtime_quote"
    assert intent["params"].get("code") == "600519"
    assert intent["confidence"] >= 0.85


def test_detect_intent_realtime_quote_without_code_low():
    # 问实时但没给标的 => 低置信（needs_code），不拦截
    intent = gw.detect_intent("现在大盘实时走势怎么样")
    assert intent["tool"] == "get_realtime_quote"
    assert intent["confidence"] < 0.85


def test_detect_intent_market_sentiment_no_code():
    intent = gw.detect_intent("现在市场情绪怎么样，温度计到冰点了吗")
    assert intent["tool"] == "get_market_sentiment"
    assert intent["confidence"] >= 0.85


def test_detect_intent_sentiment_panic_keyword():
    intent = gw.detect_intent("今天市场是不是很恐慌")
    assert intent["tool"] == "get_market_sentiment"
    assert intent["confidence"] >= 0.85


def test_call_tool_timeout_guard(monkeypatch):
    """call_tool 应有总超时护栏：工具内部无界阻塞时返回友好错误，不卡死。"""
    import time

    def slow(**kwargs):
        time.sleep(2)
        return {"ok": True, "data": {}}

    # 注入一个慢工具并临时把超时压到极小
    monkeypatch.setattr(gw, "_GATEWAY_TIMEOUT", 0.1)
    monkeypatch.setitem(gw._TOOL_FUNCS, "slow_tool", "slow_tool")
    gw._resolve_func_cache = {}  # 清缓存（若有）

    # 直接 patch _resolve_func 返回 slow
    def fake_resolve(n):
        return slow if n == "slow_tool" else gw._resolve_func(n)

    monkeypatch.setattr(gw, "_resolve_func", fake_resolve)
    r = gw.call_tool("slow_tool")
    assert r["ok"] is False
    assert "超时" in r["error"]
