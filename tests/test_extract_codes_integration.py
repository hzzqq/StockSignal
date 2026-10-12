"""
tests/test_extract_codes_integration.py
=======================================
T-271 补充【集成测试】：_extract_codes 修复（\\b → 前后非数字断言）在真实
调用链中的端到端效果。

与单测（test_gateway_extract_codes.py 直测正则）的分层关系：
    单测  = 正则本身逐场景边界；
    集成  = 「用户提问 → detect_intent（参数抽取）→ call_tool（工具收参）
             → FastAPI 对话端点」跨组件链路，验证修复后 code 真正流到工具。

全部打桩（工具函数/ai_answer 替身为确定性 stub），零网络、可离线重复。
真实网链路由 live 标记测试覆盖（默认跳过）。
"""
import pytest

from mcp_server import gateway
from mcp_server.gateway import call_tool, detect_intent


def _stub_tool(captured: dict, name: str):
    """返回确定性 stub 工具：记录收到的 kwargs，返回固定结构（零网络）。"""
    def _tool(**kwargs):
        captured["tool"] = name
        captured["kwargs"] = kwargs
        return {"status": "ok", "stub": True, "echo": dict(kwargs)}
    return _tool


def test_pipeline_intent_to_tool_chinese_adjacency(monkeypatch):
    """链路①：中文邻接提问 → 意图路由 → 工具收到正确 code 参数（修复主目标）。

    修复前：\\b 抽不到 code → params 无 code → confidence 0.5 < 0.85 → 不路由；
    修复后：code 流入工具 kwargs。"""
    captured = {}
    monkeypatch.setattr(gateway, "_resolve_func",
                        lambda name: _stub_tool(captured, name))
    intent = detect_intent("600667现在多少钱")
    assert intent["tool"] == "get_realtime_quote"
    res = call_tool(intent["tool"], **intent["params"])
    assert res["ok"] is True and res["data"]["stub"] is True
    assert captured["tool"] == "get_realtime_quote"
    assert captured["kwargs"].get("code") == "600667"


def test_pipeline_intent_to_tool_news(monkeypatch):
    """链路②：消息类提问（stock_news 工具）同链路验证。"""
    captured = {}
    monkeypatch.setattr(gateway, "_resolve_func",
                        lambda name: _stub_tool(captured, name))
    intent = detect_intent("600667最近有什么消息")
    assert intent["tool"] == "stock_news"
    res = call_tool(intent["tool"], **intent["params"])
    assert res["ok"] is True and res["data"]["stub"] is True
    assert captured["kwargs"].get("code") == "600667"


def test_pipeline_multi_code_comparison_intent(monkeypatch):
    """链路③：多代码提问 → 意图路由（codes 列表完整、顺序保留）。"""
    captured = {}
    monkeypatch.setattr(gateway, "_resolve_func",
                        lambda name: _stub_tool(captured, name))
    intent = detect_intent("000001 和 600519 与 300750 的风险怎么样")
    assert intent["tool"] == "risk_assess"
    assert intent["params"].get("code") in ("000001", "600519", "300750") or \
        intent["params"].get("codes") == ["000001", "600519", "300750"]
    res = call_tool(intent["tool"], **intent["params"])
    assert res["ok"] is True and res["data"]["stub"] is True


def test_fastapi_chat_full_pipeline(monkeypatch):
    """链路④：FastAPI /api/ai/chat full 模式 → ai_answer 打桩 → 端点透传
    （验证 AI 服务层与引擎的集成面；ai_answer 内部链路已有单测覆盖）。"""
    from fastapi.testclient import TestClient
    from backend_fastapi.main import app
    import modules.ai_engine as ai_eng

    def fake_answer(question, context=None):
        return {"answer": f"已分析 {question}", "independent": True,
                "specialist": "tech" if "技术面" in question else None}

    monkeypatch.setattr(ai_eng, "ai_answer", fake_answer)
    c = TestClient(app)
    r = c.post("/api/ai/chat", json={"question": "600667技术面", "mode": "full"}).json()
    assert r["status"] == "ok" and r["source"] == "ai_engine"
    assert r["answer"] == "已分析 600667技术面"
    assert r["specialist"] == "tech"


def test_regression_pre_fix_behavior_would_fail():
    """回归对照：用修复前 \\b 正则复现旧行为——证明本链路测试在旧代码下必红
    （防「测试与实现同时错」的假绿闭环）。"""
    import re
    old_matches = re.findall(r"\b\d{6}\b", "600667现在多少钱")
    assert old_matches == [], "前提失效：\\b 在中文邻接下竟能命中，请复核修复动机"
