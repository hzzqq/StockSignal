"""
模块 similar_day_cluster：历史相似日聚类 + 前向分布（方案⑧）

数据边界（诚实声明，实测确认 2026-09-11）：
  · 取最新一日的真实广度向量（REAL_FEATURES），在全历史按欧氏距离找最相似 top-N 日
    （排除末日 ±exclude_window 交易日邻居以防前视泄漏）。
  · 对每个相似日，取其之后 5/10/20 交易日的红盘占比，统计前向分布（均值/中位数/分位/红盘占比）。
  · 连板梯队类维度离线缺真值，已通过 `usable_dims` 闸门剔除，**不进入距离计算、不编造**。
  · 这是**历史类比**——用过去相似情境的后继表现描述当前情境的“经验分布”，**不是预测、不保证复现**。

取数失败优雅降级（available=False）。
"""
import logging

import numpy as np
import pandas as pd

from modules import market_regime as mr
from modules.breadth_features import REAL_FEATURES, labels as _labels, usable_dims

logger = logging.getLogger(__name__)
_LABELS = _labels()


def load_breadth_history() -> pd.DataFrame:
    return mr.load_breadth_history()


def similar_day_cluster(df: pd.DataFrame | None = None, dims=None,
                       top_n: int = 15, exclude_window: int = 15,
                       forward_days=(5, 10, 20)) -> dict:
    """历史相似日聚类 + 前向红盘率分布。

    返回 {available, target_date, dims, dropped, similar:[{date, dist, fwd}],
          forward_stats:{d:{mean,median,p10,p90,up_ratio,n}}}。
    """
    if df is None:
        try:
            df = load_breadth_history()
        except Exception as exc:  # pragma: no cover
            logger.warning("breadth load failed: %s", exc)
            return dict(available=False, similar=[], forward_stats={}, dropped={})
    if df is None or len(df) == 0:
        return dict(available=False, similar=[], forward_stats={}, dropped={})

    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    cols, dropped = usable_dims(d, candidate=(dims or REAL_FEATURES))
    if len(cols) < 2 or len(d) < exclude_window + top_n + 5:
        return dict(available=False, similar=[], forward_stats={},
                    dims=cols, dropped=dropped, reason="样本或维度不足")

    mat = np.stack([pd.to_numeric(d[c], errors="coerce").fillna(0.0).values.astype(float)
                    for c in cols], axis=1)  # (N, D)
    rr = pd.to_numeric(d["red_ratio"], errors="coerce").values.astype(float)
    N = len(d)
    target = mat[-1]
    # 用历史均值/标准差标准化，避免量纲主导距离
    mu = mat.mean(axis=0)
    sd = mat.std(axis=0)
    sd[sd == 0] = 1.0
    mat_z = (mat - mu) / sd
    target_z = (target - mu) / sd
    dists = np.linalg.norm(mat_z - target_z, axis=1)

    cand = []
    for i in range(N):
        if abs(i - (N - 1)) <= exclude_window:
            continue  # 排除末日邻居，防前视泄漏
        if np.isnan(dists[i]):
            continue
        cand.append((i, float(dists[i])))
    cand.sort(key=lambda x: x[1])
    top = cand[:top_n]
    if not top:
        return dict(available=False, similar=[], forward_stats={},
                    dims=cols, dropped=dropped, reason="无候选相似日")

    similar = []
    fwd_buckets = {k: [] for k in forward_days}
    for i, dist in top:
        fwd = {}
        for off in forward_days:
            j = i + off
            if 0 <= j < N and rr[j] == rr[j]:
                fwd[off] = round(float(rr[j]), 2)
                fwd_buckets[off].append(float(rr[j]))
        similar.append({
            "date": str(d["date"].iloc[i].date()),
            "dist": round(dist, 3),
            "fwd": fwd,
        })

    forward_stats = {}
    for off in forward_days:
        arr = np.array(fwd_buckets[off])
        if len(arr) == 0:
            forward_stats[off] = dict(n=0)
            continue
        up = float(np.mean(arr >= 50.0)) * 100.0
        forward_stats[off] = dict(
            n=int(len(arr)),
            mean=round(float(np.mean(arr)), 2),
            median=round(float(np.median(arr)), 2),
            p10=round(float(np.percentile(arr, 10)), 2),
            p90=round(float(np.percentile(arr, 90)), 2),
            up_ratio=round(up, 1),
        )
    return dict(
        available=True,
        target_date=str(d["date"].iloc[-1].date()),
        dims=cols,
        dropped=dropped,
        n_total=int(N),
        exclude_window=exclude_window,
        similar=similar,
        forward_stats=forward_stats,
    )
