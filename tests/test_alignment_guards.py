"""
tests/test_alignment_guards.py
==============================
T-273C：全链路口径对齐守卫——钉住审计矩阵（docs/alignment-matrix.md）中
**可自动化**的关键对齐点，防止口径静默漂移。

- 锚点 49.1%（1722/3507）已由 test_thesis_numbers_consistency /
  test_public_numbers_consistency / test_flat_day_direction 三层钉死，不重复；
- 本文件只钉矩阵新增可自动点：P1 horizon==10（rf 错配桶教训的再发防线）。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def test_p1_signal_horizon_is_10():
    """现役 h10 口径信号必须存在（rf=15 错配桶教训的再发防线，矩阵 #1）。

    信号目录允许多 horizon 模型共存（如 baseline_v39 为 h20——p1_signal.py
    已知剥 _h<数字> 形态）；守卫钉的是「**至少一个 horizon==10 的模型存在**」
    （EV/GRU 现役 rf=10 口径的信号基座），并如实报告发现的 horizon 集合。
    环境无信号文件时 pytest.skip（仅限「环境不具备」；h10 全消失属口径漂移，
    必须 fail）。
    """
    from modules.p1_signal import P1SignalLoader
    loader = P1SignalLoader(ttl=60)
    models = loader.available_models()
    if not models:
        pytest.skip("环境不具备：data/p1_signals/ 无信号文件（CI/干净环境）")
    horizons = {}
    for m in models:
        d = loader.load(m)
        h = d.get("horizon")
        if h is not None:
            horizons[m] = int(h)
    assert horizons, "信号文件存在但均无 horizon 字段（导出口径漂移）"
    assert 10 in set(horizons.values()), (
        f"目录中不存在 horizon==10 的模型（现役 rf=10 口径失去信号基座）："
        f"实测 horizon 集合 {horizons}——若有模型换窗，rf 持有桶须同步重对齐"
        f"（rf=15 错配教训，见 docs/alignment-matrix.md #1）")


def test_alignment_matrix_documents_exist_and_complete():
    """审计矩阵文档存在且覆盖 9 个衔接点 + 3 条行动项（防文档被清空弱化）。"""
    p = ROOT / "docs" / "alignment-matrix.md"
    assert p.exists(), "口径对齐矩阵文档缺失（T-273C 产物被删）"
    src = p.read_text(encoding="utf-8")
    for i in range(1, 10):
        assert f"### {i}." in src, f"矩阵缺少衔接点 #{i}"
    for kw in ("跨仓核对", "R10 成本口径", "horizon=10", "trading_costs"):
        assert kw in src, f"行动项/备忘缺失：{kw}"
    assert "49.1" in src, "矩阵必须引用 49.1% 锚（双口径分列）"


def test_engine_adjust_qfq_documented_in_matrix():
    """矩阵 #4 必须如实标注「引擎 qfq 实证 / P1 跨仓未实证」（诚实边界不删）。"""
    src = (ROOT / "docs" / "alignment-matrix.md").read_text(encoding="utf-8")
    assert "跨仓未实证" in src, "#4 复权口径的「未实证」诚实标注被删除"
    assert "qfq" in src
