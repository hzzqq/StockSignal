"""题材/概念热度（G7）：数据获取 + 生命周期纯逻辑。

三级降级链（每级都标 ``_source`` / ``_heat_basis``，绝不冒充换手率/总市值）：
1. **东财概念板块快照**（``ak.stock_board_concept_name_em``）——字段最全（涨跌幅/总市值/换手率/涨跌家数/领涨股）。
   akshare 官方入口写死 ``79.push2.eastmoney.com``，本机代理下会拦；失败后**切东财主域直连**
   ``push2.eastmoney.com``（同一 clist 接口，字段映射等价）。
2. **同花顺概念资金流**（``ak.stock_fund_flow_concept(symbol='即时')``）——涨跌幅/净额/领涨股/公司家数，无总市值/换手率。
3. **新浪概念板块**（``ak.stock_sector_spot(indicator='概念')``）——涨跌幅/领涨股/公司家数，无总市值/换手率/净额。

生命周期为**启发式分类**（非预测）：
- 东财：涨跌幅 + 换手率分位。
- 同花顺 fallback：涨跌幅 + 资金净额绝对值分位（热度代理，不冒充换手率）。
- 新浪 fallback：涨跌幅 + 公司家数分位（热度代理）。
"""
from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)

SOURCE_EM = "eastmoney"
SOURCE_THS = "ths_fund_flow"
SOURCE_SINA = "sina_concept"

COL = {
    "name": ["板块名称", "行业", "板块"],
    "chg": ["涨跌幅", "行业-涨跌幅"],
    "mv": ["总市值"],
    "turnover": ["换手率"],
    "up": ["上涨家数"],
    "down": ["下跌家数"],
    "leader": ["领涨股票", "领涨股", "股票名称"],
    "net": ["净额亿元", "净额"],
    "members": ["公司家数"],
}

_EM_FIELDS = "f2,f3,f4,f8,f12,f14,f20,f104,f105,f128"
_EM_RENAME = {
    "f3": "涨跌幅", "f8": "换手率", "f12": "板块代码", "f14": "板块名称",
    "f20": "总市值", "f104": "上涨家数", "f105": "下跌家数", "f128": "领涨股票",
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
    """热度分位：东财用换手率；同花顺 fallback 用资金净额绝对值；新浪 fallback 用公司家数。绝不混用冒充。"""
    if col_of(df, "turnover") is not None:
        return turnover_pct(df)
    net = _net_yi(df)
    if net.notna().any() and len(net) > 1:
        p = net.abs().rank(pct=True, method="average") * 100.0
        return p.fillna(50.0)
    members = num_of(df, "members")
    if len(members) > 1:
        p = members.rank(pct=True, method="average") * 100.0
        return p.fillna(50.0)
    if len(net) == 1:
        return pd.Series([50.0], index=net.index)
    return pd.Series([50.0] * len(df), index=df.index)


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


def _mark(df: pd.DataFrame, source: str, heat_basis: str) -> pd.DataFrame:
    d = df.copy()
    d["_source"] = source
    d["_heat_basis"] = heat_basis
    return d


def _fetch_eastmoney():
    """东财主源：先 akshare 官方入口，被代理拦后切主域直连（同一接口、等价字段映射）。"""
    import akshare as ak

    try:
        df = ak.stock_board_concept_name_em()
        if df is not None and not df.empty:
            return _mark(df, SOURCE_EM, "换手率分位")
        logger.warning("[theme] 东财概念板块快照为空，切主域直连")
    except Exception as e:  # noqa: BLE001 - 官方入口失败必须留痕并继续直连
        logger.warning("[theme] 东财概念板块 akshare 入口失败，切主域直连: %s", e)

    import requests

    rows = []
    params = {
        "pz": "100", "po": "1", "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2", "invt": "2", "fid": "f12",
        "fs": "m:90 t:3 f:!50",
        "fields": _EM_FIELDS,
    }
    for pn in range(1, 21):
        params["pn"] = str(pn)
        r = requests.get(
            "https://push2.eastmoney.com/api/qt/clist/get",
            params=params, timeout=12,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        r.raise_for_status()
        diff = ((r.json() or {}).get("data") or {}).get("diff") or []
        if isinstance(diff, dict):
            diff = [diff[k] for k in sorted(diff, key=lambda x: int(x))]
        rows.extend(diff)
        if len(diff) < 100:
            break
    df = pd.DataFrame(rows).rename(columns=_EM_RENAME)
    if df.empty or "板块名称" not in df.columns:
        return None
    for c in ("涨跌幅", "总市值", "换手率", "上涨家数", "下跌家数"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return _mark(df, SOURCE_EM, "换手率分位")


def _fetch_ths_fund_flow():
    """同花顺概念资金流：真实涨跌幅/净额/领涨股；无总市值、无换手率。"""
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
    return _mark(d, SOURCE_THS, "资金净额绝对值分位")


def _fetch_sina_concept():
    """新浪概念板块（第三级）：涨跌幅/领涨股/公司家数；无总市值/换手率/净额。"""
    import akshare as ak

    df = ak.stock_sector_spot(indicator="概念")
    if df is None or df.empty:
        return None
    d = df.rename(columns={
        "板块": "板块名称",
        "股票名称": "领涨股票",
    }).copy()
    keep = [c for c in ("板块名称", "涨跌幅", "公司家数", "领涨股票") if c in d.columns]
    d = d[keep].copy()
    if "板块名称" not in d.columns:
        return None
    return _mark(d, SOURCE_SINA, "公司家数分位")


@st.cache_data(ttl=120, show_spinner=False)
def _concepts_cached() -> pd.DataFrame:
    fetchers = (
        (_fetch_eastmoney, "东财概念板块快照"),
        (_fetch_ths_fund_flow, "同花顺概念资金流"),
        (_fetch_sina_concept, "新浪概念板块"),
    )
    for fn, label in fetchers:
        try:
            d = fn()
            if d is not None:
                return d
            logger.warning("[theme] %s 为空，降级", label)
        except Exception as e:  # noqa: BLE001 - 每级失败必须留痕并继续降级
            logger.warning("[theme] %s 失败: %s", label, e)
    return pd.DataFrame()


def load_concepts():
    """取概念板块快照并派生生命周期列；三级全取不到返回 None。

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
