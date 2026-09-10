"""tests/test_calibration_single_source.py

校准「单一真理源」与数值健壮性守卫（2026-09-09 锐评 R10）。

背景一：常量副本漂移
--------------------
``scripts/backtest_decision_closure.py``（论文 6.6 节实证的全部数字来源）原先在
自己文件里**复制**了一份 ``CYCLE_GROUPS`` 与 ``GAIN / MAX_DELTA / NOISE_DELTA /
STRONG_SAMPLES``，并逐字复制了 ``_suggest_delta`` 公式。三份副本（decision_track /
calibration / backtest）虽然当时数值一致，但生产侧一改而回测未同步，论文就会
「用另一套规则」产出结论 —— 即论文校验的不再是生产校准器，且没有任何测试会报警。
现改为直接 import 生产模块；本测试锁死「不得再出现本地副本」。

背景二：非有限值崩溃（真实可触发）
----------------------------------
``_suggest_delta`` 原先只判 ``avg_realized is None``，而 ``float('nan') is not None``：

  · ``_suggest_delta(float('nan'))`` → ValueError: cannot convert float NaN to integer
  · ``_suggest_delta(float('inf'))`` → OverflowError

会直接打断 ``suggestions()`` / ``verdict()`` 与回测打分。且 ``json.dump`` 默认
``allow_nan=True``，NaN 一旦写入 ``prediction_log.json`` 就会原样读回。
"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from modules import calibration as cal  # noqa: E402
from modules import decision_track as track  # noqa: E402
from scripts import backtest_decision_closure as bt  # noqa: E402

BT_SRC = os.path.join(ROOT, "scripts", "backtest_decision_closure.py")

# 不得在回测脚本内重新定义的常量名（必须来自生产模块）
FORBIDDEN_LOCAL = ["CYCLE_GROUPS", "GAIN", "MAX_DELTA", "NOISE_DELTA", "STRONG_SAMPLES"]


def test_backtest_uses_production_constants_by_identity():
    """回测引用的必须是生产**同一个对象**（is），而非等值副本 —— 从结构上杜绝漂移。"""
    assert bt.CYCLE_GROUPS is track.CYCLE_GROUPS
    assert bt.GAIN is cal.GAIN
    assert bt.MAX_DELTA is cal.MAX_DELTA
    assert bt.NOISE_DELTA is cal.NOISE_DELTA
    assert bt.STRONG_SAMPLES is cal.DEFAULT_STRONG_SAMPLES


def test_backtest_has_no_local_constant_copies():
    """AST 守卫：回测脚本模块级不得再赋值这些常量名。"""
    tree = ast.parse(open(BT_SRC, encoding="utf-8").read())
    offenders = []
    for node in tree.body:  # 只看模块级
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in FORBIDDEN_LOCAL:
                    offenders.append((t.id, node.lineno))
    assert not offenders, f"回测脚本又出现本地常量副本：{offenders}"


def test_backtest_suggest_delta_delegates_to_production():
    """回测的 _suggest_delta 必须与生产实现逐值一致（含边界）。"""
    for v in (None, 0, 0.3, 1.6, -2.7, 5.0, -9.0, 100.0, -100.0):
        assert bt._suggest_delta(v) == cal._suggest_delta(v), f"值 {v} 不一致"


def test_suggest_delta_is_finite_safe():
    """非有限值一律返回 0，绝不抛错（原实现对 nan/inf 会崩）。"""
    for bad in (float("nan"), float("inf"), float("-inf")):
        assert cal._suggest_delta(bad) == 0, f"{bad} 应安全降级为 0"


def test_suggest_delta_non_numeric_is_safe():
    """非数值类型（字符串/对象）安全降级为 0 并留痕。"""
    assert cal._suggest_delta("not-a-number") == 0
    assert cal._suggest_delta(object()) == 0


def test_suggest_delta_finite_values_clamped():
    """有限值仍按 clamp(round(GAIN*v), ±MAX_DELTA) 计算（回归护栏）。"""
    assert cal._suggest_delta(0.4) == 1          # round(0.8) = 1
    assert cal._suggest_delta(1.6) == 3          # round(3.2) = 3
    assert cal._suggest_delta(-3.0) == -5        # clamp 下限（round(-6) = -6 → -5）
    assert cal._suggest_delta(3.0) == 5          # clamp 上限


def test_suggestions_survive_nan_realized():
    """端到端：即便分组统计里混入 NaN，suggestions() 也不得崩。"""
    import modules.calibration as _cal
    from modules import decision_track as _t

    orig = _t.by_group
    try:
        _t.by_group = lambda *a, **k: [{
            "group": "修复期", "n": 30, "n_call": 25, "hits": 12,
            "accuracy": 48.0, "avg_pct": 50.0, "avg_realized": float("nan"),
        }]
        rows = _cal.suggestions()
        assert rows, "suggestions() 应仍能返回结果"
        assert rows[0]["sug_delta"] == 0, "NaN 平均收益应降级为 0 调节"
    finally:
        _t.by_group = orig
