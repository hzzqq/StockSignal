"""决策闭环 × 真实广度历史 集成回归网（离线、真实数据驱动）。

为什么存在（R28，接 R25/R27）：
    test_decision_loop_e2e 已锁「合成周期名 → 字段契约 + verdict 门控」，但**没有任何测试把
    真实 4094 行 shepherd_history.csv 喂进生产分类器 locate_cycle 再验闭环**。真实数据能抓
    合成数据抓不到的一类回归：若某天 locate_cycle 吐出 CYCLE_ADJ 里没有的新阶段名，
    derive_position 会告警并按 0 调节——闭环「静默降级却照算仓位」，单测全绿、线上失真。

本文件用**真实历史**驱动：
    1) 词汇表对齐：locate_cycle 在真实数据上产出的所有周期名 ⊆ CYCLE_ADJ 键
       （未来新增第 7 阶段忘同步 CYCLE_ADJ → 本条红）。
    2) 现代段不坍缩：2015+ 真实数据应分散到 >=4 个阶段（锁死 R25「修复试探坍缩已解」结论，
       若 zt 反推回归、现代段塌回单阶段 → 本条红）。
    3) 仓位硬约束：对每个真实出现的周期名 × 边界温度/方向/梯队/事件 网格，
       derive_position 输出恒在 [5,95]，且退潮+低温封顶 30、高潮分化+高温兜底 40。

真实数据被 .gitignore 忽略、且本沙箱已备份（R27），测试只读不写。
"""
from __future__ import annotations

import os

import pandas as pd
import pytest

from modules import decision as _dec
from modules.shepherd_forecast import locate_cycle
from modules.shepherd_reconstruct import _BREADTH_FILE


def _load_real_history() -> pd.DataFrame | None:
    """读取真实广度历史；gitignore 导致 CI 可能缺失，缺失则跳过（不人为造假）。"""
    if not os.path.exists(_BREADTH_FILE):
        return None
    return pd.read_csv(_BREADTH_FILE, encoding="utf-8-sig")


def _row_dict(df: pd.DataFrame, i: int) -> dict:
    return {c: (None if pd.isna(v) else v) for c, v in df.iloc[i].to_dict().items()}


@pytest.fixture(scope="module")
def real_history():
    df = _load_real_history()
    if df is None:
        pytest.skip("真实 shepherd_history.csv 缺失（被 .gitignore 忽略），跳过真实数据回归网")
    return df


def test_locate_cycle_vocabulary_subset_of_cycle_adj(real_history):
    """真实数据上 locate_cycle 产出的所有周期名，必须全部落在 CYCLE_ADJ 键集合内。

    这是闭环词汇表对齐的真护栏：新增阶段忘同步 CYCLE_ADJ 会立即红。
    """
    seen = set()
    for i in range(1, len(real_history)):
        today = _row_dict(real_history, i)
        prev = _row_dict(real_history, i - 1)
        cyc = locate_cycle(today=today, prev=prev)
        seen.add(cyc["name"])
    assert seen, "真实数据未产出任何周期（分类器异常）"
    unknown = seen - set(_dec.CYCLE_ADJ.keys())
    assert not unknown, f"locate_cycle 产出 CYCLE_ADJ 未覆盖的周期名: {unknown}"


def test_modern_segment_cycle_spread(real_history):
    """R25 结论锁死：2015+ 真实数据应分散到 >=4 个情绪阶段（非坍缩成单阶段）。"""
    modern = real_history[real_history["date"] >= "2015-01-01"]
    assert len(modern) > 100, "现代段样本过少，无法验证分布"
    names = set()
    for i in range(1, len(modern)):
        today = _row_dict(modern, i)
        prev = _row_dict(modern, i - 1)
        cyc = locate_cycle(today=today, prev=prev)
        names.add(cyc["name"])
    # 六阶段中至少命中 4 个，证明现代段广度信号有效、未坍缩
    assert len(names) >= 4, f"现代段周期分布过窄（疑似坍缩）: {sorted(names)}"


def test_derive_position_grid_within_bounds(real_history):
    """对每个真实出现的周期名 × 边界网格，derive_position 输出恒在 [5,95]，
    且极端风控分支正确生效。"""
    # 收集真实数据上实际出现的周期名（来自生产分类器，而非硬编码）
    real_cycles = set()
    for i in range(1, len(real_history)):
        today = _row_dict(real_history, i)
        prev = _row_dict(real_history, i - 1)
        real_cycles.add(locate_cycle(today=today, prev=prev)["name"])
    assert real_cycles, "未收集到真实周期名"

    temps = [0, 20, 50, 80, 100]
    biases = ["偏多", "偏空", "中性"]
    promos = [0, 40, 60, 100, None]
    events = [None, 5, -5]

    for cycle in sorted(real_cycles):
        for t in temps:
            for b in biases:
                for p in promos:
                    for e in events:
                        out = _dec.derive_position(
                            temp=t, bias=b, cycle_name=cycle,
                            overall_promo=p, event_adj=e,
                        )
                        pct = out["pct"]
                        assert 5 <= pct <= 95, (
                            f"仓位越界 [{5,95}]: cycle={cycle} temp={t} bias={b} "
                            f"promo={p} event={e} -> {pct}"
                        )
                        # 极端风控：退潮 + 低温封顶 30
                        if t < 20 and cycle == "退潮":
                            assert pct <= 30, f"退潮+低温未封顶30: {pct}"
                        # 极端风控：高潮分化 + 高温兜底 40
                        if t >= 80 and cycle == "高潮分化":
                            assert pct >= 40, f"高潮分化+高温未兜底40: {pct}"
