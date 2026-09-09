# -*- coding: utf-8 -*-
"""
scripts/backtest_decision_closure.py — 决策闭环 × 真实广度历史 大样本回测

目的（服务论文「决策闭环 + 刻度校准」主线）：
    第 3 章已用真实 4094 天 A 股全市场广度历史证实了「数据基础」。本脚本把
    生产级决策链路（locate_cycle 六阶段定位 + derive_position 仓位推导）原样跑在
    这 4094 天真实数据上，验证两个核心命题：
      (1) 情绪六阶段模型对「次日市场方向」是否具备客观预测对应（不含前视泄漏）；
      (2) 全链路给出的「方向 + 仓位」建议，次日命中率几何、分周期是否分化。

输入：data/shepherd_history.csv（真实广度历史，4094 行，gitignore，已双备份）。只读。
输出：reports/backtest_decision_closure.json（可复现、论文可直接引用）+ 控制台摘要。

⚠️ 诚实披露（论文必须如实写）：
    · 生产 temp（市场温度）来自联网缓存，离线历史里没有 → 用同日 red_ratio 作代理
      （红盘率本身即 0-100 的广度温度，语义吻合 derive_position 的 0-100 入参）。
    · 生产 bias（偏多/偏空/中性）由情绪评分模块给出，离线历史里没有 → 用
      同日广度推导（red_ratio 阈值 + median_chg 符号），无前视泄漏。
    · overall_promo（连板晋级率）离线历史未存 → 设 None（derive_position 不调节）。
    · 次日「真实方向」用下一交易日 median_chg 符号作代理（广度口径的市场涨跌）。
    以上均为离线可复现的代理口径，与线上实时盘不同源，结论用于验证「闭环逻辑
    在真实数据上的统计行为」，而非宣称实盘收益。
"""
from __future__ import annotations

import json
import logging
import math
import os
import sys
from collections import defaultdict

# 让脚本独立于调用方式可导入 modules（兼容 `python scripts/xxx.py` 与 `PYTHONPATH=` 两种入口）
_HERE0 = os.path.dirname(os.path.abspath(__file__))
_ROOT0 = os.path.dirname(_HERE0)
if _ROOT0 not in sys.path:
    sys.path.insert(0, _ROOT0)

import pandas as pd

from modules.shepherd_forecast import locate_cycle
from modules.decision import derive_position
from modules import decision_track as _track

logger = logging.getLogger(__name__)

# 路径（与 shepher_reconstruct / decision_track 同一套 SS_DATA_DIR 隔离机制）
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
DATA_DIR = os.environ.get("SS_DATA_DIR", os.path.join(_ROOT, "data"))
_BREADTH_FILE = os.path.join(DATA_DIR, "shepherd_history.csv")
OUT_PATH = os.environ.get(
    "BACKTEST_OUT",
    os.path.join(_ROOT, "reports", "backtest_decision_closure.json"),
)

# ── 六阶段模型「自身界定的方向意图」（取自 CYCLES[i]["bias"] 描述，零前视） ──
# 冰点:次日报复性修复概率高 → 偏多；修复试探:震荡分化 → 中性(含糊)；
# 修复确认:次日偏强 → 偏多；主升高潮:次日多延续 → 偏多；
# 高潮分化:次日分歧加大、降仓 → 偏空；退潮:次日偏弱 → 偏空。
STAGE_DIR = {
    "冰点": "偏多",
    "修复试探": "中性",
    "修复确认": "偏多",
    "主升高潮": "偏多",
    "高潮分化": "偏空",
    "退潮": "偏空",
}

# 四大战术分组（与 decision_track.CYCLE_GROUPS 完全一致，避免口径漂移）
CYCLE_GROUPS = {
    "主升高潮": "进攻期",
    "修复确认": "进攻期",
    "高潮分化": "分化期",
    "修复试探": "修复期",
    "冰点": "修复期",
    "退潮": "防守期",
}
GROUP_ORDER = ["进攻期", "分化期", "修复期", "防守期"]

# 刻度校准公式（与 modules/calibration.py 完全一致，仅作用对象换成回测分组统计）
GAIN = 2.0
MAX_DELTA = 5
NOISE_DELTA = 2
STRONG_SAMPLES = 20


def _num(v):
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _proxy_bias(red, mchg) -> str:
    """同日广度推导 bias（无前视）：红盘率高且中位数上涨 → 偏多；反之偏空；含糊则中性。"""
    if red is None:
        return "中性"
    up = mchg is not None and mchg > 0
    down = mchg is not None and mchg < 0
    if red >= 55 and up:
        return "偏多"
    if red <= 45 and down:
        return "偏空"
    return "中性"


def _suggest_delta(avg_realized: float | None) -> int:
    """与 calibration._suggest_delta 完全相同的公式。"""
    if avg_realized is None:
        return 0
    raw = GAIN * float(avg_realized)
    return int(max(-MAX_DELTA, min(MAX_DELTA, round(raw))))


def run(breadth_file: str | None = None) -> dict:
    path = breadth_file or _BREADTH_FILE
    df = pd.read_csv(path, encoding="utf-8-sig")
    df = df.sort_values("date").reset_index(drop=True)

    # 阶段隐含方向命中（实验 1）：仅统计阶段本身给出明确方向（偏多/偏空）的日子
    stage_dir = defaultdict(lambda: {"call": 0, "hit": 0, "n": 0,
                                     "next_up": 0, "sum_next": 0.0, "sum_sq_next": 0.0})
    # 全链路方向命中（实验 2）：temp/bias 代理 → derive_position → 方向
    full_dir = defaultdict(lambda: {"call": 0, "hit": 0, "n": 0,
                                    "sum_pct": 0.0, "sum_next": 0.0, "sum_sq_next": 0.0})
    # 分组聚合（用于刻度校准演示）
    group_stat = defaultdict(lambda: {"n": 0, "call": 0, "hit": 0,
                                      "sum_pct": 0.0, "sum_next": 0.0, "sum_sq_next": 0.0})

    total = 0
    total_call = 0
    total_hit = 0

    rows = df.to_dict("records")
    for i in range(len(rows) - 1):
        today = rows[i]
        prev = rows[i - 1] if i > 0 else None
        nxt = rows[i + 1]

        red = _num(today.get("red_ratio"))
        mchg = _num(today.get("median_chg"))
        next_mchg = _num(nxt.get("median_chg"))
        if next_mchg is None:
            continue  # 次日无涨跌数据（末尾/缺口），跳过
        actual_dir = 1 if next_mchg > 0 else -1

        cyc = locate_cycle(today, prev)
        cname = cyc.get("name") or ""
        group = CYCLE_GROUPS.get(cname, "其他")

        # ── 实验 1：阶段隐含方向 ──
        sd = STAGE_DIR.get(cname)
        if sd in ("偏多", "偏空"):
            stage_dir[cname]["n"] += 1
            stage_dir[cname]["call"] += 1
            if (1 if sd == "偏多" else -1) == actual_dir:
                stage_dir[cname]["hit"] += 1
        stage_dir[cname]["next_up"] += 1 if actual_dir == 1 else 0
        stage_dir[cname]["sum_next"] += next_mchg
        stage_dir[cname]["sum_sq_next"] += next_mchg * next_mchg

        # ── 实验 2：全链路 ──
        temp = red if red is not None else 50.0
        bias = _proxy_bias(red, mchg)
        pos = derive_position(temp, bias=bias, cycle_name=cname)
        pct = pos.get("pct")
        pred_dir = 1 if pct and pct > 50 else -1

        full_dir[cname]["n"] += 1
        full_dir[cname]["sum_pct"] += pct if pct is not None else 50.0
        full_dir[cname]["sum_next"] += next_mchg
        full_dir[cname]["sum_sq_next"] += next_mchg * next_mchg
        if bias in ("偏多", "偏空"):
            full_dir[cname]["call"] += 1
            if pred_dir == actual_dir:
                full_dir[cname]["hit"] += 1

        # 分组（刻度校准演示口径：与 decision_track.by_group 一致，中性不计入 call）
        g = group_stat[group]
        g["n"] += 1
        g["sum_pct"] += pct if pct is not None else 50.0
        g["sum_next"] += next_mchg
        g["sum_sq_next"] += next_mchg * next_mchg
        if bias in ("偏多", "偏空"):
            g["call"] += 1
            if pred_dir == actual_dir:
                g["hit"] += 1

        total += 1
        if bias in ("偏多", "偏空"):
            total_call += 1
            if pred_dir == actual_dir:
                total_hit += 1

    # ── 汇总 ──
    def _rate(d):
        return round(d["hit"] / d["call"] * 100, 1) if d["call"] else None

    def _std(d):
        """次日 median_chg 的样本标准差（衡量该周期/分组的尾部波动风险）。"""
        n = d["n"]
        if n < 2:
            return None
        mean = d["sum_next"] / n
        var = d["sum_sq_next"] / n - mean * mean
        return round(math.sqrt(max(var, 0.0)), 3)

    stage_rows = []
    for cname in STAGE_DIR:  # 固定顺序
        d = stage_dir[cname]
        if d["n"] == 0:
            continue
        stage_rows.append({
            "cycle": cname,
            "n": d["n"],
            "call": d["call"],
            "hit": d["hit"],
            "dir_accuracy": _rate(d),
            "next_up_ratio": round(d["next_up"] / d["n"] * 100, 1),
            "avg_next_median_chg": round(d["sum_next"] / d["n"], 3),
            "std_next_median_chg": _std(d),
        })

    full_rows = []
    for cname in ["冰点", "修复试探", "修复确认", "主升高潮", "高潮分化", "退潮"]:
        d = full_dir[cname]
        if d["n"] == 0:
            continue
        full_rows.append({
            "cycle": cname,
            "n": d["n"],
            "call": d["call"],
            "hit": d["hit"],
            "dir_accuracy": _rate(d),
            "avg_pct": round(d["sum_pct"] / d["n"], 1),
            "avg_next_median_chg": round(d["sum_next"] / d["n"], 3),
            "std_next_median_chg": _std(d),
        })

    group_rows = []
    for g in GROUP_ORDER:
        d = group_stat[g]
        if d["n"] == 0:
            continue
        avg_pct = round(d["sum_pct"] / d["n"], 1)
        avg_realized = round(d["sum_next"] / d["n"], 3)
        delta = _suggest_delta(avg_realized)
        group_rows.append({
            "group": g,
            "n": d["n"],
            "call": d["call"],
            "hit": d["hit"],
            "dir_accuracy": _rate(d),
            "avg_pct": avg_pct,
            "avg_realized": avg_realized,
            "std_next_median_chg": _std(d),
            "suggest_delta": delta,
            "actionable": bool(d["call"] >= STRONG_SAMPLES and abs(delta) >= NOISE_DELTA),
        })

    result = {
        "meta": {
            "source": "data/shepherd_history.csv",
            "n_trading_days_scored": total,
            "note": ("离线代理回测：temp=red_ratio, bias=同日广度推导, overall_promo=None, "
                     "次日真实方向=下一交易日 median_chg 符号。非实盘收益，验证闭环逻辑在真实"
                     "数据上的统计行为。"),
            "calibration_formula": f"sug_delta=clamp(round({GAIN}*avg_realized), -{MAX_DELTA}, +{MAX_DELTA})",
            "strong_samples": STRONG_SAMPLES,
        },
        "overall": {
            "n": total,
            "call": total_call,
            "hit": total_hit,
            "dir_accuracy": round(total_hit / total_call * 100, 1) if total_call else None,
        },
        "by_stage_implied_direction": stage_rows,
        "by_stage_full_closure": full_rows,
        "by_group_calibration": group_rows,
    }
    return result


def main() -> dict:
    result = run()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    m = result["meta"]
    o = result["overall"]
    print(f"[backtest] 数据源={m['source']} 评分交易日={m['n_trading_days_scored']}")
    print(f"[backtest] 全链路方向命中率：{o['hit']}/{o['call']} = {o['dir_accuracy']}%")
    print("[backtest] 六阶段「隐含方向」次日表现：")
    for r in result["by_stage_implied_direction"]:
        print(f"    {r['cycle']:>5}  n={r['n']:>4}  次日上涨占比={r['next_up_ratio']:>5}%  "
              f"平均次日median_chg={r['avg_next_median_chg']:>7}  方向命中={r['dir_accuracy']}%")
    print("[backtest] 四大战术分组（刻度校准演示）：")
    for r in result["by_group_calibration"]:
        print(f"    {r['group']:>4}  call={r['call']:>4}  方向命中={r['dir_accuracy']}%  "
              f"平均建议仓位={r['avg_pct']}  次日平均实际={r['avg_realized']}  "
              f"建议调节={r['suggest_delta']:+}  可采纳={r['actionable']}")
    print(f"[backtest] 已写出 {OUT_PATH}")
    return result


if __name__ == "__main__":
    main()
