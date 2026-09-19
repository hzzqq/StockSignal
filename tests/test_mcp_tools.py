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


# ---------------------------------------------------------------------------
# T-138：估值深钻 / 风险排雷薄转发工具（H2/H6 能力暴露）
# ---------------------------------------------------------------------------
T138_TOOLS = ("get_valuation", "list_risk_alerts")


@pytest.mark.parametrize("name", T138_TOOLS)
def test_t138_tool_registered_with_schema(name):
    assert name in _srv.TOOLS, f"T-138 新工具 {name} 未注册"
    entry = _srv.TOOLS[name]
    assert callable(entry["handler"])
    assert entry["description"]


@pytest.mark.parametrize("name", T138_TOOLS)
def test_t138_tools_are_thin_forwarders(name):
    import inspect

    src = inspect.getsource(_srv.TOOLS[name]["handler"])
    assert "from modules" in src, f"{name} 疑似空壳：未转发到 modules.*"


def test_t138_get_valuation_passthrough(monkeypatch):
    import modules.valuation as val

    seen = {}

    def _fake(code, period="近十年"):
        seen["code"], seen["period"] = code, period
        return {"pe": [11.2, 12.0], "pb": [1.8], "span": "2016~2026"}

    monkeypatch.setattr(val, "fetch_pe_pb_series", _fake)
    out = _tools_pkg.get_valuation("600519", period="近三年")
    assert out == {"pe": [11.2, 12.0], "pb": [1.8], "span": "2016~2026"}  # 原样透传不加工
    assert seen == {"code": "600519", "period": "近三年"}


def test_t138_get_valuation_none_wraps_unavailable(monkeypatch):
    import modules.valuation as val

    monkeypatch.setattr(val, "fetch_pe_pb_series", lambda code, period="近十年": None)
    out = _tools_pkg.get_valuation("600519")
    assert out["ok"] is False
    assert out["error"]  # 诚实语义：数据不足如实说明，绝不编造默认值


def test_t138_get_valuation_exception_wraps_ok_false(monkeypatch):
    import modules.valuation as val

    def _boom(code, period="近十年"):
        raise RuntimeError("估值源不可达")

    monkeypatch.setattr(val, "fetch_pe_pb_series", _boom)
    out = _tools_pkg.get_valuation("600519")
    assert out["ok"] is False
    assert "估值源不可达" in out["error"]


def test_t138_list_risk_alerts_passthrough(monkeypatch):
    import modules.stock_risk as sr

    seen = {}

    def _fake(code, name=None, st_set=None):
        seen["code"] = code
        return {"code": code, "components": {"质押": {"ratio": 0.3}}, "errors": []}

    monkeypatch.setattr(sr, "scan_stock", _fake)
    out = _tools_pkg.list_risk_alerts("000001")
    assert out["components"] == {"质押": {"ratio": 0.3}}
    assert seen == {"code": "000001"}


def test_t138_list_risk_alerts_exception_wraps_ok_false(monkeypatch):
    import modules.stock_risk as sr

    def _boom(code, name=None, st_set=None):
        raise RuntimeError("排雷源不可达")

    monkeypatch.setattr(sr, "scan_stock", _boom)
    out = _tools_pkg.list_risk_alerts("000001")
    assert out["ok"] is False
    assert "排雷源不可达" in out["error"]
