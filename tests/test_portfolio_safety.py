"""test_portfolio_safety.py
验证：
- format_helpers.safe_pct 的百分比计算全程防 NaN / inf / 除零；
- PortfolioManager 对买入价/股数的非法输入做清晰校验（不再裸抛 TypeError）；
- calc_pnl 在行情接口返回 NaN 收盘价时回退到买入价，不污染盈亏。
"""
import math
import pandas as pd
import pytest

from modules.format_helpers import safe_pct
from modules.portfolio import PortfolioManager


class TestSafePct:
    def test_normal(self):
        assert safe_pct(10, 100) == 10.0
        assert safe_pct(-5, 100) == -5.0

    def test_zero_denominator(self):
        assert safe_pct(10, 0) == 0.0

    def test_none_denominator(self):
        assert safe_pct(10, None) == 0.0

    def test_nan_numerator(self):
        assert safe_pct(float("nan"), 100) == 0.0

    def test_inf_denominator(self):
        assert safe_pct(10, float("inf")) == 0.0

    def test_custom_default(self):
        assert safe_pct(10, 0, default=-1.0) == -1.0


class TestPortfolioInputValidation:
    @staticmethod
    def _make_pm(tmp_path):
        config_path = str(tmp_path / "config.yaml")
        portfolio_file = str(tmp_path / "portfolio.csv")
        with open(config_path, "w") as f:
            f.write(f"portfolio:\n  file: '{portfolio_file}'\n")
        pm = PortfolioManager(config_path)
        pm.file_path = portfolio_file
        pm._ensure_file()
        return pm

    def test_reject_non_positive_price(self, tmp_path):
        pm = self._make_pm(tmp_path)
        with pytest.raises(ValueError):
            pm.add_position("600519", "贵州茅台", "2025-01-01", 0, 100)

    def test_reject_negative_shares(self, tmp_path):
        pm = self._make_pm(tmp_path)
        with pytest.raises(ValueError):
            pm.add_position("600519", "贵州茅台", "2025-01-01", 1500.0, -10)

    def test_reject_non_numeric_price(self, tmp_path):
        pm = self._make_pm(tmp_path)
        with pytest.raises(ValueError):
            pm.add_position("600519", "贵州茅台", "2025-01-01", "abc", 100)

    def test_reject_none_shares(self, tmp_path):
        pm = self._make_pm(tmp_path)
        with pytest.raises(ValueError):
            pm.add_position("600519", "贵州茅台", "2025-01-01", 1500.0, None)

    def test_accepts_float_shares(self, tmp_path):
        pm = self._make_pm(tmp_path)
        # 100.0 股应被规范为 100 股整数，而非静默截断或报错
        result = pm.add_position("600519", "贵州茅台", "2025-01-01", 1500.0, 100.0)
        assert result["shares"] == 100


class TestPortfolioNanPrice:
    """calc_pnl 在收盘价 NaN 时回退到买入价，盈亏保持 0 而非 NaN。"""

    @staticmethod
    def _make_pm(tmp_path):
        config_path = str(tmp_path / "config.yaml")
        portfolio_file = str(tmp_path / "portfolio.csv")
        with open(config_path, "w") as f:
            f.write(f"portfolio:\n  file: '{portfolio_file}'\n")
        pm = PortfolioManager(config_path)
        pm.file_path = portfolio_file
        pm._ensure_file()
        return pm

    def test_nan_close_falls_back_to_buy_price(self, tmp_path, monkeypatch):
        pm = self._make_pm(tmp_path)
        pm.add_position("600519", "贵州茅台", "2025-01-01", 1500.0, 100)

        nan_df = pd.DataFrame([{"close": float("nan")}])
        monkeypatch.setattr(pm.fetcher, "get_daily", lambda *a, **k: nan_df)

        pnl = pm.calc_pnl()
        assert not pnl.empty
        row = pnl.iloc[0]
        assert row["current_price"] == 1500.0
        assert row["pnl"] == 0.0
        assert not math.isnan(row["pnl_pct"])
        assert row["pnl_pct"] == 0.0

    def test_inf_close_falls_back_to_buy_price(self, tmp_path, monkeypatch):
        pm = self._make_pm(tmp_path)
        pm.add_position("600519", "贵州茅台", "2025-01-01", 1500.0, 100)

        inf_df = pd.DataFrame([{"close": float("inf")}])
        monkeypatch.setattr(pm.fetcher, "get_daily", lambda *a, **k: inf_df)

        pnl = pm.calc_pnl()
        row = pnl.iloc[0]
        assert row["current_price"] == 1500.0
        assert not math.isnan(row["pnl_pct"])


class TestPortfolioAtomicWrite:
    """持仓/交易文件写入必须是原子写（tmp+os.replace），
    避免 Streamlit rerun 并发读时读到半截 CSV 导致持仓显示错乱或文件损坏。
    """

    @staticmethod
    def _make_pm(tmp_path):
        import os
        config_path = str(tmp_path / "config.yaml")
        portfolio_file = str(tmp_path / "portfolio.csv")
        with open(config_path, "w") as f:
            f.write(f"portfolio:\n  file: '{portfolio_file}'\n")
        pm = PortfolioManager(config_path)
        pm.file_path = portfolio_file
        pm._ensure_file()
        return pm

    def test_atomic_to_csv_leaves_no_tmp(self, tmp_path):
        import os
        from modules.portfolio import _atomic_to_csv
        p = str(tmp_path / "x.csv")
        _atomic_to_csv(pd.DataFrame({"a": [1, 2]}), p)
        assert os.path.exists(p)
        assert not os.path.exists(p + ".tmp")  # 关键：写完后临时文件已 replace 掉
        assert list(pd.read_csv(p)["a"]) == [1, 2]

    def test_add_position_is_atomic_and_reloadable(self, tmp_path):
        import os
        pm = self._make_pm(tmp_path)
        pm.add_position("600519", "贵州茅台", "2025-01-01", 1500.0, 100)
        # 主文件存在、无残留 .tmp、reload 完整
        assert os.path.exists(pm.file_path)
        assert not os.path.exists(pm.file_path + ".tmp")
        reloaded = pm._load()
        assert len(reloaded) == 1
        assert reloaded.iloc[0]["ticker"] == "600519"

    def test_sell_trades_write_atomic(self, tmp_path):
        import os
        pm = self._make_pm(tmp_path)
        pm.add_position("600519", "贵州茅台", "2025-01-01", 1500.0, 100)
        pm.sell_position("600519", "2025-02-01", 1600.0, 100)
        tp = pm._trades_path()
        assert os.path.exists(tp)
        assert not os.path.exists(tp + ".tmp")
        trades = pm._load_trades()
        assert len(trades) == 1
        assert trades.iloc[0]["ticker"] == "600519"
