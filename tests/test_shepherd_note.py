"""
tests/test_shepherd_note.py — 情绪笔记（快照持久化 + 历史情绪回测）单元测试

锁住：
- 笔记读写：保存/读取/更新手记/删除，文件损坏优雅降级
- 次日走势判定：主口径 zt_prev_ret，备用涨停家数环比，缺失→未知
- 回填次日实际走势（含当日/次日行配对）
- 历史情绪回测：逐日重跑周期定位 + 准确率只统计有效样本
- 聚合统计：count（总出现）与 valid（有效样本）分开

离线测试：IO 用 monkeypatch 把 NOTE_FILE 指到 tmp_path，绝不污染 data/。
"""
import json
import os

import pandas as pd
import pytest

from modules import shepherd_note as sn


# ─────────────────────────────────────────────────────────────
#  次日走势判定
# ─────────────────────────────────────────────────────────────
def test_verdict_by_prev_ret():
    """主口径：次日打板溢价。"""
    assert sn._verdict(3.0) == "偏强"
    assert sn._verdict(-2.0) == "偏弱"
    assert sn._verdict(0.2) == "震荡"


def test_verdict_threshold_edges():
    """阈值边界：+1.0 偏强 / -1.0 偏弱（含等号）。"""
    assert sn._verdict(1.0) == "偏强"
    assert sn._verdict(-1.0) == "偏弱"
    assert sn._verdict(0.99) == "震荡"


def test_verdict_fallback_to_limit_up():
    """zt_prev_ret 缺失 → 退回涨停家数环比。"""
    assert sn._verdict(None, next_lu=130.0, cur_lu=100.0) == "偏强"     # 1.30 ≥1.15
    assert sn._verdict(None, next_lu=80.0, cur_lu=100.0) == "偏弱"      # 0.80 ≤0.85
    assert sn._verdict(None, next_lu=105.0, cur_lu=100.0) == "震荡"     # 1.05 中间


def test_verdict_unknown_when_no_data():
    """两者都缺 → 未知（不瞎猜）。"""
    assert sn._verdict(None) == "未知"
    assert sn._verdict(float("nan")) == "未知"
    assert sn._verdict(None, next_lu=None, cur_lu=100.0) == "未知"


# ─────────────────────────────────────────────────────────────
#  笔记读写（IO 隔离到 tmp_path）
# ─────────────────────────────────────────────────────────────
@pytest.fixture
def note_file(tmp_path, monkeypatch):
    """把笔记文件重定向到临时目录，避免污染真实 data/。"""
    p = tmp_path / "notes.json"
    monkeypatch.setattr(sn, "NOTE_FILE", str(p))
    monkeypatch.setattr(sn, "NOTE_DIR", str(tmp_path))
    return p


def test_save_and_load(note_file):
    fc = {
        "cycle": dict(id="main", name="主升高潮", emoji="🔥"),
        "score": 72.0, "bias": "偏多", "confidence": 90,
        "signals": [{"name": "主升确认"}], "summary": "test",
    }
    assert sn.save_note("2026-08-28", {"limit_up": 82.0}, fc, user_note="今日情绪不错")
    notes = sn.load_notes()
    assert "2026-08-28" in notes
    rec = notes["2026-08-28"]
    assert rec["indicators"]["limit_up"] == 82.0
    assert rec["forecast"]["cycle_name"] == "主升高潮"
    assert rec["forecast"]["signals"] == ["主升确认"]
    assert rec["user_note"] == "今日情绪不错"


def test_save_note_keeps_user_note_when_empty(note_file):
    """二次保存时 user_note 传空 → 不覆盖已有手记。"""
    sn.save_note("2026-08-28", {"limit_up": 80.0}, None, user_note="原始手记")
    sn.save_note("2026-08-28", {"limit_up": 82.0}, None, user_note="")
    assert sn.load_notes()["2026-08-28"]["user_note"] == "原始手记"
    # 指标应被更新
    assert sn.load_notes()["2026-08-28"]["indicators"]["limit_up"] == 82.0


def test_set_user_note(note_file):
    sn.save_note("2026-08-28", {"limit_up": 80.0})
    assert sn.set_user_note("2026-08-28", "更新后的手记")
    assert sn.load_notes()["2026-08-28"]["user_note"] == "更新后的手记"
    # 不存在的日期返回 False
    assert sn.set_user_note("2000-01-01", "x") is False


def test_delete_note(note_file):
    sn.save_note("2026-08-28", {"limit_up": 80.0})
    assert sn.delete_note("2026-08-28") is True
    assert sn.load_notes() == {}
    assert sn.delete_note("2026-08-28") is False


def test_load_notes_missing_file_returns_empty(tmp_path, monkeypatch):
    """文件不存在 → 空 dict，不抛异常。"""
    monkeypatch.setattr(sn, "NOTE_FILE", str(tmp_path / "nope.json"))
    assert sn.load_notes() == {}


def test_load_notes_corrupted_file_returns_empty(tmp_path, monkeypatch):
    """文件损坏（非法 JSON）→ 空 dict，不抛异常。"""
    p = tmp_path / "bad.json"
    p.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(sn, "NOTE_FILE", str(p))
    assert sn.load_notes() == {}


def test_load_notes_non_dict_returns_empty(tmp_path, monkeypatch):
    """文件是 JSON 数组（非 dict）→ 空 dict。"""
    p = tmp_path / "arr.json"
    p.write_text("[1,2,3]", encoding="utf-8")
    monkeypatch.setattr(sn, "NOTE_FILE", str(p))
    assert sn.load_notes() == {}


def test_save_note_nan_safe(note_file):
    """NaN 指标写 JSON 前被转 None（json 不允许 NaN，会产出非法文件）。"""
    nan = float("nan")
    sn.save_note("2026-08-28", {"limit_up": 80.0, "median_chg": nan})
    raw = note_file.read_text(encoding="utf-8")
    assert "NaN" not in raw
    assert sn.load_notes()["2026-08-28"]["indicators"]["median_chg"] is None


# ─────────────────────────────────────────────────────────────
#  回填次日实际走势
# ─────────────────────────────────────────────────────────────
def _mk_df(rows):
    return pd.DataFrame(rows)


def test_backfill_actuals(note_file):
    """回填次日 zt_prev_ret 与判定结果。"""
    sn.save_note("2026-08-27", {"limit_up": 60.0})
    df = _mk_df([
        {"date": "2026-08-27", "limit_up": 60.0, "zt_prev_ret": 1.0},
        {"date": "2026-08-28", "limit_up": 82.0, "zt_prev_ret": 3.17},
    ])
    changed = sn.backfill_actuals(df)
    assert changed == 1
    rec = sn.load_notes()["2026-08-27"]
    assert rec["actual_next"]["date"] == "2026-08-28"
    assert rec["actual_next"]["zt_prev_ret"] == pytest.approx(3.17)
    assert rec["actual_next"]["verdict"] == "偏强"


def test_backfill_no_next_day(note_file):
    """最后一天没有次日数据 → 不回填。"""
    sn.save_note("2026-08-28", {"limit_up": 82.0})
    df = _mk_df([{"date": "2026-08-28", "limit_up": 82.0, "zt_prev_ret": 3.17}])
    assert sn.backfill_actuals(df) == 0
    assert "actual_next" not in sn.load_notes()["2026-08-28"]


def test_backfill_idempotent(note_file):
    """重复回填不产生变更（changed=0）。"""
    sn.save_note("2026-08-27", {"limit_up": 60.0})
    df = _mk_df([
        {"date": "2026-08-27", "limit_up": 60.0, "zt_prev_ret": 1.0},
        {"date": "2026-08-28", "limit_up": 82.0, "zt_prev_ret": 3.17},
    ])
    assert sn.backfill_actuals(df) == 1
    assert sn.backfill_actuals(df) == 0


def test_backfill_empty_df_safe(note_file):
    """空 DataFrame / 无 date 列 → 返回 0，不抛异常。"""
    sn.save_note("2026-08-27", {"limit_up": 60.0})
    assert sn.backfill_actuals(None) == 0
    assert sn.backfill_actuals(pd.DataFrame()) == 0
    assert sn.backfill_actuals(pd.DataFrame({"x": [1]})) == 0


# ─────────────────────────────────────────────────────────────
#  历史情绪回测分析
# ─────────────────────────────────────────────────────────────
def _hist(n=20, start_ret=0.0):
    """构造 n 日历史：涨停/高度/梯队/炸板率/昨板溢价。"""
    rows = []
    for i in range(n):
        d = pd.Timestamp("2026-07-01") + pd.Timedelta(days=i)
        rows.append({
            "date": d.strftime("%Y-%m-%d"),
            "limit_up": 50.0 + i,
            "connect_hl": 4.0,
            "connect_2b": 10.0,
            "zt_fail_ratio": 20.0,
            "zt_prev_ret": start_ret + i * 0.3,
        })
    return pd.DataFrame(rows)


def test_analyze_history_structure():
    a = sn.analyze_history(_hist(20))
    for k in ("rows", "by_cycle", "accuracy", "verdict_dist"):
        assert k in a
    assert len(a["rows"]) == 19          # n-1：最后一天无次日
    assert isinstance(a["by_cycle"], list)


def test_analyze_history_accuracy_only_counts_valid():
    """准确率分母只算「次日可判定」的样本，不含未知。"""
    df = _hist(20)
    # 主口径 + 备用口径一起断掉后半段，制造真正的未知样本
    df.loc[df.index[:12], "zt_prev_ret"] = None
    df.loc[df.index[:12], "limit_up"] = None
    a = sn.analyze_history(df)
    acc = a["accuracy"]
    assert acc["total"] == 19
    assert 0 < acc["valid"] < 19
    assert acc["hit"] <= acc["valid"]
    # 未知样本确实存在
    assert a["verdict_dist"].get("未知", 0) > 0


def test_analyze_history_fallback_keeps_samples_valid():
    """主口径 zt_prev_ret 缺失时，备用口径（涨停家数环比）接管，样本不浪费。

    _hist 的 limit_up 是 50+i 递增，环比恒在 0.85~1.15 → 全部判「震荡」。
    """
    df = _hist(20)
    df["zt_prev_ret"] = None
    a = sn.analyze_history(df)
    assert a["accuracy"]["valid"] == 19
    assert a["verdict_dist"].get("震荡") == 19
    assert a["verdict_dist"].get("未知", 0) == 0


def test_analyze_history_all_unknown_rate_none():
    """全部无法判定 → rate 为 None（而不是假性 0.0）。"""
    df = _hist(20)
    df["zt_prev_ret"] = None
    df["limit_up"] = None       # 备用口径也断掉
    a = sn.analyze_history(df)
    assert a["accuracy"]["valid"] == 0
    assert a["accuracy"]["rate"] is None


def test_analyze_history_by_cycle_count_vs_valid():
    """count=该阶段总出现次数，valid=其中次日可判定的次数。"""
    df = _hist(20)
    df.loc[df.index[:10], "zt_prev_ret"] = None
    a = sn.analyze_history(df)
    for b in a["by_cycle"]:
        assert b["valid"] <= b["count"]
    assert sum(b["count"] for b in a["by_cycle"]) == len(a["rows"])


def test_analyze_history_win_rate_none_when_no_valid():
    """某阶段无有效样本 → win_rate 为 None，不是 0.0（避免误导）。"""
    df = _hist(20)
    df["zt_prev_ret"] = None
    df["limit_up"] = None
    a = sn.analyze_history(df)
    assert all(b["win_rate"] is None for b in a["by_cycle"])


def test_analyze_history_short_df():
    """样本过少 → 返回空结构，不崩。"""
    a = sn.analyze_history(_hist(2))
    assert a["rows"] == [] and a["by_cycle"] == []
    assert sn.analyze_history(None)["rows"] == []
    assert sn.analyze_history(pd.DataFrame())["rows"] == []


def test_summary_of_mentions_valid_sample():
    """总结文案必须点明「有效样本」，不能只报总数（防止被缺失数据误导）。"""
    df = _hist(20)
    df.loc[df.index[:12], "zt_prev_ret"] = None
    s = sn.summary_of(sn.analyze_history(df))
    assert "可判定" in s
    assert "有效" in s or "无法" in s


def test_summary_of_no_data():
    assert "样本不足" in sn.summary_of({})
    assert "样本不足" in sn.summary_of(sn.analyze_history(None))
