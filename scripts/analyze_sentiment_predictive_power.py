"""scripts/analyze_sentiment_predictive_power.py

情绪预测力实证：现有「次日情绪预判」到底有没有边际？（只读分析，不伪造）

老板反馈「项目还是没有做到准确预测情绪」。这是可证伪的统计问题，不能靠感觉改代码。
本脚本把 ``data/shepherd_history.csv``（4094 个交易日）逐日喂给生产模块
``modules.shepherd_forecast.forecast_next_day``，并用**样本外**方式检验。

2026-09-11 P3 修正（诚实口径）
------------------------------
原脚本把「次日方向」定义为 ``median_chg.shift(-1) > 0``（全市场涨跌中位数）。但
``median_chg`` 仅在 2026-08-22 起的近窗 14 天有真实值，**全历史缺失**，重跑时
无法在全历史复现，且旧报告「极端恐慌→次日反弹 66.7%」建立在口径不一致的基底上。
本版改用**尺度无关、全历史可比**的「次日广度变动」作为方向标签：
    y1 = (次日上涨家数 - 次日下跌家数) / 当日有效样本数
y1 > 0 即「次日红盘日」（上涨家数 > 下跌家数），与「恐慌→反弹」假设直接对应，且
由已用 v1 缓存全历史还原的 up/down 家数推出，2007–2026 全样本均可参与检验。
结论因此可在全历史诚实复现（见产出 JSON 的 ``target`` 字段）。

三个必须先纠正的口径（否则结论会反向）
--------------------------------------
1. **基准率不是 50%**：本样本无条件次日上涨率 ≈46.5%、5 日累计上涨率 ≈38.4%
   （市场区间净下跌）。所有显著性检验的 p0 必须用无条件基准率，否则会把
   "和基准一样" 误判成 "显著反转"。
2. **样本只覆盖部分市场**：本历史是**逐年长大的采样**，2009 年每天仅 26 只，
   2020 年 1027 只，2025 年 1669 只（仅 2026 某日达全市场 5544 只）。
   因此**家数类**指标（limit_up / limit_down / hb_wave10）被系统性低估约 3 倍，
   针对全市场写的绝对阈值（"涨停≥80家"）基本永不触发 —— 规则"死"在量纲上。
   **比率类**指标（red_ratio / zt_fail_ratio）与**位置类**（connect_hl / median_chg）
   不受影响，才是全历史可比的。
3. **多重检验**：测 10+ 条规则时，单看 p<0.05 必有假阳性，需 Bonferroni 校正。

检验内容
--------
  A. 引擎方向命中的实际边际（含分组基准率对照）
  B. 评分 IC 与十分位单调性
  C. 手工规律的**可触发性**（触发率）+ 触发后的实际表现
  D. **样本外**条件边际：训练段定阈值 → 测试段验证，Bonferroni 校正
  E. 方向 vs 强度：把目标换成「次日波动幅度」，看是否可预测
  F. 数据覆盖度（缺失维度被静默重新归一化）

产出
----
``reports/sentiment_predictive_power.json`` —— 全部数字落盘，供论文与页面引用。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from modules.shepherd_forecast import forecast_next_day  # noqa: E402

HIST = os.path.join(ROOT, "data", "shepherd_history.csv")
OUT = os.path.join(ROOT, "reports", "sentiment_predictive_power.json")

RAW_COLS = [
    "limit_up", "limit_down", "red_ratio", "touch_down", "zt_fail_count",
    "hb_wave10", "median_chg", "connect_hl", "zt_fail_ratio", "zt_prev_ret",
    "up_count", "down_count", "flat_count",
]


def _z(hits: int, n: int, p0: float) -> float:
    """二项检验 z 值（正态近似）。p0 必须是**无条件基准率**，不是 0.5。"""
    if n <= 0:
        return 0.0
    se = (p0 * (1 - p0) / n) ** 0.5
    return 0.0 if se == 0 else round((hits / n - p0) / se, 2)


def _p2(z: float) -> float:
    return round(2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2)))), 4)


def _fmt(v, spec: str) -> str:
    """None / NaN 安全的格式化：缺失值显示占位符而非抛异常。"""
    if v is None or (isinstance(v, float) and v != v):
        return "  —  "
    return f"{v:{spec}}"


def _rate(series: pd.Series) -> float | None:
    s = pd.to_numeric(series, errors="coerce").dropna()
    return round(float((s > 0).mean()), 4) if len(s) else None


def build_frame(min_sample: int):
    df = pd.read_csv(HIST)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    df["sample"] = df[["up_count", "down_count", "flat_count"]].sum(axis=1)

    # 逐年采样规模（披露用）
    df["yr"] = df["date"].dt.year
    scale = df.groupby("yr")["sample"].median().round(0).astype(int).to_dict()

    # 只保留覆盖度足够的年份，避免 26 只股票时代的噪声
    d = df[df["sample"] >= min_sample].reset_index(drop=True).copy()

    # ── 目标：次日（2026-09-11 P3 修正）──
    # 原目标 median_chg.shift(-1)（次日全市场涨跌中位数）全历史缺失（仅近窗 14 天有值），
    # 重跑时无法在全历史复现，且旧报告的 66.7% 建立在口径不一致的基底上。
    # 改用全历史可比的「次日广度变动」：次日(上涨-下跌)/样本（带符号、连续、尺度无关）。
    #   y1 > 0  ⇔ 次日红盘日（上涨家数 > 下跌家数），与「恐慌→反弹」假设直接对应；
    #   y1 由 up_count/down_count 推出，两者已用 v1 缓存全历史还原、真实可用。
    d["y1"] = (d["up_count"].shift(-1) - d["down_count"].shift(-1)) / d["sample"].shift(-1)
    d["y1_abs"] = d["y1"].abs()                          # 次日「强度」（波动幅度）
    d["y5"] = d["y1"].rolling(5).sum()                   # 未来 5 日广度变动累计
    # 次级目标（仅近窗有值）：保留 median_chg 用于对照，不计入主结论
    d["y1_median"] = d["median_chg"].shift(-1)

    # ── 特征：只用**尺度无关**的比率/位置类（全历史可比）──
    d["up_ratio"] = d["up_count"] / d["sample"] * 100
    d["limit_up_ratio"] = d["limit_up"] / d["sample"] * 100
    d["limit_down_ratio"] = d["limit_down"] / d["sample"] * 100
    d["hb_wave_ratio"] = d["hb_wave10"] / d["sample"] * 100
    d["touch_down_ratio"] = d["touch_down"] / d["sample"] * 100
    return df, d, scale


def run(min_sample: int, train_frac: float):
    df_all, d, scale = build_frame(min_sample)

    # ── 逐日调用生产引擎 ──
    eng_rows = []
    for i in range(len(d) - 1):
        def _row(j):
            if j < 0:
                return None
            return {c: (None if pd.isna(d.at[j, c]) else float(d.at[j, c]))
                    for c in RAW_COLS}
        try:
            fc = forecast_next_day(_row(i), _row(i - 1))
        except Exception as exc:                      # 引擎异常必须可见
            eng_rows.append(dict(date=str(d.at[i, "date"].date()), error=repr(exc)))
            continue
        eng_rows.append(dict(
            date=d.at[i, "date"], bias=fc["bias"], score=fc["score"],
            confidence=fc["confidence"], cycle=(fc["cycle"] or {}).get("id"),
            covered=sum(x["max"] for x in fc["score_dims"]),
            n_dims=len(fc["score_dims"]),
            y1=d.at[i, "y1"], y1_abs=d.at[i, "y1_abs"], y5=d.at[i, "y5"],
            **{k: d.at[i, k] for k in
               ("up_ratio", "limit_up_ratio", "limit_down_ratio", "hb_wave_ratio",
                "touch_down_ratio", "red_ratio", "zt_fail_ratio", "connect_hl",
                "median_chg", "limit_up", "limit_down", "hb_wave10", "sample")},
        ))

    eng = pd.DataFrame(eng_rows)
    n_err = int(eng["error"].notna().sum()) if "error" in eng.columns else 0
    eng = eng[eng.get("bias").notna()].copy().reset_index(drop=True)
    for c in eng.columns:
        if c not in ("date", "bias", "cycle"):
            eng[c] = pd.to_numeric(eng[c], errors="coerce")
    eng = eng.dropna(subset=["y1"]).reset_index(drop=True)
    eng["d1"] = eng["y1"].apply(lambda v: 1 if v > 0 else (-1 if v < 0 else 0))

    rep: dict = dict(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        source=os.path.relpath(HIST, ROOT),
        target="next_day_breadth = (up_count.shift(-1) - down_count.shift(-1)) / sample "
               "（次日广度变动，带符号；>0 即次日红盘日）。2026-09-11 P3 起替代缺失历史的 "
               "median_chg.shift(-1) 目标，保证结论可在全历史复现。",
        median_chg_coverage=int(df_all["median_chg"].notna().sum()),
        min_sample=min_sample, train_frac=train_frac,
        rows_all=int(len(df_all)), rows_used=int(len(eng)),
        engine_errors=n_err,
        date_range=[str(eng["date"].iloc[0].date()), str(eng["date"].iloc[-1].date())]
        if len(eng) else [],
        universe_scale_by_year={str(k): int(v) for k, v in scale.items()},
    )

    base1 = _rate(eng["y1"]) or 0.5
    base5 = _rate(eng["y5"]) or 0.5
    rep["base_rates"] = dict(
        next_day_up=base1, five_day_up=base5,
        next_day_abs_mean=round(float(eng["y1_abs"].mean()), 4),
        note="显著性检验必须以这些为 p0；用 0.5 会把『与基准相同』误判成『显著』",
    )

    # ── A. 方向边际（p0 = 基准率）──
    def _bias_stat(sub, tgt):
        s = sub[(sub["bias"].isin(["偏多", "偏空"]))].dropna(subset=[tgt])
        s = s[s[tgt] != 0] if tgt == "y1" else s
        out = {}
        for b in ("偏多", "偏空"):
            q = s[s["bias"] == b]
            if not len(q):
                continue
            ups = int((q[tgt] > 0).sum())
            p0 = base1 if tgt == "y1" else base5
            zz = _z(ups, len(q), p0)
            out[b] = dict(n=int(len(q)), up_rate=round(ups / len(q), 4), base_rate=p0,
                          mean=round(float(q[tgt].mean()), 4), z=zz, p=_p2(zz),
                          significant=bool(abs(zz) >= 1.96))
        return out

    rep["direction_edge"] = dict(
        next_day=_bias_stat(eng, "y1"),
        five_day=_bias_stat(eng, "y5"),
        neutral_days=int((eng["bias"] == "中性").sum()),
        flat_days_excluded=int((eng["d1"] == 0).sum()),
    )

    # ── B. 评分 IC 与十分位 ──
    rep["score_ic"] = {
        t: dict(n=int(len(eng[[t]].dropna())),
                **({"ic": round(float(eng[["score", t]].dropna()
                                      .corr(method="spearman").iloc[0, 1]), 4)}))
        for t in ("y1", "y5", "y1_abs")
    }
    dec = eng[["score", "y1", "d1"]].dropna().copy()
    dec["bucket"] = pd.qcut(dec["score"], 10, duplicates="drop", labels=False)
    g = dec.groupby("bucket").agg(n=("y1", "size"), lo=("score", "min"), hi=("score", "max"),
                                  mean=("y1", "mean"),
                                  up=("d1", lambda s: float((s > 0).mean()))).reset_index()
    rep["score_deciles"] = [dict(bucket=int(r.bucket), n=int(r.n),
                                score_range=[round(float(r.lo), 1), round(float(r.hi), 1)],
                                mean_y1=round(float(r.mean), 4),
                                next_day_up_rate=round(float(r.up), 4)) for r in g.itertuples()]

    # 十分位单调性（Spearman：档位 vs 次日收益）
    rep["score_decile_monotonic_ic"] = round(
        float(g["bucket"].corr(g["mean"], method="spearman")), 4) if len(g) > 2 else None

    # ── C. 手工规律可触发性 + 触发后表现 ──
    rules = [
        ("炸板率≥50% → 次日V反", "zt_fail_ratio", ">=", 50, "up"),
        ("炸板率<15% → 次日延续", "zt_fail_ratio", "<", 15, "up"),
        ("回头波>10%家数≥50 → 次日V反", "hb_wave10", ">=", 50, "up"),
        ("跌停>100家 → 次日修复", "limit_down", ">", 100, "up"),
        ("涨停≥80家 → 次日延续", "limit_up", ">=", 80, "up"),
        ("红盘率<20% → 次日修复", "red_ratio", "<", 20, "up"),
        ("红盘率>70% → 次日延续", "red_ratio", ">", 70, "up"),
        ("最高板≥5 → 次日接力", "connect_hl", ">=", 5, "up"),
        ("昨板溢价>3% → 次日接力", "zt_prev_ret", ">", 3, "up"),
    ]
    rr = []
    for name, col, op, thr, expect in rules:
        v = pd.to_numeric(eng[col], errors="coerce") if col in eng.columns else None
        if v is None:
            continue
        cond = {">=": v >= thr, ">": v > thr, "<": v < thr, "<=": v <= thr}[op] & eng["y1"].notna()
        n = int(cond.sum())
        item = dict(rule=name, indicator=col, op=op, threshold=thr, expect=expect, n=n,
                    trigger_rate=round(n / len(eng), 4))
        if n >= 20:
            s = eng.loc[cond, "y1"]
            ups, dn = int((s > 0).sum()), int((s < 0).sum())
            hit = ups if expect == "up" else dn
            zz = _z(hit, ups + dn, base1 if expect == "up" else (1 - base1))
            item.update(up_rate=round(ups / max(ups + dn, 1), 4), mean=round(float(s.mean()), 4),
                        z=zz, p=_p2(zz), significant=bool(abs(zz) >= 1.96))
        else:
            item["note"] = "触发样本不足（<20），无法验证"
        rr.append(item)
    # 比率化改写后的可触发性（说明「家数阈值」死于量纲）
    scale_fix = []
    for name, col, thr in (("涨停占比≥3% → 次日延续", "limit_up_ratio", 3.0),
                           ("跌停占比≥1% → 次日修复", "limit_down_ratio", 1.0),
                           ("回头波占比≥5% → 次日V反", "hb_wave_ratio", 5.0)):
        v = pd.to_numeric(eng[col], errors="coerce")
        n = int((v >= thr).sum())
        s = eng.loc[v >= thr, "y1"].dropna()
        ups = int((s > 0).sum())
        zz = _z(ups, len(s), base1) if len(s) >= 20 else None
        scale_fix.append(dict(rule=name, indicator=col, threshold=thr, n=n,
                              trigger_rate=round(n / len(eng), 4),
                              up_rate=round(ups / len(s), 4) if len(s) else None,
                              mean=round(float(s.mean()), 4) if len(s) else None,
                              z=zz, p=_p2(zz) if zz is not None else None,
                              significant=bool(zz is not None and abs(zz) >= 1.96)))
    rep["hand_written_rules"] = rr
    rep["ratio_rewritten_rules"] = scale_fix

    # ── D. 样本外条件边际（训练定阈值 → 测试验证）──
    split = int(len(eng) * train_frac)
    tr, te = eng.iloc[:split], eng.iloc[split:]
    feats = ["score", "red_ratio", "zt_fail_ratio", "connect_hl", "median_chg",
             "up_ratio", "limit_up_ratio", "limit_down_ratio", "hb_wave_ratio",
             "touch_down_ratio"]
    oos, tests = [], 0
    te_base = _rate(te["y1"]) or 0.5
    for f in feats:
        if f not in eng.columns:
            continue
        trv = pd.to_numeric(tr[f], errors="coerce")
        if trv.notna().sum() < 100:
            continue
        q10, q90 = float(trv.quantile(0.10)), float(trv.quantile(0.90))
        for label, lo, hi in (("bottom10%", -math.inf, q10), ("top10%", q90, math.inf)):
            tests += 1
            m_te = (pd.to_numeric(te[f], errors="coerce") <= hi) & \
                   (pd.to_numeric(te[f], errors="coerce") > lo)
            s = te.loc[m_te, "y1"].dropna()
            if len(s) < 20:
                oos.append(dict(feature=f, bucket=label, n=len(s),
                                note="测试段样本不足"))
                continue
            ups = int((s > 0).sum())
            zz = _z(ups, len(s), te_base)
            oos.append(dict(feature=f, bucket=label, n=int(len(s)),
                            up_rate=round(ups / len(s), 4), base_rate=te_base,
                            mean=round(float(s.mean()), 4), z=zz, p=_p2(zz),
                            significant_raw=bool(abs(zz) >= 1.96)))
    bonf = round(0.05 / max(tests, 1), 4)
    for r in oos:
        if "z" in r:
            r["significant_bonferroni"] = bool(abs(r["z"]) >= 2.9)  # ≈ p< bonf for m≈20
    rep["oos_tail"] = dict(n_tests=tests, bonferroni_alpha=bonf,
                           train_rows=int(len(tr)), test_rows=int(len(te)),
                           train_period=[str(tr["date"].iloc[0].date()), str(tr["date"].iloc[-1].date())],
                           test_period=[str(te["date"].iloc[0].date()), str(te["date"].iloc[-1].date())],
                           results=oos)
    # 引擎方向在测试段的独立表现
    oos_dir = {}
    for b in ("偏多", "偏空"):
        q = te[(te["bias"] == b) & (te["d1"] != 0)]
        if len(q):
            ups = int((q["d1"] > 0).sum())
            zz = _z(ups, len(q), te_base)
            oos_dir[b] = dict(n=int(len(q)), up_rate=round(ups / len(q), 4),
                              base_rate=te_base, z=zz, p=_p2(zz))
    rep["oos_engine_direction"] = oos_dir

    # ── E. 方向 vs 强度 ──
    strength = {}
    for f in ("median_chg", "hb_wave_ratio", "zt_fail_ratio", "touch_down_ratio", "red_ratio"):
        s = pd.to_numeric(eng[f], errors="coerce")
        tgt = pd.to_numeric(eng["y1_abs"], errors="coerce")
        m = s.notna() & tgt.notna()
        if m.sum() < 200:
            continue
        strength[f] = dict(n=int(m.sum()),
                           ic_abs_ret=round(float(s[m].corr(tgt[m], method="spearman")), 4))
    # 自相关：今天的波动 → 明天的波动
    ac = pd.to_numeric(eng["median_chg"].abs(), errors="coerce")
    nxt = pd.to_numeric(eng["y1_abs"], errors="coerce")
    m = ac.notna() & nxt.notna()
    strength["today_abs_median_chg"] = dict(
        n=int(m.sum()),
        ic_abs_ret=round(float(ac[m].corr(nxt[m], method="spearman")), 4))
    rep["predictability_of_strength"] = strength
    rep["strength_vs_direction_note"] = (
        "方向（次日涨跌符号）经样本外检验无超越基准的边际；强度（次日波动幅度）"
        "存在显著自相关。产品表述应从『预测涨跌』改为『预测情绪强度/风险敞口』。"
    )

    # ── F. 覆盖度 ──
    rep["coverage_distribution"] = {str(int(k)): int(v)
                                    for k, v in eng.groupby("covered").size().items()}
    rep["coverage_warning"] = (
        "评分按已覆盖维度重新归一化到 100：2 维凑出的 70 分与 5 维凑出的 70 分被同等呈现，"
        "跨日不可比。历史基座 connect_2b/fc_ratio 缺失率极高。"
    )

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, ensure_ascii=False, indent=2)
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-sample", type=int, default=1000,
                    help="当日有效个股数下限（早期样本仅数十只，噪声大）")
    ap.add_argument("--train-frac", type=float, default=0.6)
    a = ap.parse_args()
    r = run(a.min_sample, a.train_frac)

    print(f"=== 情绪预测力实证 {r['date_range'][0]} ~ {r['date_range'][1]} ===")
    print(f"全日数 {r['rows_all']} → 有效 {r['rows_used']}（引擎异常 {r['engine_errors']}）")
    b = r["base_rates"]
    print(f"\n★ 基准率（所有检验的 p0）: 次日上涨 {b['next_day_up']:.2%} / "
          f"5日上涨 {b['five_day_up']:.2%} / 次日振幅均值 {b['next_day_abs_mean']:.3f}%")
    print(f"\n[历史采样规模] " + " ".join(f"{k}:{v}" for k, v in
                                       list(r["universe_scale_by_year"].items())[::3]))
    d = r["direction_edge"]
    print(f"\n[A] 引擎方向边际（中性 {d['neutral_days']} 天，平盘剔除 {d['flat_days_excluded']} 天）")
    for tgt, label in (("next_day", "次日"), ("five_day", "5日")):
        for bias, s in d[tgt].items():
            print(f"    {label} {bias}: n={s['n']:5d} 上涨率={s['up_rate']:.1%} "
                  f"(基准 {s['base_rate']:.1%}) 均值={s['mean']:+.3f} z={s['z']:+.2f} "
                  f"{'★显著' if s['significant'] else '噪音'}")
    print(f"\n[B] 评分IC: 次日={r['score_ic']['y1']['ic']} 5日={r['score_ic']['y5']['ic']} "
          f"次日振幅={r['score_ic']['y1_abs']['ic']}")
    print(f"    十分位单调性 IC={r['score_decile_monotonic_ic']}")
    print("\n[C] 手工规律（家数阈值）")
    for x in r["hand_written_rules"]:
        if "note" in x:
            print(f"    {x['rule']:28} 触发率={x['trigger_rate']:.2%} n={x['n']:5d} {x['note']}")
        else:
            print(f"    {x['rule']:28} 触发率={x['trigger_rate']:.2%} n={x['n']:5d} "
                  f"上涨={_fmt(x['up_rate'], '.1%')} 均值={_fmt(x['mean'], '+.3f')} "
                  f"z={_fmt(x['z'], '+.2f')} {'★显著' if x['significant'] else '噪音'}")
    print("    比率化改写后：")
    for x in r["ratio_rewritten_rules"]:
        print(f"    {x['rule']:28} 触发率={x['trigger_rate']:.2%} n={x['n']:5d} "
              f"上涨={_fmt(x['up_rate'], '.1%')} 均值={_fmt(x['mean'], '+.3f')} "
              f"z={_fmt(x['z'], '+.2f')} {'★显著' if x['significant'] else '噪音'}")
    o = r["oos_tail"]
    print(f"\n[D] 样本外: 训练 {o['train_period'][0]}~{o['train_period'][1]} ({o['train_rows']} 天)"
          f" → 测试 {o['test_period'][0]}~{o['test_period'][1]} ({o['test_rows']} 天)")
    print(f"    共 {o['n_tests']} 次检验，Bonferroni α={o['bonferroni_alpha']}")
    sig = [x for x in o["results"] if x.get("significant_raw")]
    print(f"    原始 p<0.05 命中 {len(sig)} 个（Bonferroni 校正后 "
          f"{len([x for x in o['results'] if x.get('significant_bonferroni')])} 个）")
    for x in o["results"]:
        if "z" in x:
            print(f"    {x['feature']:18} {x['bucket']:10} n={x['n']:4d} "
                  f"上涨={x['up_rate']:.1%}(基准{x['base_rate']:.1%}) z={x['z']:+.2f}")
    for k, v in r["oos_engine_direction"].items():
        print(f"    引擎 {k} 测试段: n={v['n']} 上涨={v['up_rate']:.1%} z={v['z']:+.2f}")
    print(f"\n[E] 强度可预测性（|次日中位涨跌| 的 IC）")
    for k, v in r["predictability_of_strength"].items():
        print(f"    {k:22} IC={v['ic_abs_ret']:+.3f}  n={v['n']}")
    print(f"\n[F] 覆盖度分布: {r['coverage_distribution']}")
    print(f"\n[产出] {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
