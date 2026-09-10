"""scripts/calibrate_sentiment_edge.py

情绪预测力「生产校准件」生成器 —— 把经样本外验证的边际固化成可加载的阈值表。

为什么要这个文件
----------------
``scripts/analyze_sentiment_predictive_power.py`` 证明了：
  · 引擎现有方向输出在 1547 天上**全部是噪音**（偏多 z=+0.61、偏空 z=+1.67、5 日 z≈0）；
  · 0-100「次日情绪评分」与次日收益的 IC = **-0.031**（负相关），十分位单调性 IC≈0.02；
  · 20 次样本外尾部检验 + Bonferroni 校正（α=0.0025）后，**只有 2 个活下来**：
        limit_down_ratio   前10% → 次日上涨 76.4%（基准 49.3%）z=+4.02
        touch_down_ratio   前10% → 次日上涨 76.9%（基准 49.3%）z=+3.45
    经济含义明确且可解释：**极端恐慌出清 → 次日反弹（V 反）**。

所以本脚本**只固化这一个经得起检验的边际**，且用 **walk-forward（扩张窗口）** 估计：
第 i 天的阈值只用 [warmup, i) 的历史算，绝不使用未来信息。产出的阈值表供
``modules/sentiment_edge.py`` 在生产中加载，用于「要么给出有统计依据的极值信号，
要么明确弃权」。

产出
----
``data/sentiment_edge_calibration.json``

用法
----
    python scripts/calibrate_sentiment_edge.py
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

HIST = os.path.join(ROOT, "data", "shepherd_history.csv")
OUT = os.path.join(ROOT, "data", "sentiment_edge_calibration.json")
# 同步落一份到 reports/：data/ 被 .gitignore 忽略，只写那里会导致换机器后
# 情绪极值层「静默失效」（模块会优雅降级，但页面连一句提示都没有）。
MIRROR = os.path.join(ROOT, "reports", "sentiment_edge_calibration.json")

# 仅保留**尺度无关**的特征：家数类指标在本历史里是逐年长大的采样（2009 年 26 只 →
# 2025 年 1669 只），绝对家数阈值与量纲不匹配（"跌停>100家" 4094 天只触发 7 次）。
FEATURES = [
    dict(key="limit_down_ratio", name="跌停占比", how="limit_down / 当日有效样本数 × 100",
         sign="high", expected="up",
         why="跌停占比冲到历史前 10% = 恐慌彻底出清，次日易有抄底盘做 V 反"),
    dict(key="touch_down_ratio", name="触及跌停占比", how="touch_down / 当日有效样本数 × 100",
         sign="high", expected="up",
         why="盘中触及跌停的家数占比极高 = 抛压当日释放最充分，次日修复概率显著抬升"),
]

WARMUP = 500          # 至少积累 500 天历史才允许触发
Q = 0.90              # 极值分位
MIN_TRIG = 20         # 触发样本下限，不足则不对外发布该信号


def _z(hits: int, n: int, p0: float) -> float:
    if n <= 0:
        return 0.0
    se = (p0 * (1 - p0) / n) ** 0.5
    return 0.0 if se == 0 else round((hits / n - p0) / se, 2)


def _p2(z: float) -> float:
    return round(2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2)))), 4)


def main():
    df = pd.read_csv(HIST)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    sample = df[["up_count", "down_count", "flat_count"]].sum(axis=1)
    df["sample"] = sample
    df = df[df["sample"] >= 1000].reset_index(drop=True).copy()

    df["limit_down_ratio"] = df["limit_down"] / df["sample"] * 100
    df["touch_down_ratio"] = df["touch_down"] / df["sample"] * 100
    df["y1"] = df["median_chg"].shift(-1)

    base = float((df["y1"] > 0).mean())
    out: dict = dict(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        source=os.path.relpath(HIST, ROOT),
        method="walk-forward / expanding window（第 i 天阈值只用 [warmup, i) 计算，无未来信息）",
        warmup=WARMUP, quantile=Q, min_trigger_samples=MIN_TRIG,
        base_next_day_up_rate=round(base, 4),
        date_range=[str(df["date"].iloc[0].date()), str(df["date"].iloc[-1].date())],
        universe_note=("本历史为逐年长大的采样（2009 年仅 26 只 → 2025 年 1669 只），"
                       "故校准只使用尺度无关的占比类特征；绝对家数阈值不可用。"),
        features={},
    )

    for f in FEATURES:
        col = f["key"]
        hist = df[col].to_numpy(dtype=float)
        trig_idx = []
        for i in range(WARMUP, len(df)):
            past = hist[:i]
            past = past[~pd.isna(past)]
            if len(past) < 100:
                continue
            thr = float(pd.Series(past).quantile(Q))
            v = hist[i]
            if pd.isna(v):
                continue
            if (f["sign"] == "high" and v >= thr):
                trig_idx.append(i)
        # 触发日的次日结果
        ys = [df.at[i, "y1"] for i in trig_idx if not pd.isna(df.at[i, "y1"])]
        n = len(ys)
        ups = sum(1 for y in ys if y > 0)
        zz = _z(ups, n, base)
        # 逐年稳定性
        by_year = {}
        for i in trig_idx:
            y = df.at[i, "y1"]
            if pd.isna(y):
                continue
            yr = str(df.at[i, "date"].year)
            b = by_year.setdefault(yr, dict(n=0, up=0, mean=0.0))
            b["n"] += 1
            b["up"] += 1 if y > 0 else 0
            b["mean"] += float(y)
        for yr, b in by_year.items():
            b["up_rate"] = round(b["up"] / b["n"], 4)
            b["mean"] = round(b["mean"] / b["n"], 4)

        prod_thr = float(df[col].quantile(Q))
        entry = dict(
            key=col, name=f["name"], how=f["how"], sign=f["sign"],
            expected_direction=f["expected"], why=f["why"],
            production_threshold=round(prod_thr, 4),
            threshold_basis=f"全样本 P{int(Q*100)}（{out['date_range'][0]}~{out['date_range'][1]}）",
            walk_forward=dict(
                trigger_days=n, up_days=ups,
                up_rate=round(ups / n, 4) if n else None,
                base_rate=round(base, 4),
                mean_next_day=round(sum(ys) / n, 4) if n else None,
                z=zz, p=_p2(zz),
                significant=bool(abs(zz) >= 1.96),
            ),
            by_year=by_year,
            publishable=bool(n >= MIN_TRIG and abs(zz) >= 1.96),
        )
        out["features"][col] = entry
        print(f"[{col}] walk-forward 触发 {n} 天，次日上涨 {ups}（{ups/n:.1%} vs 基准 {base:.1%}）"
              f" z={zz} → {'可发布' if entry['publishable'] else '不发布（样本/显著性不足）'}")

    # 波动（强度）可预测性：IC 弱但稳定为正，仅作为「风险提示」而非方向信号
    df["y1_abs"] = df["y1"].abs()
    strength = {}
    for col in ("touch_down_ratio", "hb_wave_ratio"):
        if col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        t = pd.to_numeric(df["y1_abs"], errors="coerce")
        m = s.notna() & t.notna()
        if m.sum() > 200:
            strength[col] = round(float(s[m].corr(t[m], method="spearman")), 4)
    out["strength_ic"] = strength
    out["strength_note"] = ("次日波动幅度与当日占比类指标秩相关 IC≈0.13~0.16（弱正），"
                            "可用于『次日波动偏大』的风险提示；但**方向不可预测**。")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"\n[产出] {os.path.relpath(OUT, ROOT)}")
    os.makedirs(os.path.dirname(MIRROR), exist_ok=True)
    with open(MIRROR, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"[同步] {os.path.relpath(MIRROR, ROOT)}（随仓库发布，防换机器静默失效）")
    print(f"基准次日上涨率 {base:.2%}；仅发布 walk-forward 显著的特征。")


if __name__ == "__main__":
    main()
