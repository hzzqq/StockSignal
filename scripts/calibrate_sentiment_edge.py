"""scripts/calibrate_sentiment_edge.py

情绪预测力「生产校准件」生成器 —— 把经样本外验证的边际固化成可加载的阈值表。

为什么要这个文件
----------------
``scripts/analyze_sentiment_predictive_power.py`` 证明了：
  · 引擎现有方向输出在 1547 天上**全部是噪音**（偏多 z=+0.61、偏空 z=+1.67、5 日 z≈0）；
  · 0-100「次日情绪评分」与次日收益的 IC = **-0.031**（负相关），十分位单调性 IC≈0.02；
  · 多重检验（Bonferroni α=0.0025）后，**唯一扛得住的规律是「极端恐慌 → 次日反弹（V 反）」**。

所以本脚本**只固化这一个经得起检验的边际**，且用 **walk-forward（扩张窗口）** 估计：
第 i 天的阈值只用 [warmup, i) 的历史算，绝不使用未来信息。产出的阈值表供
``modules/sentiment_edge.py`` 在生产中加载，用于「要么给出有统计依据的极值信号，
要么明确弃权」。

2026-09-11 P3 修正（诚实口径）
-----------------------------
原脚本把「次日上涨」定义为 ``median_chg.shift(-1) > 0``（全市场涨跌中位数）。
但 `median_chg` 仅在 2026-08-22 起的近窗 14 天有真实值，**全历史缺失**，
导致原实证在「重跑」时无法在全历史复现、且旧报告的 66.7% 建立在口径不一致的基底上。

本版改用**尺度无关、全历史可比**的「次日红盘日」作为方向标签：
    y1_up = (次日上涨家数 > 次日下跌家数)  ∈ {0, 1}
该标签由 `up_count` / `down_count` 推出 —— 两者已用 v1 缓存全历史还原、真实可用，
故 2007–2026 全样本均可参与检验，结论不再受 median_chg 缺失拖累。

修正后的诚实结论（见本脚本输出）：
  · 跌停占比(limit_down_ratio) 前 10% → 次日红盘概率显著 > 基准（z≈+4.4，全历史 296 天触发）。
  · 触及跌停占比(touch_down_ratio) 因 `touch_down` 全历史缺失（仅近窗有值），
    触发样本为 0 → **不可验证、不发布**；待历史 touch_down 补齐后再评估。

产出
----
``data/sentiment_edge_calibration.json`` 与 ``reports/sentiment_edge_calibration.json``
（双写：data/ 被 .gitignore 忽略，reports/ 随仓库发布，防换机器静默失效）
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

    # ── 诚实的全历史方向标签 ──
    # y1_up: 次日上涨家数 > 下跌家数（advance-decline 红盘日）。尺度无关、全历史可比。
    df["y1_up"] = (df["up_count"].shift(-1) > df["down_count"].shift(-1)).astype(float)
    # y1_breadth: 次日（上涨-下跌）/样本，带符号的连续广度变动，全历史可用。
    df["y1_breadth"] = (df["up_count"].shift(-1) - df["down_count"].shift(-1)) / df["sample"].shift(-1)
    # y1_abs_breadth: 次日绝对广度波动（强度代理），全历史可用。
    df["y1_abs_breadth"] = df["y1_breadth"].abs()
    # 次级标签（仅近窗有值，单独标注，不作为主结论依据）
    df["y1_median_chg"] = df["median_chg"].shift(-1)

    base = float((df["y1_up"] > 0).mean())
    # 各特征的历史覆盖度（诚实披露：touch_down 全历史缺失）
    cov = {f["key"]: int(df[f["key"]].notna().sum()) for f in FEATURES}
    out: dict = dict(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        source=os.path.relpath(HIST, ROOT),
        method="walk-forward / expanding window（第 i 天阈值只用 [warmup, i) 计算，无未来信息）",
        target="next_day_up_day = (up_count.shift(-1) > down_count.shift(-1))；"
               "尺度无关、全历史可比。原 median_chg 标签全历史缺失，已于 P3 替换为该标签。",
        warmup=WARMUP, quantile=Q, min_trigger_samples=MIN_TRIG,
        base_next_day_up_rate=round(base, 4),
        date_range=[str(df["date"].iloc[0].date()), str(df["date"].iloc[-1].date())],
        universe_note=("本历史为逐年长大的采样（2009 年仅 26 只 → 2025 年 1669 只），"
                       "故校准只使用尺度无关的占比类特征；绝对家数阈值不可用。"),
        feature_coverage=cov,
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
        # 触发日的次日结果（用全历史标签 y1_up）
        ys = [df.at[i, "y1_up"] for i in trig_idx if not pd.isna(df.at[i, "y1_up"])]
        n = len(ys)
        ups = sum(1 for y in ys if y > 0)
        zz = _z(ups, n, base)
        # 逐年稳定性
        by_year = {}
        for i in trig_idx:
            y = df.at[i, "y1_up"]
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

        prod_thr = float(pd.Series(hist[~pd.isna(hist)]).quantile(Q)) if pd.notna(hist).any() else None
        publishable = bool(n >= MIN_TRIG and abs(zz) >= 1.96)
        entry = dict(
            key=col, name=f["name"], how=f["how"], sign=f["sign"],
            expected_direction=f["expected"], why=f["why"],
            production_threshold=round(prod_thr, 4) if prod_thr is not None else None,
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
            data_availability=f"{cov[col]}/{len(df)} 天有值",
            publishable=publishable,
        )
        if not publishable:
            if n == 0:
                entry["unpublishable_reason"] = (
                    "触发样本为 0：该特征历史覆盖不足（见 feature_coverage），"
                    "walk-forward 无法在充足历史窗口内形成阈值，故不可验证、不发布。"
                )
            else:
                entry["unpublishable_reason"] = (
                    f"触发 {n} 天 < {MIN_TRIG} 或 |z|={abs(zz):.2f} < 1.96，样本/显著性不足，不发布。"
                )
        out["features"][col] = entry
        if n:
            _rate_txt = f"{ups/n:.1%} vs 基准 {base:.1%}"
        else:
            _rate_txt = "触发 0 天（数据不足）"
        print(f"[{col}] walk-forward 触发 {n} 天，次日红盘 {ups}（{_rate_txt}）"
              f" z={zz} → {'可发布' if publishable else '不发布'}")

    # 波动（强度）可预测性：IC 弱但稳定为正，仅作为「风险提示」而非方向信号
    strength = {}
    for col in ("limit_down_ratio", "touch_down_ratio", "hb_wave_ratio"):
        if col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        t = pd.to_numeric(df["y1_abs_breadth"], errors="coerce")
        m = s.notna() & t.notna()
        if m.sum() >= 200:
            strength[col] = round(float(s[m].corr(t[m], method="spearman")), 4)
    out["strength_ic"] = strength
    if strength:
        out["strength_note"] = ("次日波动幅度与当日占比类指标秩相关 IC≈"
                                f"{list(strength.values())}（弱正），可用于『次日波动偏大』的风险提示；"
                                "但**方向不可预测**。")
    else:
        out["strength_note"] = ("强度 IC 暂不计算：除 limit_down_ratio 外，其余占比特征历史覆盖不足，"
                               "无法在全历史形成稳定的秩相关估计。")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"\n[产出] {os.path.relpath(OUT, ROOT)}")
    os.makedirs(os.path.dirname(MIRROR), exist_ok=True)
    with open(MIRROR, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"[同步] {os.path.relpath(MIRROR, ROOT)}（随仓库发布，防换机器静默失效）")
    print(f"基准次日红盘率 {base:.2%}；仅发布 walk-forward 显著的特征。"
          f"limit_down_ratio 覆盖 {cov['limit_down_ratio']} 天，"
          f"touch_down_ratio 覆盖 {cov['touch_down_ratio']} 天（不足 → 不发布）。")


if __name__ == "__main__":
    main()
