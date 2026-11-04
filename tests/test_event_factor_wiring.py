"""事件因子接入决策系统的单元测试（离线、零网络）。

验证三件套：
1. event_driven_long_list 选股池（真实信号 / 离线降级）
2. SignalEngine.event_score 优先吃真实 P1 EV 信号，取不到回退本地
3. evaluate 暴露 event_source / event_signal
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from modules import event_factor as _ef
from modules.p1_signal import P1SignalLoader
from modules.signal import SignalEngine


@pytest.fixture
def sig_dir(tmp_path: Path) -> Path:
    d = tmp_path / "signals"
    d.mkdir()
    payload = {
        "model": "ev", "latest_date": "2026-08-14", "horizon": 10,
        "top_long": [
            {"symbol": "sh600869", "pred": 0.0298, "rank": 1.0},
            {"symbol": "sh600001", "pred": 0.0100, "rank": 0.9},
        ],
        "top_short": [{"symbol": "sh603118", "pred": -0.0545, "rank": 0.0007}],
        "daily": [
            {"date": "2026-08-14", "symbol": "sh600000", "score": 0.021, "signal": "看多"},
        ],
    }
    (d / "signal_ev_h10.json").write_text(json.dumps(payload), encoding="utf-8")
    return d


@pytest.fixture
def loader(sig_dir: Path) -> P1SignalLoader:
    return P1SignalLoader(source_dirs=[str(sig_dir)], ttl=10_000)


# ───────────────────────── 1. 选股池 ─────────────────────────
def test_long_list_ranked(loader):
    rows = _ef.event_driven_long_list(top_n=20, model="ev", loader=loader)
    assert len(rows) == 2
    assert rows[0]["symbol"] == "sh600869"
    assert rows[0]["score"] == 100.0          # rank 1.0 → 100
    assert rows[0]["signal"] == "看多"
    assert rows[0]["source"] == "P1-ev-top_long"
    assert rows[1]["score"] == 90.0           # rank 0.9 → 90
    # 按 rank 降序
    assert rows[0]["score"] >= rows[1]["score"]


def test_long_list_offline_empty():
    with tempfile.TemporaryDirectory() as td:
        ld = P1SignalLoader(source_dirs=[td], ttl=10_000)
        assert _ef.event_driven_long_list(top_n=20, model="ev", loader=ld) == []


# ───────────────────────── 2. event_score 真实信号优先 ─────────────────────────
def test_event_score_p1_hit(loader):
    eng = SignalEngine()
    eng._p1l = loader  # 注入假加载器，避免扫真实目录
    s = eng.event_score("sh600869", ["x"])
    assert 0 <= s <= 100
    assert s == 95  # rank 1.0 → 100 → clamp 95


def test_event_score_p1_short_maps_low(loader):
    eng = SignalEngine()
    eng._p1l = loader
    # sh603118 在 top_short，rank 0.0007 → 接近 0
    s = eng.event_score("sh603118", ["x"])
    assert 0 <= s <= 100
    assert s <= 10


def test_event_score_fallback_when_absent(loader):
    """不在 P1 池的标的 → 回退本地事件库逻辑，仍返回合法 0-100。"""
    eng = SignalEngine()
    eng._p1l = loader
    s = eng.event_score("sh999999", ["x"])
    assert 0 <= s <= 100


# ───────────────────────── 3. evaluate 暴露事件源 ─────────────────────────
def test_evaluate_exposes_event_source(loader):
    eng = SignalEngine()
    eng._p1l = loader
    r = eng.evaluate("sh600869", ["x"])
    assert r["event_source"] == "P1-ev-top_long"
    assert r["event_signal"] == "看多"
    assert r["event_score"] == 95
    assert 0 <= r["total"] <= 100


def test_evaluate_fallback_source(loader):
    eng = SignalEngine()
    eng._p1l = loader
    r = eng.evaluate("sh999999", ["x"])
    assert r["event_source"] == "本地事件库"
    assert r["event_signal"] is None
    assert 0 <= r["event_score"] <= 100


# ───────────── 4. 第五源（语音转写事件）接线守卫（2026-11-04 ③）────────────
class _NoSignalLoader:
    """前四源全空：P1 无榜单/无 daily，新闻/龙虎榜/主表均打空。"""
    source_dirs = ["<wiring-test>"]

    def available_models(self):
        return ["ev"]

    def top_long(self, *a, **k):
        return []

    def top_short(self, *a, **k):
        return []

    def daily_df(self, *a, **k):
        return None

    def load(self, *a, **k):
        return {}


def _patch_lower_sources(monkeypatch):
    monkeypatch.setattr(_ef, "news_event_signal", lambda *a, **k: {"available": False})
    monkeypatch.setattr(_ef, "lhb_event_signal", lambda *a, **k: {"available": False})
    monkeypatch.setattr(_ef, "tracked_event_signal", lambda *a, **k: {"available": False})


def _patch_voice_items(monkeypatch, items):
    monkeypatch.setattr("modules.voice_event.load_voice_events",
                        lambda *a, **k: items)


def test_fifth_source_wired_only_with_voice_user(monkeypatch):
    """第五源已接入兜底链：默认跳过，显式 voice_user 才命中（隐私闸门）。"""
    from datetime import datetime, timedelta
    _patch_lower_sources(monkeypatch)
    _patch_voice_items(monkeypatch, [{
        "ts": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
        "text": "公司中标大额合同", "sentiment": "利好", "urgency": "已发生/突发",
    }])
    # 默认：不读语音桶，诚实降级
    r0 = _ef.get_event_factor("601088", loader=_NoSignalLoader())
    assert r0["available"] is False
    # 显式：第五源命中
    r1 = _ef.get_event_factor("601088", loader=_NoSignalLoader(), voice_user="alice")
    assert r1["available"] is True
    assert r1["source"] == "voice-event"
    assert r1["score"] == pytest.approx(60.0)


def test_include_macro_does_not_leak_into_default_path(monkeypatch):
    """宏观上下文默认不触发、不污染既有返回结构（向后兼容）。"""
    seen = []
    monkeypatch.setattr("modules.macro_data.global_regime_score",
                        lambda: seen.append(1))
    r = _ef.get_event_factor("601088", loader=_NoSignalLoader())
    assert "macro" not in r
    assert seen == []
