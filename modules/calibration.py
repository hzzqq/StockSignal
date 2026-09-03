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


def apply_patch(strong_samples: int = DEFAULT_STRONG_SAMPLES,
                dry_run: bool = True, max_abs: int = 15) -> dict:
    """把「值得采纳」的分组建议落到 decision.CYCLE_ADJ（带护栏，闭合校准环路）。

    设计权衡（务必先读上面的「核心设计决策」）：
        本模块原本 T1「只出建议不自动改规则」，是为了防止早期小样本过拟合把规则改坏。
        但「只展示不闭环」导致 as_patch() 算出的补丁永远靠人肉 copy 进 decision.py，
        容易漏改、容易与 tests/test_decision.py 期望值漂移 —— 闭环最后一步没接通。
        本函数补上**带护栏的程序化落地**，仍守住 T1 的灵魂：
          · 必须 verdict.ready（单组样本够 + 调节量超噪音）才允许写，否则拒绝；
          · dry_run=True（默认）只回显将要改什么，**绝不写文件**；
          · 改后值 clamp 到 [-max_abs, max_abs]，防离谱；
          · 写前备份 decision.py.bak，写后追加审计日志 calibration_apply.log。
        人仍在回路：真正落地需显式 dry_run=False（由 scripts/apply_calibration.py 触发）。

    :return: {"applied": bool, "changed": {...}|None, "patch": {...}, "reason": str}
    """
    v = verdict(strong_samples=strong_samples)
    if not v["ready"]:
        return {"applied": False, "reason": v["msg"], "patch": {}, "changed": None}
    patch = as_patch(strong_samples=strong_samples)
    if not patch:
        return {"applied": False, "reason": "无值得采纳的建议", "patch": {}, "changed": None}
    if dry_run:
        return {"applied": False, "dry_run": True, "patch": patch,
                "reason": "dry-run，未写入；加 --apply 才真正落地", "changed": None}

    # 真正写：只替换 CYCLE_ADJ 字面量中各键的值，保留其余文件与注释（不 ast.unparse 整文件）
    try:
        import re
        import shutil
        from datetime import datetime as _dt
        from modules import decision as _dec
        from pathlib import Path

        src_path = Path(_dec.__file__)
        src = src_path.read_text(encoding="utf-8")
        start = src.index("CYCLE_ADJ = {")
        i = src.index("{", start)
        depth = 0
        j = i
        while j < len(src):
            if src[j] == "{":
                depth += 1
            elif src[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        block = src[i:j + 1]
        changed: dict[str, int] = {}
        new_block = block
        for key, val in patch.items():
            nv = max(-max_abs, min(max_abs, int(val)))
            pat = re.compile(r'("' + re.escape(key) + r'"\s*:\s*-?\d+)')
            m = pat.search(new_block)
            if m:
                new_block = pat.sub(f'"{key}": {nv}', new_block, count=1)
                changed[key] = nv
        if not changed:
            return {"applied": False, "reason": "无匹配键可改", "patch": patch, "changed": None}
        # 备份 + 写回
        shutil.copy(src_path, src_path.with_suffix(src_path.suffix + ".bak"))
        src_path.write_text(src[:i] + new_block + src[j + 1:], encoding="utf-8")
        log_path = Path(DATA_DIR) / "calibration_apply.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{_dt.now().isoformat(timespec='seconds')}] apply CYCLE_ADJ {changed}\n")
        logger.info("[calibration] 已落地 CYCLE_ADJ 补丁: %s", changed)
        return {"applied": True, "changed": changed, "patch": patch, "reason": "已写入"}
    except Exception as e:  # noqa: BLE001
        logger.warning("[calibration] apply_patch 写回失败: %s", e)
        return {"applied": False, "reason": f"写回失败: {e}", "patch": patch, "changed": None}


def verdict(strong_samples: int = DEFAULT_STRONG_SAMPLES) -> dict:
    """一句话总览：现在能不能校准、还差多少样本。

    「ready」的语义 = **至少有一个战术分组达到可采纳阈值**（样本够 + 调节量超噪音），
    而不是「全局样本数 >= strong_samples」。原因：真实样本会平摊到 4 个分组，
    全局到 20 时往往没有任何单组到 20，此时 as_patch() 返回空——若 verdict 仍报
    「可校准」，会和页面下方「各分组表态样本均不足」自相矛盾。所以 ready 必须对齐
    as_patch 的实际产出（见 test_verdict_spread_not_ready）。
    """
    s = _track.summary()
    n_call = s["n_call"]
    any_actionable = any(x["actionable"] for x in suggestions(strong_samples=strong_samples))
    ready = any_actionable
    if ready:
        msg = "样本已足够，可据下方建议人工校准刻度"
    elif n_call >= strong_samples:
        msg = (f"总量已够（{n_call} 条）但各周期样本分散，尚无单组达到可采纳阈值"
               f"（单组需 ≥{strong_samples} 条），继续积累")
    else:
        gap = max(0, strong_samples - n_call)
        msg = f"样本积累中：已表态 {n_call} 条，还需 {gap} 条才能开始校准（单组需 ≥{strong_samples} 条）"

    # 样本新鲜度：若打分自动化挂了，命中率会停在旧日期——必须如实暴露，
    # 否则页面显示「闭环在转」是假的。
    from datetime import date as _d
    last_scored = _track.last_scored_date()
    stale_days = None
    if last_scored:
        try:
            stale_days = (_d.today() - _d.fromisoformat(str(last_scored)[:10])).days
        except Exception:  # noqa: BLE001
            stale_days = None
    return {
        "ready": ready,
        "any_actionable": any_actionable,
        "n_call": n_call,
        "n": s["n"],
        "strong_samples": strong_samples,
        "gap": max(0, strong_samples - n_call),
        "last_scored_date": last_scored,
        "stale_days": stale_days,
        "msg": msg,
    }
