"""
持仓 / 盈亏数据契约层。

把「分批建仓 FIFO」「已实现盈亏 FIFO」「remaining_shares 契约」等财务语义
从代码注释提升为**可机器校验的 schema**，供 ``get_positions`` / ``calc_pnl`` /
``summary`` 入口 fail-fast 校验，避免日后加字段 / 改结构时无声漂移
（替代「靠正则守门」的补丁文化——正则挡不住语义漂移，schema 能挡）。

契约要点（详见 docs/finance_contract.md）：
- 同一股票分批建仓会有多行；剩余股数必须按买入日期升序「先进先出」逐行分配，
  Σ各行 remaining_shares == 整票真实剩余（allocate_fifo 契约）。
- 已实现盈亏同样按 FIFO：先买的批次先被卖，Σ(卖价-批次买价)×吃货股数
  （compute_realized_fifo 契约），与 allocate_fifo 同一套 FIFO 语义。
- calc_pnl 输出列固定为 PNL_OUTPUT_COLUMNS，任何重构不得增删，
  否则 validate_pnl_output 直接失败。
"""

from __future__ import annotations

import pandas as pd


class FinanceContractError(ValueError):
    """持仓 / 盈亏数据违反契约时抛出（fail-fast）。"""


# 持仓原始行（portfolio.csv 落盘）必须包含的稳定列
POSITION_REQUIRED_COLUMNS = {"ticker", "buy_date", "buy_price", "shares", "cost"}
# get_positions 额外产出的派生列
POSITION_DERIVED_COLUMNS = {"remaining_shares", "name"}
# calc_pnl 输出列契约：任何重构不得增删，除非同步改本常量 + 测试
PNL_OUTPUT_COLUMNS = [
    "ticker", "name", "buy_date", "buy_price", "shares",
    "remaining_shares", "cost", "current_price", "market_value",
    "realized_pnl", "pnl", "pnl_pct",
]
# 卖出交易记录必须包含的列
TRADE_REQUIRED_COLUMNS = {"ticker", "sell_date", "sell_price", "sell_shares"}


def validate_position_schema(df: pd.DataFrame, *, require_remaining: bool = False) -> None:
    """fail-fast 校验持仓 DataFrame 符合契约。

    :param require_remaining: True 时还要求已含 derived 列 remaining_shares
                              （即应先跑过 get_positions）
    """
    if not isinstance(df, pd.DataFrame):
        raise FinanceContractError(f"持仓必须是 DataFrame，收到 {type(df).__name__}")
    if df.empty:
        return
    missing = POSITION_REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise FinanceContractError(f"持仓缺少必需列: {sorted(missing)}")
    if require_remaining and "remaining_shares" not in df.columns:
        raise FinanceContractError(
            "持仓缺少派生列 remaining_shares（应先跑 get_positions 做 FIFO 分配）"
        )


def validate_pnl_output(df: pd.DataFrame) -> None:
    """fail-fast 校验 calc_pnl 输出列严格等于契约（不多不少）。"""
    if not isinstance(df, pd.DataFrame):
        raise FinanceContractError(f"盈亏必须是 DataFrame，收到 {type(df).__name__}")
    if df.empty:
        return
    cols = set(df.columns)
    missing = set(PNL_OUTPUT_COLUMNS) - cols
    if missing:
        raise FinanceContractError(f"盈亏输出缺少契约列: {sorted(missing)}")
    extra = cols - set(PNL_OUTPUT_COLUMNS)
    if extra:
        raise FinanceContractError(f"盈亏输出出现非契约列（疑似误加字段）: {sorted(extra)}")
