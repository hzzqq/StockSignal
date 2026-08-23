"""
tests/test_finance_contract.py — 财务契约层 + FIFO 逻辑锁定测试

目标：锁住持仓/盈亏的财务语义正确性，防止重构静默漂移：
- finance_contract 的 schema 校验（缺列/多列/空 DataFrame/非 DataFrame）fail-fast
- PNL_OUTPUT_COLUMNS 契约稳定（任何重构不得增删）
- allocate_fifo：分批建仓 Σ各行 remaining == 整票真实剩余（防旧实现 2x 市值虚增回归）
- compute_realized_fifo：FIFO 已实现盈亏正确（先买批次先被吃）
"""
import pandas as pd
import pytest

from modules import finance_contract as fc
from modules.portfolio import allocate_fifo, compute_realized_fifo


# ─────────────────────────────────────────────────────────────
#  schema 校验
# ─────────────────────────────────────────────────────────────
def test_validate_position_schema_ok():
    df = pd.DataFrame({
        "ticker": ["600519"], "buy_date": ["2024-01-01"],
        "buy_price": [100.0], "shares": [100], "cost": [10000.0],
    })
    fc.validate_position_schema(df)  # 不应抛


def test_validate_position_schema_missing_column():
    df = pd.DataFrame({"ticker": ["600519"], "buy_price": [100.0]})
    with pytest.raises(fc.FinanceContractError):
        fc.validate_position_schema(df)


def test_validate_position_schema_require_remaining():
    df = pd.DataFrame({
        "ticker": ["600519"], "buy_date": ["2024-01-01"],
        "buy_price": [100.0], "shares": [100], "cost": [10000.0],
    })
    with pytest.raises(fc.FinanceContractError):
        fc.validate_position_schema(df, require_remaining=True)


def test_validate_position_schema_non_df():
    with pytest.raises(fc.FinanceContractError):
        fc.validate_position_schema([1, 2, 3])


def test_validate_position_schema_empty_ok():
    fc.validate_position_schema(pd.DataFrame())  # 空 DataFrame 直接放行


def test_validate_pnl_output_strict_columns():
    df = pd.DataFrame(columns=fc.PNL_OUTPUT_COLUMNS)
    fc.validate_pnl_output(df)  # 列齐，空行也放行
    # 缺一列
    df2 = pd.DataFrame(columns=fc.PNL_OUTPUT_COLUMNS[:-1])
    with pytest.raises(fc.FinanceContractError):
        fc.validate_pnl_output(df2)
    # 多一列（误加字段）
    df3 = pd.DataFrame(columns=fc.PNL_OUTPUT_COLUMNS + ["bonus"])
    with pytest.raises(fc.FinanceContractError):
        fc.validate_pnl_output(df3)


def test_pnl_output_columns_stable():
    # 契约列不可随意变动（重构若需增删必须同步改常量+本测试）
    assert fc.PNL_OUTPUT_COLUMNS == [
        "ticker", "name", "buy_date", "buy_price", "shares",
        "remaining_shares", "cost", "current_price", "market_value",
        "realized_pnl", "pnl", "pnl_pct",
    ]


# ─────────────────────────────────────────────────────────────
#  allocate_fifo：防 2x 市值虚增回归
# ─────────────────────────────────────────────────────────────
def test_allocate_fifo_sum_equals_real_remaining():
    """分批建仓 100 + 200 股，卖出 50 股，Σ各行 remaining 必须 == 250。"""
    positions = pd.DataFrame({
        "ticker": ["X", "X"],
        "buy_date": ["2024-01-01", "2024-02-01"],
        "shares": [100, 200],
    })
    sold_map = {"X": 50}
    remaining, consumed = allocate_fifo(positions, sold_map)
    assert sum(remaining) == 250           # 真实剩余：300 - 50
    assert sum(consumed) == 50             # 总卖出
    # 先买批次先被吃：第一批剩 50、第二批满 200
    assert remaining[0] == 50
    assert remaining[1] == 200


def test_allocate_fifo_exhaust_first_batch():
    """卖出 120 股 > 第一批 100：跨批次吃，第一批归零、第二批剩 180。"""
    positions = pd.DataFrame({
        "ticker": ["X", "X"],
        "buy_date": ["2024-01-01", "2024-02-01"],
        "shares": [100, 200],
    })
    remaining, consumed = allocate_fifo(positions, {"X": 120})
    assert remaining[0] == 0
    assert remaining[1] == 180
    assert sum(remaining) == 180


def test_allocate_fifo_multiple_tickers_independent():
    """两只股票独立 FIFO，互不串扰。"""
    positions = pd.DataFrame({
        "ticker": ["A", "A", "B"],
        "buy_date": ["2024-01-01", "2024-02-01", "2024-01-15"],
        "shares": [100, 200, 50],
    })
    remaining, _ = allocate_fifo(positions, {"A": 50, "B": 50})
    assert remaining[0] == 50   # A 第一批剩 50
    assert remaining[1] == 200  # A 第二批满
    assert remaining[2] == 0    # B 全卖
    assert sum(remaining) == 250


def test_allocate_fifo_sell_more_than_held():
    """卖出超过总持仓：剩余全 0，不出现负股数。"""
    positions = pd.DataFrame({
        "ticker": ["X", "X"],
        "buy_date": ["2024-01-01", "2024-02-01"],
        "shares": [100, 200],
    })
    remaining, consumed = allocate_fifo(positions, {"X": 999})
    assert all(r == 0 for r in remaining)
    assert sum(consumed) == 300


def test_allocate_fifo_empty():
    positions = pd.DataFrame(columns=["ticker", "buy_date", "shares"])
    remaining, consumed = allocate_fifo(positions, {})
    assert remaining == [] and consumed == []


# ─────────────────────────────────────────────────────────────
#  compute_realized_fifo：FIFO 语义
# ─────────────────────────────────────────────────────────────
def test_realized_fifo_basic():
    """两批买入 10@100、10@110，卖 15@120 → 已实现 = 10*20 + 5*10 = 250。"""
    buy = [(100.0, 10), (110.0, 10)]
    sell = [(120.0, 15)]
    assert compute_realized_fifo(buy, sell) == 250.0


def test_realized_fifo_loss():
    """买 10@100，卖 10@90 → 亏损 100。"""
    assert compute_realized_fifo([(100.0, 10)], [(90.0, 10)]) == -100.0


def test_realized_fifo_partial_cross_batch():
    """买 10@100、10@200，卖 5@150 → 只吃第一批 5 股，盈亏 5*50=250。"""
    buy = [(100.0, 10), (200.0, 10)]
    sell = [(150.0, 5)]
    assert compute_realized_fifo(buy, sell) == 250.0


def test_realized_fifo_no_sell():
    assert compute_realized_fifo([(100.0, 10)], []) == 0.0


def test_realized_fifo_sell_exceeds_buy():
    """卖超过买：多卖部分无批次可吃，按已吃批次算（不报错、不无限循环）。"""
    r = compute_realized_fifo([(100.0, 10)], [(120.0, 999)])
    assert r == 200.0  # 只 10 股被吃


def test_realized_fifo_zero_shares_batch_safe():
    """买入批次含 0 股脏数据：应安全跳过、不死循环。"""
    r = compute_realized_fifo([(100.0, 0), (100.0, 10)], [(120.0, 5)])
    assert r == 100.0  # 只第二批 5 股被吃
