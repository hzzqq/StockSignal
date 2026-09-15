"""财报猎手（G10）纯逻辑：业绩预告信号的解析与分级。

数据源：``modules.fundflow.get_earnings_forecast(period)`` → 东财 ``stock_yjyg_em``。

信号分级为**启发式**（按预告类型文本），仅用于快速筛查「值得看一眼」的标的，
非投资建议、非预测。
"""
from __future__ import annotations

import pandas as pd

COL = {
    "code": ["股票代码"],
    "name": ["股票简称"],
    "type": ["预告类型"],
    "pct": ["业绩变动幅度"],
    "reason": ["业绩变动原因"],
    "date": ["公告日期"],
    "metric": ["预测指标"],
}


def col_of(df: pd.DataFrame, key: str):
    for c in COL.get(key, []):
        if c in df.columns:
            return c
    return None


def signal_of(type_text) -> str:
    """预告类型 → 信号级别：利好 / 偏多 / 利空 / 偏空 / 中性。"""
    t = str(type_text or "")
    if "扭亏" in t or "预增" in t:
        return "利好"
    if "略增" in t or "续盈" in t:
        return "偏多"
    if "首亏" in t or "预减" in t:
        return "利空"
    if "略减" in t or "续亏" in t:
        return "偏空"
    return "中性"


SIGNAL_ORDER = ["利好", "偏多", "中性", "偏空", "利空"]


def annotate(df: pd.DataFrame) -> pd.DataFrame:
    """加 ``_signal`` 列与数值化 ``_pct`` 列（纯函数，可单测）。"""
    if df is None or len(df) == 0:
        return pd.DataFrame()
    d = df.copy()
    type_c = col_of(d, "type")
    d["_signal"] = d[type_c].map(signal_of) if type_c else "中性"
    pct_c = col_of(d, "pct")
    d["_pct"] = pd.to_numeric(d[pct_c], errors="coerce") if pct_c else float("nan")
    return d


def scan(df: pd.DataFrame, min_pct: float | None = None,
         signals: list | None = None) -> pd.DataFrame:
    """按信号级别 / 最小变动幅度筛选，并按变动幅度降序。"""
    d = annotate(df)
    if d.empty:
        return d
    if signals:
        d = d[d["_signal"].isin(signals)]
    if min_pct is not None:
        d = d[d["_pct"].fillna(-1e9) >= float(min_pct)]
    if "_pct" in d.columns:
        d = d.sort_values("_pct", ascending=False)
    return d
