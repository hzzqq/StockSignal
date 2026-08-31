# -*- coding: utf-8 -*-
"""
modules/calibration.py — 用回测数据反向校准「情绪周期 → 仓位调节」刻度

为什么要有这个模块（这是把差异化主线从「拍脑袋」推向「用数据说话」）：
    decision.py 里的 CYCLE_ADJ（主升高潮 +5 / 退潮 -10 / 冰点 +5 ……）当初是**拍的常数**，
    从来没有被真实数据检验过。「退潮期该减 10 点还是 5 点？」这种问题，
    只有拿「该周期下给的建议仓位」对照「次日的真实涨跌」才能回答。

    本模块做的事：按四大战术分组（进攻/分化/修复/防守）统计
        avg_pct      该周期下系统平均给出的建议仓位
        avg_realized 该周期下次日基准（上证）平均真实涨跌%
    再据此算出**建议的刻度调节量**。

核心设计决策（务必遵守，改之前先读）：
    1. 【只出建议，不自动改规则】本模块绝不写 decision.py 的 CYCLE_ADJ。
       原因：样本早期只有几十条，自动拟合历史 = 过拟合，会把噪音当信号，
       下一次改版就得推倒重来。人工确认后才落地，且要求样本 >= strong_samples。
    2. 【调节量有界】sug_delta 被 clamp 在 ±MAX_DELTA(5) 之间。
       原因：单周期样本再怎么多也是小样本，一次校准最多微调 5 点，剩下的靠下一轮。
    3. 【小样本不表态】actionable 要求 n_call >= strong_samples(20) 且 |sug_delta| >= 2。
       1 条样本算出的 100% 命中率不是结论，是噪音，页面必须能看到「样本不足」。
    4. 【口径与 by_group 一致】中性预测不表态，不计入 n_call 分母。

调节量怎么算（可解释，不是黑箱）：
    next-day 平均涨跌 avg_realized ≈ 该周期下「按满仓能拿到的平均收益」。
    若某周期次日平均跌 1.5%，说明这个周期系统性不友好，刻度应下调；反之上调。
        sug_delta = clamp(round(GAIN * avg_realized), -MAX_DELTA, +MAX_DELTA)
    GAIN=2.0 的含义：次日平均涨跌 1% → 刻度调 2 点（仓位点数与涨跌幅不同量纲，
    2 倍是刻意保守的换算，避免单次校准把规则改头换面）。

纯本地、不联网、不依赖 streamlit；路径跟随 decision_track 的 SS_DATA_DIR 隔离机制。
"""

from __future__ import annotations

import logging
import os

from modules import decision_track as _track

logger = logging.getLogger(__name__)

# ── 校准参数（改这里之前先读上面的「核心设计决策」） ──────────────────────
GAIN = 2.0        # 次日平均涨跌 1% → 刻度调几点
MAX_DELTA = 5     # 单次校准调节上限（防过拟合）
DEFAULT_MIN_SAMPLES = 8    # 样本低于此数，连建议都不展示（页面默认）
DEFAULT_STRONG_SAMPLES = 20  # 样本达到此数，才认为「可以人工采纳」
NOISE_DELTA = 2   # |sug_delta| 小于此值视为噪音，不建议动手


# ───────────────────────── 分组 → 六阶段 ─────────────────────────
def _cycles_of(group: str) -> list[str]:
    """反查某战术分组包含哪些情绪周期阶段。"""
    return sorted(c for c, g in _track.CYCLE_GROUPS.items() if g == group)


def _cur_adj(cycles: list[str]) -> float | None:
    """该分组下各阶段当前 CYCLE_ADJ 的均值（读 decision.py 的单一真理源）。"""
    try:
        from modules import decision as _dec
    except Exception:  # noqa: BLE001
        return None
    vals = [_dec.CYCLE_ADJ.get(c) for c in cycles]
    vals = [v for v in vals if isinstance(v, (int, float))]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 1)


# ───────────────────────── 建议生成 ─────────────────────────
def _suggest_delta(avg_realized: float | None) -> int:
    """由「次日平均实际涨跌」推出建议调节量（有界、取整）。"""
    if avg_realized is None:
        return 0
    raw = GAIN * float(avg_realized)
    return int(max(-MAX_DELTA, min(MAX_DELTA, round(raw))))


def suggestions(min_samples: int = DEFAULT_MIN_SAMPLES,
                strong_samples: int = DEFAULT_STRONG_SAMPLES) -> list[dict]:
    """按四大战术分组给出仓位刻度的校准建议（纯本地，不联网、不改规则）。

    返回列表（顺序与 decision_track._GROUP_ORDER 一致），每项：
        group        战术分组名（进攻期/分化期/修复期/防守期）
        cycles       该分组覆盖的六阶段
        n_call       表态次数（偏多/偏空；中性不计）
        avg_pct      平均建议仓位(%)
        avg_realized 次日基准平均实际涨跌(%)
        edge         仓位加权后的暴露收益 = avg_pct/100 * avg_realized(%)，
                     用来看「敢给的仓位」是否换来了「对等的收益」
        cur_adj      该分组当前 CYCLE_ADJ 均值
        sug_delta    建议调节量（有界 ±MAX_DELTA）
        sug_adj      cur_adj + sug_delta（None 表示取不到当前值）
        confidence   0~1，n_call/strong_samples 封顶，页面用来显示可信度
        actionable   是否值得人工采纳（样本够 + 调节量超噪音阈值）
        verdict      一句话结论（人话，直接展示给用户）
    """
    out: list[dict] = []
    for g in _track.by_group(min_samples=min_samples):
        cycles = _cycles_of(g["group"])
        cur = _cur_adj(cycles)
        delta = _suggest_delta(g["avg_realized"])
        n_call = g["n_call"]
        actionable = bool(n_call >= strong_samples and abs(delta) >= NOISE_DELTA)

        # 结论文案：先判样本，再判刻度，避免拿噪音当结论
        if n_call < strong_samples:
            verdict = f"样本仅 {n_call} 条（需 ≥{strong_samples}），暂不构成调参依据"
        elif abs(delta) < NOISE_DELTA:
            verdict = "刻度基本合适，无需调整"
        elif delta > 0:
            verdict = f"该周期次日平均涨 {g['avg_realized']}%，建议仓位刻度上调 {delta} 点"
        else:
            verdict = f"该周期次日平均跌 {abs(g['avg_realized'])}%，建议仓位刻度下调 {abs(delta)} 点"

        edge = None
        if g["avg_pct"] is not None and g["avg_realized"] is not None:
            edge = round(g["avg_pct"] / 100.0 * g["avg_realized"], 3)

        out.append({
            "group": g["group"],
            "cycles": cycles,
            "n_call": n_call,
            "n": g["n"],
            "avg_pct": g["avg_pct"],
            "avg_realized": g["avg_realized"],
            "edge": edge,
            "cur_adj": cur,
            "sug_delta": delta,
            "sug_adj": (round(cur + delta, 1) if cur is not None else None),
            "confidence": round(min(n_call / float(strong_samples), 1.0), 2),
            "actionable": actionable,
            "verdict": verdict,
        })
    return out


def as_patch(strong_samples: int = DEFAULT_STRONG_SAMPLES) -> dict[str, int]:
    """把「值得采纳」的分组建议摊回六阶段，得到可直接抄进 decision.py 的 CYCLE_ADJ 补丁。

    只含 actionable 的分组；非 actionable 的阶段**不出现在返回值里**（保持原值不动）。
    本函数只生成字典，绝不写文件 —— 采纳与否由人决定。
    """
    patch: dict[str, int] = {}
    for s in suggestions(min_samples=strong_samples, strong_samples=strong_samples):
        if not s["actionable"]:
            continue
        for c in s["cycles"]:
            cur = None
            try:
                from modules import decision as _dec
                cur = _dec.CYCLE_ADJ.get(c)
            except Exception:  # noqa: BLE001
                cur = None
            if isinstance(cur, (int, float)):
                patch[c] = int(cur) + s["sug_delta"]
    return patch


def verdict(strong_samples: int = DEFAULT_STRONG_SAMPLES) -> dict:
    """一句话总览：现在能不能校准、还差多少样本。"""
    s = _track.summary()
    n_call = s["n_call"]
    ready = n_call >= strong_samples
    return {
        "ready": ready,
        "n_call": n_call,
        "n": s["n"],
        "strong_samples": strong_samples,
        "gap": max(0, strong_samples - n_call),
        "msg": ("样本已足够，可据下方建议人工校准刻度" if ready
                else f"样本积累中：已表态 {n_call} 条，还需 {max(0, strong_samples - n_call)} 条才能给出可信校准"),
    }
