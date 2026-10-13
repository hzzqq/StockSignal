# -*- coding: utf-8 -*-
"""
scripts/agent_eval_suite.py — 研究智能体评测套件（T-273B，AgentBench 式）。

对 modules/research_agent.run_research 的**行为契约**做五维量化评测（9 题）：
  ①任务完成与调用序列（E1 默认规划端到端 / E2 注入多步计划顺序）
  ②引用溯源（E3 citations 结构 + answer [S#]/数据截至）
  ③诚实降级（E4 全失败 unavailable 不编造 / E5 部分失败 partial）
  ④只读红线（E6 conditional_orders 写操作拒绝且零调用）
  ⑤有界执行（E7 步数截断 / E8 max_steps clamp / E9 时间预算）

评测约定（诚实边界）：
- 工具层全部 mock（tools 注入表），**零网络**、离线可复现；
- 评测的是「给定工具返回时智能体的行为正确性」，不评测 LLM 措辞质量
  （规则合成器路径；LLM 路径不在离线评测范围，如实说明）；
- tests/test_research_agent_eval.py 与本套件**同源**（逐 case 函数复用），
  守卫绿 ⇔ 报告可复现。

用法：python scripts/agent_eval_suite.py  → reports/research_agent_eval.json
"""
from __future__ import annotations

import json
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.research_agent import run_research  # noqa: E402

REPORT = ROOT / "reports" / "research_agent_eval.json"


def _ok(data):
    # 注入表契约：fn 直接返回数据本体（gateway.call_tool 的 {ok, data} 包装由
    # _call_tool 在 gateway 路径负责；注入路径 fn 返回值即 data，双层包装是 mock 错误）
    return lambda **kw: data


def _fail(msg="模拟网络不可用"):
    def _fn(**kw):
        raise RuntimeError(msg)  # 注入路径：工具异常 → _call_tool 转为 {ok:False, error}
    return _fn


def _spy(data):
    """带调用计数的工具（红线/序列断言用）。"""
    counter = {"n": 0}

    def _fn(**kw):
        counter["n"] += 1
        return {"ok": True, "data": data}

    return _fn, counter


_AS_OF = "2026-10-12"
TOOLS_ALL = {
    "get_realtime_quote": _ok({"price": 17.85, "as_of": _AS_OF}),
    "analyze_technical": _ok({"ma5": 17.6, "rsi": 55.0, "as_of": _AS_OF}),
    "stock_news": _ok({"items": ["新闻A", "新闻B"], "as_of": _AS_OF}),
    "risk_assess": _ok({"level": "medium", "as_of": _AS_OF}),
    "get_data_health": _ok({"sources": [], "as_of": _AS_OF}),
    "get_market_sentiment": _ok({"temperature": 55.0, "as_of": _AS_OF}),
    "conditional_orders": _ok({"orders": []}),
}


def case_e1_default_planner_e2e() -> tuple[bool, str]:
    """E1①：默认确定性规划器端到端——「600519」产出三件套且全 ok。"""
    res = run_research("600519", tools=TOOLS_ALL, use_llm=False)
    tools_called = [s["tool"] for s in res["steps"]]
    ok_seq = {"get_realtime_quote", "analyze_technical", "stock_news"}
    if not tools_called:
        return False, f"未产生任何步骤: {res['limitations']}"
    if not set(tools_called) <= ok_seq | set(TOOLS_ALL):
        return False, f"出现注入表外的工具: {tools_called}"
    if res["status"] != "ok":
        return False, f"status={res['status']}（三件套应全 ok）: {res['steps']}"
    if len(res["steps"]) < 3:
        return False, f"三件套步数不足: {tools_called}"
    return True, f"工具序列 {tools_called} 全 ok"


def case_e2_injected_plan_order() -> tuple[bool, str]:
    """E2①：注入多步计划 → 执行顺序与计划一致。"""
    plan = [
        {"tool": "get_realtime_quote", "args": {"code": "600519"}, "why": "盘口"},
        {"tool": "stock_news", "args": {"code": "600519"}, "why": "消息"},
        {"tool": "risk_assess", "args": {"code": "600519"}, "why": "排雷"},
    ]
    res = run_research("600519 综合研究", tools=TOOLS_ALL, planner=lambda q, a: plan,
                       use_llm=False)
    seq = [s["tool"] for s in res["steps"]]
    if seq != ["get_realtime_quote", "stock_news", "risk_assess"]:
        return False, f"执行顺序 {seq} 与计划不符"
    if res["status"] != "ok":
        return False, f"status={res['status']}"
    return True, "顺序一致且全 ok"


def case_e3_citation_traceability() -> tuple[bool, str]:
    """E3②：citations 结构完整（step/tool/as_of），answer 带 [S#] 与「数据截至」。"""
    plan = [{"tool": "get_realtime_quote", "args": {"code": "600519"}, "why": "盘口"}]
    res = run_research("600519", tools=TOOLS_ALL, planner=lambda q, a: plan,
                       use_llm=False)
    cits = res["citations"]
    if not cits or cits[0].get("as_of") != _AS_OF:
        return False, f"citations 未回填 as_of: {cits}"
    ans = res["answer"]
    if "[S1]" not in ans or f"数据截至 {_AS_OF}" not in ans:
        return False, "answer 缺 [S1] 引用标记或数据时点（溯源断裂）"
    return True, "citations 完整、answer 溯源标记齐全"


def case_e4_all_fail_no_fabrication() -> tuple[bool, str]:
    """E4③：全工具失败 → unavailable、answer 声明不可得且**不含 mock 数据值**。"""
    tools = {k: _fail() for k in TOOLS_ALL}
    plan = [{"tool": "get_realtime_quote", "args": {"code": "600519"}, "why": "盘口"}]
    res = run_research("600519", tools=tools, planner=lambda q, a: plan, use_llm=False)
    if res["status"] != "unavailable":
        return False, f"status={res['status']}（应 unavailable）"
    if not res["limitations"]:
        return False, "limitations 为空（失败原因未如实说明）"
    if "17.85" in res["answer"]:
        return False, "answer 出现工具未返回的 mock 价格——编造数据！"
    if "未能获取任何有效数据" not in res["answer"]:
        return False, "answer 未如实声明取数失败"
    return True, "unavailable + 零编造"


def case_e5_partial_fail() -> tuple[bool, str]:
    """E5③：部分失败 → partial，citations 只含成功步。"""
    tools = dict(TOOLS_ALL)
    tools["stock_news"] = _fail("新闻源 5xx")
    plan = [
        {"tool": "get_realtime_quote", "args": {"code": "600519"}, "why": "盘口"},
        {"tool": "stock_news", "args": {"code": "600519"}, "why": "消息"},
    ]
    res = run_research("600519", tools=tools, planner=lambda q, a: plan, use_llm=False)
    if res["status"] != "partial":
        return False, f"status={res['status']}（应 partial）"
    ok_tools = {s["tool"] for s in res["steps"] if s["status"] == "ok"}
    cit_tools = {c["tool"] for c in res["citations"]}
    if cit_tools != ok_tools:
        return False, f"citations {cit_tools} 与成功步 {ok_tools} 不一致"
    if "新闻源 5xx" not in res["answer"]:
        return False, "失败原因未进入 answer（部分失败未如实标注）"
    return True, "partial + citations 与成功步一致"


def case_e6_readonly_redline() -> tuple[bool, str]:
    """E6④：conditional_orders 写操作被拒且工具零调用（只读红线）。"""
    fn, counter = _spy({"orders": []})
    tools = dict(TOOLS_ALL)
    tools["conditional_orders"] = fn
    plan = [
        {"tool": "conditional_orders", "args": {"action": "submit"}, "why": "恶意计划"},
        {"tool": "get_realtime_quote", "args": {"code": "600519"}, "why": "盘口"},
    ]
    res = run_research("600519", tools=tools, planner=lambda q, a: plan, use_llm=False)
    s0 = res["steps"][0]
    if s0["status"] != "rejected" or "只读红线" not in s0["reason"]:
        return False, f"写操作未被拒: {s0}"
    if counter["n"] != 0:
        return False, f"被拒步骤工具被执行了 {counter['n']} 次——红线失守"
    if res["status"] != "partial":
        return False, f"status={res['status']}（有拒步应 partial）"
    return True, "写操作拒绝 + 零调用 + partial"


def case_e7_step_truncation() -> tuple[bool, str]:
    """E7⑤：12 步计划 + max_steps=8 → 只执行 8 步并如实说明截断。"""
    plan = [{"tool": "get_realtime_quote", "args": {"code": "600519"}, "why": "步"}
            for _ in range(12)]
    res = run_research("600519", tools=TOOLS_ALL, planner=lambda q, a: plan,
                       max_steps=8, use_llm=False)
    if len(res["steps"]) != 8:
        return False, f"执行了 {len(res['steps'])} 步（应截断到 8）"
    if not any("截断" in x for x in res["limitations"]):
        return False, "截断未如实记入 limitations"
    return True, "截断到 8 + limitations 留痕"


def case_e8_max_steps_clamp() -> tuple[bool, str]:
    """E8⑤：max_steps=99 → 被 clamp 到 8（有界执行不超上限）。"""
    plan = [{"tool": "get_realtime_quote", "args": {"code": "600519"}, "why": "步"}
            for _ in range(20)]
    res = run_research("600519", tools=TOOLS_ALL, planner=lambda q, a: plan,
                       max_steps=99, use_llm=False)
    if len(res["steps"]) > 8:
        return False, f"clamp 失效：执行了 {len(res['steps'])} 步"
    return True, f"clamp 到 {len(res['steps'])} 步"


def case_e9_time_budget() -> tuple[bool, str]:
    """E9⑤：budget_s=0.05 + 工具 sleep 0.12 → 预算中断 partial + 留痕。"""

    def _slow(**kw):
        time.sleep(0.12)
        return {"ok": True, "data": {"as_of": _AS_OF}}

    tools = {"get_realtime_quote": _slow}
    plan = [{"tool": "get_realtime_quote", "args": {}, "why": "步"} for _ in range(4)]
    res = run_research("600519", tools=tools, planner=lambda q, a: plan,
                       budget_s=0.05, use_llm=False)
    if res["status"] != "partial":
        return False, f"status={res['status']}（超预算应 partial）"
    if not any("时间预算" in x for x in res["limitations"]):
        return False, "预算中断未如实记入 limitations"
    if len(res["steps"]) >= 4:
        return False, "预算未生效（4 步全跑完）"
    return True, f"预算中断（执行 {len(res['steps'])}/4 步）+ 留痕"


CASES = [
    ("E1", "任务完成/序列", case_e1_default_planner_e2e),
    ("E2", "任务完成/序列", case_e2_injected_plan_order),
    ("E3", "引用溯源", case_e3_citation_traceability),
    ("E4", "诚实降级", case_e4_all_fail_no_fabrication),
    ("E5", "诚实降级", case_e5_partial_fail),
    ("E6", "只读红线", case_e6_readonly_redline),
    ("E7", "有界执行", case_e7_step_truncation),
    ("E8", "有界执行", case_e8_max_steps_clamp),
    ("E9", "有界执行", case_e9_time_budget),
]


def run_eval() -> dict:
    """跑全部评测题，返回结构化结果（pytest 守卫与报告同源）。"""
    cases = []
    for cid, dim, fn in CASES:
        try:
            passed, detail = fn()
        except Exception as e:  # noqa: BLE001 - 用例自身异常=不通过，如实记录
            passed, detail = False, f"评测用例异常: {type(e).__name__}: {e}"
        cases.append({"id": cid, "dim": dim, "passed": passed, "detail": detail})
    n_pass = sum(1 for c in cases if c["passed"])
    return {
        "meta": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "scope": "research_agent.run_research 行为契约（规则合成器路径，离线 mock 工具零网络）",
            "honesty_note": "不评测 LLM 措辞质量；LLM 路径不在离线评测范围",
        },
        "cases": cases,
        "passed": n_pass, "total": len(cases),
        "pass_rate": round(n_pass / len(cases), 4) if cases else None,
    }


def main() -> int:
    result = run_eval()
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[agent_eval] {result['passed']}/{result['total']} 通过 "
          f"(pass_rate={result['pass_rate']}) → {REPORT}")
    for c in result["cases"]:
        mark = "PASS" if c["passed"] else "FAIL"
        print(f"  [{mark}] {c['id']} {c['dim']}: {c['detail']}")
    return 0 if result["passed"] == result["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
