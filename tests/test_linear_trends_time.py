"""linear_trends 集中式 CST 时源 + 既有纯函数边缘回归（无网依赖）。

覆盖：
- now_cst：返回 Asia/Shanghai (UTC+8) 时区感知时间，不再依赖服务器本地时区
- now_cst_str：按给定格式输出（默认日期）
- _parse_date / _to_yi：None / NaN / 非法值兜底（隐性健壮化）
"""
import datetime as dt
from datetime import timedelta, timezone

import pandas as pd

import modules.linear_trends as LT


def test_now_cst_is_utc8():
    t = LT.now_cst()
    # 必须是 Asia/Shanghai（UTC+8，无夏令时）
    assert t.utcoffset() == timedelta(hours=8)


def test_now_cst_str_default_and_custom():
    assert len(LT.now_cst_str()) == 10  # YYYY-MM-DD
    assert LT.now_cst_str("%Y%m%d") == LT.now_cst().strftime("%Y%m%d")
    # 与 UTC 当前时刻相差约 8 小时（验证确实是 CST 而非本地时区）
    utc_now = dt.datetime.now(timezone.utc)
    cst_as_utc = LT.now_cst().astimezone(timezone.utc)
    diff = abs((cst_as_utc - utc_now).total_seconds())
    assert diff < 9  # 9 秒内视为一致


def test_parse_date_edge():
    assert LT._parse_date(None) is None
    assert LT._parse_date(float("nan")) is None
    assert LT._parse_date("2026-07-25 13:00:00") == "2026-07-25"
    assert LT._parse_date(pd.Timestamp("2026-07-25")) == "2026-07-25"


def test_to_yi_edge():
    assert LT._to_yi(1e8) == 1.0
    assert LT._to_yi("2e8") == 2.0
    assert LT._to_yi("abc") is None
    assert LT._to_yi(None) is None
