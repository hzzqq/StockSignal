# -*- coding: utf-8 -*-
"""tests/test_event_score_fusion.py — PR-2 事件评分融合守卫。

锁死 event_score 的融合语义（2026-11-03 事件数据链闭环）：
1. ef 命中 + tracked 命中 → 0.7/0.3 加权融合（用户沉淀事件不再被短路无视）；
2. ef 命中 + tracked 无关联事件 → 100% ef（与旧短路行为一致，零回归）；
3. ef 本身就是 tracked 源 → 直接返回，不自我融合；
4. tracked 异常 → 按无事件处理，返回 100% ef（鲁棒降级）。
诚实红线：全部 monkeypatch 隔离，不依赖真实 P1 目录与 data/events.csv。
"""
import pytest

from modules.signal import SignalEngine


@pytest.fixture()
def eng():
    e = SignalEngine()
    e._p1l = object()  # 令 _p1_loader 返回非 None（真实加载器不参与本测试）
    return e


def test_fusion_blend_07_03(monkeypatch, eng):
    """ef 95 + tracked 76 → 0.7*95 + 0.3*76 = 89.3 → 89。"""
    monkeypatch.setattr(
        "modules.event_factor.get_event_factor",
        lambda *a, **k: {"available": True, "rank": 1.0,
                         "source": "P1-ev-top_long", "signal": "看多"})
    monkeypatch.setattr(
        "modules.event_factor.tracked_event_signal",
        lambda *a, **k: {"available": True, "score": 76.0, "source": "tracked-events"})
    s = eng.event_score("sh600869", ["x"])
    assert s == 89


def test_fusion_no_tracked_keeps_ef(monkeypatch, eng):
    """tracked 无关联事件 → 100% ef（与旧短路行为一致）。"""
    monkeypatch.setattr(
        "modules.event_factor.get_event_factor",
        lambda *a, **k: {"available": True, "rank": 1.0,
                         "source": "P1-ev-top_long", "signal": "看多"})
    monkeypatch.setattr(
        "modules.event_factor.tracked_event_signal",
        lambda *a, **k: {"available": False, "reason": "无关联事件"})
    assert eng.event_score("sh600869", ["x"]) == 95


def test_tracked_source_not_self_blended(monkeypatch, eng):
    """ef 即 tracked 源 → 直接返回因子分，不做 0.7/0.3 自我融合。"""
    calls = {"n": 0}

    def _fake_tracked(*a, **k):
        calls["n"] += 1
        return {"available": True, "score": 52.0, "source": "tracked-events"}

    monkeypatch.setattr(
        "modules.event_factor.get_event_factor",
        lambda *a, **k: {"available": True, "rank": 0.8,
                         "source": "tracked-events", "signal": "中性"})
    monkeypatch.setattr("modules.event_factor.tracked_event_signal", _fake_tracked)
    s = eng.event_score("sh600869", ["x"])
    assert s == 80  # rank 0.8 → 50 + 30 = 80，原样返回
    assert calls["n"] == 0  # 未触发二次 tracked 调用


def test_tracked_exception_degrades_to_ef(monkeypatch, eng):
    """tracked 抛异常 → 按无事件处理，返回 100% ef（不拖垮评分）。"""
    monkeypatch.setattr(
        "modules.event_factor.get_event_factor",
        lambda *a, **k: {"available": True, "rank": 1.0,
                         "source": "P1-ev-top_long", "signal": "看多"})

    def _boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr("modules.event_factor.tracked_event_signal", _boom)
    assert eng.event_score("sh600869", ["x"]) == 95
