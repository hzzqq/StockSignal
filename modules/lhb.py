"""modules/lhb.py — 龙虎榜取数与摘要（补空白）。

为什么补：龙虎榜是 A 股最经典的「席位级资金博弈 + 事件驱动」信号源，
但 StockSignal 此前只有板块/个股层面的资金流向，没有席位级别的龙虎榜。
对「事件驱动 + 情绪决策」的定位来说，游资/机构席位动向是直接的证据。

红线：
- 取不到返回 ``None``，**不臆造明细**；所有结果必须带真实交易日。
- 列名按**子串匹配**（akshare 各版本列名会变），匹配不到就返回 None，
  不做"猜一个列出来"的事 —— 猜错列等于给出错误的资金方向，比缺失更危险。
"""
from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)

CODE_CANDS = ("代码",)
NAME_CANDS = ("名称", "股票名称")
REASON_CANDS = ("上榜原因", "上榜")
PCT_CANDS = ("涨跌幅",)
NET_BUY_CANDS = ("净买额", "净买入", "龙虎榜净买")
AMOUNT_CANDS = ("龙虎榜成交额", "成交额")


def find_col(df: pd.DataFrame, cands: tuple) -> str | None:
    """按子串找列；找不到返回 None（不猜）。"""
    for c in df.columns:
        for cand in cands:
            if cand in str(c):
                return c
    return None


def fetch_lhb(date: str | None = None) -> pd.DataFrame | None:
    """取某交易日龙虎榜明细。``date`` 形如 ``20260915``；``None`` 用今天。

    取不到（akshare 缺失 / 网络失败 / 非交易日无数据）返回 None。
    """
    try:
        import akshare as ak
    except Exception as e:  # noqa: BLE001
        logger.info(f"[lhb] akshare 不可用: {e}")
        return None
    d = date or datetime.now().strftime("%Y%m%d")
    try:
        df = ak.stock_lhb_detail_em(start_date=d, end_date=d)
    except Exception as e:  # noqa: BLE001
        logger.info(f"[lhb] 龙虎榜取数失败({d}): {e}")
        return None
    if df is None or getattr(df, "empty", True):
        return None
    return df


def summarize(df: pd.DataFrame, top_n: int = 15) -> dict | None:
    """从明细里抽出净买入 Top / 净卖出 Top 与家数。

    净买额列匹配不到时返回 ``None`` —— 宁可什么都不显示，也不用错列编出方向。
    """
    if df is None or getattr(df, "empty", True):
        return None
    net_col = find_col(df, NET_BUY_CANDS)
    code_col = find_col(df, CODE_CANDS)
    name_col = find_col(df, NAME_CANDS)
    if net_col is None:
        return None

    work = df.copy()
    work["_net"] = pd.to_numeric(work[net_col], errors="coerce")
    work = work.dropna(subset=["_net"])
    if work.empty:
        return None

    cols = [c for c in (code_col, name_col) if c]
    buy = work.sort_values("_net", ascending=False).head(top_n)
    sell = work.sort_values("_net", ascending=True).head(top_n)

    def _pick(part):
        out = part[cols + ["_net"]].copy() if cols else part[["_net"]].copy()
        out = out.rename(columns={"_net": "净买额"})
        return out

    return {
        "count": int(len(work)),
        "net_col": net_col,
        "net_sum": float(work["_net"].sum()),
        "buy_top": _pick(buy),
        "sell_top": _pick(sell),
    }
