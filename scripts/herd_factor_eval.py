# -*- coding: utf-8 -*-
"""
scripts/herd_factor_eval.py — 羊群拥挤度「预测因子化」留出验证（T-184 · 自研创新点延伸）

目的：T-182 把拥挤度做成了**仓位调节器**（decision 端 -8/-4pt）；本脚本回答
更高阶的问题——它作为**预测因子**是否有截面预测力：
  ① 拥挤度分桶 × 次日收益：score 与次日 median_chg 的 Spearman 秩相关
    （贪婪端单调性 = 红挤越极端次日越差 → 因子化成立的实证）
  ② regime 状态分桶 × 次日收益：五状态各自的前瞻分布（暴跌/恐慌左尾实证）

⚠️ 诚实口径：
  · 全程无前视：拥挤度与状态只用当日及以前信息（同 backtest_dual_factor）
  · 分桶样本不足如实标 n，不 skip 不编造；小桶（如暴跌 n=7）结论只作描述
  · 真值 = 下一交易日 median_chg 符号（与 backtest_decision_closure 同口径）

输入：data/shepherd_history.csv（4094 行，含 median_chg 真值）
输出：reports/herd_factor_eval.json + 控制台摘要
"""
from __future__ import annotations

import json
import logging
import math
import os
import sys
from datetime import datetime

_HERE0 = os.path.dirname(os.path.abspath(__file__))
_ROOT0 = os.path.dirname(_HERE0)
if _ROOT0 not in sys.path:
    sys.path.insert(0, _ROOT0)

import pandas as pd
from scipy import stats as sps

from modules.herd_crowding import MILD_CROWD, STRONG_CROWD, crowding_from_history
from modules.market_regime import STATE_ORDER, classify_state
from modules.time_utils import now_cst_naive

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
DATA_DIR = os.environ.get("SS_DATA_DIR", os.path.join(_ROOT, "data"))
_BREADTH_FILE = os.path.join(DATA_DIR, "shepherd_history.csv")
OUT_PATH = os.environ.get(
    "HERD_FACTOR_OUT",
    os.path.join(_ROOT, "reports", "herd_factor_eval.json"),
)

BUCKETS = [(0, 30), (30, 50), (50, MILD_CROWD), (MILD_CROWD, STRONG_CROWD),
           (STRONG_CROWD, 100.01)]  # 末桶含 85 自身（闭区间语义）
BUCKET_LABELS = ["0-30", "30-50", "50-70", "70-85", "85+"]


def _num(v):
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _bucket_of(score: float) -> int:
    for k, (lo, hi) in enumerate(BUCKETS):
        if lo <= score < hi:
            return k
    return len(BUCKETS) - 1


def _bucket_stat(rows: list[dict]) -> dict:
    """一个分桶的次日收益统计（空桶如实 n=0，字段 None 不编造）。"""
    n = len(rows)
    if n == 0:
        return {"n": 0, "avg_next_chg": None, "median_next_chg": None, "up_frac": None}
    chg = sorted(r["next_chg"] for r in rows)
    return {
        "n": n,
        "avg_next_chg": round(sum(chg) / n, 4),
        "median_next_chg": round(chg[n // 2] if n % 2 else (chg[n // 2 - 1] + chg[n // 2]) / 2, 4),
        "up_frac": round(sum(1 for c in chg if c > 0) / n, 4),
    }


def _spearman(xs: list[float], ys: list[float]) -> dict | None:
    """Spearman 秩相关（样本 <10 或零方差 → None，不硬算）。"""
    if len(xs) < 10 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    rho, p = sps.spearmanr(xs, ys)
    if rho != rho:  # NaN
        return None
    return {"rho": round(float(rho), 4), "p_value": round(float(p), 6), "n": len(xs)}


def run(breadth_file: str | None = None) -> dict:
    path = breadth_file or _BREADTH_FILE
    df = pd.read_csv(path, encoding="utf-8-sig")
    df = df.sort_values("date").reset_index(drop=True)

    bucket_rows: list[list[dict]] = [[] for _ in BUCKETS]
    state_rows: dict[str, list[dict]] = {st: [] for st in STATE_ORDER}
    greed_xy: list[tuple[float, float]] = []   # (score, next_chg) 贪婪端单调性
    all_xy: list[tuple[float, float]] = []

    rows = df.to_dict("records")
    for i in range(1, len(rows) - 1):
        today = rows[i]
        red = _num(today.get("red_ratio"))
        lu, ld = _num(today.get("limit_up")), _num(today.get("limit_down"))
        next_chg = _num(rows[i + 1].get("median_chg"))
        if red is None or lu is None or ld is None or next_chg is None:
            continue  # 当日特征或次日真值缺失 → 诚实跳过

        herd = crowding_from_history(df, i)
        state = classify_state(today)
        st_row = {"next_chg": next_chg}
        state_rows[state].append(st_row)

        if herd.get("status") == "ok" and herd.get("score") is not None:
            score = float(herd["score"])
            all_xy.append((score, next_chg))
            bucket_rows[_bucket_of(score)].append(st_row)
            if herd.get("side") == "greed":
                greed_xy.append((score, next_chg))

    by_bucket = []
    for label, rows_ in zip(BUCKET_LABELS, bucket_rows):
        by_bucket.append({"bucket": label, **_bucket_stat(rows_)})

    greed_spearman = _spearman([x for x, _ in greed_xy], [y for _, y in greed_xy])
    all_spearman = _spearman([x for x, _ in all_xy], [y for _, y in all_xy])

    by_state = {st: _bucket_stat(rows_) for st, rows_ in state_rows.items()}

    return {
        "meta": {
            "generated_at": now_cst_naive().isoformat(timespec="seconds"),
            "source": os.path.basename(path),
            "n_scored": sum(b["n"] for b in by_bucket),
            "bucket_edges": BUCKET_LABELS,
            "thresholds": {"mild": MILD_CROWD, "strong": STRONG_CROWD},
            "disclosure": "无前视（拥挤度/状态只用当日及以前）；真值=次日 median_chg；"
                          "小样本桶（如暴跌）结论仅描述性，不外推；Spearman 样本<10 不算。",
        },
        "monotonic": {
            "greed_side_score_vs_next_chg": greed_spearman,
            "all_days_score_vs_next_chg": all_spearman,
            "interpretation": "rho<0 且显著 = 红挤越极端次日越差（因子化成立）",
        },
        "by_crowding_bucket": by_bucket,
        "by_state": by_state,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = run()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[herd_factor_eval] report → {OUT_PATH}")
    m = report["monotonic"]
    print(f"  greed spearman: {m['greed_side_score_vs_next_chg']}")
    print(f"  all   spearman: {m['all_days_score_vs_next_chg']}")
    for b in report["by_crowding_bucket"]:
        print(f"  bucket {b['bucket']:>6} n={b['n']:5d} avg_next={b['avg_next_chg']} "
              f"up_frac={b['up_frac']}")
    for st, s in report["by_state"].items():
        print(f"  state  {st:>4} n={s['n']:5d} avg_next={s['avg_next_chg']} "
              f"up_frac={s['up_frac']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
