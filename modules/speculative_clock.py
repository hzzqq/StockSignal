"""
模块 speculative_clock：投机情绪周期时钟（方案⑥）

数据边界（诚实声明，实测确认 2026-09-11）：
  · 离线健康镜像 `shepherd_history.json` 仅可靠填充 6 个广度字段：
      limit_up(涨停家数) / limit_down(跌停家数) / red_ratio(红盘占比%)
      up_count / down_count / flat_count
  · 连板梯队类维度（连板高度/连板家数/炸板率/封成比/昨日涨停表现/倒跌停）离线缺真值，
    本页**一律不引入、不编造**，仅在页面诚实标注「离线无真值」。
  · 本页以「涨停家数 + 红盘占比」的历史分位构造「投机情绪相位」：亢奋/活跃/偏冷/冰点/中性。
  · 这是描述性框架（描述当前处于投机情绪谱的哪个区间），不预测收益、不构成买卖建议。

取数失败优雅降级（available=False / 相位=数据不足）。
"""
import logging

import numpy as np
import pandas as pd

from modules import market_regime as mr
from modules.breadth_features import REAL_FEATURES, labels as _labels

logger = logging.getLogger(__name__)

_COLS = {
    "limit_up": _labels()["limit_up"],
    "limit_down": _labels()["limit_down"],
    "red_ratio": _labels()["red_ratio"],
    "up_count": _labels()["up_count"],
    "down_count": _labels()["down_count"],
}


def load_breadth_history() -> pd.DataFrame:
    return mr.load_breadth_history()


def _f(v):
    try:
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def speculative_sentiment_series(df: pd.DataFrame | None = None, window: int = 250) -> dict:
    """取 5 个广度维度的时序（按日期升序，窗口截断）。

    返回 {available, dates, series{col->[v]}, labels}。
    各序列为原始值（含 None），归一化在页面层处理。
    """
    if df is None:
        try:
            df = load_breadth_history()
        except Exception as exc:  # pragma: no cover
            logger.warning("breadth load failed: %s", exc)
            return dict(available=False, dates=[], series={}, labels=_COLS)
    if df is None or len(df) == 0:
        return dict(available=False, dates=[], series={}, labels=_COLS)

    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    if window and window > 0 and len(d) > window:
        d = d.tail(int(window)).reset_index(drop=True)

    dates = [str(x.date()) for x in d["date"]]
    series = {}
    for k in _COLS:
        if k in d.columns:
            vals = pd.to_numeric(d[k], errors="coerce")
            series[k] = [None if pd.isna(v) else round(float(v), 3) for v in vals]
        else:
            series[k] = [None] * len(d)
    avail = any(v is not None for s in series.values() for v in s)
    return dict(available=avail, dates=dates, series=series, labels=_COLS)


def _percentile_rank(series: pd.Series, value) -> float:
    """返回 value 在 series 中的历史分位（0~1）。"""
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) == 0 or value is None or value != value:
        return float("nan")
    return float((s < value).mean())


def current_phase(df: pd.DataFrame | None = None) -> dict:
    """最新一行的投机情绪相位（基于 red_ratio + limit_up 的历史分位）。"""
    if df is None:
        try:
            df = load_breadth_history()
        except Exception:  # pragma: no cover
            return dict(available=False, phase="数据不足")
    if df is None or len(df) == 0:
        return dict(available=False, phase="数据不足")
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    if len(d) == 0:
        return dict(available=False, phase="数据不足")
    last = d.iloc[-1]
    rr = _f(last.get("red_ratio"))
    lu = _f(last.get("limit_up"))
    ld = _f(last.get("limit_down"))
    if rr is None and lu is None:
        # 最新一行关键字段全缺失：诚实标注，而非误判为「中性」
        return dict(available=True, phase="数据不足",
                    date=str(last["date"].date()) if pd.notna(last["date"]) else None,
                    red_ratio=rr, limit_up=lu, limit_down=ld,
                    reason="最新一行 red_ratio/limit_up 均缺失，无法判定相位")

    # 历史分位
    rr_pct = _percentile_rank(d["red_ratio"], rr)
    lu_pct = _percentile_rank(d["limit_up"], lu)

    if rr is not None and rr >= 60 and lu_pct >= 0.8:
        phase, reason = "亢奋", "红盘占比≥60% 且涨停家数处历史前 20%——投机情绪亢奋"
    elif rr is not None and rr >= 60:
        phase, reason = "活跃", "红盘占比≥60%——市场偏活跃"
    elif rr is not None and rr < 30 and (lu_pct <= 0.2 or lu is None):
        phase, reason = "冰点", "红盘占比<30% 且涨停家数处历史后 20%——投机情绪冰点"
    elif rr is not None and rr < 40:
        phase, reason = "偏冷", "红盘占比<40%——市场偏冷"
    else:
        phase, reason = "中性", "未触发极端相位，投机情绪中性"

    return dict(
        available=True,
        date=str(last["date"].date()) if pd.notna(last["date"]) else None,
        red_ratio=rr, limit_up=lu, limit_down=ld,
        red_ratio_pct=round(rr_pct, 3) if rr_pct == rr_pct else None,
        limit_up_pct=round(lu_pct, 3) if lu_pct == lu_pct else None,
        phase=phase, reason=reason,
    )
