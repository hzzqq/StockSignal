"""
模块 breadth_divergence：广度结构分化（方案③）

数据边界（诚实声明）：
  · 离线基座只有「全市场广度」聚合序列（red_ratio / 涨跌家数 / 涨跌停 / 涨停前日收益），
    **没有行业分类、没有指数序列**，因此无法做「行业广度热力」或「广度 vs 指数背离」。
  · 本模块改用广度**内部结构**刻画分化：
      1) 广度日历热力图：按 年×月 聚合红盘率，直观看广度季节/区间结构；
      2) 结构分化检测：当「红盘率偏高（表面普涨）」却伴随「跌停数也偏高（内部分化/杀跌）」，
         即典型的「涨多但杀跌」结构牛特征（如 2017、2021 核心资产牛市）。
  · 所有判定基于广度内部可观测量，不引入任何外部/编造数据。

取数失败优雅降级（返回 available=False / 空表）。
"""
import logging

import numpy as np
import pandas as pd

from modules import market_regime as mr

logger = logging.getLogger(__name__)


def load_breadth_history() -> pd.DataFrame:
    """取全量牧羊人广度历史（单一真理源：market_regime.load_breadth_history）。"""
    return mr.load_breadth_history()


def _safe_ratio(numer, denom):
    try:
        n, d = float(numer), float(denom)
    except (TypeError, ValueError):
        return None
    if d <= 0 or n != n:
        return None
    return n / d


def breadth_calendar(df: pd.DataFrame | None = None) -> dict:
    """按 年×月 聚合红盘率，供 Plotly 热力图使用。

    返回：{available, years, months, z(二维列表, 行=年, 列=月), latest_year}
    z 中缺失月份为 None（不编造）。
    """
    if df is None:
        try:
            df = load_breadth_history()
        except Exception as exc:  # pragma: no cover
            logger.warning("breadth history load failed: %s", exc)
            return dict(available=False, years=[], months=list(range(1, 13)), z=[], latest_year=None)
    if df is None or len(df) == 0:
        return dict(available=False, years=[], months=list(range(1, 13)), z=[], latest_year=None)

    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date"])
    d["year"] = d["date"].dt.year
    d["month"] = d["date"].dt.month
    d["rr"] = pd.to_numeric(d["red_ratio"], errors="coerce")
    piv = d.pivot_table(index="year", columns="month", values="rr", aggfunc="mean")
    years = sorted(piv.index.tolist())
    months = list(range(1, 13))
    z = []
    for y in years:
        row = []
        for m in months:
            v = piv.loc[y, m] if (y in piv.index and m in piv.columns) else np.nan
            row.append(None if pd.isna(v) else round(float(v), 1))
        z.append(row)
    return dict(available=True, years=years, months=months, z=z, latest_year=years[-1] if years else None)


def divergence_episodes(df: pd.DataFrame | None = None,
                        red_thresh: float = 50.0,
                        ld_quantile: float = 0.90) -> dict:
    """结构分化检测：红盘率偏高 且 跌停数处历史高位 → 「涨多但杀跌」内部分化。

    返回：{available, threshold_red, ld_p90, episodes(list of dict), current(dict|None)}
    episodes 每项：{date, red_ratio, limit_down, limit_down_ratio, zt_prev_ret}
    current：最新一行的分化状态（含 is_divergent 布尔）。
    """
    if df is None:
        try:
            df = load_breadth_history()
        except Exception as exc:  # pragma: no cover
            logger.warning("breadth history load failed: %s", exc)
            return dict(available=False, threshold_red=red_thresh, ld_p90=None, episodes=[], current=None)
    if df is None or len(df) == 0:
        return dict(available=False, threshold_red=red_thresh, ld_p90=None, episodes=[], current=None)

    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    d["rr"] = pd.to_numeric(d["red_ratio"], errors="coerce")
    d["ld"] = pd.to_numeric(d["limit_down"], errors="coerce")
    d["up"] = pd.to_numeric(d["up_count"], errors="coerce")
    d["down"] = pd.to_numeric(d["down_count"], errors="coerce")
    d["tot"] = d["up"] + d["down"]
    d["ld_ratio"] = d.apply(lambda r: _safe_ratio(r["ld"], r["tot"]), axis=1)
    d["ztr"] = pd.to_numeric(d["zt_prev_ret"], errors="coerce")

    ld_p90 = float(np.nanpercentile(d["ld_ratio"].dropna(), ld_quantile * 100)) if d["ld_ratio"].notna().any() else None

    mask = (d["rr"] >= red_thresh)
    if ld_p90 is not None:
        mask = mask & (d["ld_ratio"] >= ld_p90)
    flagged = d[mask]

    episodes = []
    for _, r in flagged.iterrows():
        episodes.append(dict(
            date=str(r["date"].date()),
            red_ratio=None if pd.isna(r["rr"]) else round(float(r["rr"]), 1),
            limit_down=None if pd.isna(r["ld"]) else int(r["ld"]),
            limit_down_ratio=None if pd.isna(r["ld_ratio"]) else round(float(r["ld_ratio"]) * 100, 2),
            zt_prev_ret=None if pd.isna(r["ztr"]) else round(float(r["ztr"]), 4),
        ))

    # 当前分化状态
    last = d.iloc[-1]
    cur_ld_ratio = _safe_ratio(last["ld"], last["tot"])
    is_div = (not pd.isna(last["rr"]) and last["rr"] >= red_thresh and
              ld_p90 is not None and cur_ld_ratio is not None and cur_ld_ratio >= ld_p90)
    current = dict(
        date=str(last["date"].date()),
        red_ratio=None if pd.isna(last["rr"]) else round(float(last["rr"]), 1),
        limit_down=None if pd.isna(last["ld"]) else int(last["ld"]),
        limit_down_ratio=None if cur_ld_ratio is None else round(cur_ld_ratio * 100, 2),
        is_divergent=bool(is_div),
    )
    return dict(available=True, threshold_red=red_thresh, ld_p90=ld_p90,
                episodes=episodes, current=current, n_episodes=len(episodes))
