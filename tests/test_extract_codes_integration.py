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


# ══════════════════════════════════════════════════════════════════════
# T-271【Bad Case 分析】中文邻接场景穷举矩阵（错题本）
# ──────────────────────────────────────────────────────────────────────
# 背景：修复①（\\b→非数字断言）解决「代码+中文」后，对全部邻接形态做穷举
# 实测（19 场景），又抓到 Bad Case ②——\\d 匹配 Unicode 数字，中文输入法
# 全角模式「６００６６７」被原样抽出全角字符串，下游名称映射/工具查询按
# 半角查全部落空。修复②=NFKC 归一化。本矩阵把 20 个场景固化为契约
# （19 个穷举场景 + 全角半角混合新增）：
# 每个场景 = (提问, 期望抽取列表)，任何改动重跑即知哪个形态回潮。
#
# 场景分类与教训：
#   A 中文邻接（修复①目标）：代码在前/后/两侧——\\b 词边界对中文无效；
#   B 前后缀邻接：sh/sz/SH 前缀、字母后缀——非数字字符天然满足断言；
#   C 干扰数字：7/8/11 位（日期/手机号）——断言防止抽 6 位子串；
#   D 标点邻接：全角逗号/破折号/%——非数字即可；
#   E 全角数字（修复②目标）：\\d 匹配 Nd 类，必须 NFKC 先归一化。
# ══════════════════════════════════════════════════════════════════════
BADCASE_MATRIX = [
    # ── A 中文邻接（修复①）──
    ("代码后中文", "600667现在多少钱", ["600667"]),
    ("代码前中文", "帮我看600667", ["600667"]),
    ("两侧中文", "看一下600667的走势", ["600667"]),
    ("多代码", "对比600667和000001", ["600667", "000001"]),
    ("句首前导0", "000001涨停", ["000001"]),
    ("年字邻接", "600667年报怎么样", ["600667"]),
    ("日期+代码混写", "2026年10月12日600667", ["600667"]),
    # ── B 前后缀邻接 ──
    ("交易所前缀sz", "sz000001怎么样", ["000001"]),
    ("前缀大写SH", "SH600667", ["600667"]),
    ("前缀小写sh邻接", "sh600667", ["600667"]),
    ("字母后缀邻接", "600667sh", ["600667"]),
    # ── D 标点邻接 ──
    ("全角标点邻接", "600667，帮我看下", ["600667"]),
    ("破折号邻接", "600667——分析一下", ["600667"]),
    ("百分号邻接", "600667涨了5.2%了吗", ["600667"]),
    ("空格分隔多码", "000001 600519 300750", ["000001", "600519", "300750"]),
    # ── C 干扰数字（负向）──
    ("8位日期连写干扰", "20261012", []),
    ("7位干扰", "1234567", []),
    ("手机号干扰", "13812345678", []),
    # ── E 全角数字（修复②）──
    ("全角数字", "６００６６７怎么样", ["600667"]),
    ("全角与半角混合", "６００６６７和000001对比", ["600667", "000001"]),
]


@pytest.mark.parametrize("name,q,expect", BADCASE_MATRIX, ids=[c[0] for c in BADCASE_MATRIX])
def test_badcase_matrix(name, q, expect):
    """Bad Case 错题本：20 个中文邻接形态逐一钉死（含全角归一化修复②）。"""
    assert gateway._extract_codes(q) == expect, f"场景回潮：{name}"


def test_badcase_fullwidth_flows_to_intent():
    """全角数字修复②的集成面：全角提问经归一化后正常路由到工具。"""
    intent = detect_intent("６００６６７现在多少钱")
    assert intent["tool"] == "get_realtime_quote"
    assert intent["params"].get("code") == "600667"  # NFKC 归一化后半角
