"""集中式中国标准时间（CST / Asia/Shanghai, UTC+8, 无夏令时）时源。

R12 锐评专项（时区债清理）的单一真理源。

背景与风险
----------
本仓库大量模块用 ``datetime.now()`` / ``pd.Timestamp.now()``（服务器本地时区）生成
行情拉取起止日期窗、事件/信号时间窗、次日打分窗口。若部署机不在 CST 时区
（典型：UTC 云服务器，或海外 CI），``datetime.now().strftime("%Y-%m-%d")`` 在
北京时间凌晨 0~8 点之间会取到「错误的一天」（相对中国少一天），造成：

* 拉数窗口整体错位一天 → 静默取到错误/缺失的行情；
* 次日打分窗口偏移 → 回测命中率统计失真；
* 自动刷新在错误时间触发。

此前 ``linear_trends.now_cst`` 与 ``page_widgets._now_cst`` 各实现了一份，
口径不完全一致（回退分支不同），存在漂移风险。本模块收口为唯一入口。

使用约定
--------
* 需要「中国日期字符串 / 日期窗」→ 用 :func:`now_cst_str` / :func:`today_cst_str`。
  返回 tz-aware 时间后 strftime，天然给出中国日期，跨时区正确。
* 需要「可比较的 datetime 对象」且对方是朴素（naive）时间（如 ``session._parse_iso``
  解析出的朴素 datetime）→ 用 :func:`now_cst_naive`，避免 tz-aware 与 naive 相减抛 TypeError。
* 不要把 :func:`now_cst`（tz-aware）直接与朴素 datetime 做算术/比较。
"""

import logging
from datetime import datetime, timedelta, timezone

_logger = logging.getLogger(__name__)

_CST = timezone(timedelta(hours=8))  # 中国标准时间，无夏令时


def now_cst() -> datetime:
    """返回带时区的「中国标准时间（Asia/Shanghai, UTC+8）」。

    优先用 ``zoneinfo``（Python 3.9+ 标准库），不可用再试 ``pytz``，
    最后兜底到固定 ``UTC+8``（中国无夏令时，兜底也正确）。
    返回 tz-aware datetime，可直接 ``strftime`` 得到中国日期。
    """
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Shanghai"))
    except Exception as e:  # noqa: BLE001
        _logger.warning("[time_utils] zoneinfo 不可用，尝试 pytz: %s", e)
    try:
        import pytz
        return datetime.now(pytz.timezone("Asia/Shanghai"))
    except Exception as e:  # noqa: BLE001
        _logger.warning("[time_utils] pytz 也不可用，兜底 UTC+8: %s", e)
    return datetime.now(_CST)


def now_cst_naive() -> datetime:
    """返回「朴素（naive）的中国本地时间」，用于与朴素 datetime 比较/相减。

    例如 ``session._parse_iso`` 解析 ISO 时间戳时丢弃了 tzinfo 得到朴素 datetime，
    若用 tz-aware 的 :func:`now_cst` 与之相减会抛 ``TypeError``。此类场景用本函数。
    """
    return datetime.now(_CST).replace(tzinfo=None)


def now_cst_str(fmt: str = "%Y-%m-%d") -> str:
    """``now_cst()`` 格式化字符串（默认日期），供日期窗拼接复用。"""
    return now_cst().strftime(fmt)


def today_cst_str() -> str:
    """中国今天日期字符串（``%Y-%m-%d``），最常用的取「今天」入口。"""
    return now_cst_str("%Y-%m-%d")
