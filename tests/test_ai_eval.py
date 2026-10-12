"""
tests/test_ai_eval.py
=====================
T-271 星辰 AI「期末考试」：标准问题路由矩阵评测。

对应 Agent 平台能力清单的「模型评测/测试集建设」：把典型问题（含正常题、
复合题、刁钻题）固化为路由契约，每次改动 ai_engine/knowledge_base/
ai_specialists 后重考——路由错位即红。

路由优先级（ai_engine 4c-2）：RAG 知识合成 → 专家分派 → 意图路由 → fallback。
新增知识条目/专家/触发词导致期望变化时，须同步更新本表并在提交信息说明
（这就是 Bad Case → 评测用例的闭环：线上坏例先落这里防回潮）。
"""
import pytest

from modules import ai_specialists, knowledge_base as kb
from mcp_server.gateway import detect_intent


def _route(q: str) -> tuple:
    """复现 ai_engine 4c-2 的路由优先级，返回 (source, id_or_tool)。"""
    if kb.compose(q):
        return ("kb", _kb_id(q))
    sp = ai_specialists.dispatch(q)
    if sp:
        return ("specialist", sp["specialist_id"])
    intent = detect_intent(q)
    if intent.get("tool") and intent.get("confidence", 0) >= 0.85:
        return ("intent", intent["tool"])
    return ("fallback", "")


def _kb_id(q: str) -> str:
    return kb.search(q)["entry"]["id"]


# ── 期末考卷：{(问题, 期望source, 期望id)} ──────────────────────────────
EVAL_CASES = [
    # 概念类 → 知识库
    ("什么是市盈率", "kb", "concept_pe"),
    ("市净率怎么看", "kb", "concept_pb"),
    ("北向资金是什么意思", "kb", "concept_north"),
    ("ST股票有什么风险", "kb", "concept_st"),
    ("MACD金叉什么意思", "kb", "concept_macd"),
    ("涨停是什么", "kb", "mech_limit"),
    ("T+1是什么制度", "kb", "mech_t1"),
    # 项目口径类 → 知识库（专属条目）
    ("49.1%是什么口径", "kb", "cal_491"),
    ("回测用的什么参数", "kb", "cal_backtest"),
    ("融合权重是多少", "kb", "cal_fusion"),
    ("牧羊人温度是什么", "kb", "ind_shepherd"),
    ("综合评分怎么来的", "kb", "ind_composite"),
    # 策略/风险/事件/上手类 → 知识库
    ("仓位怎么管理", "kb", "strat_position"),
    ("止损怎么设置", "kb", "strat_stoploss"),
    ("利好出尽是什么意思", "kb", "event_read"),
    ("这个平台怎么用", "kb", "tuto_start"),
    ("排雷都查什么", "kb", "risk_general"),
    # 复合题 → RAG 多条目合成（compose 至少整合 2 条）
    ("MACD金叉配合换手率怎么看", "kb", "concept_macd"),
    ("市盈率和市净率有什么区别", "kb", "concept_pe"),
    # 方法论类 → 专家分派（仅知识库未覆盖的场景；仓位类已被 strat_position 接走）
    ("600667的技术面怎么看走势", "specialist", "tech"),
    ("大盘回调我的仓位该怎么办", "kb", "strat_position"),
    # 意图路由类（需实时数据，confidence≥0.85）
    ("600667现在多少钱", "intent", "get_realtime_quote"),
    ("我的持仓盈亏怎么样", "intent", "portfolio_query"),
    ("600667最近有什么消息", "intent", "stock_news"),
]


@pytest.mark.parametrize("q,src,eid", EVAL_CASES, ids=[c[0] for c in EVAL_CASES])
def test_route(q, src, eid):
    got_src, got_id = _route(q)
    assert (got_src, got_id) == (src, eid), \
        f"路由错位：{q!r} 期望 ({src},{eid}) 实得 ({got_src},{got_id})"


def test_fallback_for_gibberish():
    """刁钻题：无意义输入落 fallback（不硬凑）。"""
    assert _route("qwerty zzz 无意义")[0] == "fallback"


def test_rag_compose_multi_entry():
    """复合题必须合成 ≥2 条目（RAG 多片段而非单条）。"""
    ans = kb.compose("MACD金叉配合换手率怎么看")
    assert ans and ans.count("**") >= 2 and "相关条目要点" in ans


def test_specialists_registry_complete():
    """专家注册表 ≥5 人，每人有工具依赖与触发词（分派地基）。"""
    agents = ai_specialists.list_specialists()
    assert len(agents) >= 5
    assert all(a["tools"] and a["triggers"] >= 3 for a in agents)
