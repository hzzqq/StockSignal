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
