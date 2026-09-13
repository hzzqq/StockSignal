"""
模块 speculative_clock：投机情绪周期时钟（方案⑥）

数据边界（诚实声明）：
  · 只用牧羊人广度内部可得的「涨停梯队质量」维度：连板高度 / 连板家数(≥2板) /
    炸板率 / 昨日涨停表现 / 平均封成比。这些离线基座均有真值（shepherd_history.csv）。
  · 离线基座没有指数/行业/资金流/逐股序列，本页不引入这些维度，不编造。
  · 时间序列化描述「投机情绪周期」（梯队厚→断层→退潮→冰点→重启），是描述性框架，
    不预测收益、不构成买卖建议。

取数失败优雅降级（available=False / 空序列）。
"""
import logging

import numpy as np
import pandas as pd

from modules import market_regime as mr

logger = logging.getLogger(__name__)

_COLS = {
    "connect_hl": "连板高度",
    "connect_2b": "连板家数(≥2板)",
    "zt_fail_ratio": "炸板率(%)",
    "zt_prev_ret": "昨日涨停表现(%)",
    "fc_ratio": "平均封成比",
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
    """取 5 个梯队质量维度的时间序列（按日期升序，窗口截断）。

    返回 {available, dates, series{col->[v]}, labels}。
    各序列为原始值（含 None），归一化在页面层按各自 min/max 处理。
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


def _classify(hl, tb, zr, zpr, fc):
    """极简相位判定（描述性，非预测）。"""
    if hl is not None and tb is not None and hl >= 6 and tb >= 15:
        return "亢奋", "连板高度≥6 且 连板家数≥15，投机情绪亢奋、梯队厚"
    if hl is not None and zr is not None and hl < 3 and zr > 50:
        return "退潮", "连板高度<3 且 炸板率>50%，封板分歧大、题材退潮"
    if tb is not None and tb < 5:
        return "梯队断层", "连板家数<5，赚钱效应梯队断层"
    if hl is not None and zpr is not None and hl < 3 and zpr < 0:
        return "冰点", "连板高度<3 且 昨日涨停表现<0，投机情绪冰点"
    return "中性", "未触发极端相位，投机情绪中性"


def current_phase(df: pd.DataFrame | None = None) -> dict:
    """最新一行的投机情绪相位。"""
    if df is None:
        try:
            df = load_breadth_history()
        except Exception:  # pragma: no cover
            return dict(available=False)
    if df is None or len(df) == 0:
        return dict(available=False)
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    if len(d) == 0:
        return dict(available=False)
    last = d.iloc[-1]
    hl = _f(last.get("connect_hl"))
    tb = _f(last.get("connect_2b"))
    zr = _f(last.get("zt_fail_ratio"))
    zpr = _f(last.get("zt_prev_ret"))
    fc = _f(last.get("fc_ratio"))
    phase, reason = _classify(hl, tb, zr, zpr, fc)
    return dict(
        available=True,
        date=str(last["date"].date()) if pd.notna(last["date"]) else None,
        connect_hl=hl, connect_2b=tb, zt_fail_ratio=zr, zt_prev_ret=zpr, fc_ratio=fc,
        phase=phase, reason=reason,
    )
