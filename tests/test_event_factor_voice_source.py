# -*- coding: utf-8 -*-
"""tests/test_event_factor_voice_source.py — 第五真实源（语音转写事件）守卫。

锁死 voice_event_signal 与 get_event_factor 第五源接线的诚实行为：
1. 隐私闸门：username 为空 → 不读任何语音桶、available=False；
2. 命中：近窗口内语音事件按 T-288 小档聚合出分，source=voice-event，voice 元数据齐备；
3. 五档聚合：利好+利空相消 → 52 中性；多空交织不加减；
4. urgency 仅元数据透传、**不参与评分**（避免未回测口径耦合）；
5. 市场级语义：语音事件无 ticker 字段 → 对所有标的生效；
6. 窗口外 / 损坏 ts / 空列表 → 诚实降级 available=False，绝不造数；
7. 接线：get_event_factor 默认（voice_user=None）完全跳过第五源；显式传入才启用。
诚实红线：本文件任何用例不得依赖网络与真实 data/voice_events（monkeypatch 隔离）。
"""
from datetime import datetime, timedelta

import pytest

from modules.event_factor import get_event_factor, voice_event_signal


def _ts(days_ago: int = 1) -> str:
    return (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")


def _ev(text, sentiment, urgency="笼统", days_ago=1, ticker=None):
    d = {"ts": _ts(days_ago), "text": text, "event": "硬逻辑",
         "urgency": urgency, "sentiment": sentiment}
    if ticker is not None:
        d["ticker"] = ticker
    return d


def _patch_voice(monkeypatch, items, seen=None):
    """把语音事件读取指到内存列表（惰性导入在调用时绑定，patch 生效）。

    seen 记录 (limit, username) 调用，供隐私/隔离断言。
    """
    def fake(limit=20, username=None):
        if seen is not None:
            seen.append((limit, username))
        return items
    monkeypatch.setattr("modules.voice_event.load_voice_events", fake)


# ── 1. 隐私闸门 ────────────────────────────────────────────────────────────
def test_no_username_never_reads_bucket(monkeypatch):
    """username 为空/None → 不读任何桶，理由明示隐私闸门。"""
    seen = []
    _patch_voice(monkeypatch, [_ev("中标大合同", "利好")], seen)
    for u in (None, "", "   "):
        r = voice_event_signal("601088", username=u)
        assert r["available"] is False
        assert "隐私闸门" in r["reason"]
    assert seen == [], "空 username 时不得读取任何语音桶"


# ── 2. 命中 ────────────────────────────────────────────────────────────────
def test_hit_score_and_metadata(monkeypatch):
    """命中：小利好 +1 → 60 看多，source/rank/hard_logic/voice 元数据齐备。"""
    _patch_voice(monkeypatch, [_ev("公司中标大额合同", "利好")])
    r = voice_event_signal("601088", username="alice")
    assert r["available"] is True
    assert r["source"] == "voice-event"
    assert r["score"] == pytest.approx(60.0)   # 52 + 8*1
    assert r["signal"] == "看多"
    assert r["rank"] == pytest.approx(0.60)
    assert r["voice"]["n_events"] == 1
    assert r["voice"]["window_days"] == 7
    assert any("中标" in t for t in r["voice"]["titles"])
    assert r["hard_logic"].get("status") in ("ok", "unavailable")


# ── 3. 五档聚合 ────────────────────────────────────────────────────────────
def test_pos_neg_cancel_to_neutral(monkeypatch):
    """利好+利空相消 → 52 中性。"""
    _patch_voice(monkeypatch, [_ev("中标", "利好"), _ev("减持", "利空")])
    r = voice_event_signal("601088", username="alice")
    assert r["score"] == pytest.approx(52.0)
    assert r["signal"] == "中性"


def test_mixed_and_neutral_do_not_count(monkeypatch):
    """多空交织 / 中性 → 不加减（关注度不冒充方向）。"""
    _patch_voice(monkeypatch, [_ev("传闻四起", "多空交织"), _ev("例行公告", "中性")])
    r = voice_event_signal("601088", username="alice")
    assert r["score"] == pytest.approx(52.0)
    assert r["signal"] == "中性"


def test_clamp_bounds(monkeypatch):
    """极端多条同向事件仍被 clamp(5,95) 钳住，不溢出。"""
    _patch_voice(monkeypatch, [_ev(f"中标{i}", "利好") for i in range(20)])
    assert voice_event_signal("601088", username="alice")["score"] == pytest.approx(95.0)
    _patch_voice(monkeypatch, [_ev(f"减持{i}", "利空") for i in range(20)])
    assert voice_event_signal("601088", username="alice")["score"] == pytest.approx(5.0)


# ── 4. urgency 仅元数据、不加权评分 ─────────────────────────────────────────
def test_urgency_is_metadata_only(monkeypatch):
    """urgency 只进 urgency_breakdown，不改变 score（避免未回测口径耦合）。"""
    urgent = [_ev("突发中标", "利好", urgency="已发生/突发")]
    neutral = [_ev("中标", "利好", urgency="笼统")]
    _patch_voice(monkeypatch, urgent)
    a = voice_event_signal("601088", username="alice")
    _patch_voice(monkeypatch, neutral)
    b = voice_event_signal("601088", username="alice")
    assert a["score"] == b["score"] == pytest.approx(60.0)
    assert a["voice"]["urgency_breakdown"]["urgent"] == 1
    assert b["voice"]["urgency_breakdown"]["neutral"] == 1


# ── 5. 市场级语义 + ticker 过滤 ─────────────────────────────────────────────
def test_market_level_applies_to_any_ticker(monkeypatch):
    """语音事件无 ticker（转写时尚未关联个股）→ 市场级，对所有标的生效。"""
    _patch_voice(monkeypatch, [_ev("央行降准利好市场", "利好")])
    for sym in ("601088", "000001", "sh600000"):
        assert voice_event_signal(sym, username="alice")["available"] is True


def test_explicit_ticker_filters(monkeypatch):
    """未来若 entry 带 ticker，则按包含式匹配，不串味到别的标的。"""
    _patch_voice(monkeypatch, [_ev("中标", "利好", ticker="601088")])
    assert voice_event_signal("601088", username="alice")["available"] is True
    assert voice_event_signal("000001", username="alice")["available"] is False


# ── 6. 窗口外 / 损坏 / 空列表 → 诚实降级 ────────────────────────────────────
def test_out_of_window_excluded(monkeypatch):
    _patch_voice(monkeypatch, [_ev("旧中标", "利好", days_ago=30)])
    r = voice_event_signal("601088", username="alice", lookback_days=7)
    assert r["available"] is False
    assert "近 7 日" in r["reason"]


def test_broken_ts_skipped(monkeypatch):
    _patch_voice(monkeypatch, [{"ts": "not-a-date", "text": "中标", "sentiment": "利好"}])
    assert voice_event_signal("601088", username="alice")["available"] is False


def test_empty_list_and_read_failure(monkeypatch):
    _patch_voice(monkeypatch, [])
    assert voice_event_signal("601088", username="alice")["available"] is False

    def boom(*a, **k):
        raise RuntimeError("disk error")
    monkeypatch.setattr("modules.voice_event.load_voice_events", boom)
    r = voice_event_signal("601088", username="alice")
    assert r["available"] is False
    assert "读取失败" in r["reason"]


def test_username_isolation(monkeypatch):
    """按 username 读取专属桶（不跨用户），调用参数如实透传。"""
    seen = []
    _patch_voice(monkeypatch, [_ev("中标", "利好")], seen)
    voice_event_signal("601088", username="alice")
    assert seen[0][1] == "alice"


# ── 7. get_event_factor 第五源接线 ─────────────────────────────────────────
class _EmptyLoader:
    """前四源全空：P1 无模型/无榜单/无 daily，新闻/龙虎榜/主表也打空。"""
    source_dirs = ["<test>"]

    def available_models(self):
        return ["ev"]  # 含 model 才不会在模型检查处提前短路，得以走完整兜底链

    def top_long(self, *a, **k):
        return []

    def top_short(self, *a, **k):
        return []

    def daily_df(self, *a, **k):
        return None

    def load(self, *a, **k):
        return {}


def _patch_other_sources(monkeypatch):
    monkeypatch.setattr("modules.event_factor.news_event_signal",
                        lambda *a, **k: {"available": False})
    monkeypatch.setattr("modules.event_factor.lhb_event_signal",
                        lambda *a, **k: {"available": False})
    monkeypatch.setattr("modules.event_factor.tracked_event_signal",
                        lambda *a, **k: {"available": False})


def test_get_event_factor_default_skips_voice(monkeypatch):
    """默认 voice_user=None → 第五源完全跳过（向后兼容，行为与旧版一致）。"""
    seen = []
    _patch_voice(monkeypatch, [_ev("中标", "利好")], seen)
    _patch_other_sources(monkeypatch)
    r = get_event_factor("601088", loader=_EmptyLoader())
    assert r["available"] is False
    assert "近 7 日无语音转写事件" in r["reason"]  # reason 提及，但确实没读桶
    assert seen == [], "默认不得读取语音桶"


def test_get_event_factor_voice_user_enables_fifth_source(monkeypatch):
    """显式传 voice_user → 第五源启用并命中，source=voice-event。"""
    seen = []
    _patch_voice(monkeypatch, [_ev("公司中标大合同", "利好")], seen)
    _patch_other_sources(monkeypatch)
    r = get_event_factor("601088", loader=_EmptyLoader(), voice_user="alice")
    assert r["available"] is True
    assert r["source"] == "voice-event"
    assert r["score"] == pytest.approx(60.0)
    assert seen and seen[0][1] == "alice"
