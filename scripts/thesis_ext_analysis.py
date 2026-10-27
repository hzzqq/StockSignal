"""T-340 论文扩展三方向分析（A 马尔可夫 / B 涨停生态 / C 滚动校准）。

数据源：data/shepherd_history.csv（4811 个真实交易日，2007-01-05 ~ 至今）。
周期复算：复用 modules/shepherd_forecast.locate_cycle 纯函数（与生产同口径）。
诚实纪律：全部数字来自真实数据计算；窗口不足/样本不足如实标注，绝不编造。

产物（thesis/素材/论文扩展_分析产物/）：
    thesis_ext_A_markov.json       A 转移矩阵与统计
    thesis_ext_A_heatmap.png       A 转移概率热力图
    thesis_ext_B_limitup.json      B 涨停生态统计
    thesis_ext_C_walkforward.json  C 滚动校准逐年结果
    thesis_ext_C_walkforward.png   C 样本外进攻/防守建议仓位折线
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from modules.shepherd_forecast import CYCLES, locate_cycle  # noqa: E402

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

CSV = ROOT / "data" / "shepherd_history.csv"
OUT = ROOT / "thesis" / "素材" / "论文扩展_分析产物"
OUT.mkdir(parents=True, exist_ok=True)

ORDER = [c["id"] for c in CYCLES]                      # ice probe confirm main diverge retreat
CNAME = {c["id"]: c["name"] for c in CYCLES}
RING = list(zip(ORDER, ORDER[1:])) + [(ORDER[-1], ORDER[0])]   # 环状相邻对
# 四大战术分组（modules/decision_track.CYCLE_GROUPS 同口径）
G4MAP = {"ice": "修复", "probe": "修复", "confirm": "进攻",
         "main": "进攻", "diverge": "分化", "retreat": "防守"}
G4ORDER = ["修复", "进攻", "分化", "防守"]
GROUPS = {"主升高潮": "进攻期", "修复确认": "进攻期", "高潮分化": "分化期",
          "修复试探": "修复期", "冰点": "修复期", "退潮": "防守期"}
CYCLE_ADJ0 = {"主升高潮": 5, "修复确认": 3, "修复试探": 0,
              "高潮分化": -5, "退潮": -10, "冰点": 5}
GAIN, MAX_DELTA, NOISE_DELTA, MIN_SAMPLES = 2.0, 5, 2, 8   # calibration.py 同参


def suggest_delta(avg_realized: float | None) -> int:
    """复刻 modules/calibration._suggest_delta（有界 ±5、取整）。"""
    if avg_realized is None or not np.isfinite(avg_realized):
        return 0
    return int(max(-MAX_DELTA, min(MAX_DELTA, round(GAIN * float(avg_realized)))))


def load_data() -> tuple[pd.DataFrame, list[dict]]:
    df = pd.read_csv(CSV)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df, df.to_dict("records")


# ────────────────────────── Part A：马尔可夫转移 ──────────────────────────
def part_a(df: pd.DataFrame, rows: list[dict]) -> dict:
    print("== Part A：六阶段序列复算 + 马尔可夫转移矩阵 ==")
    cids = [locate_cycle(rows[i], rows[i - 1] if i else None)["id"]
            for i in range(len(rows))]
    print(f"  六阶段天数分布: "
          + ", ".join(f"{CNAME[c]}={cids.count(c)}" for c in ORDER))
    cyc = pd.Series(cids, index=df["date"].values)
    n = len(cids)
    k = len(ORDER)
    ix = {c: i for i, c in enumerate(ORDER)}

    M = np.zeros((k, k))
    for a, b in zip(cids[:-1], cids[1:]):
        M[ix[a], ix[b]] += 1
    P = M / M.sum(axis=1, keepdims=True)

    diag = [round(float(P[i, i]), 4) for i in range(k)]
    diag_mean = float(np.mean(diag))
    off_mean = float((P.sum() - np.trace(P)) / (k * k - k))

    ring = {}
    for a, b in RING:
        ring[f"{CNAME[a]}->{CNAME[b]}"] = round(float(P[ix[a], ix[b]]), 4)
    ring_vals = [P[ix[a], ix[b]] for a, b in RING]
    ring_mean = float(np.mean(ring_vals))
    off_diag_vals = [P[i, j] for i in range(k) for j in range(k) if i != j]
    off_diag_mean = float(np.mean(off_diag_vals))

    # 实测持续段长（同一阶段连续出现的天数）
    runs = {c: [] for c in ORDER}
    cur, ln = cids[0], 1
    for c in cids[1:]:
        if c == cur:
            ln += 1
        else:
            runs[cur].append(ln)
            cur, ln = c, 1
    runs[cur].append(ln)
    durations = {}
    for c in ORDER:
        arr = np.array(runs[c])
        p_ii = P[ix[c], ix[c]]
        dur_c = {
            "n_runs": int(len(arr)),
            "mean_run_days": round(float(arr.mean()), 2),
            "median_run_days": float(np.median(arr)),
            "markov_expected_days": round(float(1 / (1 - p_ii)), 2) if p_ii < 1 else None,
        }
        durations[CNAME[c]] = dur_c

    # 稳态分布（转移矩阵特征值 1 的左特征向量）
    try:
        w, v = np.linalg.eig(P.T)
        st = np.real(v[:, np.argmin(np.abs(w - 1))])
        st = np.abs(st / st.sum())
        stationary = {CNAME[ORDER[i]]: round(float(st[i]), 4) for i in range(k)}
    except Exception:
        stationary = None
    actual_freq = {CNAME[c]: round(float(cids.count(c) / n), 4) for c in ORDER}

    # 分期稳定性：2016-12-31 为界的两段对角线对比
    split = "2016-12-31"
    seg = {}
    for tag, sub in [("2007-2016", cyc[cyc.index <= split]),
                     ("2017-2026", cyc[cyc.index > split])]:
        Mi = np.zeros((k, k))
        cl = list(sub)
        for a, b in zip(cl[:-1], cl[1:]):
            Mi[ix[a], ix[b]] += 1
        s = Mi.sum(axis=1, keepdims=True)
        Pi = np.divide(Mi, s, out=np.zeros_like(Mi), where=s > 0)
        seg[tag] = {"n_days": len(cl), "diag_mean": round(float(np.mean([Pi[i, i] for i in range(k)])), 4)}

    # 四大战术分组 4×4 转移矩阵（主结论层；六阶段为底层明细）
    gids = [G4MAP[c] for c in cids]
    M4 = np.zeros((4, 4))
    for a, b in zip(gids[:-1], gids[1:]):
        M4[G4ORDER.index(a), G4ORDER.index(b)] += 1
    P4 = np.divide(M4, M4.sum(axis=1, keepdims=True),
                   out=np.zeros_like(M4), where=M4.sum(axis=1, keepdims=True) > 0)
    diag4 = {G4ORDER[i]: round(float(P4[i, i]), 4) for i in range(4)}
    # 中转枢纽统计：进攻↔防守一步直达 vs 转入中性修复态
    iF, iA, iD, iR = (G4ORDER.index(x) for x in ("修复", "进攻", "分化", "防守"))
    hub = {
        "进攻->防守_直达": int(M4[iA, iR]),
        "进攻->修复(中转)": int(M4[iA, iF] + M4[iA, iD]),
        "防守->进攻_直达": int(M4[iR, iA]),
        "防守->修复(中转)": int(M4[iR, iF]),
        "修复天数占比": round(float(sum(1 for g in gids if g == "修复") / n), 4),
    }

    # 热力图（左：战术分组 4×4 主结论；右：六阶段 6×6 明细）
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 5.6))
    for ax, Mat, labels, title in [
        (axes[0], P4, G4ORDER, "四大战术分组（主结论）"),
        (axes[1], P, [CNAME[c] for c in ORDER], "六阶段明细"),
    ]:
        im = ax.imshow(Mat * 100, cmap="YlOrRd", vmin=0, vmax=100)
        ax.set_xticks(range(len(labels)), labels, rotation=30)
        ax.set_yticks(range(len(labels)), labels)
        for i in range(len(labels)):
            for j in range(len(labels)):
                ax.text(j, i, f"{Mat[i, j]*100:.1f}", ha="center", va="center",
                        color="white" if Mat[i, j] > 0.5 else "black", fontsize=9)
        ax.set_xlabel("次日状态")
        ax.set_ylabel("当日状态")
        ax.set_title(title)
    fig.suptitle(f"情绪周期日频转移概率（{df['date'].min().date()} ~ {df['date'].max().date()}，n={n - 1}）")
    fig.colorbar(im, ax=axes, label="转移概率 (%)", shrink=0.85)
    fig.savefig(OUT / "thesis_ext_A_heatmap.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    res = {
        "n_days": n, "n_transitions": n - 1,
        "date_range": [str(df["date"].min().date()), str(df["date"].max().date())],
        "order": [CNAME[c] for c in ORDER],
        "count_matrix": [[int(v) for v in row] for row in M],
        "prob_matrix": [[round(float(v), 4) for v in row] for row in P],
        "diag_probs": {CNAME[ORDER[i]]: diag[i] for i in range(k)},
        "diag_mean": round(diag_mean, 4), "offdiag_mean": round(off_diag_mean, 4),
        "ring_transitions": ring,
        "ring_mean": round(ring_mean, 4),
        "offdiag_all_mean": round(off_diag_mean, 4),
        "durations": durations,
        "stationary_dist": stationary,
        "actual_freq": actual_freq,
        "segment_stability": seg,
        "g4_count_matrix": [[int(v) for v in row] for row in M4],
        "g4_prob_matrix": [[round(float(v), 4) for v in row] for row in P4],
        "g4_diag_probs": diag4,
        "hub_stats": hub,
        "caveat": ("locate_cycle 判定依赖派生指标：zt_fail_ratio 自 2014-01-28、"
                   "connect_2b 自 2026-08 才有历史；高潮分化全样本仅少数交易日、"
                   "冰点在昨板溢价段仅 7 天——6×6 明细如实保留，主结论在 4×4 战术分组级；"
                   "修复试探为判定兜底默认态（占 61% 天数），解释其高自环"),
        "note": "转移=相邻交易日；环=冰点→修复试探→修复确认→主升高潮→高潮分化→退潮→冰点",
    }
    (OUT / "thesis_ext_A_markov.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  n={n} 对角均值={diag_mean:.3f} 非对角均值={off_diag_mean:.3f} 环均值={ring_mean:.3f}")
    return res, cyc


# ────────────────────────── Part B：涨停生态 ──────────────────────────
def part_b(df: pd.DataFrame, cyc: pd.Series) -> dict:
    print("== Part B：涨停生态微观结构 ==")
    d = df[["date", "zt_prev_ret", "zt_fail_ratio", "connect_hl", "median_chg"]].copy()
    d["cycle"] = cyc.reindex(d["date"].values).values
    d["cname"] = d["cycle"].map(CNAME)

    def grp_stats(col: str) -> dict:
        sub = d.dropna(subset=[col])
        out = {}
        for cn, g in sub.groupby("cname"):
            v = g[col].dropna()
            if len(v) == 0:
                continue
            out[cn] = {
                "n": int(len(v)),
                "mean": round(float(v.mean()), 3),
                "median": round(float(v.median()), 3),
                "pos_rate": round(float((v > 0).mean()), 4) if col == "zt_prev_ret" else None,
                "start": str(g["date"].min().date()), "end": str(g["date"].max().date()),
            }
        return out

    prev_by_cycle = grp_stats("zt_prev_ret")     # 2014-01-29 起
    fail_by_cycle = grp_stats("zt_fail_ratio")   # 2014-01-28 起

    # 极端连板高度后的条件风险：未来 1/5/10/20 日 median_chg 累计（2009-11-02 起）
    dm = d.dropna(subset=["median_chg"]).reset_index(drop=True)
    fwd = {}
    for horizon in (1, 5, 10, 20):
        dm[f"f{horizon}"] = dm["median_chg"].shift(-1).rolling(horizon).sum().shift(-(horizon - 1) - 1)
    # 修正：未来 h 日累计 = sum(median_chg[t+1 .. t+h])
    for horizon in (1, 5, 10, 20):
        s = dm["median_chg"]
        dm[f"f{horizon}"] = sum(s.shift(-i) for i in range(1, horizon + 1))
    base = {f"f{h}": {"n": int(dm[f"f{h}"].notna().sum()),
                      "mean": round(float(dm[f"f{h}"].mean()), 3),
                      "p10": round(float(dm[f"f{h}"].quantile(0.10)), 3)}
            for h in (1, 5, 10, 20)}
    cond = {}
    for th in (6, 8):
        hit = dm[dm["connect_hl"] >= th]
        if len(hit) < 10:
            cond[f"hl>={th}"] = {"n": int(len(hit)), "note": "样本不足"}
            continue
        cond[f"hl>={th}"] = {
            "n": int(len(hit)),
            "first_date": str(hit["date"].min().date()),
            **{f"h{h}": {"mean": round(float(hit[f"f{h}"].dropna().mean()), 3),
                         "median": round(float(hit[f"f{h}"].dropna().median()), 3),
                         "p10": round(float(hit[f"f{h}"].dropna().quantile(0.10)), 3),
                         "worst": round(float(hit[f"f{h}"].dropna().min()), 3)}
               for h in (1, 5, 10, 20) if hit[f"f{h}"].notna().sum() >= 10},
        }
    res = {
        "zt_prev_ret_by_cycle": prev_by_cycle,
        "zt_fail_ratio_by_cycle": fail_by_cycle,
        "connect_hl_extreme_conditional": cond,
        "unconditional_baseline": base,
        "note": ("zt_prev_ret=昨板溢价%（2014-01-29 起）；zt_fail_ratio=炸板率%"
                 "（2014-01-28 起）；connect_hl=最高板（2009-11-02 起）；"
                 "h{N}=其后 N 个交易日 median_chg 累计%"),
    }
    (OUT / "thesis_ext_B_limitup.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  zt_prev_ret 分组 {len(prev_by_cycle)} 组 | 极端高度条件组: "
          + ", ".join(f"{kk}(n={vv.get('n')})" for kk, vv in cond.items()))
    return res


# ────────────────────────── Part C：滚动校准 ──────────────────────────
def part_c(df: pd.DataFrame, cyc: pd.Series) -> dict:
    print("== Part C：刻度校准样本外滚动验证（walk-forward） ==")
    d = pd.DataFrame({"date": df["date"],
                      "cname": cyc.reindex(df["date"].values).map(CNAME).values,
                      "next_chg": df["median_chg"].shift(-1)})
    # 口径铁律：median_chg 完整段自 2009-11-02 起（T-222 备案），更早历史缺失如实不参与
    d = d[(d["date"] >= "2009-11-02") & d["next_chg"].notna() & d["cname"].notna()]
    d = d.dropna(subset=["cname", "next_chg"])
    d["year"] = d["date"].dt.year

    val_years = list(range(2012, 2027))
    years_out = []
    for y in val_years:
        tr, te = d[d["year"] < y], d[d["year"] == y]
        if len(te) < 100:
            continue
        sug, nsamp = {}, {}
        for g in ("进攻期", "分化期", "修复期", "防守期"):
            cycles_g = [c for c, gg in GROUPS.items() if gg == g]
            sub = tr[tr["cname"].isin(cycles_g)]["next_chg"]
            n = len(sub)
            nsamp[g] = n
            if n < MIN_SAMPLES:                       # 样本不足 → 维持原常数（连建议都不出）
                sug[g] = None
            else:
                sug[g] = suggest_delta(float(sub.mean()))
        sug_adj = {}
        for g in ("进攻期", "分化期", "修复期", "防守期"):
            base = float(np.mean([CYCLE_ADJ0[c] for c, gg in GROUPS.items() if gg == g]))
            sug_adj[g] = round(base + (sug[g] if sug[g] is not None else 0), 1)
        held = sum(1 for g in sug if sug[g] is not None and abs(sug[g]) < NOISE_DELTA)
        years_out.append({
            "year": y, "n_train": int(len(tr)), "n_test": int(len(te)),
            "n_by_group_train": nsamp,
            "sug_delta": sug, "sug_adj": sug_adj,
            "attack_defense_spread": round(sug_adj["进攻期"] - sug_adj["防守期"], 1),
            "noise_held_groups": held,
        })
    spreads = [r["attack_defense_spread"] for r in years_out]
    res = {
        "params": {"GAIN": GAIN, "MAX_DELTA": MAX_DELTA, "NOISE_DELTA": NOISE_DELTA,
                   "MIN_SAMPLES": MIN_SAMPLES},
        "base_cycle_adj": CYCLE_ADJ0,
        "data_start": "2009-11-02（median_chg 完整段起点，此前历史缺失如实不参与）",
        "validation": "expanding walk-forward：用截至 Y-1 年末数据校准 → Y 年样本外",
        "years": years_out,
        "spread_summary": {"n_years": len(spreads),
                           "mean": round(float(np.mean(spreads)), 2),
                           "min": round(float(np.min(spreads)), 2),
                           "max": round(float(np.max(spreads)), 2),
                           "positive_years": int(sum(1 for s in spreads if s > 0))},
        "note": "建议仓位 = 温度基准外 CYCLE_ADJ 常数 + 样本外 sug_delta；None=训练样本不足维持原常数",
    }
    (OUT / "thesis_ext_C_walkforward.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    yrs = [r["year"] for r in years_out]
    for g, color in [("进攻期", "#ee2a2a"), ("防守期", "#00a862"), ("分化期", "#7c5cff")]:
        ax.plot(yrs, [r["sug_adj"][g] for r in years_out], marker="o", label=g, color=color)
    ax.axhline(0, color="#999", lw=0.8, ls="--")
    ax.set_xlabel("样本外验证年（校准数据截止前一年末）")
    ax.set_ylabel("周期刻度建议 adj（百分点）")
    ax.set_title("刻度校准样本外滚动验证：进攻/分化/防守组建议刻度（walk-forward）")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "thesis_ext_C_walkforward.png", dpi=150)
    plt.close(fig)
    print(f"  {len(years_out)} 个验证年 | 攻-防价差 mean={res['spread_summary']['mean']} "
          f"range=[{res['spread_summary']['min']}, {res['spread_summary']['max']}] "
          f"正年份 {res['spread_summary']['positive_years']}/{len(spreads)}")
    return res


def main() -> int:
    df, rows = load_data()
    _, cyc = part_a(df, rows)
    part_b(df, cyc)
    part_c(df, cyc)
    print(f"\n全部产物已写入: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
