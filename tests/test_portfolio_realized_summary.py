"""
回归测试：portfolio 已实现盈亏改 FIFO + summary 总盈亏纳入已实现（cycle 47）。

【缺陷本体】
  1) calc_pnl 的 realized 原用平均成本法（avg_cost × 卖出股数）。同一只票分批建仓、
     批次买入价不同时，与模块自身的 FIFO 契约（allocate_fifo）冲突，算错已实现盈亏。
     例：100@10 + 100@20，FIFO 卖最早一批 100 股@卖价20 → 真实已实现 = 100*(20-10)=1000；
     平均成本 15 算得 100*(20-15)=500，相对误差 100%。
  2) summary() 的 total_pnl 只 sum 未实现 pnl，漏掉 calc_pnl 已产出的 realized_pnl 列，
     账户一旦有过卖出，总盈亏整体低估全部已实现部分。

【修复】
  calc_pnl 改用 compute_realized_fifo（与 allocate_fifo 同一 FIFO 契约）；
  summary() 的 total_pnl = (pnl + realized_pnl).sum()。

本文件用临时 csv + stub 行情/名称，不触网、不读磁盘配置。
"""

import os
import sys

import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from modules.portfolio import PortfolioManager  # noqa: E402


def _make(tmp_path, price):
    """构造一个网络调用全 stub 的 PortfolioManager。"""
    pm = PortfolioManager(config_path="config.yaml")
    pm.file_path = str(tmp_path / "portfolio.csv")
    pm._ensure_file()
    pm.fetcher.get_stock_name = lambda t: t
    price = float(price)
    pm.fetcher.get_daily = lambda *a, **k: pd.DataFrame([{"close": price}])
    return pm


class TestRealizedUsesFifo:
    def test_fifo_realized_not_avg_cost(self, tmp_path):
        """分批建仓、卖出最早批次：已实现盈亏必须是 FIFO 口径（1000），而非平均成本（500）。"""
        pm = _make(tmp_path, price=25.0)
        pm.add_position("600000", "分批股", "2024-01-01", 10, 100)   # A 批 100@10
        pm.add_position("600000", "分批股", "2024-03-01", 20, 100)   # B 批 100@20
        pm.sell_position("600000", "2024-05-01", 20, 100)           # FIFO 卖 A 批(成本10)

        pnl = pm.calc_pnl()
        total_realized = pnl["realized_pnl"].sum()
        # FIFO: 100*(20-10) = 1000
        assert total_realized == pytest.approx(1000.0, abs=0.01)
        # 防御：绝不能退回到平均成本口径(500)
        assert total_realized != pytest.approx(500.0, abs=0.01)

    def test_three_batches_interleaved(self, tmp_path):
        """三批不同价、跨批卖出：FIFO 应按批次顺序吃货。"""
        pm = _make(tmp_path, price=100.0)
        pm.add_position("600001", "三批", "2024-01-01", 10, 100)   # 批次1
        pm.add_position("600001", "三批", "2024-02-01", 20, 100)   # 批次2
        pm.add_position("600001", "三批", "2024-03-01", 30, 100)   # 批次3
        # 卖 250 股@40：先吃批次1(100)、批次2(100)、批次3(50)
        pm.sell_position("600001", "2024-04-01", 40, 250)
        expected = 100 * (40 - 10) + 100 * (40 - 20) + 50 * (40 - 30)
        expected = 3000 + 2000 + 500  # = 5500
        pnl = pm.calc_pnl()
        assert pnl["realized_pnl"].sum() == pytest.approx(5500.0, abs=0.01)

    def test_no_sell_zero_realized(self, tmp_path):
        pm = _make(tmp_path, price=15.0)
        pm.add_position("600002", "无卖", "2024-01-01", 10, 100)
        pnl = pm.calc_pnl()
        assert pnl["realized_pnl"].sum() == 0.0


class TestSummaryIncludesRealized:
    def test_total_pnl_includes_realized(self, tmp_path):
        """卖出部分后：summary.total_pnl 应含已实现(500)+未实现(500)=1000，而非仅未实现(500)。"""
        pm = _make(tmp_path, price=20.0)
        pm.add_position("000001", "测试股", "2024-01-01", 10, 100)
        pm.sell_position("000001", "2024-02-01", 20, 50)  # 已实现 50*(20-10)=500；剩50股

        summ = pm.summary()
        # 未实现：剩余50股 @现价20,成本10 → 50*(20-10)=500
        # 已实现：500；total 应为 1000
        assert summ["total_pnl"] == pytest.approx(1000.0, abs=0.01)
        # 防御：不能退回到只算未实现的版本(500)
        assert summ["total_pnl"] != pytest.approx(500.0, abs=0.01)

    def test_no_sell_total_pnl_matches_unrealized(self, tmp_path):
        pm = _make(tmp_path, price=12.0)
        pm.add_position("000002", "纯持仓", "2024-01-01", 10, 100)
        summ = pm.summary()
        # 无卖出时 total_pnl == 未实现 = 100*(12-10)=200
        assert summ["total_pnl"] == pytest.approx(200.0, abs=0.01)

    def test_empty_summary_still_zero(self, tmp_path):
        pm = _make(tmp_path, price=10.0)
        summ = pm.summary()
        assert summ["total_pnl"] == 0
        assert summ["position_count"] == 0
