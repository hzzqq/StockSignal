"""守卫：毕设算法改进实验沙盒的纯函数正确性（不依赖网络/训练）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.experiment_improvements import (  # noqa: E402
    shap_style_attribution,
    strict_holdout_eval,
    list_directions,
    get_known_findings,
    load_live_findings,
    summarize_findings,
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


# ───────────────────────── 毕设新方向：三算法诚实证据桥（T-350 后续，对齐 2026-10 改稿） ─────────────────────────
def test_known_findings_three_algorithms_honest_verdicts():
    """三算法 verdict 必须如实：#1 modest_positive、#2/#3 negative（不包装成碾压）。"""
    f = get_known_findings()
    assert set(f) == {"transformer_signal", "gnn_factor", "rl_position"}
    assert f["transformer_signal"]["verdict"] == "modest_positive"
    assert f["gnn_factor"]["verdict"] == "negative"
    assert f["rl_position"]["verdict"] == "negative"
    # 数字与已验证清单逐位一致（防止回归篡改诚实口径）
    assert f["transformer_signal"]["direction_hit"] == 0.5130
    assert f["transformer_signal"]["direction_hit_baseline"] == 0.5097
    assert f["gnn_factor"]["direction_hit"] == 0.4948
    assert f["rl_position"]["sharpe"] == -0.741
    assert f["rl_position"]["sharpe_baseline_tanh"] == 1.145


def test_load_live_findings_missing_dir_no_fabrication():
    """缺失目录/文件 → 回落 KNOWN，live=False，绝不把「没查到」当「没效果」。"""
    out = load_live_findings(results_dir="E:/nonexistent_p1_results_xyz")
    assert out["_meta"]["live"] is False
    assert out["transformer_signal"]["direction_hit"] == 0.5130
    assert out["gnn_factor"]["direction_hit"] == 0.4948
    assert out["rl_position"]["sharpe"] == -0.741


def test_load_live_findings_overrides_when_present(tmp_path):
    """真有结果 JSON 时按字段覆盖（诚实替换），且只动存在的数值键。"""
    payload = {"transformer_signal": {"direction_hit": 0.5200}, "gnn_factor": {"direction_hit": 0.5000}}
    (tmp_path / "experiment_findings.json").write_text(
        __import__("json").dumps(payload), encoding="utf-8")
    out = load_live_findings(results_dir=str(tmp_path))
    assert out["_meta"]["live"] is True
    assert out["transformer_signal"]["direction_hit"] == 0.5200  # 被覆盖
    assert out["gnn_factor"]["direction_hit"] == 0.5000          # 被覆盖
    assert out["rl_position"]["sharpe"] == -0.741                # 未提供，保持 KNOWN


def test_summarize_findings_new_direction_narrative():
    """新方向叙事：创新主轴=决策闭环；三算法=诚实证据；非对称发现。"""
    s = summarize_findings()
    assert s["core_innovation"] == "decision_closure"
    assert s["findings"]["transformer_signal"]["verdict"] == "modest_positive"
    assert s["findings"]["gnn_factor"]["verdict"] == "negative"
    assert s["findings"]["rl_position"]["verdict"] == "negative"
    assert s["asymmetric_finding"]["defensive_total_pp"] == 9.5
    assert s["asymmetric_finding"]["offensive_total_pp"] == -8.0
    assert s["decision_closure_anchor"]["accuracy"] == 0.491
