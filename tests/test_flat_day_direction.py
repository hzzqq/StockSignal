"""tests/test_flat_day_direction.py

「平盘日」方向口径回归（2026-09-09 锐评 R7）。

真实缺陷（有量化证据，非演练）
--------------------------------
两条打分路径都把「次日恰好平盘（涨跌幅 = 0.00）」当成明确方向：

1) ``scripts/backtest_decision_closure.py``（论文实证基座）
   ``actual_dir = 1 if next_mchg > 0 else -1`` —— 平盘被归为**下跌**。
   后果：偏空预测在平盘日**白拿命中**，偏多预测反被罚 → 方向性偏置。
   实测 ``data/shepherd_history.csv`` 4093 个评分日中 **177 天（4.32%）为平盘**；
   修正前 overall = 1806/3667 = 49.3%，修正后 = 1722/3507 = **49.1%**
   （即旧口径多算了 84 次命中、160 次 call，全部来自平盘日）。

2) ``modules/decision_track.py``
   ``actual_dir`` 取 0 表示平盘，再与 ±1 比较 → 恒 False，把「无信息」记成「看错」。

统一口径：**平盘 = 无方向信息**，不计入 call/hit（与「中性预测不判命中」一致），
但 realized 照常记录，并单独计数披露。

本测试锁定五条不变量。
"""
import ast
import json
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import modules.decision_track as _track  # noqa: E402

BT_SRC = os.path.join(ROOT, "scripts", "backtest_decision_closure.py")
DT_SRC = os.path.join(ROOT, "modules", "decision_track.py")

# 广度 CSV 的字段（含 locate_cycle 用到的连板/炸板字段）
COLS = ["date", "up_count", "down_count", "flat_count", "limit_up", "limit_down",
        "red_ratio", "touch_down", "zt_fail_count", "hb_wave10", "median_chg",
        "avg_price", "connect_hl", "zt_fail_ratio", "connect_2b", "zt_prev_ret",
        "turnover_amt"]


def _write_breadth(path, n=30, last_next_flat=True):
    """造一段「红盘率高 + 中位数上涨」的广度数据（bias 恒为偏多，保证有 call）。

    last_next_flat=True 时，把**最后一行的 median_chg 设为 0** ——
    这行的前一行（倒数第二行）的「次日」就落在平盘日，用于验证平盘被排除。
    """
    rows = []
    for i in range(n):
        rows.append({
            "date": f"2026-01-{i + 1:02d}",
            "up_count": 3000, "down_count": 1800, "flat_count": 100,
            "limit_up": 60, "limit_down": 5, "red_ratio": 62.0,
            "touch_down": 3, "zt_fail_count": 8, "hb_wave10": 6.0,
            "median_chg": 1.0, "avg_price": 12.0,
            "connect_hl": 6.0, "zt_fail_ratio": 0.12, "connect_2b": 12.0,
            "zt_prev_ret": 0.01, "turnover_amt": 8.0e11,
        })
    if last_next_flat:
        rows[-1]["median_chg"] = 0.0
    pd.DataFrame(rows, columns=COLS).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def _run_bt(tmp_path, last_next_flat):
    from scripts.backtest_decision_closure import run
    p = _write_breadth(os.path.join(str(tmp_path), "breadth.csv"),
                       last_next_flat=last_next_flat)
    return run(breadth_file=p)


def test_flat_day_excluded_from_direction_denominator(tmp_path):
    """平盘日必须从方向命中率的分母中剔除；非平盘日则照常计入。"""
    flat = _run_bt(tmp_path, last_next_flat=True)
    up = _run_bt(tmp_path, last_next_flat=False)

    assert flat["meta"]["flat_days_excluded"] == 1, "应识别出 1 个平盘日"
    assert up["meta"]["flat_days_excluded"] == 0

    # 唯一差别就是那一行：平盘时该日不计入 call，非平盘时计入
    assert up["overall"]["call"] == flat["overall"]["call"] + 1, (
        f"平盘日未被排除：flat.call={flat['overall']['call']} up.call={up['overall']['call']}"
    )
    # 分母口径必须显式可核对（论文/校准都依赖它）
    assert flat["overall"]["dir_call_denominator"] == flat["overall"]["call"]


def test_flat_day_gets_no_free_hit_for_bearish_call(tmp_path):
    """旧口径下偏空预测在平盘日白拿命中 —— 修正后平盘日不再产生任何命中增量。"""
    flat = _run_bt(tmp_path, last_next_flat=True)
    up = _run_bt(tmp_path, last_next_flat=False)

    # 本样本 bias 恒为偏多，非平盘日命中 → 平盘日应少 1 次命中（而非多 1 次）
    assert up["overall"]["hit"] == flat["overall"]["hit"] + 1


def test_backtest_source_uses_three_state_direction():
    """源码守卫：actual_dir 必须是三态（含 < 0 分支），不得再是 `> 0 else -1`。"""
    src = open(BT_SRC, encoding="utf-8").read()
    ast.parse(src)  # 语法健全性
    assert "else (-1 if next_mchg < 0 else 0)" in src, "actual_dir 未改成三态"
    assert "actual_dir = 1 if next_mchg > 0 else -1" not in src, "仍存在二态旧写法"
    assert "flat_days" in src and "has_dir" in src, "缺少平盘计数/方向可用性开关"


# ───────────────── decision_track 侧 ─────────────────

def _reset_track(monkeypatch, tmp_path):
    monkeypatch.setattr(_track, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(_track, "PRED_PATH", str(tmp_path / "prediction_log.json"))


def _write_recs(tmp_path, recs):
    p = tmp_path / "prediction_log.json"
    p.write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")


def test_decision_track_flat_day_not_scored(monkeypatch, tmp_path):
    """次日刚好平盘 → realized=0 但 hit=None（不判命中），且不计入 n_call。"""
    _reset_track(monkeypatch, tmp_path)
    _write_recs(tmp_path, [{
        "date": "2026-01-05", "temp": 55.0, "cycle": "修复试探", "bias": "偏空",
        "pct": 35, "event_adj": None, "event_available": None,
        "realized": None, "hit": None,
    }])
    # 收盘价完全相同 → 次日涨跌幅恰为 0.00%
    monkeypatch.setattr(_track, "_fetch_benchmark_close",
                        lambda: {"2026-01-05": 3000.0, "2026-01-06": 3000.0})

    out = _track.score_predictions()

    assert out["scored"] == 1, "realized 仍应回填（平盘也是有效事实）"
    s = _track.summary()
    recs = _track._load()
    assert recs[0]["realized"] == 0.0
    assert recs[0]["hit"] is None, "平盘日不得判为命中/未命中"
    assert s["n_call"] == 0, "平盘日不得计入方向命中率分母"


def test_decision_track_directional_days_still_scored(monkeypatch, tmp_path):
    """回归护栏：真正有方向的日子照常判定（避免把修复做成「一律不判」）。"""
    _reset_track(monkeypatch, tmp_path)
    _write_recs(tmp_path, [
        {"date": "2026-01-05", "temp": 55.0, "cycle": "修复试探", "bias": "偏空",
         "pct": 35, "realized": None, "hit": None},
        {"date": "2026-01-06", "temp": 55.0, "cycle": "修复试探", "bias": "偏多",
         "pct": 65, "realized": None, "hit": None},
    ])
    monkeypatch.setattr(_track, "_fetch_benchmark_close",
                        lambda: {"2026-01-05": 3000.0, "2026-01-06": 2970.0,
                                 "2026-01-07": 3030.0})

    _track.score_predictions()
    recs = {r["date"]: r for r in _track._load()}
    assert recs["2026-01-05"]["hit"] is True, "偏空 + 次日跌 → 命中"
    assert recs["2026-01-06"]["hit"] is True, "偏多 + 次日涨 → 命中"
    assert _track.summary()["n_call"] == 2


def test_legacy_flat_records_normalized_on_load(monkeypatch, tmp_path):
    """历史遗留：旧口径把平盘记成 hit=False，读取时须归一为 None（幂等）。"""
    _reset_track(monkeypatch, tmp_path)
    _write_recs(tmp_path, [
        {"date": "2025-12-01", "bias": "偏空", "pct": 30, "realized": 0.0, "hit": False},
        {"date": "2025-12-02", "bias": "偏空", "pct": 30, "realized": -1.2, "hit": True},
    ])

    recs = _track._load()
    by_date = {r["date"]: r for r in recs}
    assert by_date["2025-12-01"]["hit"] is None, "平盘旧账未被纠正"
    assert by_date["2025-12-02"]["hit"] is True, "有方向的历史记录不得被误改"

    # 幂等：再读一次仍一致
    again = {r["date"]: r for r in _track._load()}
    assert again["2025-12-01"]["hit"] is None


def test_decision_track_source_handles_flat_explicitly():
    """源码守卫：decision_track 必须显式处理 actual_dir == 0，而非依赖恒 False 比较。"""
    src = open(DT_SRC, encoding="utf-8").read()
    assert "actual_dir == 0" in src, "未显式处理平盘日"
    assert "_normalize_flat_days" in src, "缺少历史口径纠正"
