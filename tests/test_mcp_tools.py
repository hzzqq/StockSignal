"""MCP Server 工具注册守卫（零网络、纯 import/注册级）。

锁定不变量：
- 工具总数 >= 16（11 个原有 + 5 个 2026-09-16 新增）
- 5 个新增工具已注册且 handler 可调用
- get_data_health 这类「诚实口径」工具始终返回 dict（离线也不崩）
"""

import importlib

import pytest

# 触发 side-effect：import 即跑 _register_all() 把所有工具注册进 server.TOOLS
import mcp_server.tools as _tools_pkg  # noqa: F401
from mcp_server import server as _srv


NEW_TOOLS = (
    "get_data_health",      # 数据源时效：外部 AI 给建议前先知道数据多旧
    "get_macro_indicators", # 宏观 PMI/CPI/PPI/GDP/M2/LPR
    "get_lhb",              # 龙虎榜席位动向
    "get_ai_skills",        # 用户自定义 AI 分析规则库
    "get_p1_signal",        # P1 事件因子 latest_date，判断是否陈旧
)


def test_tool_count_floor():
    # 上界不锁死（允许后续继续加工具），但下界是硬底线
    assert len(_srv.TOOLS) >= 16, f"工具数回退到 {len(_srv.TOOLS)}，预期 >=16"


@pytest.mark.parametrize("name", NEW_TOOLS)
def test_new_tool_registered(name):
    assert name in _srv.TOOLS, f"新增工具 {name} 未注册"
    entry = _srv.TOOLS[name]
    assert callable(entry["handler"]), f"{name} 的 handler 不可调用"
    assert entry["description"], f"{name} 缺少描述"


def test_get_data_health_offline_safe():
    # 离线/无数据也不应抛异常，必须返回 dict 且带 ok 布尔
    out = _tools_pkg.get_data_health()
    assert isinstance(out, dict), "get_data_health 必须返回 dict"
    assert "ok" in out, "get_data_health 必须带 ok 字段（诚实口径：失败也明示）"


def test_new_tools_are_thin_forwarders_not_stubs():
    # 5 个新工具都是对 modules.* 的薄转发，函数体应真正 import 对应模块
    import inspect

    for name in NEW_TOOLS:
        src = inspect.getsource(_srv.TOOLS[name]["handler"])
        # 至少做了 from modules import xxx 的转发（而非空壳 return）
        assert "from modules import" in src or "import modules" in src, (
            f"{name} 疑似空壳：未转发到 modules.*"
        )
