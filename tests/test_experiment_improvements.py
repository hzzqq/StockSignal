"""守卫：毕设算法改进实验沙盒的纯函数正确性（不依赖网络/训练）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.experiment_improvements import (  # noqa: E402
    shap_style_attribution,
    strict_holdout_eval,
    list_directions,
)


def test_shap_attribution_sorts_by_abs():
    contribs = [
        {"factor": "市场温度（基准）", "delta": 0.0, "running": 50.0},
        {"factor": "方向「偏多」", "delta": 8.0, "running": 58.0},
        {"factor": "周期「退潮」", "delta": -10.0, "running": 48.0},
    ]
    out = shap_style_attribution(contribs)
    keys = list(out.keys())
    # |-10| 最大应排第一；贡献值正确累积
    assert keys[0] == "周期「退潮」"
    assert out["方向「偏多」"] == 8.0
    assert out["市场温度（基准）"] == 0.0


def test_holdout_accuracy_basic():
    preds = [1.0, -1.0, 0.5, -0.2]
    labels = [1, -1, 0, 1]  # 第 3 个平盘不计
    r = strict_holdout_eval(preds, labels)
    # i0 多中多(hit), i1 空中空(hit), i3 多但 pred<0 不中 → 2/3
    assert r["n"] == 3
    assert abs(r["accuracy"] - 2 / 3) < 1e-9
    assert r["n_long"] == 2 and r["n_short"] == 1


def test_holdout_empty():
    assert strict_holdout_eval([], [])["n"] == 0
    assert strict_holdout_eval([1.0], [2])["n"] == 0  # 长度不一致


def test_four_directions_present():
    d = list_directions()
    assert len(d) == 4
    keys = {x["key"] for x in d}
    assert {"transformer_signal", "gnn_factor", "rl_position", "shap_attribution"} <= keys
    # #4 应排第一（最易出成果）
    assert d[0]["key"] == "shap_attribution"
