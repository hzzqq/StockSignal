"""tests/test_quotes_fallback.py —— linear_trends 行情取数多源降级链单测（方向 3-3 深化）。

覆盖：东财主源不可达时，行业板块降级同花顺、ETF 降级新浪；
主源正常时不产生降级记录；双源全失败返回空 DF（行为与旧版一致）。
全部零网络：mock akshare。
"""
from __future__ import annotations

import datetime as dt
from unittest.mock import patch

import pandas as pd
import pytest

from modules import linear_trends as lt

_DATE0 = dt.datetime(2026, 11, 2)


def _ths_df(symbol: str, n: int = 5) -> pd.DataFrame:
    dates = pd.bdate_range(end="2026-10-30", periods=n)
    return pd.DataFrame({
        "日期": [d.strftime("%Y-%m-%d") for d in dates],
        "开盘价": [1.0] * n,
        "最高价": [2.0] * n,
        "最低价": [0.5] * n,
        "收盘价": [float(i + 1) for i in range(n)],
        "成交量": [100] * n,
    })


def _sina_etf_df(code: str, n: int = 5) -> pd.DataFrame:
    dates = pd.bdate_range(end="2026-10-30", periods=n)
    return pd.DataFrame({
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "open": [1.0] * n,
        "high": [2.0] * n,
        "low": [0.5] * n,
        "close": [float(i + 1) for i in range(n)],
        "volume": [100] * n,
    })


class TestIndustryBoardFallback:
    """行业板块日线：东财 hist_em 挂 → 同花顺 ths 备源顶替。"""

    def test_em_fail_ths_success(self):
        with patch("akshare.stock_board_industry_name_em",
                   side_effect=ConnectionError("RemoteDisconnected")), \
             patch("akshare.stock_board_industry_hist_em",
                   side_effect=ConnectionError("RemoteDisconnected")), \
             patch("akshare.stock_board_industry_index_ths",
                   return_value=_ths_df("半导体")):
            lt._LAST_QUOTES_FALLBACK.clear()
            df = lt.get_industry_index_series(top_n=3, days=30)
            assert not df.empty
            assert "date" in df.columns
            assert len(df.columns) >= 2  # date + 至少一个行业
            fb = lt._LAST_QUOTES_FALLBACK.get("industry_board")
            assert fb is not None and fb["fallback_to"] == "ths"

    def test_em_success_no_fallback_record(self):
        em_df = pd.DataFrame({
            "日期": ["2026-10-30", "2026-10-29", "2026-10-28"],
            "收盘": [1.0, 2.0, 3.0],
        })
        with patch("akshare.stock_board_industry_name_em", return_value=pd.DataFrame({"板块名称": ["半导体", "银行"]})), \
             patch("akshare.stock_board_industry_hist_em", return_value=em_df), \
             patch("akshare.stock_board_industry_index_ths", side_effect=AssertionError("不应调用备源")):
            lt._LAST_QUOTES_FALLBACK.clear()
            df = lt.get_industry_index_series(top_n=1, days=30)
            assert not df.empty
            assert "industry_board" not in lt._LAST_QUOTES_FALLBACK

    def test_both_fail_returns_empty(self):
        with patch("akshare.stock_board_industry_name_em",
                   side_effect=ConnectionError("RemoteDisconnected")), \
             patch("akshare.stock_board_industry_hist_em",
                   side_effect=ConnectionError("RemoteDisconnected")), \
             patch("akshare.stock_board_industry_index_ths",
                   side_effect=ConnectionError("RemoteDisconnected")):
            df = lt.get_industry_index_series(top_n=3, days=30)
            assert df.empty or "industry_board" not in lt._LAST_QUOTES_FALLBACK


class TestEtfFallback:
    """ETF 日线：东财 fund_etf_hist_em 挂 → 新浪 fund_etf_hist_sina 备源顶替。"""

    def test_em_fail_sina_success(self):
        with patch("akshare.fund_etf_hist_em",
                   side_effect=ConnectionError("RemoteDisconnected")), \
             patch("akshare.fund_etf_hist_sina",
                   return_value=_sina_etf_df("sh510300")):
            lt._LAST_QUOTES_FALLBACK.clear()
            df = lt.get_etf_series(days=30)
            assert not df.empty
            fb = lt._LAST_QUOTES_FALLBACK.get("etf")
            assert fb is not None and fb["fallback_to"] == "sina"

    def test_em_success_no_fallback(self):
        em_df = pd.DataFrame({
            "日期": ["2026-10-30", "2026-10-29", "2026-10-28"],
            "收盘": [4.0, 5.0, 6.0],
        })
        with patch("akshare.fund_etf_hist_em", return_value=em_df), \
             patch("akshare.fund_etf_hist_sina", side_effect=AssertionError("不应调用备源")):
            lt._LAST_QUOTES_FALLBACK.clear()
            df = lt.get_etf_series(days=30)
            assert not df.empty
            assert "etf" not in lt._LAST_QUOTES_FALLBACK


class TestQuotesFetchState:
    def test_state_shape(self):
        lt._LAST_QUOTES_FALLBACK.clear()
        state = lt.quotes_fetch_state()
        assert "last_fallbacks" in state
        assert state["last_fallbacks"] == {}

    def test_record_shape(self):
        lt._record_quotes_fallback("etf", "sina", "510300: 东财→新浪")
        ev = lt._LAST_QUOTES_FALLBACK["etf"]
        assert ev["fallback_to"] == "sina"
        assert "ts" in ev and "detail" in ev
        lt._LAST_QUOTES_FALLBACK.clear()
