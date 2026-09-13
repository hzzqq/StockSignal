"""
模块 inflection_scanner：情绪拐点扫描器（方案⑨）

数据边界（诚实声明，实测确认 2026-09-11）：
  · 仅对离线健康镜像可靠填充的广度维度（REAL_FEATURES）算滚动 z-score（窗口 60 日），
    检测「极端后反转」形态：自 < -2 回升越过 -1 → 触底反转；自 > +2 回落越过 +1 → 触顶回落。
  · 连板梯队类维度离线缺真值，已通过 `usable_dims` 闸门剔除，**不扫描、不编造**。
  · 仅描述历史序列的拐点形态，**不构成方向预测、不构成买卖建议**。

取数失败优雅降级（available=False）。
"""
import logging

import numpy as np
import pandas as pd

from modules import market_regime as mr
from modules.breadth_features import REAL_FEATURES, labels as _labels, usable_dims

logger = logging.getLogger(__name__)
_LABELS = _labels()
_DOWN, _UP = -2.0, 2.0
_RECOVER_DOWN, _RECOVER_UP = -1.0, 1.0


def load_breadth_history() -> pd.DataFrame:
    return mr.load_breadth_history()


def _zscore(x, window):
    s = pd.Series(x, dtype=float)
    roll = s.rolling(window, min_periods=max(10, window // 2))
    m = roll.mean()
    sd = roll.std()
    return ((s - m) / sd).values


def _r(v):
    return None if v is None or (isinstance(v, float) and v != v) else round(float(v), 3)


def list_events(df: pd.DataFrame | None = None, dims=None,
                window: int = 60, recent: int = 20) -> dict:
    """扫描所有可用维度的近期拐点事件（末 recent 个交易日内）。"""
    if df is None:
        try:
            df = load_breadth_history()
        except Exception as exc:  # pragma: no cover
            logger.warning("breadth load failed: %s", exc)
            return dict(available=False, events=[], dropped={})
    if df is None or len(df) == 0:
        return dict(available=False, events=[], dropped={})

    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    n = len(d)

    dims, dropped = usable_dims(d, candidate=(dims or REAL_FEATURES))
    out = []
    for c in dims:
        x = pd.to_numeric(d[c], errors="coerce").values.astype(float)
        if np.all(np.isnan(x)):
            continue
        z = _zscore(x, window)
        state, ext_z, ext_v = "none", None, None
        for i in range(1, n):
            zi = z[i]
            if zi != zi:
                continue
            if state == "none":
                if zi < _DOWN:
                    state, ext_z, ext_v = "down", zi, x[i]
                elif zi > _UP:
                    state, ext_z, ext_v = "up", zi, x[i]
            elif state == "down":
                if zi < ext_z:
                    ext_z, ext_v = zi, x[i]
                elif zi > _RECOVER_DOWN:
                    if i >= n - recent:
                        out.append(dict(dim=c, label=_LABELS.get(c, c),
                                       date=str(d["date"].iloc[i].date()),
                                       type="触底反转", extreme=_r(ext_v), current=_r(x[i])))
                    state, ext_z, ext_v = "none", None, None
            elif state == "up":
                if zi > ext_z:
                    ext_z, ext_v = zi, x[i]
                elif zi < _RECOVER_UP:
                    if i >= n - recent:
                        out.append(dict(dim=c, label=_LABELS.get(c, c),
                                       date=str(d["date"].iloc[i].date()),
                                       type="触顶回落", extreme=_r(ext_v), current=_r(x[i])))
                    state, ext_z, ext_v = "none", None, None
    out.sort(key=lambda e: e["date"])
    return dict(available=True, dims=dims, dropped=dropped, events=out)


def series_for(dim: str, df: pd.DataFrame | None = None, window: int = 60) -> dict:
    """取单维度的原始值与 z-score（供页面画折线 + 拐点标注）。"""
    if df is None:
        try:
            df = load_breadth_history()
        except Exception:  # pragma: no cover
            return dict(available=False, dates=[], raw=[], z=[], markers=[])
    if df is None or len(df) == 0 or dim not in df.columns:
        return dict(available=False, dates=[], raw=[], z=[], markers=[])
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    if dim not in d.columns:
        return dict(available=False, dates=[], raw=[], z=[], markers=[])
    x = pd.to_numeric(d[dim], errors="coerce").values.astype(float)
    z = _zscore(x, window)
    dates = [str(t.date()) for t in d["date"]]
    markers = []
    state, ext_z = "none", None
    for i in range(1, len(z)):
        zi = z[i]
        if zi != zi:
            continue
        if state == "none":
            if zi < _DOWN:
                state, ext_z = "down", zi
            elif zi > _UP:
                state, ext_z = "up", zi
        elif state == "down":
            if zi < ext_z:
                ext_z = zi
            elif zi > _RECOVER_DOWN:
                markers.append(i)
                state, ext_z = "none", None
        elif state == "up":
            if zi > ext_z:
                ext_z = zi
            elif zi < _RECOVER_UP:
                markers.append(i)
                state, ext_z = "none", None
    return dict(available=True, label=_LABELS.get(dim, dim), dates=dates,
                raw=[_r(v) for v in x], z=[None if v != v else round(float(v), 2) for v in z],
                markers=markers)
