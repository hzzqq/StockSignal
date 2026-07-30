"""
财务数据契约层测试（Task C）：把 FIFO / 列结构语义从「正则守门」升级为机器可校验 schema。

覆盖：
- validate_position_schema / validate_pnl_output 的 fail-fast 行为
- allocate_fifo / compute_realized_fifo 的核心不变式
- calc_pnl 真实输出严格符合 PNL_OUTPUT_COLUMNS 契约（集成断言，替代源码级正则）
"""

from __future__ import annotations

import pandas as pd
import pytest

from modules.finance_contract import (
    FinanceContractError,
    PNL_OUTPUT_COLUMNS,
    validate_pnl_output,
    validate_position_schema,
)
from modules.portfolio import PortfolioManager, allocate_fifo, compute_realized_fifo


def _make_pm(tmp_path):
    config_path = str(tmp_path / "config.yaml")
    portfolio_file = str(tmp_path / "portfolio.csv")
    with open(config_path, "w") as f:
        f.write(f"portfolio:\n  file: '{portfolio_file}'\n")
    pm = PortfolioManager(config_path)
    pm.file_path = portfolio_file
    pm._ensure_file()
    return pm


class TestPositionSchema:
    def test_valid_df_ok(self):
        df = pd.DataFrame([{"ticker": "600519", "buy_date": "2025-01-01",
                             "buy_price": 100.0, "shares": 10, "cost": 1000.0}])
        validate_position_schema(df)  # 不应抛

    def test_empty_ok(self):
        validate_position_schema(pd.DataFrame())

    def test_missing_column_raises(self):
        df = pd.DataFrame([{"ticker": "600519"}])  # 缺 buy_price/shares/cost/buy_date
        with pytest.raises(FinanceContractError):
            validate_position_schema(df)

    def test_require_remaining_raises_without_derived(self):
        df = pd.DataFrame([{"ticker": "600519", "buy_date": "2025-01-01",
                             "buy_price": 100.0, "shares": 10, "cost": 1000.0}])
        with pytest.raises(FinanceContractError):
            validate_position_schema(df, require_remaining=True)


class TestPnlOutputContract:
    def test_exact_columns_ok(self):
        out = pd.DataFrame([{c: 0 for c in PNL_OUTPUT_COLUMNS}])
        validate_pnl_output(out)  # 不应抛

    def test_missing_column_raises(self):
        cols = list(PNL_OUTPUT_COLUMNS)
        cols.remove("realized_pnl")
        out = pd.DataFrame([{c: 0 for c in cols}])
        with pytest.raises(FinanceContractError):
            validate_pnl_output(out)

    def test_extra_column_raises(self):
        out = pd.DataFrame([{c: 0 for c in PNL_OUTPUT_COLUMNS}])
        out["unexpected_field"] = 0
        with pytest.raises(FinanceContractError):
            validate_pnl_output(out)


class TestFifoInvariants:
    def test_allocate_fifo_sum_equals_net(self):
        """Σ各行 remaining == 整票(总买入 - 总卖出)，不限批次数量。"""
        df = pd.DataFrame([
            {"ticker": "600519", "buy_date": "2025-01-01", "shares": 100},
            {"ticker": "600519", "buy_date": "2025-03-01", "shares": 200},
        ])
        remaining, _ = allocate_fifo(df, {"600519": 150})
        assert sum(remaining) == 300 - 150  # 150

    def test_compute_realized_fifo_cross_batch(self):
        """先买批次先被卖：100@10 + 100@20，FIFO 卖 100@25 → 已实现=1500。"""
        realized = compute_realized_fifo(
            buy_batches=[(10.0, 100), (20.0, 100)],
            sell_trades=[(25.0, 100)],
        )
        assert realized == 1500.0

    def test_compute_realized_fifo_span_two_batches(self):
        """卖 250 跨两批：先吃 100@10 再吃 150@20，卖价 30。
        已实现 = (30-10)*100 + (30-20)*150 = 2000 + 1500 = 3500。"""
        realized = compute_realized_fifo(
            buy_batches=[(10.0, 100), (20.0, 100), (20.0, 100)],
            sell_trades=[(30.0, 250)],
        )
        assert realized == 3500.0


class TestCalcPnlConformsToContract:
    def test_calc_pnl_output_strictly_matches_contract(self, tmp_path, monkeypatch):
        """集成断言：真实 calc_pnl 输出列严格等于契约（不再靠正则守门）。"""
        pm = _make_pm(tmp_path)
        pm.add_position("600519", "贵州茅台", "2025-01-01", 1500.0, 100)
        pm.add_position("601088", "中国神华", "2025-01-01", 30.0, 500)

        # stub 行情，避免联网；返回带 close 的单行
        class _FakeDaily(pd.DataFrame):
            pass

        def _fake_daily(self, ticker, start=None, end=None):
            return pd.DataFrame([{"close": 1600.0 if ticker == "600519" else 32.0}])

        monkeypatch.setattr(type(pm.fetcher), "get_daily", _fake_daily)

        out = pm.calc_pnl()
        # validate_pnl_output 已在 calc_pnl 内部调用；此处再断言以文档化契约
        validate_pnl_output(out)
        assert list(out.columns) == PNL_OUTPUT_COLUMNS
        # FIFO: 无卖出 → realized_pnl 全 0，未实现 pnl 按剩余股数算
        assert (out["realized_pnl"] == 0).all()
        assert (out["remaining_shares"] == out["shares"]).all()


def test_get_positions_runs_under_contract(tmp_path, monkeypatch):
    """get_positions 入口经 validate_position_schema 不抛（落盘数据合法）。"""
    pm = _make_pm(tmp_path)
    pm.add_position("600519", "贵州茅台", "2025-01-01", 1500.0, 100)
    df = pm.get_positions()
    validate_position_schema(df, require_remaining=True)
