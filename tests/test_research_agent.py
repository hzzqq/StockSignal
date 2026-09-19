"""H1 AI 研究智能体契约测试（spec: .workbuddy/specs/ai_research_agent_contract.md）。

全部离线：tools/planner/synthesizer 均依赖注入，LLM 一律关闭（AC6）。
覆盖 AC1 返回契约 / AC2 有界性 / AC3 只读红线 / AC4 溯源完整 / AC5 诚实降级 /
AC6 零 LLM 可用 / AC7 新鲜度溯源 / AC8 确定性规划器路由 + gateway registry 兜底 +
worker/task_routes/53 页接线。
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from modules import research_agent as ra

REPO = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# fake 工具表（离线）
# ---------------------------------------------------------------------------
def _ok(result):
    def _fn(**kwargs):
        return result
    return _fn


def _boom(**kwargs):
    raise RuntimeError("网络炸了")


def _slow(**kwargs):
    time.sleep(0.5)
    return {"value": 1, "generated_at": "2026-09-17 10:00"}


FAKE_TOOLS = {
    "always_ok": _ok({"value": 1, "generated_at": "2026-09-17 10:00"}),
    "as_of_last": _ok({"end": "2026-01-01", "generated_at": "2026-09-17 10:00"}),
    "big_list": _ok({"items": list(range(100)), "name": "x"}),
    "err_result": _ok({"error": "数据源不可用"}),
    "boom": _boom,
    "slow": _slow,
    "get_data_health": _ok({
        "ok": True,
        "sources": [
            {"source": "akshare", "status": "stale"},
            {"source": "baostock", "status": "ok"},
            {"source": "tushare", "status": "ok", "stalled": True},
        ],
    }),
    "get_market_sentiment": _ok({"temperature": 62.5, "generated_at": "2026-09-17 09:30"}),
    "get_macro_indicators": _ok({"indicators": {"PMI": 50.1}, "as_of": "2026-08-31"}),
    "get_lhb": _ok({"available": False, "reason": "非交易日"}),
    "portfolio_query": _ok({"cash": 100000.0, "positions": [{"code": "600519"}]}),
    "get_realtime_quote": _ok({"current": 1700.0, "datetime": "2026-09-17 15:00:00"}),
    "analyze_technical": _ok({"analysis": {"score": {"total": 66}}}),
    "stock_news": _ok({"news": [{"title": "t1", "date": "2026-09-17"}]}),
    "fund_flow": _ok({"data": {"net": 1.2}}),
    "risk_assess": _ok({"risk_level": "中"}),
    "smart_pick": _ok({"picks": [{"code": "600519", "rank": 1}]}),
    "conditional_orders": _ok({"orders": [], "count": 0}),
    "get_valuation": _ok({"pe": [11.2], "pb": [1.8], "span": "2016~2026",
                           "as_of": "2026-09-17"}),
    "list_risk_alerts": _ok({"code": "600519",
                             "components": {"质押": {"ratio": 0.3}}, "errors": []}),
}


def _plan(*tools_):
    return [{"tool": t, "args": {}, "why": "test"} for t in tools_]


def _run(question="测试问题", plan=None, tools=None, **kw):
    return ra.run_research(
        question,
        tools=tools if tools is not None else FAKE_TOOLS,
        planner=(lambda q, avail: plan) if plan is not None else None,
        use_llm=False,
        **kw,
    )


# ---------------------------------------------------------------------------
# AC1 返回契约
# ---------------------------------------------------------------------------
def test_ac1_result_contract_keys_and_ok_status():
    r = _run(plan=_plan("always_ok"))
    for k in ("question", "status", "steps", "answer", "citations",
              "limitations", "generated_at", "elapsed_s"):
        assert k in r, f"缺少键 {k}"
    assert r["status"] == "ok"
    assert isinstance(r["elapsed_s"], (int, float))


def test_ac1_step_trace_fields_complete():
    r = _run(plan=_plan("always_ok"))
    s = r["steps"][0]
    for k in ("idx", "tool", "args", "status", "duration_ms", "summary", "data_as_of"):
        assert k in s, f"step 缺少 {k}"
    assert s["status"] == "ok"
    assert s["tool"] == "always_ok"
    assert s["duration_ms"] >= 0
    assert s["data_as_of"] == "2026-09-17 10:00"


def test_ac1_partial_when_mixed_and_ok_when_all_success():
    r_all = _run(plan=_plan("always_ok", "get_macro_indicators"))
    assert r_all["status"] == "ok"
    r_mix = _run(plan=_plan("boom", "always_ok"))
    assert r_mix["status"] == "partial"


# ---------------------------------------------------------------------------
# AC2 有界性
# ---------------------------------------------------------------------------
def test_ac2_max_steps_clamped_to_eight():
    r = _run(plan=_plan(*(["always_ok"] * 10)), max_steps=99)
    assert len(r["steps"]) <= 8
    assert any("max_steps" in lim or "截断" in lim for lim in r["limitations"])


def test_ac2_max_steps_default_truncates_plan():
    r = _run(plan=_plan(*(["always_ok"] * 8)), max_steps=3)
    assert len(r["steps"]) == 3
    assert r["limitations"]


def test_ac2_budget_stops_between_steps():
    r = _run(plan=_plan("slow", "always_ok"), budget_s=0.2)
    assert [s["tool"] for s in r["steps"]] == ["slow"]
    assert r["status"] == "partial"
    assert any("预算" in lim for lim in r["limitations"])


# ---------------------------------------------------------------------------
# AC3 只读安全红线
# ---------------------------------------------------------------------------
def test_ac3_unknown_tool_rejected_not_executed():
    r = _run(plan=_plan("no_such_tool", "always_ok"))
    st = {s["tool"]: s["status"] for s in r["steps"]}
    assert st["no_such_tool"] == "rejected"
    assert st["always_ok"] == "ok"


def test_ac3_write_action_rejected():
    r = _run(plan=[{"tool": "conditional_orders",
                    "args": {"action": "create", "code": "600519", "side": "buy",
                             "trigger_type": "price_above", "threshold": 1,
                             "quantity": 100, "dry_run": True},
                    "why": "试探写操作"}])
    s = r["steps"][0]
    assert s["status"] == "rejected"
    assert "只读" in s.get("reason", "") or "写" in s.get("reason", "")


def test_ac3_rejected_never_in_citations():
    r = _run(plan=_plan("no_such_tool"))
    assert r["citations"] == []
    assert r["status"] == "unavailable"


def test_ac3_list_action_allowed():
    r = _run(plan=[{"tool": "conditional_orders", "args": {"action": "list"}, "why": "查询"}])
    assert r["steps"][0]["status"] == "ok"


# ---------------------------------------------------------------------------
# AC4 溯源完整
# ---------------------------------------------------------------------------
def test_ac4_summary_truncates_big_list():
    r = _run(plan=_plan("big_list"))
    summ = r["steps"][0]["summary"]
    assert len(summ["items"]) <= 5
    assert summ.get("_total_items") == 100
    # 原始结果未被改动（防失真）
    assert len(FAKE_TOOLS["big_list"]()["items"]) == 100


def test_ac4_citations_reference_existing_steps_with_as_of():
    r = _run(plan=_plan("always_ok", "get_market_sentiment"))
    assert len(r["citations"]) == 2
    idx_set = {s["idx"] for s in r["steps"]}
    for c in r["citations"]:
        assert c["step"] in idx_set
        assert c["tool"]
        assert c["as_of"]


def test_ac4_rule_answer_carries_citations():
    r = _run(plan=_plan("always_ok"))
    assert "[S1]" in r["answer"]
    # 引用必须挂在「数据要点行」上（而非仅脚注），防 mutation 丢行内引用（AC4）
    assert "- [S1] `always_ok`：" in r["answer"]


# ---------------------------------------------------------------------------
# AC5 诚实降级
# ---------------------------------------------------------------------------
def test_ac5_all_fail_unavailable_with_limitations():
    r = _run(plan=_plan("err_result", "boom"))
    assert r["status"] == "unavailable"
    assert r["citations"] == []
    assert r["limitations"]
    assert r["answer"]  # 如实说明而非空串
    st = {s["tool"]: s["status"] for s in r["steps"]}
    assert st["err_result"] == "error"      # 工具返回 error 键 → error
    assert st["boom"] == "error"            # 抛异常 → error（隔离不崩）


def test_ac5_error_isolated_later_steps_run():
    r = _run(plan=_plan("boom", "always_ok"))
    st = {s["tool"]: s["status"] for s in r["steps"]}
    assert st["boom"] == "error"
    assert st["always_ok"] == "ok"
    assert r["status"] == "partial"


# ---------------------------------------------------------------------------
# AC6 零 LLM 可用（use_llm=False 全程；此处验证默认规划器+规则合成器端到端）
# ---------------------------------------------------------------------------
def test_ac6_zero_llm_end_to_end():
    r = _run("市场情绪怎么样", plan=None)  # planner=None → 确定性规划器
    tools_used = [s["tool"] for s in r["steps"]]
    assert tools_used[0] == "get_data_health"          # 治理词首步（AC7/AC8）
    assert "get_market_sentiment" in tools_used
    assert r["status"] in ("ok", "partial")
    assert r["answer"] and r["citations"]


def test_ac6_llm_failure_falls_back_to_rule_synthesizer():
    # LLM 声称可用但返回 None（模拟超时/限流）→ 必须回退规则合成器且仍带引用
    class _FakeLLM:
        @staticmethod
        def is_configured():
            return True

        @staticmethod
        def chat_completion(*a, **kw):
            return None

        @staticmethod
        def chat_completion_json(*a, **kw):
            return None

    r = ra.run_research(
        "测试", tools=FAKE_TOOLS,
        planner=lambda q, avail: _plan("always_ok"),
        use_llm=_FakeLLM(),
    )
    assert r["status"] == "ok"
    assert "[S1]" in r["answer"]


# ---------------------------------------------------------------------------
# AC7 新鲜度溯源
# ---------------------------------------------------------------------------
def test_ac7_data_as_of_priority_order():
    r = _run(plan=_plan("as_of_last"))
    # 优先级 as_of > generated_at > datetime > date > end > latest_date
    assert r["steps"][0]["data_as_of"] == "2026-09-17 10:00"


def test_ac7_stale_sources_surface_in_limitations():
    r = _run("市场情绪怎么样", plan=None)
    joined = "\n".join(r["limitations"])
    assert "akshare" in joined
    assert "tushare" in joined


def test_ac7_source_name_fits_real_data_health_shape():
    """真实 data_health 行字段是 name/key（非 source），源名必须提取成功（真实冒烟暴露）。"""
    tools = dict(FAKE_TOOLS)
    tools["get_data_health"] = _ok({
        "ok": True,
        "sources": [
            {"key": "shepherd_sentiment", "name": "牧羊人情绪", "as_of": "2026-09-04",
             "lag_days": 13, "status": "stale", "stalled": False},
            {"key": "p1_event", "name": "P1 事件因子", "status": "ok", "stalled": True},
        ],
    })
    r = _run("市场情绪怎么样", plan=None, tools=tools)
    joined = "\n".join(r["limitations"])
    assert "牧羊人情绪" in joined, f"stale 源名未浮出: {joined}"
    assert "P1 事件因子" in joined, f"stalled 源名未浮出: {joined}"
    assert "?" not in joined, f"源名提取落空: {joined}"


# ---------------------------------------------------------------------------
# AC8 确定性规划器路由
# ---------------------------------------------------------------------------
def test_ac8_route_realtime_with_code():
    tools = [s["tool"] for s in ra.plan_steps("600519 现在多少钱")]
    assert tools[0] == "get_data_health" or tools[0] == "get_realtime_quote"
    assert "get_realtime_quote" in tools


def test_ac8_route_sentiment_governance_first():
    tools = [s["tool"] for s in ra.plan_steps("市场情绪怎么样，恐慌吗")]
    assert tools[0] == "get_data_health"
    assert "get_market_sentiment" in tools


def test_ac8_route_macro_and_lhb():
    assert "get_macro_indicators" in [s["tool"] for s in ra.plan_steps("宏观 PMI 最近如何")]
    assert "get_lhb" in [s["tool"] for s in ra.plan_steps("今天龙虎榜有什么动静")]


def test_ac8_route_bare_code_trio():
    tools = [s["tool"] for s in ra.plan_steps("600519")]
    assert tools == ["get_realtime_quote", "analyze_technical", "stock_news"]


def test_ac8_route_portfolio_and_pick():
    assert "portfolio_query" in [s["tool"] for s in ra.plan_steps("我的持仓盈亏如何")]
    tools = [s["tool"] for s in ra.plan_steps("帮我选几只股票")]
    assert tools[-1] == "smart_pick"  # 慢任务置末


def test_ac8_route_fallback_honest():
    tools = [s["tool"] for s in ra.plan_steps("今天天气怎么样")]
    assert tools == ["get_data_health", "get_market_sentiment"]


def test_ac8_plan_dedup_and_cap():
    tools = [s["tool"] for s in ra.plan_steps("600519 实时 技术面 新闻 资金 风险 情绪 温度计 龙虎榜 宏观 持仓 选股")]
    assert len(tools) == len(set(tools)), "计划内工具必须去重"
    assert len(tools) <= 8


# ---------------------------------------------------------------------------
# gateway registry 兜底（修复 11/16 漂移）
# ---------------------------------------------------------------------------
def test_gateway_available_tools_covers_registry():
    from mcp_server import gateway
    from mcp_server.server import TOOLS
    from mcp_server import tools as _reg  # noqa: F401 注册副作用

    avail = set(gateway.available_tools())
    assert avail >= set(TOOLS), f"gateway 缺工具: {set(TOOLS) - avail}"
    assert len(avail) >= 16


def test_gateway_can_call_registry_only_tool():
    from mcp_server import gateway

    res = gateway.call_tool("get_data_health")
    assert isinstance(res, dict) and "ok" in res  # 离线 True/False 均可，关键是可达不抛


def test_gateway_unknown_tool_still_fails_gracefully():
    from mcp_server import gateway

    res = gateway.call_tool("definitely_not_a_tool")
    assert res.get("ok") is False


# ---------------------------------------------------------------------------
# worker / task_routes 接线
# ---------------------------------------------------------------------------
def test_worker_registers_ai_research_handler():
    from backend.tasks.worker import task_worker

    assert "ai_research" in task_worker._handlers


def test_worker_handler_calls_run_research(monkeypatch):
    import backend.tasks.worker as w
    import modules.research_agent as ra_mod

    sentinel = {"question": "q", "status": "ok", "steps": [], "answer": "a",
                "citations": [], "limitations": [], "generated_at": "x", "elapsed_s": 0.0}
    seen = {}

    def _fake(question, **kw):
        seen["question"] = question
        seen["on_step"] = kw.get("on_step")
        return sentinel

    monkeypatch.setattr(ra_mod, "run_research", _fake)
    out = w._handle_ai_research({"question": "q", "__task_id__": "tid"})
    assert out is sentinel
    assert seen["question"] == "q"
    assert callable(seen["on_step"])  # 进度回调必须接线


def test_task_routes_allowlist_includes_ai_research():
    from backend.api.task_routes import _ALLOWED_TASK_TYPES

    assert "ai_research" in _ALLOWED_TASK_TYPES


# ---------------------------------------------------------------------------
# 53 页 additive 接线
# ---------------------------------------------------------------------------
def test_page53_has_research_mode_wiring():
    src = (REPO / "pages" / "53_星辰AI.py").read_text(encoding="utf-8")
    assert "深度研究" in src
    assert '"ai_research"' in src or "'ai_research'" in src
    # 既有 ai_consult 流程不得被移除（additive-only）
    assert "ai_consult" in src


def test_module_compiles():
    import py_compile

    py_compile.compile(str(REPO / "modules" / "research_agent.py"), doraise=True)
    py_compile.compile(str(REPO / "mcp_server" / "gateway.py"), doraise=True)
    py_compile.compile(str(REPO / "backend" / "tasks" / "worker.py"), doraise=True)


# ---------------------------------------------------------------------------
# T-122：gateway 分工具超时 + sentiment 缓存 TTL 分档（H1 验收观察的修复）
# ---------------------------------------------------------------------------
def test_t122_gateway_timeout_per_tool():
    """重工具 gateway 护栏 ≥ 内部护栏（sentiment 冷启动实测 47.5s；smart_pick/run_backtest 内部 90s/60s）。"""
    from mcp_server import gateway

    assert gateway._timeout_for("get_market_sentiment") == 60
    assert gateway._timeout_for("smart_pick") == 100
    assert gateway._timeout_for("run_backtest") == 70
    assert gateway._timeout_for("get_realtime_quote") == 12  # 轻工具默认
    assert gateway._timeout_for("no_such_tool") == 12        # 未知回落默认


def test_t122_gateway_call_tool_passes_tiered_timeout(monkeypatch):
    """call_tool 必须真的把分档超时传给 run_with_timeout（防纯函数对但没接上的假绿）。"""
    import mcp_server.gateway as gw
    import modules.timeout_exec as te

    seen = {}

    def _fake_rwt(fn, timeout=None):
        seen["timeout"] = timeout
        return {"marker": 1}

    monkeypatch.setattr(te, "run_with_timeout", _fake_rwt)
    monkeypatch.setattr(gw, "_resolve_func", lambda n: lambda **kw: {"x": 1})

    assert gw.call_tool("get_market_sentiment")["ok"] is True
    assert seen["timeout"] == 60
    assert gw.call_tool("get_realtime_quote")["ok"] is True
    assert seen["timeout"] == 12


def test_t122_sentiment_cache_ttl_300s(monkeypatch):
    """sentiment 结果缓存 TTL=300s：冷启动 47.5s 的重工具会话内重复提问应近零成本。

    走 get_market_sentiment 真实代码路径（shepherd 打桩，离线）；回拨缓存时间戳 200s
    后仍必须命中——若实现退回全局 30s TTL 则本测试变红（mutation 目标）。
    """
    import modules.shepherd as shepherd
    from mcp_server import tools as mt

    calls = {"n": 0}

    def _fake_today():
        calls["n"] += 1
        today = {k: 1.0 for k in shepherd.THRESHOLDS}
        return today, {"available": list(today.keys()), "unavailable": []}

    monkeypatch.setattr(shepherd, "get_shepherd_today", _fake_today)
    monkeypatch.setattr(shepherd, "shepherd_temperature", lambda today, hist_days=30: 55.0)
    monkeypatch.setattr(mt, "_TOOL_CACHE", {})

    mt.get_market_sentiment(days=30)
    mt.get_market_sentiment(days=30)
    assert calls["n"] == 1, "二次调用应命中缓存"

    key = next(k for k in mt._TOOL_CACHE if k.startswith("sentiment:"))
    ts, ttl, val = mt._TOOL_CACHE[key]
    assert ttl == 300, f"sentiment 缓存 TTL 应为 300，实际 {ttl}"
    mt._TOOL_CACHE[key] = (ts - 200, ttl, val)  # 回拨 200s（< 300 仍新鲜）
    mt.get_market_sentiment(days=30)
    assert calls["n"] == 1, "TTL=300 下 200s 前的缓存应仍命中"


def test_t122_tool_cache_helper_backward_compatible():
    """缓存 helper 旧行为兼容：不传 ttl 时按全局 30s 语义（kline/tech 等既有调用点不受影响）。"""
    from mcp_server import tools as mt

    mt._tool_cache_set("k:test", {"a": 1})
    assert mt._TOOL_CACHE["k:test"][1] == mt._TOOL_CACHE_TTL
    assert mt._tool_cache_get("k:test") == {"a": 1}


# ---------------------------------------------------------------------------
# T-124：分工具超时配置修复（错误消息报告真实分档 + 配置块位置归位）
# ---------------------------------------------------------------------------
def test_t124_timeout_error_message_reports_actual_tier(monkeypatch):
    """超时错误消息必须报告真实分档上限：sentiment（60s 档）被砍时报 >60s，而非硬编码 >12s。"""
    import mcp_server.gateway as gw
    import modules.timeout_exec as te

    monkeypatch.setattr(te, "run_with_timeout", lambda fn, timeout=None: None)  # 模拟超时
    monkeypatch.setattr(gw, "_resolve_func", lambda n: lambda **kw: {"x": 1})

    res = gw.call_tool("get_market_sentiment")
    assert res["ok"] is False
    assert ">60s" in res["error"], f"错误消息未反映真实分档: {res['error']}"

    res2 = gw.call_tool("get_realtime_quote")  # 默认档仍报 12s
    assert ">12s" in res2["error"], f"默认档错误消息异常: {res2['error']}"


def test_t124_timeout_config_defined_before_use():
    """配置块（_PER_TOOL_TIMEOUT/_timeout_for）必须在 call_tool 使用点之前定义（可读性/防误改）。"""
    import inspect

    import mcp_server.gateway as gw

    src = inspect.getsource(gw)
    pos_use = src.index("timeout=_timeout_for(name)")
    pos_def = src.index("_PER_TOOL_TIMEOUT: Dict[str, int] = {")
    assert pos_def < pos_use, "_PER_TOOL_TIMEOUT 定义出现在 call_tool 使用点之后（应上移到常量区）"


def test_t122_sentiment_failure_not_cached(monkeypatch):
    """失败/空结果绝不缓存（诚实语义）：全源失败时每次重试，不得把网络抖动放大成 5 分钟假数据。"""
    import modules.shepherd as shepherd
    from mcp_server import tools as mt

    calls = {"n": 0}

    def _fake_today_down():
        calls["n"] += 1
        return {}, {"available": [], "unavailable": [("legu", "x"), ("zt_pool", "y")]}

    monkeypatch.setattr(shepherd, "get_shepherd_today", _fake_today_down)
    monkeypatch.setattr(shepherd, "shepherd_temperature", lambda today, hist_days=30: 50.0)
    monkeypatch.setattr(mt, "_TOOL_CACHE", {})

    r1 = mt.get_market_sentiment(days=30)
    r2 = mt.get_market_sentiment(days=30)
    assert calls["n"] == 2, "全源失败不得写缓存（每次调用都应真实重试）"
    assert r1["indicators"] == {} and r2["indicators"] == {}
    assert not any(k.startswith("sentiment:") for k in mt._TOOL_CACHE)


# ===========================================================================
# T-138：H1 增量——多轮对话记忆 + 估值/排雷路由（spec: h1_increments_contract.md）
# ===========================================================================

# ---------------------------------------------------------------------------
# M1：history 规范化（角色过滤 / 截断 / 最近 6 条 / 非法整体降级）
# ---------------------------------------------------------------------------
def test_t138_m1_normalize_history_filters_and_truncates():
    hist = [
        {"role": "system", "content": "系统提示"},
        {"role": "tool", "content": "数据卡片"},
        {"role": "user", "content": "   "},
        {"role": "user", "content": "q" * 300},
        {"role": "assistant", "content": "a" * 300},
        {"role": "user", "content": "最后一条"},
    ]
    out = ra.normalize_history(hist)
    assert len(out) == 3
    assert all(h["role"] in ("user", "assistant") for h in out)
    assert len(out[0]["content"]) == 200
    assert out[1]["content"] == "a" * 200
    assert out[-1]["content"] == "最后一条"


def test_t138_m1_normalize_history_keeps_most_recent_six():
    hist = [{"role": "user", "content": f"消息{i}"} for i in range(10)]
    out = ra.normalize_history(hist)
    assert len(out) == 6
    assert out[0]["content"] == "消息4"
    assert out[-1]["content"] == "消息9"


def test_t138_m1_normalize_history_invalid_input_degrades_to_empty():
    assert ra.normalize_history(None) == []
    assert ra.normalize_history("不是列表") == []
    assert ra.normalize_history({"role": "user", "content": "dict 而非 list"}) == []
    assert ra.normalize_history([{"role": "user"}]) == []
    assert ra.normalize_history(["不是字典"]) == []
    assert ra.normalize_history(
        [{"role": "user", "content": "ok"}, {"content": "缺 role"}]
    ) == []


def test_t138_m1_run_research_accepts_history_and_garbage_without_error():
    r = _run("它呢", plan=_plan("always_ok"),
             history=[{"role": "user", "content": "600519 怎么样"}])
    assert r["status"] == "ok"
    r_bad = _run("它呢", plan=_plan("always_ok"), history=42)
    assert r_bad["status"] == "ok"


# ---------------------------------------------------------------------------
# M2：LLM 规划 / 合成 prompt 带历史节（LLM 失败回退与 AC6 等价）
# ---------------------------------------------------------------------------
class _CapPlanLLM:
    prompts = []

    @staticmethod
    def is_configured():
        return True

    @staticmethod
    def chat_completion_json(messages, **kw):
        _CapPlanLLM.prompts.append(messages[0]["content"])
        return None  # 恒失败 → 回退确定性规划器

    @staticmethod
    def chat_completion(messages, **kw):
        return None


class _CapSynthLLM:
    prompts = []

    @staticmethod
    def is_configured():
        return True

    @staticmethod
    def chat_completion_json(messages, **kw):
        return None

    @staticmethod
    def chat_completion(messages, **kw):
        _CapSynthLLM.prompts.append(messages[0]["content"])
        return None  # 恒失败 → 回退规则合成器


def test_t138_m2_llm_plan_prompt_contains_history_section():
    _CapPlanLLM.prompts = []
    hist = [{"role": "user", "content": "600519 市盈率多少"}]
    r = ra.run_research("再看看 PE 分位", tools=FAKE_TOOLS,
                        use_llm=_CapPlanLLM, history=hist)
    assert r["status"] in ("ok", "partial")
    assert _CapPlanLLM.prompts, "LLM 规划未被调用"
    assert "最近对话" in _CapPlanLLM.prompts[0]
    assert "600519 市盈率多少" in _CapPlanLLM.prompts[0]
    # LLM 失败回退后：确定性规划器 + M3 继承 + T3 路由仍命中（行为与 AC6 等价）
    assert any(s["tool"] == "get_valuation" for s in r["steps"])


def test_t138_m2_llm_plan_prompt_pins_code_constraint():
    _CapPlanLLM.prompts = []
    ra.run_research("测试", tools=FAKE_TOOLS, use_llm=_CapPlanLLM,
                    history=[{"role": "user", "content": "600519 怎么样"}])
    assert _CapPlanLLM.prompts
    assert "6 位代码" in _CapPlanLLM.prompts[0]


def test_t138_m2_llm_synthesize_prompt_contains_history():
    _CapSynthLLM.prompts = []
    hist = [{"role": "user", "content": "之前问过 600519"}]
    r = ra.run_research("测试", tools=FAKE_TOOLS,
                        planner=lambda q, avail: _plan("always_ok"),
                        use_llm=_CapSynthLLM, history=hist)
    assert "[S1]" in r["answer"]  # LLM 合成失败 → 规则合成器兜底且引用不丢（AC4/AC6）
    assert _CapSynthLLM.prompts, "LLM 合成未被调用"
    assert "最近对话" in _CapSynthLLM.prompts[0]
    assert "之前问过 600519" in _CapSynthLLM.prompts[0]


def test_t138_m2_no_history_no_history_section():
    _CapPlanLLM.prompts = []
    ra.run_research("市场情绪怎么样", tools=FAKE_TOOLS, use_llm=_CapPlanLLM)
    assert _CapPlanLLM.prompts
    assert "最近对话" not in _CapPlanLLM.prompts[0]


# ---------------------------------------------------------------------------
# M3：确定性规划器代码继承（mutation 目标）
# ---------------------------------------------------------------------------
def test_t138_m3_code_inherited_from_recent_history():
    hist = [
        {"role": "user", "content": "600519 基本面怎么样"},
        {"role": "assistant", "content": "600519 研究结论如下"},
    ]
    plan = ra.plan_steps("它现在多少钱", hist)
    tools = [s["tool"] for s in plan]
    assert "get_realtime_quote" in tools
    quote = next(s for s in plan if s["tool"] == "get_realtime_quote")
    assert quote["args"].get("code") == "600519"


def test_t138_m3_current_question_code_wins_over_history():
    hist = [{"role": "user", "content": "600519 怎么样"}]
    plan = ra.plan_steps("000001 现在多少钱", hist)
    quote = next(s for s in plan if s["tool"] == "get_realtime_quote")
    assert quote["args"]["code"] == "000001"  # 当前问题优先，不得被历史覆盖


def test_t138_m3_inherits_most_recent_history_code():
    hist = [
        {"role": "user", "content": "看看 000001"},
        {"role": "assistant", "content": "000001 的情况如下"},
        {"role": "user", "content": "600519 呢"},
        {"role": "assistant", "content": "600519 结论"},
    ]
    plan = ra.plan_steps("资金流怎么样", hist)
    ff = next(s for s in plan if s["tool"] == "fund_flow")
    assert ff["args"]["code"] == "600519"  # 取离当前问题最近的一条


def test_t138_m3_inheritance_only_from_last_two_entries():
    hist = [
        {"role": "user", "content": "600519 早年如何"},
        {"role": "assistant", "content": "600519 早年结论"},
        {"role": "user", "content": "谢谢"},
        {"role": "assistant", "content": "不客气，随时问"},
    ]
    tools = [s["tool"] for s in ra.plan_steps("资金流怎么样", hist)]
    assert "fund_flow" not in tools    # 最近 2 条无代码 → needs_code 路由不得命中
    assert "get_data_health" in tools  # 诚实兜底仍在


def test_t138_m3_inheritance_does_not_create_new_routes():
    # 历史带「资金流」路由词，当前问题「它呢」没有 → 不得因历史产生 fund_flow；
    # 继承代码在无路由词时的合法出口只有默认研究三件套
    hist = [
        {"role": "user", "content": "600519 资金流怎么样"},
        {"role": "assistant", "content": "主力净流入 1.2 亿"},
    ]
    tools = [s["tool"] for s in ra.plan_steps("它呢", hist)]
    assert "fund_flow" not in tools
    assert tools == ["get_realtime_quote", "analyze_technical", "stock_news"]


# ---------------------------------------------------------------------------
# T3：get_valuation / list_risk_alerts 路由词（mutation 目标）
# ---------------------------------------------------------------------------
def test_t138_t3_route_valuation():
    plan = ra.plan_steps("600519 估值怎么样，PE 高吗")
    tools = [s["tool"] for s in plan]
    assert "get_valuation" in tools
    v = next(s for s in plan if s["tool"] == "get_valuation")
    assert v["args"]["code"] == "600519"


def test_t138_t3_route_valuation_pb_and_percentile_words():
    tools = [s["tool"] for s in ra.plan_steps("600519 市净率处于什么分位")]
    assert "get_valuation" in tools


def test_t138_t3_route_risk_alerts():
    plan = ra.plan_steps("600519 帮我排雷，质押和解禁多吗")
    tools = [s["tool"] for s in plan]
    assert "list_risk_alerts" in tools
    r = next(s for s in plan if s["tool"] == "list_risk_alerts")
    assert r["args"]["code"] == "600519"


def test_t138_t3_risk_alerts_coexists_with_risk_assess():
    tools = [s["tool"] for s in ra.plan_steps("600519 风险高吗，帮我排雷")]
    assert "risk_assess" in tools
    assert "list_risk_alerts" in tools  # 互不替代，共存于同一计划


def test_t138_t3_valuation_works_end_to_end_via_agent():
    r = _run("600519 估值贵不贵", plan=None)  # 确定性规划器直连 FAKE_TOOLS
    tools = [s["tool"] for s in r["steps"]]
    assert "get_valuation" in tools
    assert r["status"] in ("ok", "partial")


# ---------------------------------------------------------------------------
# M4：worker history 校验（非法静默降级单轮）
# ---------------------------------------------------------------------------
def _fake_run_research_capture(seen):
    def _fake(question, **kw):
        seen["question"] = question
        seen.update(kw)
        return {"question": question, "status": "ok", "steps": [], "answer": "a",
                "citations": [], "limitations": [], "generated_at": "x", "elapsed_s": 0.0}
    return _fake


def test_t138_m4_worker_passes_valid_history(monkeypatch):
    import backend.tasks.worker as w
    import modules.research_agent as ra_mod

    seen = {}
    monkeypatch.setattr(ra_mod, "run_research", _fake_run_research_capture(seen))
    hist = [{"role": "user", "content": "600519 怎么样"},
            {"role": "assistant", "content": "结论如下"}]
    w._handle_ai_research({"question": "它呢", "history": hist, "__task_id__": "tid"})
    assert seen.get("history") == hist


def test_t138_m4_worker_drops_invalid_history(monkeypatch):
    import backend.tasks.worker as w
    import modules.research_agent as ra_mod

    seen = {}
    monkeypatch.setattr(ra_mod, "run_research", _fake_run_research_capture(seen))
    # 非 list
    w._handle_ai_research({"question": "q", "history": "垃圾", "__task_id__": "tid"})
    assert "history" not in seen
    # 超过 8 条
    seen.clear()
    w._handle_ai_research({"question": "q",
                           "history": [{"role": "user", "content": "x"}] * 9,
                           "__task_id__": "tid"})
    assert "history" not in seen
    # 条目非 dict
    seen.clear()
    w._handle_ai_research({"question": "q", "history": ["垃圾"], "__task_id__": "tid"})
    assert "history" not in seen
    # 未带 history → 与旧契约一致（不多传键）
    seen.clear()
    w._handle_ai_research({"question": "q", "__task_id__": "tid"})
    assert "history" not in seen


def test_t138_m4_worker_history_at_eight_passes(monkeypatch):
    import backend.tasks.worker as w
    import modules.research_agent as ra_mod

    seen = {}
    monkeypatch.setattr(ra_mod, "run_research", _fake_run_research_capture(seen))
    hist = [{"role": "user", "content": f"m{i}"} for i in range(8)]
    w._handle_ai_research({"question": "q", "history": hist, "__task_id__": "tid"})
    assert seen.get("history") == hist


# ---------------------------------------------------------------------------
# M4b：53 页深度模式提交带 history（additive；ai_consult 流程不动）
# ---------------------------------------------------------------------------
def test_t138_page53_deep_mode_submits_history():
    src = (REPO / "pages" / "53_星辰AI.py").read_text(encoding="utf-8")
    # 深度模式 payload 必须携带 history（多轮记忆上下文）
    assert '"history": _deep_history' in src
    # WELCOME/系统提示必须被排除在深度历史之外
    assert '!= WELCOME.get("content")' in src
    # ai_consult 既有 history 构建不得被移除（additive-only）
    assert 'ctx["history"]' in src
