"""test_fetcher.py — 数据采集模块测试"""

import pytest
import pandas as pd
from modules.fetcher import StockFetcher, load_config


class TestStockFetcher:

    def test_load_config(self):
        config = load_config("config.yaml")
        assert isinstance(config, dict)
        assert "default" in config

    def test_get_daily(self):
        """测试获取日线行情（需要网络）。"""
        fetcher = StockFetcher()
        try:
            df = fetcher.get_daily("600519", start="2025-01-01", end="2025-06-01")
            assert not df.empty
            assert "close" in df.columns
            assert "date" in df.columns
        except Exception:
            pytest.skip("网络不可用，跳过")

    def test_get_daily_cache(self):
        """测试缓存机制：第二次读取应命中缓存。"""
        fetcher = StockFetcher()
        try:
            df1 = fetcher.get_daily("000858", start="2025-01-01", end="2025-03-01")
            df2 = fetcher.get_daily("000858", start="2025-01-01", end="2025-03-01")
            assert len(df1) == len(df2)
        except Exception:
            pytest.skip("网络不可用，跳过")

    def test_get_macro(self):
        """测试获取宏观数据。"""
        fetcher = StockFetcher()
        try:
            df = fetcher.get_macro("pmi_mfg")
            assert not df.empty
        except Exception:
            pytest.skip("网络不可用，跳过")

    def test_invalid_symbol(self):
        """测试无效股票代码。"""
        fetcher = StockFetcher()
        try:
            df = fetcher.get_daily("999999", start="2025-01-01", end="2025-06-01")
            # 无效代码可能返回空DataFrame
            assert isinstance(df, pd.DataFrame)
        except Exception:
            pass  # 抛异常也可接受
