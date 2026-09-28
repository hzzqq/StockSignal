"""实时强势榜数据与评分（G8 纯逻辑层）。

抽取到模块层的目的：① 评分是纯函数，可单测；② 取数入口可被测试 monkeypatch，
页面只做编排（与 ``modules/shepherd`` 的测试模式一致）。

数据源：东财全市场实时快照 akshare ``stock_zh_a_spot_em``（缓存 60 秒）。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

# 东财快照列名候选（字段偶有增删，按候选表匹配而非硬编码）
COL = {
    "code": ["代码"],
    "name": ["名称"],
    "price": ["最新价"],
    "chg": ["涨跌幅"],
    "amount": ["成交额"],
    "turnover": ["换手率"],
    "vol_ratio": ["量比"],
}

# 评分权重（合计 1.0）：涨幅 0.40 / 量比 0.30 / 换手 0.20 / 成交额 0.10
WEIGHTS = {"chg": 0.40, "vol_ratio": 0.30, "turnover": 0.20, "amount": 0.10}


def _col(df: pd.DataFrame, key: str):
    for c in COL.get(key, []):
        if c in df.columns:
            return c
    return None


def _num(df: pd.DataFrame, key: str, default: float = 0.0) -> pd.Series:
    c = _col(df, key)
    if not c:
        return pd.Series([default] * len(df), index=df.index, dtype="float64")
    return pd.to_numeric(df[c], errors="coerce").fillna(default)


def _ordinal_pct(series: pd.Series) -> pd.Series:
    """百分位排名(0-100)，抗极值（单只巨量不会把其余压成一条线）。"""
    n = len(series)
    if n <= 1:
        return pd.Series([100.0] * n, index=series.index)
    return series.rank(pct=True, method="average") * 100.0


def strong_score(df: pd.DataFrame) -> pd.DataFrame:
    """多因子强势评分（启发式加权，非预测模型）。"""
    out = df.copy()
    out["_s_chg"] = _ordinal_pct(_num(df, "chg")).round(1)
    out["_s_vr"] = _ordinal_pct(_num(df, "vol_ratio")).round(1)
    out["_s_to"] = _ordinal_pct(_num(df, "turnover")).round(1)
    out["_s_amt"] = _ordinal_pct(_num(df, "amount")).round(1)
    out["_score"] = (
        WEIGHTS["chg"] * out["_s_chg"]
        + WEIGHTS["vol_ratio"] * out["_s_vr"]
        + WEIGHTS["turnover"] * out["_s_to"]
        + WEIGHTS["amount"] * out["_s_amt"]
    ).round(1)
    return out


def _spot_cached_akshare() -> pd.DataFrame:
    """akshare 兜底源（82.push2 子域在本机恒断连，仅当直连层 None 时才走）。"""
    import akshare as ak
    return ak.stock_zh_a_spot_em()


def _spot_impl() -> pd.DataFrame:
    """东财直连薄层优先（T-177）→ akshare 兜底；双失败异常上抛由页面诚实降级。"""
    from modules import em_snapshot as ems
    df = ems.fetch_a_spot_em()
    if df is not None and not df.empty:
        return df
    return _spot_cached_akshare()


@st.cache_data(ttl=60, show_spinner=False)
def _spot_cached() -> pd.DataFrame:
    """全市场实时快照（缓存 60s）。失败抛出，由调用方诚实降级。"""
    return _spot_impl()


def load_spot():
    """取快照并剔除非正常交易标的（ST/退市/新股）。取不到返回 None。"""
    df = _spot_cached()
    if df is None or df.empty:
        return None
    d = df.copy()
    name_c = _col(d, "name")
    if name_c:
        mask = ~d[name_c].astype(str).str.contains("ST|退|^N|^U", case=False, regex=True, na=False)
        d = d[mask]
    return d
