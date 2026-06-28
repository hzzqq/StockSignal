"""test_whitebox_portfolio.py — PortfolioManager 白盒测试
覆盖 add_position / remove_position / get_positions / calc_pnl / summary / export_excel / pnl_attribution
所有分支条件、边界值和异常路径。
"""

import os
import pytest
import pandas as pd
from datetime import datetime
from modules.portfolio import PortfolioManager


class TestPortfolioManagerWhite:

    def test_ensure_file_created(self, tmp_path):
        """初始化时自动创建持仓文件。"""
        config_path = str(tmp_path / "config.yaml")
        with open(config_path, "w") as f:
            f.write(f"portfolio:\n  file: '{tmp_path / 'portfolio.csv'}'\n")
        pm = PortfolioManager(config_path)
        assert os.path.exists(tmp_path / "portfolio.csv")

    def test_add_position(self, tmp_path):
        pm = self._make_pm(tmp_path)
        result = pm.add_position("600519", "贵州茅台", "2025-01-01", 1500.0, 100, "测试")
        assert result["ticker"] == "600519"
        assert result["name"] == "贵州茅台"
        assert result["shares"] == 100
        assert result["cost"] == 150000.0

    def test_add_position_cost_calculation(self, tmp_path):
        """成本 = buy_price * shares。"""
        pm = self._make_pm(tmp_path)
        result = pm.add_position("601088", "中国神华", "2025-01-01", 30.0, 500)
        assert result["cost"] == 15000.0

    def test_add_multiple_positions(self, tmp_path):
        pm = self._make_pm(tmp_path)
        pm.add_position("600519", "贵州茅台", "2025-01-01", 1500.0, 100)
        pm.add_position("601088", "中国神华", "2025-01-01", 30.0, 500)
        positions = pm.get_positions()
        assert len(positions) == 2

    def test_remove_position_valid(self, tmp_path):
        pm = self._make_pm(tmp_path)
        pm.add_position("600519", "贵州茅台", "2025-01-01", 1500.0, 100)
        removed = pm.remove_position(0)
        assert removed is not None
        assert str(removed["ticker"]) == "600519"
        assert len(pm.get_positions()) == 0

    def test_remove_position_invalid_index(self, tmp_path):
        """无效索引返回 None。"""
        pm = self._make_pm(tmp_path)
        result = pm.remove_position(999)
        assert result is None

    def test_remove_position_negative_index(self, tmp_path):
        """负索引返回 None。"""
        pm = self._make_pm(tmp_path)
        pm.add_position("600519", "贵州茅台", "2025-01-01", 1500.0, 100)
        result = pm.remove_position(-1)
        assert result is None

    def test_get_positions_empty(self, tmp_path):
        pm = self._make_pm(tmp_path)
        positions = pm.get_positions()
        assert positions.empty

    def test_get_positions_with_data(self, tmp_path):
        pm = self._make_pm(tmp_path)
        pm.add_position("600519", "贵州茅台", "2025-01-01", 1500.0, 100)
        positions = pm.get_positions()
        assert len(positions) == 1
        assert "ticker" in positions.columns

    def test_calc_pnl_empty(self, tmp_path):
        pm = self._make_pm(tmp_path)
        result = pm.calc_pnl()
        assert result.empty

    def test_summary_empty(self, tmp_path):
        pm = self._make_pm(tmp_path)
        summary = pm.summary()
        assert summary["total_cost"] == 0
        assert summary["total_market_value"] == 0
        assert summary["total_pnl"] == 0
        assert summary["position_count"] == 0

    def test_export_excel(self, tmp_path):
        """导出 Excel 报告。"""
        pm = self._make_pm(tmp_path)
        pm.add_position("600519", "贵州茅台", "2025-01-01", 1500.0, 100)
        output = pm.export_excel(output_path=str(tmp_path / "report.xlsx"))
        assert os.path.exists(output)

    def test_export_excel_auto_filename(self, tmp_path):
        """不指定路径时自动生成文件名。"""
        pm = self._make_pm(tmp_path)
        pm.add_position("600519", "贵州茅台", "2025-01-01", 1500.0, 100)
        output = pm.export_excel()
        assert os.path.exists(output)
        assert output.endswith(".xlsx")

    def test_pnl_attribution_empty(self, tmp_path):
        pm = self._make_pm(tmp_path)
        result = pm.pnl_attribution()
        assert result.empty

    def test_pnl_attribution_with_data(self, tmp_path, monkeypatch):
        """盈亏归因分析。"""
        pm = self._make_pm(tmp_path)
        pm.add_position("600519", "贵州茅台", "2025-01-01", 1500.0, 100)
        pm.add_position("601088", "中国神华", "2025-01-01", 30.0, 500)

        # Mock calc_pnl 返回固定结果
        mock_pnl = pd.DataFrame([
            {"ticker": "600519", "name": "贵州茅台", "buy_date": "2025-01-01",
             "buy_price": 1500.0, "shares": 100, "cost": 150000.0,
             "current_price": 1600.0, "market_value": 160000.0,
             "pnl": 10000.0, "pnl_pct": 6.67},
            {"ticker": "601088", "name": "中国神华", "buy_date": "2025-01-01",
             "buy_price": 30.0, "shares": 500, "cost": 15000.0,
             "current_price": 28.0, "market_value": 14000.0,
             "pnl": -1000.0, "pnl_pct": -6.67},
        ])
        monkeypatch.setattr(pm, "calc_pnl", lambda: mock_pnl)

        result = pm.pnl_attribution()
        assert len(result) == 2
        assert "contribution" in result.columns
        # 茅台盈利10000，神华亏损-1000，总盈=9000
        # 茅台贡献 = 10000/9000 * 100 = 111.11
        # 神华贡献 = -1000/9000 * 100 = -11.11
        assert result.iloc[0]["pnl"] == 10000.0  # 降序排列

    def test_pnl_attribution_total_zero(self, tmp_path, monkeypatch):
        """总盈亏为0时贡献率为0。"""
        pm = self._make_pm(tmp_path)
        mock_pnl = pd.DataFrame([
            {"ticker": "600519", "name": "贵州茅台", "buy_date": "2025-01-01",
             "buy_price": 1500.0, "shares": 100, "cost": 150000.0,
             "current_price": 1600.0, "market_value": 160000.0,
             "pnl": 5000.0, "pnl_pct": 3.33},
            {"ticker": "601088", "name": "中国神华", "buy_date": "2025-01-01",
             "buy_price": 30.0, "shares": 500, "cost": 15000.0,
             "current_price": 28.0, "market_value": 14000.0,
             "pnl": -5000.0, "pnl_pct": -33.33},
        ])
        monkeypatch.setattr(pm, "calc_pnl", lambda: mock_pnl)
        result = pm.pnl_attribution()
        assert all(result["contribution"] == 0)

    def test_add_position_with_note(self, tmp_path):
        """添加持仓时备注应保存。"""
        pm = self._make_pm(tmp_path)
        pm.add_position("600519", "贵州茅台", "2025-01-01", 1500.0, 100, note="事件驱动买入")
        positions = pm.get_positions()
        assert positions.iloc[0]["note"] == "事件驱动买入"

    def test_add_position_without_note(self, tmp_path):
        """不填备注时默认为空字符串。"""
        pm = self._make_pm(tmp_path)
        pm.add_position("600519", "贵州茅台", "2025-01-01", 1500.0, 100)
        positions = pm.get_positions()
        # CSV 往返后空字符串变为 NaN，两种情况都算"无备注"
        assert pd.isna(positions.iloc[0]["note"]) or positions.iloc[0]["note"] == ""

    @staticmethod
    def _make_pm(tmp_path):
        """创建临时 PortfolioManager。"""
        config_path = str(tmp_path / "config.yaml")
        portfolio_file = str(tmp_path / "portfolio.csv")
        with open(config_path, "w") as f:
            f.write(f"portfolio:\n  file: '{portfolio_file}'\n")
        pm = PortfolioManager(config_path)
        pm.file_path = portfolio_file
        pm._ensure_file()
        return pm
