"""
tests/test_ai_knowledge_fastapi.py
==================================
T-268 星辰 AI 能力升级守卫（用户要求：不能问什么都同一个模板回答；打造真正的
金融 AI 助手；建知识库；FastAPI 架构完善）。

契约：
1. knowledge_base：≥8 大类 ≥18 条目；典型问题命中（市盈率/仓位/49.1%/牧羊人/
   涨跌停/止损）；未命中返回 None；49.1% 条目必须含「外部参考锚」诚实口径表述。
2. ai_engine 集成：知识库插桩位于 ai_answer 的 4d（页面上下文）之前、
   仅在无标的时生效（AST 契约防回潮）。
3. FastAPI AI 服务层（TestClient）：knowledge/search 命中与未命中、chat fast 模式
   命中与 fallback、intents 自省 ≥11 条工具规则、stats 结构完整。
4. FastAPI 试点红线持续有效：切片不得引入写库语句。

mutation：删 ai_engine 知识库插桩 / 删 49.1 条目 → 对应用例变红。
"""
import ast
from pathlib import Path

from fastapi.testclient import TestClient

from modules import knowledge_base as kb

ROOT = Path(__file__).resolve().parents[1]
AI_ENGINE = ROOT / "modules" / "ai_engine.py"


def test_kb_scale_and_categories():
    """契约1a：≥8 类 ≥18 条（多设几条规则——单一模板问题的根治量）。"""
    s = kb.stats()
    assert s["entries"] >= 18, f"知识条目不足: {s}"
    assert len(s["categories"]) >= 8, f"知识类别不足 8 类: {s['categories']}"


def test_kb_hits_typical_questions():
    """契约1b：典型金融问题必须命中对应条目。"""
    cases = {
        "什么是市盈率": "concept_pe",
        "仓位怎么定": "strat_position",
        "49.1% 是什么口径": "cal_491",
        "牧羊人温度是什么": "ind_shepherd",
        "涨停是什么意思": "mech_limit",
        "止损怎么设置": "strat_stoploss",
        "北向资金是什么": "concept_north",
    }
    for q, expect_id in cases.items():
        hit = kb.search(q)
        assert hit and hit["entry"]["id"] == expect_id, f"「{q}」未命中 {expect_id}"


def test_kb_miss_returns_none():
    """契约1c：未命中返回 None（调用方继续走原兜底，不硬凑）。"""
    assert kb.search("今天天气怎么样") is None
    assert kb.search("") is None
    assert kb.answer("qwertyuiop 无意义串") is None


def test_kb_491_honest_caliber():
    """契约1d：49.1% 条目必须保留诚实口径（外部参考锚，非本项目实测）——学术红线。"""
    hit = kb.search("49.1% 是什么")
    assert hit and hit["entry"]["id"] == "cal_491"
    content = hit["entry"]["content"]
    assert "外部参考锚" in content and "不是本项目模型的实测命中率" in content


def test_ai_engine_kb_wired_before_context():
    """契约2：ai_answer 内知识库插桩必须存在，且位于 4d 页面上下文分支之前。
    （T-271 演进：answer→compose 多条目 RAG 合成，并追加专家分派。）"""
    src = AI_ENGINE.read_text(encoding="utf-8")
    assert "from modules import knowledge_base" in src or "knowledge_base" in src
    i_kb = src.index("knowledge_base.compose(question)")
    i_4d = src.index("4d) 没有解析到股票")
    assert i_kb < i_4d, "知识库插桩必须先于页面上下文分支（否则概念问题被组合分析答非所问）"
    # 插桩必须带「无标的」守卫（有股票时走数据链路）+ 专家分派紧随其后
    seg = src[i_kb - 200: i_kb]
    assert "not resolved and not history_stock" in seg
    i_sp = src.index("ai_specialists.dispatch(question)")
    assert i_kb < i_sp < i_4d, "专家分派应在知识库之后、兜底之前"
    ast.parse(src)


def _client() -> TestClient:
    from backend_fastapi.main import app
    return TestClient(app)


def test_fastapi_knowledge_endpoints():
    """契约3a：/api/ai/knowledge/search 与 /stats。"""
    c = _client()
    r = c.get("/api/ai/knowledge/search", params={"q": "什么是市盈率"}).json()
    assert r["status"] == "ok" and r["found"] and r["data"]["id"] == "concept_pe"
    r2 = c.get("/api/ai/knowledge/search", params={"q": "无意义字符串xyz"}).json()
    assert r2["status"] == "ok" and r2["found"] is False and "stats" in r2
    r3 = c.get("/api/ai/knowledge/stats").json()
    assert r3["status"] == "ok" and r3["data"]["entries"] >= 18


def test_fastapi_chat_fast_mode():
    """契约3b：POST /api/ai/chat（fast）——RAG 命中与 fallback 双路径。"""
    c = _client()
    r1 = c.post("/api/ai/chat", json={"question": "什么是换手率", "mode": "fast"}).json()
    assert r1["source"] == "knowledge_base_rag" and "换手率" in r1["answer"]
    r2 = c.post("/api/ai/chat", json={"question": " meaningless zzz ", "mode": "fast"}).json()
    assert r2["source"] == "fallback" and r2["status"] == "ok"
    # Pydantic 校验：空问题自动 422（声明式校验对照 Flask 手写分支）
    assert c.post("/api/ai/chat", json={"question": "", "mode": "fast"}).status_code == 422


def test_fastapi_intents_selfinspect():
    """契约3c：/api/ai/intents 意图规则自省 ≥11 条（多意图路由的地基）。"""
    c = _client()
    r = c.get("/api/ai/intents").json()
    assert r["status"] == "ok" and r["count"] >= 11
    tools = {x["tool"] for x in r["data"]}
    assert {"smart_pick", "run_backtest", "get_market_sentiment"} <= tools


def test_fastapi_slice_still_readonly():
    """契约4：AI 端点加入后，切片只读红线持续有效。"""
    src = (ROOT / "backend_fastapi" / "main.py").read_text(encoding="utf-8")
    upper = src.upper()
    for kw in ("INSERT INTO", "UPDATE ", "DELETE FROM", "DROP TABLE"):
        assert kw not in upper, f"切片出现写库语句: {kw}"
    assert "mode=ro" in src
