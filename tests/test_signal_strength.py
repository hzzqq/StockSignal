"""R22：SignalEngine 信号强度档位 + event_score 空关键词隐性 bug 回归。

覆盖：
- strength_label 静态方法（新能力）：强(>=70)/中(50-69)/弱(<50)，且越界值经 _clamp 收口；
- event_score 在 keyword 为空时不应命中任何事件（空正则 "" 会匹配全部，属历史隐性 bug）；
- _score_by_return 在行情缺失(NaN)时返回中性 50 而非最低档。
"""
import pandas as pd
import pytest

from modules.signal import SignalEngine


# ---------- strength_label（新能力） ----------

def test_strength_strong():
    assert SignalEngine.strength_label(85) == "强"


def test_strength_mid():
    assert SignalEngine.strength_label(60) == "中"


def test_strength_weak():
    assert SignalEngine.strength_label(30) == "弱"


def test_strength_clamps_overflow():
    assert SignalEngine.strength_label(150) == "强"


def test_strength_clamps_negative():
    assert SignalEngine.strength_label(-10) == "弱"


def test_strength_boundary_70_is_strong():
    assert SignalEngine.strength_label(70) == "强"


def test_strength_boundary_50_is_mid():
    assert SignalEngine.strength_label(50) == "中"


# ---------- event_score 空关键词回归 ----------

def test_event_score_empty_keywords_no_false_match(tmp_path):
    """空关键词不应匹配事件库中的利空事件（回归：此前 "" 正则命中全部）。"""
    eng = object.__new__(SignalEngine)
    csv = tmp_path / "events.csv"
    pd.DataFrame({
        "date": ["2024-01-01"],
        "ticker": ["600519"],
        "title": ["重大利空公告"],
        "type": ["利空"],
    }).to_csv(csv, index=False, encoding="utf-8-sig")
    eng.event_db_path = str(csv)

    # 空关键词 → 命中为空 → 中性偏多基准 52（不被利空拉低到 45）
    score = eng.event_score("600519", [], date=None)
    assert score == 52


def test_event_score_keyword_still_matches(tmp_path):
    """有真实关键词时仍能命中对应事件。"""
    eng = object.__new__(SignalEngine)
    csv = tmp_path / "events.csv"
    pd.DataFrame({
        "date": ["2024-01-01"],
        "ticker": ["600519"],
        "title": ["业绩大幅预增利好"],
        "type": ["利好"],
    }).to_csv(csv, index=False, encoding="utf-8-sig")
    eng.event_db_path = str(csv)

    score = eng.event_score("600519", ["预增"], date=None)
    # 命中一条利好 → 52 + 14 = 66
    assert score == 66


# ---------- _score_by_return NaN 防护 ----------

def test_score_by_return_nan_is_neutral():
    r = SignalEngine._score_by_return(
        float("nan"),
        [10, 5, 2, 0, -2, -5],
        [95, 80, 68, 58, 45, 30, 15],
    )
    assert r == 50
