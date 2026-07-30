"""
tests/test_calendar_utils.py
===========================
周/月线双击弹分时时的「周期末 → 最近交易日」映射回归测试。

这是此前一个真实 bug 的守护：周/月 K 线柱子的 x 坐标是周期末(周五/月末)，
常落在周末或节假日，若直接用该日期拉分时图会拉不到数据。映射必须返回
「不晚于周期末的最近真实交易日」。
"""
from modules.calendar_utils import nearest_trading_day


def _jan_2024():
    # 2024-01 交易日（跳过周末）：1/2,1/3,1/4,1/5,1/8,1/9,1/10,1/11,1/12,
    # 1/15,1/16,...,1/30,1/31
    days = []
    d = 2
    while d <= 31:
        import datetime
        dt = datetime.date(2024, 1, d)
        if dt.weekday() < 5:  # 周一~周五
            days.append(dt.strftime("%Y-%m-%d"))
        d += 1
    return days


def test_period_end_on_weekend_maps_to_friday():
    days = _jan_2024()
    # 2024-01-06 是周六，应映射到前一个交易日 2024-01-05(周五)
    assert nearest_trading_day("2024-01-06", days) == "2024-01-05"
    # 2024-01-07 是周日，同样映射到 2024-01-05
    assert nearest_trading_day("2024-01-07", days) == "2024-01-05"


def test_period_end_on_trading_day_returns_itself():
    days = _jan_2024()
    # 2024-01-31 是周三(交易日)，应原样返回
    assert nearest_trading_day("2024-01-31", days) == "2024-01-31"


def test_period_end_on_holiday_maps_back():
    days = _jan_2024()
    # 2024-01-01 元旦(非交易日且早于所有交易日) → 无更早交易日，回退为自身
    assert nearest_trading_day("2024-01-01", days) == "2024-01-01"
    # 2024-02-03 是周六，早于它的最后交易日是 2024-01-31
    assert nearest_trading_day("2024-02-03", days) == "2024-01-31"


def test_empty_trading_days_falls_back_to_self():
    assert nearest_trading_day("2024-01-31", []) == "2024-01-31"


def test_accepts_timestamp_objects():
    import pandas as pd
    days = _jan_2024()
    ts = pd.Timestamp("2024-01-06")
    assert nearest_trading_day(ts, days) == "2024-01-05"
