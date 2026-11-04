# -*- coding: utf-8 -*-
"""tests/test_voice_decision_boundary.py — 语音事件进入决策链的边界守卫。

背景（2026-11-04，事件因子适配器 ③ 评估结论）：
用户希望「语音源接入 signal.event_score 决策评分」。勘测发现直接把第五源
（voice_event_signal，按用户隔离的语音草稿）硬接进 event_score 会踩三条红线：

1. 隐私闸门崩塌：event_score 是 SignalEngine 纯计算函数（evaluate / backtest /
   daily_snapshot 都调它），**无用户上下文**；第五源强制 username 必填且数据按
   用户隔离。硬接必然要么绕过闸门、要么把用户态引入全局决策。
2. 毁掉决策单一真理源与 49.1% 回测锚：daily_snapshot.json 是全局真理源，
   derive_position 按市场全局算仓位；若评分依赖某登录用户的私有草稿，
   不同用户算出不同决策分、回测（无用户态）无法复现 → 论文 49.1%(1722/3507)
   锚失效。backtest.py 用历史 date_str 回放，语音草稿是「当下」数据 → 前视污染。
3. 目标其实已达成：语音事件经「用户显式点存入主表 → SignalEngine.add_event →
   data/events.csv → 第四源 tracked_event_signal → event_score PR-2 融合」早已
   进入决策闭环。event_score 内 get_event_factor(...) 不传 voice_user，
   第五源天然不进决策链——这正是正确边界。

故本文件用**两组守卫**把边界钉死（零决策口径变更、无需重跑回测）：
- 正向：语音入库 → events.csv → tracked_event_signal → event_score 确实生效；
- 反向 AST：决策/回测链禁止出现 voice_user / voice_event_signal，且 event_score
  内 get_event_factor 调用不得携带 voice_user 关键字。

诚实红线：全部 monkeypatch 隔离，零网络、零真实 data/ 文件。
"""
import ast
import os

import pandas as pd
import pytest

from modules import signal as signal_mod
from modules.event_factor import tracked_event_signal
from modules.signal import SignalEngine

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 决策/回测链：这些模块必须与「按用户隔离的语音草稿」完全解耦
DECISION_CHAIN = [
    "modules/signal.py",
    "modules/decision.py",
    "modules/backtest.py",
    "scripts/daily_snapshot.py",
]
FORBIDDEN_VOICE_NAMES = {"voice_user", "voice_event_signal"}


def _recent(days_ago: int = 1) -> str:
    return str((pd.Timestamp.now() - pd.Timedelta(days=days_ago)).date())


# ── 正向：语音入库 → 第四源 → 决策评分（既有合法链路）────────────────────────
def _patch_engine(monkeypatch, tmp_path):
    """把 SignalEngine 事件主表与 tracked_event_signal 同时指到 tmp 隔离文件。

    两者共用 modules.signal.events_db_path（单一真理源），patch 该函数即可让
    「入库」与「第四源读取」落在同一份数据上，复现真实链路。
    """
    p = tmp_path / "events.csv"
    monkeypatch.setattr(signal_mod, "events_db_path", lambda *a, **k: str(p))
    eng = SignalEngine()
    eng.event_db_path = str(p)
    # 打空 P1/新闻路径：让 event_score 稳定走本地事件库（零网络）
    monkeypatch.setattr(eng, "_p1_loader", lambda: None)
    monkeypatch.setattr(eng, "_live_news_sentiment", lambda *a, **k: None)
    return eng, p


def test_voice_ingest_reaches_fourth_source(monkeypatch, tmp_path):
    """语音事件按 save_voice_event_to_db 的形态入库后，第四源能读到并给出看多分。

    模拟的是 voice_event.save_voice_event_to_db → engine.add_event 的落库结果：
    date / ticker / title(转写文本) / type(情绪倾向映射的小档)。
    """
    eng, _ = _patch_engine(monkeypatch, tmp_path)
    # 与 map_sentiment_to_strength('positive') 一致：语音只落「小」档，不冒充大档
    eng.add_event(_recent(), "601088", "公司中标大额合同", "小利好")
    r = tracked_event_signal("601088")
    assert r["available"] is True
    assert r["source"] == "tracked-events"
    assert r["score"] > 52, "小利好应抬高事件分"
    assert r["tracked"]["n_events"] == 1


def test_voice_ingest_reaches_event_score(monkeypatch, tmp_path):
    """入库语音事件最终影响 event_score（决策评分入口）——证明目标已达成。"""
    eng, _ = _patch_engine(monkeypatch, tmp_path)
    eng.add_event(_recent(), "601088", "煤炭价格大涨中标利好", "小利好")
    score_with = eng.event_score("601088", ["煤炭", "中标"], date=_recent())
    # 无事件时的对照（同一引擎、空库）
    eng.event_db_path = str(tmp_path / "empty.csv")
    score_without = eng.event_score("601088", ["煤炭", "中标"], date=_recent())
    assert 0 <= score_with <= 100
    assert score_with > score_without, "入库语音事件必须真实抬高决策评分"


def test_fifth_source_is_not_used_by_event_score(monkeypatch, tmp_path):
    """第五源草稿（未入库、按用户隔离）绝不参与 event_score：无 voice_user 即跳过。

    即便该用户存在利好语音草稿，只要没显式入库，决策评分就不应被它左右。
    """
    eng, _ = _patch_engine(monkeypatch, tmp_path)
    # 模拟「有草稿但未入库」：给一个存在的语音桶，但 events.csv 为空
    from datetime import datetime
    monkeypatch.setattr(
        "modules.voice_event.load_voice_events",
        lambda *a, **k: [{
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "text": "突发重大利好", "sentiment": "利好", "urgency": "已发生/突发",
        }],
    )
    score = eng.event_score("601088", ["煤炭"], date=_recent())
    # 无入库事件 → 落在中性基准区间，未被草稿拉高
    assert 45 <= score <= 60, f"决策评分被未入库语音草稿污染: {score}"


# ── 反向 AST：决策链不得引入用户隔离语音源 ──────────────────────────────────
@pytest.mark.parametrize("rel", DECISION_CHAIN, ids=lambda p: os.path.basename(p))
def test_decision_chain_has_no_voice_user_coupling(rel):
    """决策/回测链源码不得出现 voice_user / voice_event_signal（防前视与隐私泄漏）。"""
    path = os.path.join(ROOT, rel)
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    bad = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id in FORBIDDEN_VOICE_NAMES:
            bad.append(f"Name {n.id} @line {n.lineno}")
        elif isinstance(n, ast.Attribute) and n.attr in FORBIDDEN_VOICE_NAMES:
            bad.append(f"Attr .{n.attr} @line {n.lineno}")
        # 关键字参数（如 get_event_factor(..., voice_user=...)）
        elif isinstance(n, ast.keyword) and n.arg in FORBIDDEN_VOICE_NAMES:
            bad.append(f"keyword {n.arg}= @line {n.lineno}")
    assert not bad, (
        f"{rel} 出现用户隔离语音源耦合，会破坏决策单一真理源/回测复现性/隐私闸门：\n"
        + "\n".join(bad)
    )


def test_event_score_get_event_factor_call_has_no_voice_keyword():
    """精确锁：event_score 内每次 get_event_factor(...) 调用都不带 voice_user。"""
    path = os.path.join(ROOT, "modules", "signal.py")
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == "event_score"), None)
    assert fn is not None, "未找到 event_score 定义"
    calls = [n for n in ast.walk(fn)
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "get_event_factor"]
    assert calls, "event_score 应仍通过适配器取真实事件因子（守卫防被整段移除）"
    for c in calls:
        kws = {k.arg for k in c.keywords}
        assert "voice_user" not in kws, (
            f"event_score @line {c.lineno} 传入 voice_user → 决策评分将被"
            "按用户隔离的语音草稿污染，禁止"
        )


def test_voice_privacy_gate_still_enforced():
    """第五源隐私闸门未被削弱：无 username 绝不读桶。"""
    from modules.event_factor import voice_event_signal
    r = voice_event_signal("601088", username=None)
    assert r["available"] is False
    assert "隐私闸门" in r["reason"]
