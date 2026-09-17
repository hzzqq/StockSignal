"""tests/test_backtest_robustness.py — H5 回测稳健性（离线纯计算）。"""

import pandas as pd

from modules.backtest_robustness import (
    ic_decay,
    overfit_assessment,
    param_sensitivity_matrix,
    summarize_walk_forward,
    walk_forward_windows,
)


# ───────── walk_forward_windows ─────────
def test_walk_forward_windows_orders_and_expands():
    w = walk_forward_windows("2024-01-01", "2025-01-01", n_splits=3)
    assert len(w) == 3
    for i, f in enumerate(w, start=1):
        assert f["fold"] == i
        assert f["train_start"] == "2024-01-01"          # 扩张窗口：训练起点固定
        assert f["train_end"] == f["test_start"]          # 训练止 == 测试起，无缝
        assert f["test_start"] < f["test_end"]
        assert f["train_days"] >= 60 and f["test_days"] >= 5
    # 训练段不断加长
    assert w[0]["train_days"] < w[-1]["train_days"]
    assert w[-1]["test_end"] == "2025-01-01"


def test_walk_forward_too_short_returns_empty():
    assert walk_forward_windows("2024-01-01", "2024-02-01", n_splits=3) == []
    assert walk_forward_windows("2025-01-01", "2024-01-01", n_splits=3) == []
    assert walk_forward_windows("bad", "worse", n_splits=3) == []


# ───────── overfit_assessment ─────────
def test_overfit_verdicts():
    assert overfit_assessment(20.0, 25.0)["verdict"] == "robust"
    assert overfit_assessment(20.0, 15.0)["verdict"] == "acceptable"   # 衰减 25% ≤ 50%
    assert overfit_assessment(20.0, 4.0)["verdict"] == "overfit_risk"  # 衰减 80%
    assert overfit_assessment(-3.0, 5.0)["verdict"] == "no_edge"
    assert overfit_assessment(None, 5.0)["status"] == "unavailable"
    assert overfit_assessment("x", 5.0)["status"] == "unavailable"


def test_overfit_tolerance_param():
    # 衰减 40%：默认容忍 50% → acceptable；收紧到 30% → overfit_risk
    assert overfit_assessment(10.0, 6.0, tolerance=0.5)["verdict"] == "acceptable"
    assert overfit_assessment(10.0, 6.0, tolerance=0.3)["verdict"] == "overfit_risk"


# ───────── summarize_walk_forward ─────────
def test_summarize_walk_forward_aggregates():
    folds = [
        {"is_return_pct": 20.0, "oos_return_pct": 18.0},
        {"is_return_pct": 22.0, "oos_return_pct": 12.0},
        {"is_return_pct": 24.0, "oos_return_pct": 20.0},
    ]
    s = summarize_walk_forward(folds)
    assert s["status"] == "ok"
    assert s["n_folds"] == 3
    assert s["mean_is"] == 22.0
    assert s["mean_oos"] == round((18 + 12 + 20) / 3, 2)
    assert s["oos_win_rate"] == 100.0
    assert "assessment" in s


def test_summarize_walk_forward_unavailable_and_skips_incomplete():
    assert summarize_walk_forward([])["status"] == "unavailable"
    assert summarize_walk_forward(None)["status"] == "unavailable"
    # 缺 OOS 的 fold 被跳过；无有效 fold → unavailable
    assert summarize_walk_forward([{"is_return_pct": 5.0}])["status"] == "unavailable"
    s = summarize_walk_forward([{"is_return_pct": 5.0},
                                {"is_return_pct": 10.0, "oos_return_pct": 8.0}])
    assert s["n_folds"] == 1


# ───────── param_sensitivity_matrix ─────────
def _runs():
    out = []
    for tp in (3, 5, 8):
        for sl in (5, 7):
            out.append({"params": {"take_profit_pct": tp, "stop_loss_pct": sl},
                        "total_return": 100 - abs(tp - 5) * 10 - abs(sl - 5) * 5})
    out.append({"params": {"take_profit_pct": 3, "stop_loss_pct": 5}, "error": "boom"})
    return out


def test_param_matrix_grid_best_plateau():
    m = param_sensitivity_matrix(_runs(), "take_profit_pct", "stop_loss_pct")
    assert m["x_labels"] == [3, 5, 8]
    assert m["y_labels"] == [5, 7]
    assert len(m["values"]) == 2 and len(m["values"][0]) == 3
    assert m["best"]["value"] == 100.0
    assert m["best"]["x"] == 5 and m["best"]["y"] == 5
    assert 0 <= m["plateau_ratio"] <= 100
    assert m["n_cells"] == 6


def test_param_matrix_empty():
    m = param_sensitivity_matrix([], "a", "b")
    assert m["values"] == [] and m["plateau_ratio"] is None and m["best"] is None
    assert param_sensitivity_matrix(None, "a", "b")["best"] is None


# ───────── ic_decay ─────────
def test_ic_decay_returns_entries():
    dates = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    codes = ["a", "b", "c"]
    factor = pd.DataFrame([[3, 2, 1], [1, 2, 3], [3, 2, 1], [1, 2, 3], [3, 2, 1]],
                          index=dates, columns=codes)
    # 让「下一期收益」的排序与当期因子完全同向 → IC = +1
    ret = pd.DataFrame([[0, 0, 0], [1, 0, -1], [-1, 0, 1], [1, 0, -1], [-1, 0, 1]],
                       index=dates, columns=codes)
    out = ic_decay(factor, ret, horizons=(1, 10))
    assert len(out) == 2
    assert out[0]["horizon"] == 1
    assert out[0]["n"] > 0                       # forward=1 有样本
    assert out[0]["ic_mean"] == 1.0              # 排序完全同向
    assert out[1]["horizon"] == 10 and out[1]["n"] == 0   # horizon 超出 → 诚实 0，不编造


def test_ic_decay_bad_panels_no_crash():
    out = ic_decay(None, None, horizons=(1,))
    assert out == [{"horizon": 1, "ic_mean": None, "ir": None, "n": 0}]
