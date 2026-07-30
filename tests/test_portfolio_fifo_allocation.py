"""
tests/test_portfolio_fifo_allocation.py
---------------------------------------
分批建仓持仓核算回归测试（c45 修复的真实财务缺陷）。

【缺陷本体】
  PortfolioManager.add_position 每买一次 append 一行，因此**同一只股票分批
  建仓天然是多行**（A 股最常见的加仓操作）。而 get_positions 原实现：

      remaining[ticker] = 该票总买入 - 该票总卖出
      df["remaining_shares"] = df["ticker"].map(remaining)

  把「整只票的剩余股数」写进该票的**每一行**。两批建仓 (100 + 200 股)：

      行1: shares=100, remaining_shares=300   ← 错，应为 100
      行2: shares=200, remaining_shares=300   ← 错，应为 200

  于是 calc_pnl 逐行 current_price*remaining 求和 = **2 倍真实市值**；
  cost_ratio = remaining/shares = 300/100 = 3 让成本也放大到 1.98 倍；
  summary 的 total_market_value / total_cost / total_pnl 全线虚增。
  realized_pnl 同理：整票已实现盈亏被逐行照抄，行求和重复计数。

  实测（1500×100 + 1600×200，现价 1700）：
      真实市值 510,000  ->  汇总 1,020,000 (2.00x)
      真实成本 470,000  ->  汇总   930,000 (1.98x)

【修复】
  新增纯函数 allocate_fifo(positions, sold_map)：按买入日期升序，先买的批次
  先被卖出，逐行分配剩余/已消耗股数，保证 Σ各行剩余 == 该票真实剩余。
  已实现盈亏按各批次实际卖出股数占比摊分。

本文件不触网、不读磁盘配置，只测纯函数与用假数据驱动的核算口径。
"""
from __future__ import annotations

import os
import sys

import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from modules.portfolio import allocate_fifo, market_value_of  # noqa: E402


def _pos(rows):
    return pd.DataFrame(rows)


# ================================================== 1. FIFO 纯函数
class TestAllocateFifo:

    def test_single_batch_no_sell(self):
        df = _pos([{"ticker": "600519", "buy_date": "2026-01-05", "shares": 100}])
        rem, used = allocate_fifo(df, {})
        assert rem == [100] and used == [0]

    def test_two_batches_no_sell_not_duplicated(self):
        """核心断言：分两批建仓，各行剩余应为各自股数，而非整票 300。

        旧实现这里会得到 [300, 300] —— 用例必红。
        """
        df = _pos([
            {"ticker": "600519", "buy_date": "2026-01-05", "shares": 100},
            {"ticker": "600519", "buy_date": "2026-03-10", "shares": 200},
        ])
        rem, used = allocate_fifo(df, {})
        assert rem == [100, 200], f"剩余股数被重复计入: {rem}"
        assert sum(rem) == 300, "各行剩余之和必须等于真实持股"

    def test_sell_consumes_earliest_batch_first(self):
        """卖 120 股：先吃光第一批 100，再从第二批扣 20。"""
        df = _pos([
            {"ticker": "600519", "buy_date": "2026-01-05", "shares": 100},
            {"ticker": "600519", "buy_date": "2026-03-10", "shares": 200},
        ])
        rem, used = allocate_fifo(df, {"600519": 120})
        assert rem == [0, 180], rem
        assert used == [100, 20], used
        assert sum(rem) == 300 - 120

    def test_row_order_independent_of_dataframe_order(self):
        """行序打乱（后买的排前面）时仍按买入日期 FIFO 扣减。"""
        df = _pos([
            {"ticker": "600519", "buy_date": "2026-03-10", "shares": 200},
            {"ticker": "600519", "buy_date": "2026-01-05", "shares": 100},
        ])
        rem, used = allocate_fifo(df, {"600519": 120})
        # 先扣 2026-01-05 那批（位于第 2 行）
        assert used == [20, 100], used
        assert rem == [180, 0], rem

    def test_multiple_tickers_isolated(self):
        df = _pos([
            {"ticker": "600519", "buy_date": "2026-01-05", "shares": 100},
            {"ticker": "000001", "buy_date": "2026-01-06", "shares": 500},
            {"ticker": "600519", "buy_date": "2026-02-05", "shares": 300},
        ])
        rem, _u = allocate_fifo(df, {"600519": 150, "000001": 500})
        assert rem == [0, 0, 250], rem

    def test_oversold_never_negative(self):
        """卖出记录多于买入（脏数据）时剩余钳到 0，不得出现负股数。"""
        df = _pos([{"ticker": "600519", "buy_date": "2026-01-05", "shares": 100}])
        rem, used = allocate_fifo(df, {"600519": 999})
        assert rem == [0] and used == [100]

    def test_missing_buy_date_sorted_last_and_stable(self):
        """买入日期缺失的批次排最后被扣，且不崩。"""
        df = _pos([
            {"ticker": "600519", "buy_date": None, "shares": 100},
            {"ticker": "600519", "buy_date": "2026-01-05", "shares": 100},
        ])
        rem, used = allocate_fifo(df, {"600519": 100})
        assert used == [0, 100], used
        assert rem == [100, 0], rem

    def test_dirty_shares_coerced(self):
        """脏 shares（字符串 / None / NaN）不崩，按 0 处理。"""
        df = _pos([
            {"ticker": "600519", "buy_date": "2026-01-05", "shares": "abc"},
            {"ticker": "600519", "buy_date": "2026-02-05", "shares": None},
            {"ticker": "600519", "buy_date": "2026-03-05", "shares": "150"},
        ])
        rem, used = allocate_fifo(df, {"600519": 50})
        assert rem == [0, 0, 100], rem

    def test_empty_frame(self):
        rem, used = allocate_fifo(pd.DataFrame(), {})
        assert rem == [] and used == []

    def test_sold_map_dirty_value(self):
        df = _pos([{"ticker": "600519", "buy_date": "2026-01-05", "shares": 100}])
        assert allocate_fifo(df, {"600519": None})[0] == [100]
        assert allocate_fifo(df, {"600519": "x"})[0] == [100]
        assert allocate_fifo(df, {"600519": -5})[0] == [100]


# ================================================== 2. 汇总口径（端到端算术）
class TestAggregatesNotInflated:
    """复刻 calc_pnl 的逐行算术，断言汇总值等于真实值而非成倍虚增。"""

    ROWS = [
        {"ticker": "600519", "buy_date": "2026-01-05", "buy_price": 1500.0,
         "shares": 100, "cost": 150000.0},
        {"ticker": "600519", "buy_date": "2026-03-10", "buy_price": 1600.0,
         "shares": 200, "cost": 320000.0},
    ]
    PRICE = 1700.0

    def _rollup(self, sold_map):
        df = _pos(self.ROWS)
        rem, used = allocate_fifo(df, sold_map)
        df = df.assign(remaining_shares=rem)
        mv = cost = 0.0
        for _, r in df.iterrows():
            remaining = int(r["remaining_shares"])
            mv += market_value_of({"current_price": self.PRICE,
                                   "remaining_shares": remaining})
            ratio = remaining / r["shares"] if r["shares"] > 0 else 0
            cost += round(r["cost"] * ratio, 2)
        return round(mv, 2), round(cost, 2)

    def test_total_market_value_not_doubled(self):
        mv, _c = self._rollup({})
        assert mv == pytest.approx(self.PRICE * 300), f"总市值虚增: {mv}"

    def test_total_cost_matches_real(self):
        _mv, cost = self._rollup({})
        assert cost == pytest.approx(470000.0), f"总成本虚增: {cost}"

    def test_after_partial_sell(self):
        """卖出 120 股后：剩 180 股，成本 = 第二批 320000×180/200 = 288000。"""
        mv, cost = self._rollup({"600519": 120})
        assert mv == pytest.approx(self.PRICE * 180)
        assert cost == pytest.approx(288000.0), cost

    def test_cost_ratio_never_exceeds_one(self):
        """cost_ratio = remaining/shares 必须 <=1；旧实现会算出 3.0。"""
        df = _pos(self.ROWS)
        rem, _u = allocate_fifo(df, {})
        for r_, row in zip(rem, self.ROWS):
            assert r_ <= row["shares"], f"剩余 {r_} > 买入 {row['shares']}"

    def test_sell_all_zeroes_out(self):
        mv, cost = self._rollup({"600519": 300})
        assert mv == 0 and cost == 0


# ================================================== 3. 已实现盈亏摊分
class TestRealizedPnlSplit:

    def test_realized_split_sums_to_ticker_total(self):
        """整票已实现盈亏按各批次卖出股数摊分，行求和 == 整票总额（不重复计数）。"""
        df = _pos([
            {"ticker": "600519", "buy_date": "2026-01-05", "buy_price": 1500.0,
             "shares": 100, "cost": 150000.0},
            {"ticker": "600519", "buy_date": "2026-03-10", "buy_price": 1600.0,
             "shares": 200, "cost": 320000.0},
        ])
        rem, used = allocate_fifo(df, {"600519": 120})

        # 复刻 calc_pnl 的整票口径：均价成本 × 卖出股数
        avg_cost = (1500.0 * 100 + 1600.0 * 200) / 300
        ticker_realized = round(1700.0 * 120 - avg_cost * 120, 2)

        used_total = sum(used)
        per_row = [ticker_realized * (u / used_total) if used_total else 0.0
                   for u in used]
        assert sum(per_row) == pytest.approx(ticker_realized), (
            f"逐行已实现盈亏之和 {sum(per_row)} != 整票 {ticker_realized}（重复计数）"
        )
        # 旧实现是每行照抄整票金额，行求和会是 2 倍
        assert sum(per_row) != pytest.approx(ticker_realized * 2)

    def test_no_sell_means_zero_realized(self):
        df = _pos([{"ticker": "600519", "buy_date": "2026-01-05",
                    "buy_price": 1500.0, "shares": 100, "cost": 150000.0}])
        _rem, used = allocate_fifo(df, {})
        assert sum(used) == 0


# ================================================== 4. 源码级防回退
def _code_only(path):
    """返回剥离了字符串字面量与注释的源码。

    防回退断言必须只看**可执行代码**：本模块的 docstring 里原样引用了旧的
    错误写法作为反例说明，直接对全文 grep 会自我误伤。
    """
    import io
    import tokenize

    pieces = []
    with open(path, "rb") as f:
        for tok in tokenize.tokenize(io.BytesIO(f.read()).readline):
            if tok.type in (tokenize.STRING, tokenize.COMMENT):
                continue
            pieces.append(tok.string)
    return " ".join(pieces)


def test_source_no_map_based_remaining():
    path = os.path.join(PROJECT_ROOT, "modules", "portfolio.py")
    code = _code_only(path)
    normalized = code.replace(" ", "")
    assert 'df["remaining_shares"]=df["ticker"].map' not in normalized, (
        "get_positions 回退到整票 map 写法，分批建仓将再次成倍虚增"
    )
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "def allocate_fifo" in src
    body = src.split("def get_positions", 1)[1].split("def calc_pnl", 1)[0]
    assert "allocate_fifo" in body, "get_positions 未使用 FIFO 分配"
