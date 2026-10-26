# -*- coding: utf-8 -*-
"""T-327 方向C 决策问答引擎测试。

覆盖：意图路由 / 六意图回答契约（数字+溯源+免责）/ unavailable 诚实降级 /
fallback 引导不编造 / mutation 自验（exec 注入缺陷证明测试可检出）。
全离线：快照/荐股/归档目录全部注入。
"""
import json
from pathlib import Path

import pytest

from modules import decision as dm
from modules import decision_qa as qa

SNAP = {
    "date": "2026-10-23",
    "temperature": 75.1,
    "cycle": "主升高潮",
    "promo_overall": 20.0,
    "ladder": {"2板→3板": 33.3, "3板→4板": 25.0},
    "position": {
        "pct": 40, "band": "中性",
        "reasons": ["市场温度 75 作为基准仓位", "⚠️ 数据陈旧：输入源滞后≥8天，仓位封顶 40%（原 87%）"],
    },
}

REC_OK = {"status": "ok", "generated_at": "2026-10-23 17:00:00", "data_as_of": "2026-10-23",
          "picks": [{"code": "600519", "name": "贵州茅台", "composite": 80.0},
                    {"code": "000001", "name": "平安银行", "composite": 20.0}]}


# ─────────────────── 意图路由 ───────────────────
def test_classify_all_intents():
    assert qa.classify("今天仓位多少？") == "position"
    assert qa.classify("为什么只有四成仓") == "reason"
    assert qa.classify("市场温度怎么样") == "market"
    assert qa.classify("今日推荐有哪些") == "recommend"
    assert qa.classify("昨天表现如何，帮我复盘") == "replay"
    assert qa.classify("有什么要注意的风险") == "caps"


def test_classify_unknown_and_empty():
    assert qa.classify("帮我写一首诗") is None
    assert qa.classify("") is None
    assert qa.classify(None) is None


# ─────────────────── fallback 引导 ───────────────────
def test_fallback_guide_no_fabrication():
    r = qa.answer("讲个笑话")
    assert r["status"] == "ok" and r["intent"] == "fallback"
    assert "仓位" in r["answer"] and "复盘" in r["answer"]   # 引导可问域
    assert r["sources"] == []


# ─────────────────── 六意图契约 ───────────────────
def test_position_answer_contract():
    r = qa.answer("今天仓位多少", snapshot=SNAP)
    assert r["status"] == "ok" and r["intent"] == "position"
    assert "**建议仓位 40%**" in r["answer"] and "中性" in r["answer"]
    assert "市场温度 75 作为基准仓位" in r["answer"]          # 理由原文透传
    assert any("快照 data/daily_snapshot.json" in s for s in r["sources"])
    assert "建议≠交易" in r["answer"]                          # 免责必带


def test_position_missing_pct_unavailable():
    r = qa.answer("仓位多少", snapshot={"date": "2026-10-23", "position": {"band": "中性"}})
    assert r["status"] == "unavailable" and "不臆算" in r["reason"]


def test_reason_answer_contract():
    r = qa.answer("为什么只有四成", snapshot=SNAP)   # 避免「仓位」先行命中 position 意图
    assert r["status"] == "ok" and r["intent"] == "reason"
    assert "1. 市场温度 75 作为基准仓位" in r["answer"]
    assert str(dm.FRESHNESS_CAPS) in r["answer"]               # 阈值单一真理源引用
    r2 = qa.answer("为什么", snapshot={"date": "d", "position": {}})
    assert r2["status"] == "unavailable" and "理由" in r2["reason"]


def test_market_answer_contract_and_missing_keys():
    r = qa.answer("市场温度怎么样", snapshot=SNAP)
    assert r["status"] == "ok" and r["intent"] == "market"
    assert "**75.1**" in r["answer"] and "主升高潮" in r["answer"] and "20" in r["answer"]
    assert "2板→3板 33.3%" in r["answer"]
    r2 = qa.answer("市场状态", snapshot={"date": "d"})
    assert "快照未含" in r2["answer"] and r2["status"] == "ok"  # 缺键如实标注，不编造


def test_recommend_contract_and_unavailable():
    r = qa.answer("今日推荐有哪些", rec=REC_OK)
    assert r["status"] == "ok" and r["intent"] == "recommend"
    assert "贵州茅台" in r["answer"] and "80" in r["answer"]
    assert any("daily_recommendation.json" in s for s in r["sources"])
    r2 = qa.answer("推荐", rec={"status": "unavailable", "reason": "今日尚未生成推荐"})
    assert r2["status"] == "unavailable" and "今日尚未生成推荐" in r2["reason"]


def test_replay_from_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "ARCHIVE_DIR", str(tmp_path / "snapshots"))
    r = qa.answer("昨天复盘一下")
    assert r["status"] == "unavailable" and "尚无归档" in r["reason"]
    d = tmp_path / "snapshots"
    d.mkdir()
    (d / "2026-10-22.json").write_text(json.dumps(
        {"date": "2026-10-22", "temperature": 61.5,
         "position": {"pct": 55, "band": "偏多"}}, ensure_ascii=False), encoding="utf-8")
    (d / "2026-10-23.json").write_text(json.dumps(SNAP, ensure_ascii=False), encoding="utf-8")
    r2 = qa.answer("近期表现怎么样")
    assert r2["status"] == "ok" and r2["intent"] == "replay"
    assert "2026-10-23" in r2["answer"] and "决策回放" in r2["answer"]   # 指向 97 页


def test_caps_answer_contract():
    r = qa.answer("有什么要注意的", snapshot=SNAP)
    assert r["status"] == "ok" and r["intent"] == "caps"
    assert "⚠️ 数据陈旧" in r["answer"]
    assert "40" in r["answer"] and "60" in r["answer"]          # FRESHNESS_CAPS 阈值
    r2 = qa.answer("注意什么", snapshot={"date": "d", "position": {"reasons": ["干净的理由"]}})
    assert "未触发封顶" in r2["answer"]


# ─────────────────── 无快照诚实降级 ───────────────────
def test_no_snapshot_unavailable_not_improvised(monkeypatch):
    monkeypatch.setattr(dm, "SNAPSHOT_PATH", "E:/nonexistent/daily_snapshot.json")
    for q in ("仓位多少", "为什么", "市场温度", "注意什么"):
        r = qa.answer(q)
        assert r["status"] == "unavailable", q
        assert "不实时臆算" in r["reason"], q


# ─────────────────── mutation 自验（防假绿）───────────────────
_SRC = Path(qa.__file__).read_text(encoding="utf-8")


def _exec_mutated(old: str, new: str) -> dict:
    mutated = _SRC.replace(old, new)
    assert mutated != _SRC, f"mutation 种子失效：{old[:40]!r}"
    ns = {"__file__": str(Path(qa.__file__))}
    exec(compile(mutated, "<mutated-decision-qa>", "exec"), ns)
    return ns


def test_mutation_intent_router_blinded_detected():
    """注入「仓位意图路由失效」→ 问题落 fallback → 路由断言可检出。"""
    ns = _exec_mutated('("position", ("仓位", "多少仓", "重仓", "轻仓", "买多少", "配置", "敞口")),',
                       '("position", ("绝不匹配的词xyz",)),')
    r = ns["answer"]("今天仓位多少？", snapshot=SNAP)
    assert r["intent"] == "fallback", "mutation 未被检出——意图路由守卫假绿"


def test_mutation_missing_pct_passes_through_detected():
    """注入「缺 pct 不拦截」→ 缺失快照被冒充回答 → unavailable 断言可检出。"""
    ns = _exec_mutated('if pct is None:\n        return {"status": "unavailable", "reason": "快照缺失 position.pct（不臆算）"}',
                       'if False:\n        pass')
    r = ns["answer"]("仓位多少", snapshot={"date": "d", "position": {}})
    assert r["status"] == "ok", "mutation 未被检出——缺失拦截守卫假绿（应放行为 ok）"


def test_mutation_disclaimer_dropped_detected():
    """注入「免责声明不拼接」→ ok 回答无免责 → 免责断言可检出。"""
    ns = _exec_mutated('result["answer"] += f"\\n\\n> ⚠️ {DISCLAIMER}"', "pass")
    r = ns["answer"]("今天仓位多少", snapshot=SNAP)
    assert "建议≠交易" not in r["answer"], "mutation 未被检出——免责声明守卫假绿"
