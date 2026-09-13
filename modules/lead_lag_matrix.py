"""
模块 lead_lag_matrix：维度领先-滞后矩阵（方案⑦）

数据边界（诚实声明，实测确认 2026-09-11）：
  · 仅使用离线健康镜像可靠填充的广度字段（REAL_FEATURES：涨跌/平家数、涨停/跌停家数、红盘占比）。
  · 连板梯队类维度（连板高度/家数/炸板率/封成比/昨日涨停表现/倒跌停）离线缺真值，已通过 `usable_dims`
    闸门剔除，**不进入相关计算、不编造**。
  · 计算各维度两两互相关在 lag 0~20 日的最优领先滞后。互相关是描述性统计（衡量两序列时间上的协同/错位），
    **不构成因果、不预测方向**。

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


def _safe_series(df, col):
    v = pd.to_numeric(df[col], errors="coerce")
    return v.values.astype(float)


def lead_lag_matrix(df: pd.DataFrame | None = None, dims=None, max_lag: int = 20) -> dict:
    """计算维度两两领先-滞后矩阵。

    返回 {available, dims, labels, matrix(n×n), dropped}：
      matrix[i][j] = i 相对 j 的最优领先滞后（带符号）：
        正值 k → i 领先 j 约 k 日（正相关）；负值 -k → i 领先 j 约 k 日但反向（负相关）；0 → 无显著领先。
    仅描述历史协同结构，非因果、非预测。
    """
    if df is None:
        try:
            df = load_breadth_history()
        except Exception as exc:  # pragma: no cover
            logger.warning("breadth load failed: %s", exc)
            return dict(available=False, dims=[], labels={}, matrix=[], dropped={})
    if df is None or len(df) == 0:
        return dict(available=False, dims=[], labels={}, matrix=[], dropped={})

    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    cand, dropped = usable_dims(d, candidate=(dims or REAL_FEATURES))
    if len(cand) < 2:
        return dict(available=False, dims=cand,
                    labels={c: _LABELS.get(c, c) for c in cand},
                    matrix=[], dropped=dropped)

    # 仅用可用维度的 z-score（消除量纲）
    norm = {}
    for c in cand:
        s = pd.Series(_safe_series(d, c), dtype=float)
        m, sd = s.mean(), s.std()
        norm[c] = ((s - m) / sd).values if (sd and sd == sd and sd != 0) else np.zeros(len(s))

    n = len(cand)
    matrix = [[0] * n for _ in range(n)]
    for i in range(n):
        xi = norm[cand[i]]
        for j in range(n):
            if i == j:
                matrix[i][j] = 0
                continue
            xj = norm[cand[j]]
            best_lag, best_corr = 0, 0.0
            for k in range(0, max_lag + 1):
                if len(xi) - k <= 2:
                    break
                a = xi[:len(xi) - k]
                b = xj[k:]
                if len(a) < 3:
                    break
                with np.errstate(invalid="ignore"):
                    cval = np.corrcoef(a, b)[0, 1]
                if cval == cval and abs(cval) > abs(best_corr):
                    best_corr = cval
                    best_lag = k
            matrix[i][j] = int(best_lag) if best_corr >= 0 else -int(best_lag)
    return dict(available=True, dims=cand,
                labels={c: _LABELS.get(c, c) for c in cand},
                matrix=matrix, max_lag=max_lag, dropped=dropped)
