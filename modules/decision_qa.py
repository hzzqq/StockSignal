# -*- coding: utf-8 -*-
"""modules/decision_qa.py — T-327 方向C：自然语言决策端（本地决策问答引擎）。

用户以自然语言提问（今天仓位多少/为什么/该注意什么），引擎做**确定性意图路由**
（先例：research_agent.plan_steps 关键词规划 + 81 页 parse_query）→ 从归档数据面
取数 → 模板化可解释回答 + 数据溯源标注。

═════════════════════════ spec（冻结）══════════════════════════
契约 answer(question, snapshot=None, rec=None, data_dir=None) -> dict：
- 输入
  - question：str（自然语言）；
  - snapshot/rec：可注入的当日快照 / 荐股 dict（测试用）；None 时从
    decision.SNAPSHOT_PATH（SS_DATA_DIR 可重定向）/ load_latest_recommendation 读；
  - data_dir：荐股文件目录注入（透传 load_latest_recommendation）。
- 输出 ok：{"status":"ok", "intent":str, "answer":str(markdown),
  "sources":[溯源标签], "data":{...}}
- 输出 unavailable：{"status":"unavailable", "reason":str}——意图命中但该意图
  核心数据缺失（无快照 / 无荐股 / 无归档），如实说明绝不编造；
- 意图不明 → status=ok + intent="fallback"：回答=可问问题引导，不冒充回答。
- 意图目录（6 类，关键词路由，命中多类时按目录顺序取第一个）：
  position(仓位) / reason(为什么) / market(市场状态) / recommend(今日推荐) /
  replay(近期复盘) / caps(该注意什么)。
- 诚实边界：只引用归档数据（daily_snapshot.json / daily_recommendation.json /
  data/snapshots/ 归档链）；快照缺键如实写「快照未含」；回答尾部必带「建议≠交易」；
  纯本地模板不依赖 LLM（离线可测、可确定性回归；LLM 增强后续另立任务）。
═══════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging

from modules import decision as dm
from modules.decision import FRESHNESS_CAPS

logger = logging.getLogger(__name__)

DISCLAIMER = "建议≠交易：以上回答只复述归档数据与既有决策口径，请独立决策。"

# 意图路由表（顺序即优先级；关键词来自老板示例问题 + 决策域同义词）
INTENTS = [
    ("position", ("仓位", "多少仓", "重仓", "轻仓", "买多少", "配置", "敞口")),
    ("reason", ("为什么", "理由", "依据", "怎么算", "怎么来的", "怎么得出")),
    ("market", ("温度", "周期", "情绪", "市场怎么样", "市场状态", "晋级率", "梯队", "环境")),
    ("recommend", ("推荐", "荐股", "买什么", "选哪些", "标的有", "关注哪些")),
    ("replay", ("昨天", "前天", "上周", "回放", "复盘", "近期表现", "历史")),
    ("caps", ("注意", "风险", "提醒", "小心", "坑", "陈旧", "新鲜度")),
]

GUIDE = (
    "我没听懂这个问题（决策问答只覆盖决策域，不跑通用研究）。可以问我：\n"
    "- 「今天仓位多少？」「为什么是这个仓位？」\n"
    "- 「市场温度/情绪周期怎么样？」\n"
    "- 「今日推荐有哪些？」「近期复盘怎么看？」\n"
    "- 「有什么要注意的风险？」"
)


def classify(question: str) -> str | None:
    """关键词意图路由；不命中返回 None（fallback 引导，不编造）。"""
    q = (question or "").strip().lower()
    if not q:
        return None
    for intent, words in INTENTS:
        if any(w.lower() in q for w in words):
            return intent
    return None


def _read_today_snapshot() -> dict | None:
    """读当日快照 decision.SNAPSHOT_PATH；缺失/损坏返回 None（诚实降级）。"""
    import json
    try:
        with open(dm.SNAPSHOT_PATH, encoding="utf-8") as f:
            snap = json.load(f)
    except Exception:  # noqa: BLE001
        return None
    return snap if isinstance(snap, dict) else None


def _fmt_num(v):
    if v is None:
        return "—"
    try:
        f = float(v)
        return f"{f:g}"
    except (TypeError, ValueError):
        return str(v)


def _ans_position(snap: dict) -> dict:
    pos = snap.get("position") or {}
    pct = pos.get("pct")
    if pct is None:
        return {"status": "unavailable", "reason": "快照缺失 position.pct（不臆算）"}
    reasons = pos.get("reasons") or []
    lines = [f"**建议仓位 {_fmt_num(pct)}%**（档位：{pos.get('band') or '—'}）。",
             "推导理由（当日快照原文）："]
    lines += [f"- {r}" for r in reasons] if reasons else ["- 快照未含推导理由"]
    lines.append(f"_数据日 {snap.get('date') or '—'}；口径与 decision.py::derive_position 一致。_")
    return {"status": "ok", "intent": "position", "answer": "\n".join(lines),
            "sources": [f"快照 data/daily_snapshot.json（数据日 {snap.get('date') or '—'}）"],
            "data": {"pct": pct, "band": pos.get("band"), "n_reasons": len(reasons)}}


def _ans_reason(snap: dict) -> dict:
    pos = snap.get("position") or {}
    reasons = pos.get("reasons") or []
    if not reasons:
        return {"status": "unavailable", "reason": "快照未含仓位推导理由（position.reasons），无法解释"}
    lines = ["**仓位推导依据**（当日快照原文逐条）："]
    lines += [f"{i}. {r}" for i, r in enumerate(reasons, 1)]
    lines.append(f"_封顶阈值单一真理源 modules.decision.FRESHNESS_CAPS：{FRESHNESS_CAPS}；"
                 f"数据日 {snap.get('date') or '—'}。_")
    return {"status": "ok", "intent": "reason", "answer": "\n".join(lines),
            "sources": [f"快照 data/daily_snapshot.json（数据日 {snap.get('date') or '—'}）",
                        "modules/decision.py::derive_position 口径"],
            "data": {"n_reasons": len(reasons)}}


def _ans_market(snap: dict) -> dict:
    parts = [f"- 市场温度：**{_fmt_num(snap.get('temperature'))}**"]
    parts.append(f"- 情绪周期：**{snap.get('cycle') or '快照未含'}**")
    promo = snap.get("promo_overall")
    parts.append(f"- 连板晋级率（综合）：**{_fmt_num(promo) + '%' if promo is not None else '快照未含'}**")
    ladder = snap.get("ladder") or {}
    if ladder:
        seg = "、".join(f"{k} {_fmt_num(v)}%" for k, v in list(ladder.items())[:6])
        parts.append(f"- 梯队晋级：{seg}")
    parts.append(f"_数据日 {snap.get('date') or '—'}。_")
    return {"status": "ok", "intent": "market", "answer": "\n".join(parts),
            "sources": [f"快照 data/daily_snapshot.json（数据日 {snap.get('date') or '—'}）"],
            "data": {"temperature": snap.get("temperature"), "cycle": snap.get("cycle"),
                     "promo_overall": promo}}


def _ans_recommend(rec, data_dir) -> dict:
    from modules.recommend_engine import load_latest_recommendation
    r = rec if isinstance(rec, dict) else load_latest_recommendation(data_dir)
    if r.get("status") != "ok":
        return {"status": "unavailable",
                "reason": f"荐股引擎数据不可用：{r.get('reason') or '未知原因'}"}
    picks = r.get("picks") or []
    if not picks:
        return {"status": "unavailable", "reason": "今日推荐候选为空（引擎如实未产出）"}
    lines = [f"**今日推荐 {len(picks)} 只**（多算法融合分 0-100，Top 5）："]
    for i, p in enumerate(picks[:5], 1):
        lines.append(f"{i}. {p.get('name') or '—'} `{p.get('code') or '—'}`　综合 {_fmt_num(p.get('composite'))}")
    lines.append(f"_生成时间 {r.get('generated_at') or '—'}；行情截至 {r.get('data_as_of') or '—'}；"
                 "逐票算法归因与买卖方案见「每日荐股」页。_")
    return {"status": "ok", "intent": "recommend", "answer": "\n".join(lines),
            "sources": [f"荐股 data/daily_recommendation.json（生成 {r.get('generated_at') or '—'}）"],
            "data": {"n_picks": len(picks)}}


def _ans_replay(data_dir=None) -> dict:
    dates = dm.list_archive_dates()
    if not dates:
        return {"status": "unavailable",
                "reason": "尚无归档快照（data/snapshots/ 为空），无复盘可答（不重构历史）"}
    latest = dm.load_archive(dates[-1])
    if not latest:
        return {"status": "unavailable", "reason": f"最近归档 {dates[-1]} 读取失败（不臆算）"}
    pos = latest.get("position") or {}
    lines = [f"**最近归档 {dates[-1]}**：",
             f"- 市场温度 {_fmt_num(latest.get('temperature'))}、"
             f"建议仓位 {_fmt_num(pos.get('pct'))}%（档位 {pos.get('band') or '—'}）",
             f"- 已归档 {len(dates)} 天（{dates[0]} 起）；逐日「当时决策依据 + 次日对照 + 预测对账」"
             "请用「决策回放」页。"]
    return {"status": "ok", "intent": "replay", "answer": "\n".join(lines),
            "sources": [f"归档 data/snapshots/{dates[-1]}.json"],
            "data": {"n_archives": len(dates), "latest": dates[-1]}}


def _ans_caps(snap: dict) -> dict:
    pos = snap.get("position") or {}
    reasons = pos.get("reasons") or []
    warns = [r for r in reasons if "⚠️" in str(r) or "封顶" in str(r) or "陈旧" in str(r)]
    lines = ["**今日风险与数据新鲜度提示**："]
    if warns:
        lines += [f"- {w}" for w in warns]
    else:
        lines.append("- 当日推导未触发封顶/降仓提示（快照无 ⚠️ 条目）")
    lines.append(f"- 新鲜度封顶阈值（单一真理源）：stale 压到 {_fmt_num(FRESHNESS_CAPS['stale'])}%、"
                 f"warn 压到 {_fmt_num(FRESHNESS_CAPS['warn'])}%")
    lines.append(f"_数据日 {snap.get('date') or '—'}；数据时效全景见「数据时效性看板」页。_")
    return {"status": "ok", "intent": "caps", "answer": "\n".join(lines),
            "sources": [f"快照 data/daily_snapshot.json（数据日 {snap.get('date') or '—'}）",
                        "modules/decision.py::FRESHNESS_CAPS"],
            "data": {"n_warns": len(warns)}}


def answer(question: str, snapshot: dict | None = None,
           rec: dict | None = None, data_dir: str | None = None) -> dict:
    """自然语言决策问答主入口（见模块 spec）。"""
    intent = classify(question)
    if intent is None:
        return {"status": "ok", "intent": "fallback", "answer": GUIDE,
                "sources": [], "data": {}}

    if intent == "recommend":
        return _ans_recommend(rec, data_dir)
    if intent == "replay":
        return _ans_replay()

    snap = snapshot if isinstance(snapshot, dict) else _read_today_snapshot()
    if snap is None:
        return {"status": "unavailable",
                "reason": "无当日市场快照（data/daily_snapshot.json 缺失/损坏）——"
                          "决策问答只引用归档数据，不实时臆算"}
    if intent == "position":
        result = _ans_position(snap)
    elif intent == "reason":
        result = _ans_reason(snap)
    elif intent == "market":
        result = _ans_market(snap)
    else:
        result = _ans_caps(snap)
    if result.get("status") == "ok":
        result["answer"] += f"\n\n> ⚠️ {DISCLAIMER}"
    return result
