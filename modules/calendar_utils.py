"""
modules/calendar_utils.py
=========================
交易日日历工具。

核心场景：K 线切到「周K / 月K」后，用户双击某根柱子的 x 坐标是「周期末」
（周五收盘 / 月末），往往是周末或节假日，并非真实交易日。若直接用这个日期去
拉分时图会拉不到数据。本模块把周期末映射到「不晚于它的最近一个真实交易日」。

纯函数、零依赖（只用到 bisect），便于单测，避免页面里重复实现导致逻辑漂移。
"""
from __future__ import annotations

import bisect
from typing import Iterable


def nearest_trading_day(period_date, trading_days: Iterable[str]) -> str:
    """把周期末日期映射到不晚于它的最近交易日。

    :param period_date: 任意可 ``str()`` 的对象（datetime / Timestamp / "2024-02-03"）
    :param trading_days: 一串交易日字符串，形如 ["2024-01-31", "2024-02-01", ...]，
                        顺序随意（内部会排序）
    :return: 最近交易日字符串(YYYY-MM-DD)；若无可匹配则返回 period_date 的 YYYY-MM-DD
    """
    pd_str = str(period_date)[:10]
    dts = sorted(str(d) for d in trading_days)
    if not dts:
        return pd_str
    # bisect_right 找到第一个 > pd_str 的位置，减 1 即「不晚于 pd_str」的最大交易日
    i = bisect.bisect_right(dts, pd_str) - 1
    if i >= 0:
        return dts[i]
    return pd_str
