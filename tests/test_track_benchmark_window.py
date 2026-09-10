"""tests/test_track_benchmark_window.py

基准窗口边界回归（2026-09-09 锐评 R9）。

真实缺陷
--------
``_fetch_benchmark_close`` 的主源（东财 ``index_zh_a_hist``）只拉**滚动 400 天**
（``start = now - 400d``），而 ``_next_day_return`` 在「预测日早于窗口起点」时的旧实现是::

    if base is None:
        base = sd[0]          # ← 兜底到窗口第一天
    ...
    return round((cn / cb - 1) * 100, 2)

即：一条 400 天前的预测会被塞上「窗口头两天」的涨跌幅，冒充它的「次日涨跌」，
再据此判定 hit → **静默污染命中率与刻度校准**，且日志里毫无痕迹（不打分与
「已打分为错」在结果上无法区分）。

正确语义：早于基准窗口 = 无法判定，返回 None，并由 ``score_predictions``
单独计数 ``out_of_range`` 上报。

本测试锁定四条。
"""
import ast
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import modules.decision_track as _track  # noqa: E402

DT_SRC = os.path.join(ROOT, "modules", "decision_track.py")


def _reset(monkeypatch, tmp_path):
    monkeypatch.setattr(_track, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(_track, "PRED_PATH", str(tmp_path / "prediction_log.json"))


def _write(tmp_path, recs):
    (tmp_path / "prediction_log.json").write_text(
        json.dumps(recs, ensure_ascii=False), encoding="utf-8"
    )


def test_next_day_return_none_when_date_predates_window():
    """预测日早于基准窗口起点 → 必须返回 None（旧实现返回窗口头两天的收益）。"""
    closes = {"2026-06-01": 3000.0, "2026-06-02": 3030.0}

    assert _track._next_day_return("2026-01-05", closes) is None, (
        "早于窗口的日期不得凭空产生收益（旧实现在此返回 +1.0%）"
    )
    # 窗口内的正常日期照常工作
    assert _track._next_day_return("2026-06-01", closes) == 1.0


def test_score_predictions_reports_out_of_range_without_scoring(monkeypatch, tmp_path):
    """窗口外的老记录：不计入 scored，且 **绝不写入** realized/hit。"""
    _reset(monkeypatch, tmp_path)
    _write(tmp_path, [
        {"date": "2025-01-05", "temp": 55.0, "cycle": "修复试探", "bias": "偏空",
         "pct": 35, "realized": None, "hit": None},
        {"date": "2026-06-01", "temp": 55.0, "cycle": "修复试探", "bias": "偏多",
         "pct": 65, "realized": None, "hit": None},
    ])
    monkeypatch.setattr(_track, "_fetch_benchmark_close",
                        lambda: {"2026-06-01": 3000.0, "2026-06-02": 3060.0})

    out = _track.score_predictions()

    assert out["out_of_range"] == 1, "早于窗口的记录必须被单独计数上报"
    assert out["scored"] == 1
    recs = {r["date"]: r for r in _track._load()}
    assert recs["2025-01-05"]["realized"] is None, "窗口外记录不得被写入 realized（会污染校准）"
    assert recs["2025-01-05"]["hit"] is None
    assert recs["2026-06-01"]["realized"] == 2.0
    assert recs["2026-06-01"]["hit"] is True, "偏多 + 次日涨 → 命中"


def test_out_of_range_does_not_enter_accuracy_denominator(monkeypatch, tmp_path):
    """窗口外记录不得进入命中率分母（否则分母虚高、命中率被稀释）。"""
    _reset(monkeypatch, tmp_path)
    _write(tmp_path, [
        {"date": "2025-01-05", "bias": "偏空", "pct": 35, "realized": None, "hit": None},
        {"date": "2026-06-01", "bias": "偏多", "pct": 65, "realized": None, "hit": None},
    ])
    monkeypatch.setattr(_track, "_fetch_benchmark_close",
                        lambda: {"2026-06-01": 3000.0, "2026-06-02": 3060.0})

    _track.score_predictions()
    s = _track.summary()

    assert s["n"] == 2, "总记录数仍为 2"
    assert s["n_call"] == 1, "只有窗口内那条进入方向命中率分母"
    assert s["accuracy"] == 100.0


def test_source_has_no_sd0_fallback():
    """源码守卫：不得再出现 `base = sd[0]` 式兜底赋值。"""
    src = open(DT_SRC, encoding="utf-8").read()
    ast.parse(src)

    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_next_day_return")
    bad = []
    for node in ast.walk(fn):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Subscript)):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        v = node.value
        if "base" in targets and isinstance(v.value, ast.Name) and v.value.id == "sd":
            bad.append(node.lineno)
    assert not bad, f"_next_day_return 仍把 base 兜底到窗口内某日（行 {bad}）"

    # 且必须显式返回 None
    assert "if base is None:" in src
    assert "无法判定" in src, "缺少「无法判定」语义说明"
