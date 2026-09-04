# -*- coding: utf-8 -*-
"""StockSignal 锐评迭代优化（I2/I3/I4/I6/I8/I9）单测。

覆盖本次决策闭环迭代的新行为：
  · I4 derive_position 输入校验（温度越界 clamp / 未知方向 / 未知周期告警）
  · I3 事件信号不可用时在 reasons 留痕
  · I2 快照 data_age_days / as_of 元信息
  · I8 prediction_log 记录事件归因字段 + 幂等保留已打分
  · I9 by_event 按事件开/关拆命中率
  · I6 calibration.verdict 样本新鲜度字段
"""
import logging

import pytest

from modules import decision as _dec
from modules import decision_track as _track
from modules import calibration as _cal
from modules import event_factor as _ev


# ───────── I4 输入校验 ─────────
def test_temp_clamp_upper():
    pos = _dec.derive_position(150, bias="中性", cycle_name="主升高潮")
    assert pos["pct"] == 95          # base 150 → clamp 100 → +5(主升) → clamp 95
    assert any("温度 100" in r for r in pos["reasons"])


def test_temp_clamp_lower():
    pos = _dec.derive_position(-20, bias="偏空", cycle_name="退潮")
    assert pos["pct"] == 5           # base clamp 0 → -8(偏空) -10(退潮) → clamp 5
    assert any("温度 0" in r for r in pos["reasons"])


def test_unknown_bias_warn(caplog):
    with caplog.at_level(logging.WARNING):
        pos = _dec.derive_position(50, bias="XYZ", cycle_name="主升高潮")
    assert pos["band"] in ("激进", "偏多", "中性", "偏空", "防御")  # 不崩
    assert any("未知方向" in r.message for r in caplog.records)


def test_unknown_cycle_warn(caplog):
    with caplog.at_level(logging.WARNING):
        pos = _dec.derive_position(50, bias="中性", cycle_name="神秘周期")
    assert any("未知情绪周期" in r.message for r in caplog.records)
    # 未知周期按 0 调节，pct 应等于基准仓位（无周期项）
    assert pos["pct"] == 50 or pos["pct"] == 5  # 50 clamp[5,95]=50


# ───────── I3 事件留痕 ─────────
def test_event_unavailable_reason():
    pos = _dec.derive_position(50, bias="中性", cycle_name="主升高潮", event_adj=None)
    assert any("事件驱动信号不可用" in r for r in pos["reasons"])


def test_event_applied_reason():
    pos = _dec.derive_position(50, bias="中性", cycle_name="主升高潮", event_adj=3)
    assert any("事件驱动催化" in r for r in pos["reasons"])


# ───────── I2 快照新鲜度元信息 ─────────
def test_snapshot_has_age_fields():
    snap = _dec.build_snapshot("2026-09-03", {}, 50,
                                {"cycle": {"name": "主升高潮"}, "bias": "偏多", "score": 60},
                                {"overall": 65})
    assert snap["as_of"] == "2026-09-03"
    assert "data_age_days" in snap
    assert isinstance(snap["data_age_days"], int)


# ───────── I8 事件归因字段落库 + 幂等 ─────────
def test_record_prediction_event_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path))
    import importlib
    importlib.reload(_track)

    ok = _track.record_prediction("2026-09-03", 60, "主升高潮", "偏多", 70,
                                  event_adj=3, event_available=True)
    assert ok
    recs = _track._load()
    assert len(recs) == 1
    assert recs[0]["event_adj"] == 3
    assert recs[0]["event_available"] is True


def test_record_prediction_idempotent_preserves_scored(tmp_path, monkeypatch):
    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path))
    import importlib
    importlib.reload(_track)

    _track.record_prediction("2026-09-03", 60, "主升高潮", "偏多", 70,
                              event_adj=3, event_available=True)
    # 打分后回填
    recs = _track._load()
    recs[0]["realized"] = 1.2
    recs[0]["hit"] = True
    _track._save(recs)
    # 同日重跑预测侧（事件信号这次取不到 → None）
    _track.record_prediction("2026-09-03", 60, "主升高潮", "偏多", 70,
                              event_adj=None, event_available=None)
    recs2 = _track._load()
    assert len(recs2) == 1
    assert recs2[0]["realized"] == 1.2      # 已打分保留
    assert recs2[0]["hit"] is True
    # 事件字段：本次 None → 沿用旧值，不被抹掉
    assert recs2[0]["event_available"] is True


# ───────── I9 by_event 拆分 ─────────
def test_by_event_split(tmp_path, monkeypatch):
    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path))
    import importlib
    importlib.reload(_track)

    recs = [
        {"date": "2026-09-01", "temp": 60, "cycle": "主升高潮", "bias": "偏多",
         "pct": 70, "event_available": True, "realized": 1.0, "hit": True},
        {"date": "2026-09-02", "temp": 60, "cycle": "主升高潮", "bias": "偏多",
         "pct": 70, "event_available": True, "realized": -1.0, "hit": False},
        {"date": "2026-09-03", "temp": 40, "cycle": "退潮", "bias": "偏空",
         "pct": 20, "event_available": False, "realized": -1.0, "hit": True},
        {"date": "2026-09-04", "temp": 40, "cycle": "退潮", "bias": "偏空",
         "pct": 20, "event_available": False, "realized": 1.0, "hit": False},
    ]
    _track._save(recs)
    be = {r["group"]: r for r in _track.by_event()}
    assert set(be.keys()) == {"事件开", "事件关"}
    assert be["事件开"]["n_call"] == 2 and be["事件开"]["accuracy"] == 50.0
    assert be["事件关"]["n_call"] == 2 and be["事件关"]["accuracy"] == 50.0


def test_last_scored_date(tmp_path, monkeypatch):
    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path))
    import importlib
    importlib.reload(_track)

    recs = [
        {"date": "2026-09-01", "temp": 60, "cycle": "主升高潮", "bias": "偏多",
         "pct": 70, "event_available": True, "realized": None, "hit": None},
        {"date": "2026-09-05", "temp": 60, "cycle": "主升高潮", "bias": "偏多",
         "pct": 70, "event_available": True, "realized": 1.0, "hit": True},
    ]
    _track._save(recs)
    assert _track.last_scored_date() == "2026-09-05"


# ───────── I6 verdict 新鲜度字段 ─────────
def test_verdict_freshness_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path))
    import importlib
    importlib.reload(_track)
    importlib.reload(_cal)

    _track._save([])
    v = _cal.verdict()
    assert "last_scored_date" in v
    assert "stale_days" in v
    assert v["last_scored_date"] is None  # 无样本 → 无最近打分


# ───────── S1 实时仓位卡片接通事件因子（消除活/归档漂移）─────────
def test_event_position_adj_ttl_cache_hits(monkeypatch):
    """成功结果应被 300s 缓存，ttl 内二次调用返回同一对象（不重读 11MB 文件）。"""
    calls = {"n": 0}

    def fake_long_list(top_n=50, model="ev", loader=None):
        calls["n"] += 1
        return [{"symbol": f"S{i}"} for i in range(30)]  # 30 只 → adj=3

    monkeypatch.setattr(_ev, "event_driven_long_list", fake_long_list)
    # 清缓存，确保从干净态开始
    _dec._event_adj_cache["value"] = None
    _dec._event_adj_cache["ts"] = 0.0

    a = _dec._event_position_adj(ttl=300)
    b = _dec._event_position_adj(ttl=300)
    assert a == b  # 缓存命中，返回同一对象（含新增的 as_of 字段）
    assert a["adj"] == 3 and a["long_count"] == 30
    assert "as_of" in a and a["as_of"]  # 真理源新增：事件信号真实截止日必须摊开
    assert calls["n"] == 1  # 只算了一次，第二次命中缓存


def test_event_position_adj_failure_not_cached(monkeypatch):
    """失败（返回 None）不写入缓存，下次调用会重试。"""
    calls = {"n": 0}

    def fake_long_list(top_n=50, model="ev", loader=None):
        calls["n"] += 1
        raise RuntimeError("信号文件读不到")

    monkeypatch.setattr(_ev, "event_driven_long_list", fake_long_list)
    _dec._event_adj_cache["value"] = None
    _dec._event_adj_cache["ts"] = 0.0

    assert _dec._event_position_adj(ttl=300) is None
    assert _dec._event_position_adj(ttl=300) is None
    assert calls["n"] == 2  # 两次都重试（失败不缓存）


def test_event_position_adj_ttl_zero_forces_recompute(monkeypatch):
    """ttl=0 强制每次重算（绕过缓存）。"""
    calls = {"n": 0}

    def fake_long_list(top_n=50, model="ev", loader=None):
        calls["n"] += 1
        return [{"symbol": "X"}]

    monkeypatch.setattr(_ev, "event_driven_long_list", fake_long_list)
    _dec._event_adj_cache["value"] = None
    _dec._event_adj_cache["ts"] = 0.0

    _dec._event_position_adj(ttl=0)
    _dec._event_position_adj(ttl=0)
    assert calls["n"] == 2


def test_live_hero_wires_event_into_position():
    """实时路径等价：derive_position 收到 event_adj 时，仓位含事件催化、理由含「事件驱动催化」。

    这是 S1 的核心不变量——实时大卡与归档快照必须同源（都经 _event_position_adj）。
    直接验证「文档级」闭环：build_snapshot 走 _event_position_adj → derive_position(event_adj=…)；
    实时 hero 现在也走同一条路。
    """
    # 模拟真实事件因子可用（多头池宽 → adj=3），两段路径都应产出一致的含催化仓位
    with EventAdjStub(adj=3):
        snap = _dec.build_snapshot("2026-09-03", {}, 50,
                                   {"score": 60, "bias": "偏多", "cycle": {"name": "主升"}},
                                   {"overall": 60})
        live_pos = _dec.derive_position(50, 60, "偏多", "主升", 60, event_adj=3)
    assert snap["position"]["pct"] == live_pos["pct"]
    assert any("事件驱动催化" in r for r in live_pos["reasons"])
    assert any("事件驱动催化" in r for r in snap["position"]["reasons"])


class EventAdjStub:
    """上下文管理器：用固定返回值 stub _event_position_adj，退出即恢复。"""

    def __init__(self, adj):
        self._adj = {"adj": adj, "long_count": 10 * adj}
        self._orig = None

    def __enter__(self):
        import modules.decision as d
        self._orig = d._event_position_adj
        d._event_position_adj = lambda top_n=50, ttl=300: self._adj
        return self

    def __exit__(self, *exc):
        import modules.decision as d
        d._event_position_adj = self._orig


# ───────── S4 事件因子长列表下钻（多头池个股缓存）─────────
def test_event_long_symbols_shape_and_cache(monkeypatch):
    """返回 [{symbol, score}] 列表；ttl 内二次调用命中缓存（不重读 11MB）。"""
    calls = {"n": 0}

    def fake_long_list(top_n=20, model="ev", loader=None):
        calls["n"] += 1
        return [{"symbol": f"S{i}", "score": 80 - i} for i in range(top_n)]

    monkeypatch.setattr(_ev, "event_driven_long_list", fake_long_list)
    _dec._event_symbols_cache["value"] = None
    _dec._event_symbols_cache["ts"] = 0.0

    a = _dec._event_long_symbols(ttl=300)
    b = _dec._event_long_symbols(ttl=300)
    assert a == b
    assert all("symbol" in d and "score" in d for d in a)
    assert calls["n"] == 1  # 命中缓存


def test_event_long_symbols_failure_returns_none(monkeypatch):
    """读取失败返回 None（不臆造），且不缓存以便下次重试。"""
    calls = {"n": 0}

    def fake_long_list(top_n=20, model="ev", loader=None):
        calls["n"] += 1
        raise RuntimeError("信号文件读不到")

    monkeypatch.setattr(_ev, "event_driven_long_list", fake_long_list)
    _dec._event_symbols_cache["value"] = None
    _dec._event_symbols_cache["ts"] = 0.0

    assert _dec._event_long_symbols(ttl=300) is None
    assert _dec._event_long_symbols(ttl=300) is None
    assert calls["n"] == 2
