"""
tests/test_ladder_leader.py — F4 连板龙头强度 + 事件×广度共振 单测

覆盖：
  · leader_strength_index（市场级强度、0-100、组件齐全、无前视泄漏）
  · next_day_promotion_probability（小样本诚实标注、高度趋势）
  · historical_promo_rate（日对不足时 available=False）
  · event_breadth_resonance（五档×三档矩阵全覆盖、未知状态不崩）
  · load_event_pool（缺失/存在/时效性）
  · 空历史优雅降级

全部通过 monkeypatch LADDER_FILE 指向临时文件，零污染真实 data/。
"""
import json
from datetime import datetime, timezone

import pytest

from modules import shepherd_ladder as sl
from modules import market_regime as mr


def _write_ladder(tmp_path, entries: dict, fname="shepherd_ladder_history.json"):
    p = tmp_path / fname
    p.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    return str(p)


def _sample_history():
    return {
        "2026-09-01": {"date": "2026-09-01", "distribution": {"1": 65, "2": 9, "3": 5, "4": 1, "6": 2, "7": 1},
                        "max_boards": 7, "total_connect": 18, "updated_at": "2026-09-01T15:30:00"},
        "2026-09-02": {"date": "2026-09-02", "distribution": {"1": 39, "2": 7, "3": 4, "4": 2},
                        "max_boards": 4, "total_connect": 13, "updated_at": "2026-09-02T15:30:00"},
        "2026-09-03": {"date": "2026-09-03", "distribution": {"1": 35, "2": 6, "4": 2, "5": 1},
                        "max_boards": 5, "total_connect": 9, "updated_at": "2026-09-03T15:30:00"},
        # 一条 suspect 应被排除
        "2026-09-04": {"date": "2026-09-04", "distribution": {"1": 99, "2": 99},
                        "max_boards": 2, "total_connect": 99, "updated_at": "2026-09-10T10:00:00",
                        "suspect": True},
    }


@pytest.fixture
def ladder_file(tmp_path, monkeypatch):
    p = _write_ladder(tmp_path, _sample_history())
    monkeypatch.setattr(sl, "LADDER_FILE", p)
    return p


def test_leader_strength_index_basic(ladder_file):
    out = sl.leader_strength_index()
    assert out["available"] is True
    assert 0 <= out["score"] <= 100
    assert out["date"] == "2026-09-03"  # 最新非 suspect 快照
    assert set(out["components"].keys()) == {"height", "density", "promo"}
    # suspect 的 2026-09-04 不应被采用
    assert out["max_boards"] == 5
    assert "非个股名单" in out["note"]


def test_leader_strength_no_lookahead(ladder_file):
    out = sl.leader_strength_index(as_of="2026-09-02")
    assert out["available"] is True
    assert out["date"] == "2026-09-02"  # 只用 ≤ as_of 的快照
    # 不能泄漏到 09-03 / 被排除的 09-04
    assert out["date"] <= "2026-09-02"


def test_leader_strength_empty(tmp_path, monkeypatch):
    p = _write_ladder(tmp_path, {})
    monkeypatch.setattr(sl, "LADDER_FILE", p)
    out = sl.leader_strength_index()
    assert out["available"] is False
    assert out["score"] is None


def test_next_day_promotion(ladder_file):
    out = sl.next_day_promotion_probability()
    assert out["available"] is True
    assert out["live_rate"] is not None
    assert out["n_pairs"] == 2          # 3 条有效日 → 2 个日对
    assert out["height_trend"] in {"高度扩张", "高度持平", "高度退潮", "无数据"}
    assert "小样本" in out["note"]


def test_historical_promo_rate_insufficient_pairs(tmp_path, monkeypatch):
    # 仅 2 天 → 1 个日对 < min_pairs(2) → available False
    hist = {
        "2026-09-01": {"date": "2026-09-01", "distribution": {"1": 65, "2": 9}, "max_boards": 2},
        "2026-09-02": {"date": "2026-09-02", "distribution": {"1": 39, "2": 7}, "max_boards": 2},
    }
    p = _write_ladder(tmp_path, hist)
    monkeypatch.setattr(sl, "LADDER_FILE", p)
    out = sl.historical_promo_rate()
    assert out["available"] is False
    assert out["n_pairs"] == 1


def test_event_breadth_resonance_matrix():
    allowed = {"bullish", "neutral", "bearish", "none"}
    for st in mr.STATE_ORDER:
        for sc in [None, 10, 45, 75]:
            r = sl.event_breadth_resonance(st, sc)
            assert r["label"], f"空标签 {st},{sc}"
            assert r["support"] in allowed
            assert r["color"].startswith("#")


def test_event_breadth_resonance_unknown_state():
    r = sl.event_breadth_resonance("未知状态", 80)
    assert r["support"] == "none"
    assert "未知" in r["label"]


def test_load_event_pool_present(tmp_path, monkeypatch):
    pool = {"date": "2026-09-03", "source": "P1-ev",
            "pool": [{"rank": i, "symbol": f"sh60000{i}", "score": 100 - i,
                      "signal": "看多", "source": "P1-ev-top_long"} for i in range(1, 21)]}
    edir = tmp_path / "data"
    edir.mkdir(exist_ok=True)
    (edir / "event_pool_brief.json").write_text(json.dumps(pool, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(sl, "LADDER_DIR", str(edir))
    out = sl.load_event_pool()
    assert out["available"] is True
    assert out["date"] == "2026-09-03"
    assert len(out["pool"]) == 20
    # 用固定 now 让时效性判定确定性：now=2026-09-11 → age=8 > 7 → stale
    monkeypatch.setattr(sl, "now_cst", lambda: datetime(2026, 9, 11, tzinfo=timezone.utc))
    out2 = sl.load_event_pool()
    assert out2["stale"] is True


def test_load_event_pool_missing(tmp_path, monkeypatch):
    edir = tmp_path / "empty"
    edir.mkdir(exist_ok=True)
    monkeypatch.setattr(sl, "LADDER_DIR", str(edir))
    out = sl.load_event_pool()
    assert out["available"] is False
    assert "缺失" in out["note"]
