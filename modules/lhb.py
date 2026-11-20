"""modules/lhb.py — 龙虎榜取数与摘要（补空白）。

为什么补：龙虎榜是 A 股最经典的「席位级资金博弈 + 事件驱动」信号源，
但 StockSignal 此前只有板块/个股层面的资金流向，没有席位级别的龙虎榜。
对「事件驱动 + 情绪决策」的定位来说，游资/机构席位动向是直接的证据。

红线：
- 取不到返回 ``None``，**不臆造明细**；所有结果必须带真实交易日。
- 列名按**子串匹配**（akshare 各版本列名会变），匹配不到就返回 None，
  不做"猜一个列出来"的事 —— 猜错列等于给出错误的资金方向，比缺失更危险。
- **请求日 ≠ 数据日**：``fetch_lhb(date)`` 的 date 是"向数据源要哪一天"的
  技术参数（缺省才用今天）；真实**数据日**只能从明细自带的日期列解析
  （见 :func:`data_date`）。对外暴露的日期必须是数据日，绝不用 now() 冒充。
"""
from __future__ import annotations

import logging

import pandas as pd

from modules.time_utils import now_cst_str

logger = logging.getLogger(__name__)

CODE_CANDS = ("代码",)
NAME_CANDS = ("名称", "股票名称")
REASON_CANDS = ("上榜原因", "上榜")
PCT_CANDS = ("涨跌幅",)
NET_BUY_CANDS = ("净买额", "净买入", "龙虎榜净买")
AMOUNT_CANDS = ("龙虎榜成交额", "成交额")
# 明细自带的数据日列（东财 TRADE_DATE → 上榜日）
DATE_CANDS = ("上榜日", "交易日期", "上榜日期", "日期")


def find_col(df: pd.DataFrame, cands: tuple) -> str | None:
    """按子串找列；找不到返回 None（不猜）。"""
    for c in df.columns:
        for cand in cands:
            if cand in str(c):
                return c
    return None


def data_date(df: pd.DataFrame | None) -> str | None:
    """从明细行里解析**真实数据日**（YYYYMMDD）；解析不出返回 None。

    红线：数据日只能来自明细自带的日期列（东财 TRADE_DATE → 上榜日）。
    明细里没有日期列 / 日期无法解析 → None（调用方据此声明"数据日不可得"），
    **绝不**用 now()/today() 兜底冒充数据日。
    """
    if df is None or getattr(df, "empty", True):
        return None
    # 候选优先级匹配（比 find_col 的列序优先更稳：先认"上榜日"这类专有列名）
    col = None
    for cand in DATE_CANDS:
        for c in df.columns:
            if cand in str(c):
                col = c
                break
        if col is not None:
            break
    if col is None:
        return None
    try:
        parsed = pd.to_datetime(df[col], errors="coerce").dropna()
    except Exception as e:  # noqa: BLE001
        logger.info(f"[lhb] 数据日解析失败: {e}")
        return None
    if parsed.empty:
        return None
    # 单日查询下所有行同一天；若有多个，取最新的一天（明细里真实存在的日期）
    return parsed.max().strftime("%Y%m%d")


def fetch_lhb(date: str | None = None) -> pd.DataFrame | None:
    """取某交易日龙虎榜明细。``date`` 形如 ``20260915``；``None`` 用今天。

    注意区分两个日期：
    - **请求日**（本函数的 date 入参）：只是"向数据源要哪一天"的技术参数，
      缺省取今天（用 CST，避免非中国时区部署取错一天）；
    - **数据日**：明细里每行自带的真实交易日，由 :func:`data_date` 解析。
    对外暴露的日期必须是数据日，绝不能用请求日/今天冒充。
    """
    try:
        import akshare as ak
    except Exception as e:  # noqa: BLE001
        logger.info(f"[lhb] akshare 不可用: {e}")
        return None
    d = date or now_cst_str("%Y%m%d")  # 请求日（技术参数），不是数据日
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
