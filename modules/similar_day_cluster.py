"""
模块 similar_day_cluster：历史相似日聚类 + 前向分布（方案⑧）

数据边界（诚实声明）：
  · 取最新一日的 8 维广度向量，在全历史里按欧氏距离找最相似的 top-N 日（排除末日 ±15 交易日邻居以防前视泄漏）。
  · 对每個相似日，取其之后 5/10/20 交易日的红盘占比，统计前向分布（均值/中位数/分位/红盘占比）。
  · 这是**历史类比**——用过去相似情境的后继表现描述当前情境的“经验分布”，**不是预测、不保证复现**。
  · 离线基座无指数/行业/资金流，全部维度来自 shepherd_history 内部变量，不编造。

取数失败优雅降级（available=False）。
"""
import logging

import numpy as np
import pandas as pd

from modules import market_regime as mr

logger = logging.getLogger(__name__)

_DIMS = ["red_ratio", "limit_up", "limit_down", "zt_prev_ret",
         "connect_hl", "connect_2b", "zt_fail_ratio", "touch_down"]


def load_breadth_history() -> pd.DataFrame:
    return mr.load_breadth_history()


def _safe_series(df, col):
    if col not in df.columns:
        return None
    return pd.to_numeric(df[col], errors="coerce").fillna(0.0).values.astype(float)


def similar_day_cluster(df: pd.DataFrame | None = None, dims=None,
                        top_n: int = 15, exclude_window: int = 15,
                        forward_days=(5, 10, 20)) -> dict:
    """历史相似日聚类 + 前向红盘率分布。

    返回 {available, target_date, dims, similar:[{date, dist, fwd:{5:rr,10:rr,20:rr}}],
          forward_stats:{d:{mean,median,p10,p90,up_ratio,n}}}。
    """
    if df is None:
        try:
            df = load_breadth_history()
        except Exception as exc:  # pragma: no cover
            logger.warning("breadth load failed: %s", exc)
            return dict(available=False, similar=[], forward_stats={})
    if df is None or len(df) == 0:
        return dict(available=False, similar=[], forward_stats={})

    dims = dims or _DIMS
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    cols = [c for c in dims if c in d.columns]
    if len(cols) < 2 or len(d) < exclude_window + top_n + 5:
        return dict(available=False, similar=[], forward_stats={}, reason="样本不足")

    mat = np.stack([_safe_series(d, c) for c in cols], axis=1)  # (N, D)
    rr = pd.to_numeric(d["red_ratio"], errors="coerce").values.astype(float)
    N = len(d)
    target = mat[-1]
    dists = np.linalg.norm(mat - target, axis=1)

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
        return dict(available=False, similar=[], forward_stats={}, reason="无候选相似日")

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
        n_total=int(N),
        exclude_window=exclude_window,
        similar=similar,
        forward_stats=forward_stats,
    )
