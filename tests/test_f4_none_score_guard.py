"""F4 无历史/空梯队时的优雅降级守卫。

防回归：leader_strength_index() 在梯队历史为空时返回 score=None（键存在、值为 None），
页面曾因 `ls.get('score', 0) >= 60` 在 score=None 时抛 TypeError。
本测试锁死两件事：
  1. leader_strength_index 空历史契约：score=None 且 available=False；
  2. event_breadth_resonance 对 None 分数不崩溃，返回合法 support。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules import shepherd_ladder as sl  # noqa: E402


def test_leader_strength_index_empty_history_returns_none_score(tmp_path, monkeypatch):
    # 指向空历史文件：模拟「全新安装 / 无梯队快照」场景
    empty = tmp_path / "ladder_history.json"
    empty.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sl, "LADDER_FILE", str(empty))
    res = sl.leader_strength_index()
    assert res["available"] is False
    assert res["score"] is None  # 关键契约：页面依赖此 None 走降级分支


def test_event_breadth_resonance_none_score_no_crash():
    for state in ("结构牛", "普涨", "震荡", "恐慌", "暴跌", None):
        out = sl.event_breadth_resonance(state, None)
        assert "support" in out
        assert out["support"] in ("bullish", "neutral", "bearish", "none")
        assert out["label"]


def test_event_breadth_resonance_band_thresholds():
    # 分数分档边界：>=60 高 / >=30 中 / 其余低
    assert sl.event_breadth_resonance("结构牛", 70)["support"] == "bullish"
    mid = sl.event_breadth_resonance("结构牛", 45)
    low = sl.event_breadth_resonance("结构牛", 10)
    assert mid["support"] in ("bullish", "neutral")
    assert low["support"] in ("neutral", "bearish", "none")
