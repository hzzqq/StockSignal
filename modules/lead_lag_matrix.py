"""
模块 lead_lag_matrix：维度领先-滞后矩阵（方案⑦）

数据边界（诚实声明）：
  · 用牧羊人 8 个广度内部维度的全历史日序列，计算两两互相关在 lag 0~20 日的最优领先滞后。
  · 互相关是描述性统计（衡量两个序列在时间上的协同/错位），**不构成因果、不预测方向**。
  · 离线基座无指数/行业/资金流，全部维度均来自 shepherd_history 内部可观测变量，不编造。

取数失败优雅降级（available=False）。
"""
import logging

import numpy as np
import pandas as pd

from modules import market_regime as mr

logger = logging.getLogger(__name__)

_DIMS = ["red_ratio", "limit_up", "limit_down", "zt_prev_ret",
         "connect_hl", "connect_2b", "zt_fail_ratio", "touch_down"]
_LABELS = {
    "red_ratio": "红盘占比", "limit_up": "涨停家数", "limit_down": "跌停家数",
    "zt_prev_ret": "昨日涨停表现", "connect_hl": "连板高度", "connect_2b": "连板家数",
    "zt_fail_ratio": "炸板率", "touch_down": "倒跌停家数",
}


def load_breadth_history() -> pd.DataFrame:
    return mr.load_breadth_history()


def _safe_series(df, col):
    if col not in df.columns:
        return None
    v = pd.to_numeric(df[col], errors="coerce").fillna(0.0).values
    return v.astype(float)


def lead_lag_matrix(df: pd.DataFrame | None = None, dims=None, max_lag: int = 20) -> dict:
    """计算维度两两领先-滞后矩阵。

    返回 {available, dims, labels, matrix(n×n)}：
      matrix[i][j] = i 相对 j 的最优领先滞后（带符号）：
        正值 k → i 领先 j 约 k 日（正相关）；
        负值 -k → i 领先 j 约 k 日但反向（负相关）；
        0 → 窗口内无显著领先（含 i==j）。
    仅描述历史协同结构，非因果、非预测。
    """
    if df is None:
        try:
            df = load_breadth_history()
        except Exception as exc:  # pragma: no cover
            logger.warning("breadth load failed: %s", exc)
            return dict(available=False, dims=[], labels={}, matrix=[])
    if df is None or len(df) == 0:
        return dict(available=False, dims=[], labels={}, matrix=[])

    dims = dims or _DIMS
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    data = {c: _safe_series(d, c) for c in dims}
    data = {c: v for c, v in data.items() if v is not None and len(v) > max_lag + 2}
    avail = list(data.keys())
    if len(avail) < 2:
        return dict(available=False, dims=avail, labels={c: _LABELS.get(c, c) for c in avail}, matrix=[])

    # z-score 归一后再算相关，消除量纲影响
    norm = {}
    for c, v in data.items():
        s = pd.Series(v)
        m, sd = s.mean(), s.std()
        norm[c] = ((s - m) / sd).values if (sd and sd == sd and sd != 0) else np.zeros(len(s))

    n = len(avail)
    matrix = [[0] * n for _ in range(n)]
    for i in range(n):
        xi = norm[avail[i]]
        for j in range(n):
            if i == j:
                matrix[i][j] = 0
                continue
            xj = norm[avail[j]]
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
    return dict(available=True, dims=avail,
                labels={c: _LABELS.get(c, c) for c in avail},
                matrix=matrix, max_lag=max_lag)
