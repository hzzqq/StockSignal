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


def test_shap_baseline_split_additive():
    """SHAP 加性归因语义：base + Σφi == final（可加性可验，教师 #4 核心实证）。"""
    contribs = [
        {"factor": "市场温度（基准）", "delta": 0.0, "running": 80.0},
        {"factor": "方向「偏多」", "delta": 8.0, "running": 88.0},
        {"factor": "羊群拥挤反向(红挤极端)", "delta": -12.0, "running": 76.0},
        {"factor": "梯队晋级率(70%)", "delta": 5.0, "running": 81.0},
    ]
    out = shap_style_attribution(contribs, baseline_split=True)
    assert out["baseline"] == 80.0
    assert out["adjustments"]["羊群拥挤反向(红挤极端)"] == -12.0
    assert "市场温度（基准）" not in out["adjustments"]  # 基准不入调节项
    assert out["adjustments_total"] == 1.0
    assert abs(out["baseline"] + out["adjustments_total"] - out["final_running"]) < 0.05
    # 排序：绝对值降序（12 > 8 > 5，无打平歧义）
    keys = list(out["adjustments"].keys())
    assert keys[0] == "羊群拥挤反向(红挤极端)"


def test_shap_baseline_split_empty_and_backward_compat():
    """空输入诚实返回 None 域；默认参数行为与旧版逐位一致（向后兼容铁律）。"""
    empty = shap_style_attribution([], baseline_split=True)
    assert empty["baseline"] is None and empty["final_running"] is None
    assert shap_style_attribution([]) == {}
    contribs = [{"factor": "A", "delta": 3.0, "running": 53.0}]
    assert shap_style_attribution(contribs) == {"A": 3.0}  # 旧签名不变


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
    # 长度不一致必须拒算（T-176 修复：原构造 [1.0] vs [2] 长度相同，守卫恒红）
    assert strict_holdout_eval([1.0], [2, 3])["n"] == 0
    assert strict_holdout_eval([1.0, -1.0], [2])["n"] == 0


def test_four_directions_present():
    d = list_directions()
    assert len(d) == 4
    keys = {x["key"] for x in d}
    assert {"transformer_signal", "gnn_factor", "rl_position", "shap_attribution"} <= keys
    # #4 应排第一（最易出成果）
    assert d[0]["key"] == "shap_attribution"
