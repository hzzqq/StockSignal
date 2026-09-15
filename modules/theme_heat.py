"""题材/概念热度（G7）：数据获取 + 生命周期纯逻辑。

数据源：东财概念板块实时快照 akshare ``stock_board_concept_name_em``（缓存 120s）。

生命周期为**启发式分类**（非预测）：以板块涨跌幅 + 换手率分位划分
发酵（刚启动）/ 高潮（涨幅与热度双高）/ 退潮（放量下跌）/ 平淡。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

COL = {
    "name": ["板块名称"],
    "chg": ["涨跌幅"],
    "mv": ["总市值"],
    "turnover": ["换手率"],
    "up": ["上涨家数"],
    "down": ["下跌家数"],
    "leader": ["领涨股票"],
}


def col_of(df: pd.DataFrame, key: str):
    for c in COL.get(key, []):
        if c in df.columns:
            return c
    return None


def num_of(df: pd.DataFrame, key: str, default: float = 0.0) -> pd.Series:
    c = col_of(df, key)
    if not c:
        return pd.Series([default] * len(df), index=df.index, dtype="float64")
    return pd.to_numeric(df[c], errors="coerce").fillna(default)


def turnover_pct(df: pd.DataFrame) -> pd.Series:
    """换手率百分位(0-100)，抗极值。"""
    t = num_of(df, "turnover")
    if len(t) <= 1:
        return pd.Series([50.0] * len(t), index=t.index)
    return t.rank(pct=True, method="average") * 100.0


def lifecycle_label(chg_pct, turnover_p):
    """启发式生命周期：发酵 / 高潮 / 退潮 / 平淡。"""
    if chg_pct is None or turnover_p is None:
        return "未知"
    try:
        c, t = float(chg_pct), float(turnover_p)
    except (TypeError, ValueError):
        return "未知"
    if c != c or t != t:
        return "未知"
    if c >= 3.0 and t >= 70.0:
        return "高潮"
    if c >= 1.0 and t >= 40.0:
        return "发酵"
    if c < 0.0 and t >= 60.0:
        return "退潮"
    return "平淡"


LIFECYCLE_ORDER = ["高潮", "发酵", "退潮", "平淡", "未知"]


@st.cache_data(ttl=120, show_spinner=False)
def _concepts_cached() -> pd.DataFrame:
    import akshare as ak
    return ak.stock_board_concept_name_em()


def load_concepts():
    """取概念板块快照并派生生命周期列；取不到返回 None。"""
    df = _concepts_cached()
    if df is None or df.empty:
        return None
    d = df.copy()
    chg = num_of(d, "chg")
    tp = turnover_pct(d)
    d["_chg"] = chg
    d["_turnover_p"] = tp
    d["_life"] = [lifecycle_label(c, t) for c, t in zip(chg, tp)]
    return d
