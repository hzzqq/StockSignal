"""题材/概念热度（G7）：数据获取 + 生命周期纯逻辑。

数据源优先级：
1. 东财概念板块实时快照 ``ak.stock_board_concept_name_em``（缓存 120s）——原始口径含涨跌幅/换手率/总市值。
2. 东财失败（代理/限流/接口变更）→ 同花顺概念资金流 ``ak.stock_fund_flow_concept(symbol='即时')``——
   真实源含涨跌幅/净额/领涨股/公司家数，但**没有换手率和总市值**。

生命周期为**启发式分类**（非预测）：
- 东财：涨跌幅 + 换手率分位。
- 同花顺 fallback：涨跌幅 + 资金净额绝对值分位（热度代理，不冒充换手率）。

所有 fallback 都带 ``_source`` / ``_heat_basis`` 标记返回，由 API 显式透出口径，前端不得把代理量包装成东财市值。
"""
from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)

SOURCE_EM = "eastmoney"
SOURCE_THS = "ths_fund_flow"

COL = {
    "name": ["板块名称", "行业"],
    "chg": ["涨跌幅", "行业-涨跌幅"],
    "mv": ["总市值"],
    "turnover": ["换手率"],
    "up": ["上涨家数"],
    "down": ["下跌家数"],
    "leader": ["领涨股票", "领涨股"],
    "net": ["净额亿元", "净额"],
    "members": ["公司家数"],
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


def _net_yi(df: pd.DataFrame) -> pd.Series:
    """净额（亿元）数值化：兼容 float / '12.5亿' / '1,234'；缺值保留 NaN 不补零。"""
    c = col_of(df, "net")
    if not c:
        return pd.Series([float("nan")] * len(df), index=df.index, dtype="float64")

    def one(v):
        if v is None or (isinstance(v, float) and v != v):
            return float("nan")
        if isinstance(v, (int, float)):
            return float(v)
        t = str(v).strip().replace(",", "").replace("亿", "").replace("%", "")
        if not t:
            return float("nan")
        try:
            return float(t)
        except (TypeError, ValueError):
            return float("nan")

    return df[c].map(one).astype("float64")


def turnover_pct(df: pd.DataFrame) -> pd.Series:
    """换手率百分位(0-100)，抗极值。"""
    t = num_of(df, "turnover")
    if len(t) <= 1:
        return pd.Series([50.0] * len(t), index=t.index)
    return t.rank(pct=True, method="average") * 100.0


def heat_pct(df: pd.DataFrame) -> pd.Series:
    """热度分位：东财用换手率；同花顺 fallback 用资金净额绝对值。绝不混用冒充。"""
    if col_of(df, "turnover") is not None:
        return turnover_pct(df)
    net = _net_yi(df).abs()
    if len(net) <= 1:
        return pd.Series([50.0] * len(net), index=net.index)
    p = net.rank(pct=True, method="average") * 100.0
    return p.fillna(50.0)


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


def _fetch_eastmoney():
    import akshare as ak

    df = ak.stock_board_concept_name_em()
    if df is None or df.empty:
        return None
    d = df.copy()
    d["_source"] = SOURCE_EM
    d["_heat_basis"] = "换手率分位"
    return d


def _fetch_ths_fund_flow():
    """同花顺概念资金流 fallback：真实涨跌幅/净额/领涨股；无总市值、无换手率。"""
    import akshare as ak

    df = ak.stock_fund_flow_concept(symbol="即时")
    if df is None or df.empty:
        return None
    d = df.rename(columns={
        "行业": "板块名称",
        "行业-涨跌幅": "涨跌幅",
        "领涨股": "领涨股票",
    }).copy()
    keep = [c for c in ("板块名称", "涨跌幅", "净额", "公司家数", "领涨股票") if c in d.columns]
    d = d[keep].copy()
    if "板块名称" not in d.columns:
        return None
    d["_source"] = SOURCE_THS
    d["_heat_basis"] = "资金净额绝对值分位"
    return d


@st.cache_data(ttl=120, show_spinner=False)
def _concepts_cached() -> pd.DataFrame:
    try:
        d = _fetch_eastmoney()
        if d is not None:
            return d
        logger.warning("[theme] 东财概念板块快照为空，切换同花顺概念资金流")
    except Exception as e:  # noqa: BLE001 - 主源失败必须留痕并继续 fallback
        logger.warning("[theme] 东财概念板块快照失败，切换同花顺概念资金流: %s", e)

    try:
        d = _fetch_ths_fund_flow()
        if d is not None:
            return d
        logger.warning("[theme] 同花顺概念资金流为空")
    except Exception as e:  # noqa: BLE001 - 备用源失败必须留痕，返回空让上层诚实降级
        logger.warning("[theme] 同花顺概念资金流失败: %s", e)
    return pd.DataFrame()


def load_concepts():
    """取概念板块快照并派生生命周期列；两源都取不到返回 None。

    返回列除原始字段外新增：``_chg``/``_turnover_p``/``_heat``/``_net_yi``/``_life``/
    ``_source``/``_heat_basis``。``_turnover_p`` 为兼容旧调用方保留，语义由 ``_heat_basis`` 显式给出。
    """
    df = _concepts_cached()
    if df is None or df.empty:
        return None
    d = df.copy()
    chg = num_of(d, "chg")
    hp = heat_pct(d)
    d["_chg"] = chg
    d["_turnover_p"] = hp
    d["_heat"] = hp
    d["_net_yi"] = _net_yi(d)
    d["_life"] = [lifecycle_label(c, t) for c, t in zip(chg, hp)]  # noqa: B905
    return d
