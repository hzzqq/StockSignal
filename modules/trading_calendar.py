"""modules/trading_calendar.py —— A 股交易日历（fundflow 体检新鲜度参考，方向 3 深化）。

用途
====
fundflow_health 的「参考交易日」此前用「前一个非周末日」近似，遇 A 股法定长假
（春节/国庆等，参考日可能落在休市日）会误报新鲜度红灯。本模块用交易所官方
休市安排消除该误报：

  - is_trading_day(d)：d 为工作日且不在官方休市区间
  - prev_trading_day(d)：从 d-1 起向前找最近交易日

数据源
======
2026 休市安排来自上海证券交易所「年度休市安排」（2026-11-01 访问核实），
与中证网/上海证券报/中新网发布口径一致。区间为闭区间，官方表述已含调休周末。

其他年份：无内置表时回退「非周末日」近似（宽松；跨年/历史体检场景）。
"""
from __future__ import annotations

from datetime import date, timedelta

# 2026 年 A 股休市区间（闭区间，交易所官方口径；含周末，双保险冗余）
HOLIDAYS_2026: tuple[tuple[date, date], ...] = (
    (date(2026, 1, 1), date(2026, 1, 3)),      # 元旦
    (date(2026, 2, 15), date(2026, 2, 23)),    # 春节（含 2/14、2/28 周末调休）
    (date(2026, 4, 4), date(2026, 4, 6)),      # 清明节
    (date(2026, 5, 1), date(2026, 5, 5)),      # 劳动节（含 5/9 周末调休）
    (date(2026, 6, 19), date(2026, 6, 21)),    # 端午节
    (date(2026, 9, 25), date(2026, 9, 27)),    # 中秋节（含 9/20 周末调休）
    (date(2026, 10, 1), date(2026, 10, 7)),    # 国庆节（含 10/10 周末调休）
)

# 按年索引；其他年份回退非周末近似
_HOLIDAYS_BY_YEAR: dict[int, tuple[tuple[date, date], ...]] = {2026: HOLIDAYS_2026}


def _in_holiday(d: date) -> bool:
    ranges = _HOLIDAYS_BY_YEAR.get(d.year)
    if not ranges:
        return False
    return any(start <= d <= end for start, end in ranges)


def is_trading_day(d: date | None = None) -> bool:
    """d 是否为 A 股交易日：工作日 且 不在官方休市区间。"""
    d = d or date.today()
    if d.weekday() >= 5:
        return False
    return not _in_holiday(d)


def prev_trading_day(today: date | None = None) -> date:
    """从 today-1 起向前找最近交易日（含休市表修正；无表年份回退非周末）。"""
    d = (today or date.today()) - timedelta(days=1)
    while True:
        if is_trading_day(d):
            return d
        d -= timedelta(days=1)
