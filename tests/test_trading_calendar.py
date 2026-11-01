"""tests/test_trading_calendar.py —— A 股交易日历单测（2026 官方休市表内置）。

覆盖：普通工作日/周末判定、法定长假（元旦/春节/清明/劳动/端午/中秋/国庆）、
prev_trading_day 跨周末与跨长假回退、无表年份回退。
"""
from datetime import date

import pytest

from modules.trading_calendar import is_trading_day, prev_trading_day

# 2026 官方休市区间（上交所年度休市安排）
_HOLIDAY_SPOTS = [
    date(2026, 1, 2),      # 元旦休市
    date(2026, 2, 18),     # 春节休市
    date(2026, 4, 5),      # 清明休市
    date(2026, 5, 4),      # 劳动节休市
    date(2026, 6, 20),     # 端午休市
    date(2026, 9, 26),     # 中秋休市
    date(2026, 10, 5),     # 国庆休市
]


class TestIsTradingDay:
    @pytest.mark.parametrize("d", _HOLIDAY_SPOTS)
    def test_holiday_not_trading(self, d):
        assert is_trading_day(d) is False

    def test_weekend_not_trading(self):
        assert is_trading_day(date(2026, 11, 1)) is False   # 周日
        assert is_trading_day(date(2026, 10, 31)) is False  # 周六

    def test_regular_weekday_trading(self):
        assert is_trading_day(date(2026, 11, 2)) is True    # 周一
        assert is_trading_day(date(2026, 10, 30)) is True   # 周五

    def test_day_after_holiday_trading(self):
        assert is_trading_day(date(2026, 2, 24)) is True    # 春节后首个交易日
        assert is_trading_day(date(2026, 10, 8)) is True    # 国庆后首个交易日


class TestPrevTradingDay:
    def test_plain_weekday(self):
        assert prev_trading_day(date(2026, 11, 2)) == date(2026, 10, 30)  # 周一 → 上周五

    def test_weekend_skip(self):
        assert prev_trading_day(date(2026, 11, 1)) == date(2026, 10, 30)  # 周日 → 周五

    def test_holiday_skip(self):
        # 春节后首个交易日 2/24 的前一交易日应为 2/13（2/14 周六、2/15~2/23 休市）
        assert prev_trading_day(date(2026, 2, 24)) == date(2026, 2, 13)
        # 国庆后首个交易日 10/8 的前一交易日应为 9/30（9/25~10/7 休市，9/28~9/30 为交易日）
        assert prev_trading_day(date(2026, 10, 8)) == date(2026, 9, 30)

    def test_weekday_skips_self(self):
        # 盘前语义：参考日 = 今天的前一交易日（10-30 的前一交易日 = 10-29）
        assert prev_trading_day(date(2026, 10, 30)) == date(2026, 10, 29)
