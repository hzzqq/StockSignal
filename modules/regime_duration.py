"""
模块 regime_duration：温度持续期与回归时长（方案⑩）

数据边界（诚实声明）：
  · 以「红盘占比」五档（冰点/偏冷/中性/活跃/狂热）作为温度代理，对每日标档。
  · 计算每段同档连续 run 的时长分布（各档 avg/median 持续天数），并重点统计
    「冰点」run 到首次回到 ≥中性 的中位天数（磨底时长）。
  · 这是历史统计描述（市场在该温度下“平均要熬多久”），**不预测未来、不构成买卖建议**。
  · 仅用 shepherd_history 内部可观测的 red_ratio，不引入指数/行业/资金流，不编造。

取数失败优雅降级（available=False）。
"""
import logging

import numpy as np
import pandas as pd

from modules import market_regime as mr

logger = logging.getLogger(__name__)

_RR_BINS = [0, 20, 40, 60, 80, 100]
_LABELS = ["冰点", "偏冷", "中性", "活跃", "狂热"]


def load_breadth_history() -> pd.DataFrame:
    return mr.load_breadth_history()


def _band(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    for i in range(len(_RR_BINS) - 1):
        if _RR_BINS[i] <= f < _RR_BINS[i + 1]:
            return i
    return 4 if f >= _RR_BINS[-1] else 0


def regime_duration(df: pd.DataFrame | None = None) -> dict:
    """温度档持续期 + 冰点回归时长统计。

    返回 {available, band_labels, durations:{band:{n,mean,median}},
          recovery:{n,mean,median}, total_runs}。
    """
    if df is None:
        try:
            df = load_breadth_history()
        except Exception as exc:  # pragma: no cover
            logger.warning("breadth load failed: %s", exc)
            return dict(available=False, durations={}, recovery={})
    if df is None or len(df) == 0:
        return dict(available=False, durations={}, recovery={})

    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    rr = pd.to_numeric(d["red_ratio"], errors="coerce")
    bands = rr.apply(_band)
    if bands.isna().all():
        return dict(available=False, durations={}, recovery={})

    bands = bands.fillna(2).astype(int).tolist()  # 缺失按中性，避免断 run
    n = len(bands)

    runs = []  # (band, start, end)
    cur, start = bands[0], 0
    for i in range(1, n):
        if bands[i] != cur:
            runs.append((cur, start, i - 1))
            cur, start = bands[i], i
    runs.append((cur, start, n - 1))

    durations = {b: [] for b in range(5)}
    for b, s, e in runs:
        durations[b].append(e - s + 1)

    recovery = []
    for b, s, e in runs:
        if b != 0:  # 仅统计冰点 run
            continue
        # 从 e+1 起找首个 >= 中性(2) 的交易日
        for j in range(e + 1, n):
            if bands[j] >= 2:
                recovery.append(j - e)
                break

    def _stat(arr):
        if not arr:
            return dict(n=0, mean=None, median=None)
        a = np.array(arr, dtype=float)
        return dict(n=int(len(a)), mean=round(float(a.mean()), 1), median=round(float(np.median(a)), 1))

    return dict(
        available=True,
        band_labels=_LABELS,
        durations={b: _stat(durations[b]) for b in range(5)},
        recovery=_stat(recovery),
        total_runs=len(runs),
    )
