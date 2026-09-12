"""
模块 momentum_breadth_resonance：动量 × 广度 共振矩阵（方案④ 离线版）

数据边界（诚实声明）：
  · 原方案为「资金流 × 广度共振」，但主力净流入属网络实时数据，离线基座拿不到真值。
  · 本模块改用**离线可得**的两组广度内部变量刻画「共振」：
      - 广度轴：red_ratio（红盘率）→ 沿用市场温度计五档语义（冰点/偏冷/中性/活跃/狂热）；
      - 动量轴：zt_prev_ret（涨停股前一日收益，动量代理）→ 反映追涨动能强弱。
  · 共振矩阵 = 两个维度分档后的**联合分布**（共现天数），用于直观看
    「广度热时动量是否也强 / 二者是否经常同冷同热」。它描述共现结构，**不是**收益预测。
  · 真·资金流（行业主力净流入）联网可用时再作为增强维度叠加，本模块不编造。

取数失败优雅降级（available=False / 空矩阵）。
"""
import logging

import numpy as np
import pandas as pd

from modules import market_regime as mr
from modules.market_temperature import temperature_band

logger = logging.getLogger(__name__)


# 广度五档边界（与市场温度计一致）
_RR_BINS = [0, 20, 40, 60, 80, 100]
_RR_LABELS = ["冰点", "偏冷", "中性", "活跃", "狂热"]
# 动量分档（涨停前日收益 %）
_MOM_BINS = [-np.inf, -1.0, 0.0, 1.0, 2.0, np.inf]
_MOM_LABELS = ["强杀跌≤-1%", "-1~0%", "0~1%温和", "1~2%强", "≥2%极强"]


def load_breadth() -> pd.DataFrame:
    return mr.load_breadth_history()


def _rr_band(v):
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


def _mom_band(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    for i in range(len(_MOM_BINS) - 1):
        if _MOM_BINS[i] <= f < _MOM_BINS[i + 1]:
            return i
    return 4 if f >= _MOM_BINS[-1] else 0


def resonance_matrix(df: pd.DataFrame | None = None) -> dict:
    """计算 广度×动量 联合分布矩阵（共现天数）。

    返回：{available, rr_labels, mom_labels, matrix(5×5, 行=广度档, 列=动量档),
           totals_row, totals_col, n_days}
    """
    if df is None:
        try:
            df = load_breadth()
        except Exception as exc:  # pragma: no cover
            logger.warning("breadth load failed: %s", exc)
            return _empty()
    if df is None or len(df) == 0:
        return _empty()

    d = df.copy()
    d["rr"] = pd.to_numeric(d["red_ratio"], errors="coerce")
    d["mom"] = pd.to_numeric(d["zt_prev_ret"], errors="coerce")
    d = d.dropna(subset=["rr", "mom"])
    if len(d) == 0:
        return _empty()

    d["rb"] = d["rr"].apply(_rr_band)
    d["mb"] = d["mom"].apply(_mom_band)
    d = d.dropna(subset=["rb", "mb"])
    d["rb"] = d["rb"].astype(int)
    d["mb"] = d["mb"].astype(int)

    matrix = np.zeros((5, 5), dtype=int)
    for rb, mb in zip(d["rb"], d["mb"]):
        matrix[rb, mb] += 1

    totals_row = matrix.sum(axis=1).tolist()      # 各广度档总天数
    totals_col = matrix.sum(axis=0).tolist()      # 各动量档总天数
    return dict(
        available=True, rr_labels=_RR_LABELS, mom_labels=_MOM_LABELS,
        matrix=matrix.tolist(), totals_row=totals_row, totals_col=totals_col,
        n_days=int(matrix.sum()),
    )


def _empty():
    return dict(available=False, rr_labels=_RR_LABELS, mom_labels=_MOM_LABELS,
                matrix=[[0] * 5 for _ in range(5)], totals_row=[0] * 5,
                totals_col=[0] * 5, n_days=0)


def current_cell(df: pd.DataFrame | None = None) -> dict:
    """最新一行的（广度档, 动量档）及共现强度上下文。"""
    if df is None:
        try:
            df = load_breadth()
        except Exception:  # pragma: no cover
            return dict(available=False)
    if df is None or len(df) == 0:
        return dict(available=False)
    last = df.sort_values("date").iloc[-1]
    rb = _rr_band(last.get("red_ratio"))
    mb = _mom_band(last.get("zt_prev_ret"))
    if rb is None or mb is None:
        return dict(available=True, date=str(last.get("date")), rr_band=None, mom_band=None,
                    rr_label=None, mom_label=None)
    rb = int(rb); mb = int(mb)
    return dict(
        available=True, date=str(last.get("date")),
        rr_band=int(rb), mom_band=int(mb),
        rr_label=_RR_LABELS[rb], mom_label=_MOM_LABELS[mb],
        red_ratio=_as_float(last.get("red_ratio")),
        zt_prev_ret=_as_float(last.get("zt_prev_ret")),
    )


def _as_float(v):
    try:
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def resonance_stats(matrix_result: dict | None = None) -> dict:
    """由矩阵派生共现强度指标。

    返回：{co_hot(广度≥活跃且动量≥强 的共现占比), co_cold(广度≤偏冷且动量≤温和 的共现占比),
            dominant_cell(共现天数最多的档位)}
    """
    if matrix_result is None:
        matrix_result = resonance_matrix()
    if not matrix_result.get("available"):
        return dict(available=False)
    M = np.array(matrix_result["matrix"])
    n = M.sum()
    if n == 0:
        return dict(available=True, co_hot=0.0, co_cold=0.0, dominant_cell=None, n_days=0)
    # 广度≥活跃 = 行 3,4；动量≥强 = 列 3,4
    co_hot = int(M[3:, 3:].sum()) / n
    # 广度≤偏冷 = 行 0,1；动量≤温和 = 列 0,1,2
    co_cold = int(M[:2, :3].sum()) / n
    rb, mb = divmod(int(M.argmax()), 5)
    dominant_cell = (matrix_result["rr_labels"][rb], matrix_result["mom_labels"][mb], int(M.max()))
    return dict(available=True, co_hot=round(co_hot * 100, 1), co_cold=round(co_cold * 100, 1),
                dominant_cell=dominant_cell, n_days=int(n))
