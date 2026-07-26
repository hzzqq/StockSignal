"""
tests/test_timeutil.py
======================
- 校验 ``backend.utils.timeutil`` 的 UTC 辅助函数行为（naive UTC、时区正确）。
- 回归：源码中不得再出现已弃用的 ``datetime.utcnow()`` / ``datetime.utcfromtimestamp()``。
"""
from __future__ import annotations

import ast
import os

from backend.utils.timeutil import (
    utc_now,
    utc_fromtimestamp,
    parse_date,
    format_date,
    is_weekday,
    is_trading_day,
    build_date_range,
)
from datetime import date


def test_utc_now_is_naive_utc():
    """utc_now 返回 tzinfo=None 的 UTC 时间（兼容 DB 按 naive UTC 存储的约定）。"""
    now = utc_now()
    assert now.tzinfo is None
    # 与「标准 UTC 当前时刻」相差不超过 2 秒
    from datetime import datetime, timezone

    ref = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((now - ref).total_seconds()) < 2


def test_utc_now_monotonic_increasing():
    a = utc_now()
    b = utc_now()
    assert b >= a


def test_utc_fromtimestamp_epoch():
    """utc_fromtimestamp(0) 应为 1970-01-01T00:00:00Z（感知型）。"""
    dt = utc_fromtimestamp(0)
    assert dt.tzinfo is not None
    assert dt.year == 1970 and dt.month == 1 and dt.day == 1
    assert dt.hour == 0 and dt.minute == 0 and dt.second == 0


def test_no_deprecated_utcnow_in_source():
    """回归：非测试源码不得再出现已弃用的 datetime.utcnow() / utcfromtimestamp() 调用。

    使用 AST 仅匹配**真实调用**，避免误伤文档字符串/注释中的提及。
    """
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    banned = {"utcnow", "utcfromtimestamp"}
    offenders = []
    for dirpath, _dirs, files in os.walk(root):
        # 跳过测试目录、venv、缓存与仓库元数据
        if any(seg in dirpath for seg in ("/tests/", "/.git/", "/__pycache__/", "/.pytest_cache/", "/venv", "/.venv/")):
            continue
        if dirpath.endswith("/tests"):
            continue
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                tree = ast.parse(open(path, encoding="utf-8").read())
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    val = node.func.value
                    if isinstance(val, ast.Name) and val.id == "datetime" and node.func.attr in banned:
                        offenders.append(f"{os.path.relpath(path, root)}:{node.lineno}: {node.func.attr}()")
    assert not offenders, "发现已弃用的 UTC 时间调用，应统一改用 backend.utils.timeutil:\n" + "\n".join(offenders)


def test_source_files_parse():
    """辅助：所有被扫描的源码文件均可正常解析（避免误把语法错误当弃用）。"""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    count = 0
    for dirpath, _dirs, files in os.walk(root):
        if any(seg in dirpath for seg in ("/tests/", "/.git/", "/__pycache__/", "/.pytest_cache/", "/venv", "/.venv/")):
            continue
        if dirpath.endswith("/tests"):
            continue
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                ast.parse(open(path, encoding="utf-8").read())
            except (OSError, UnicodeDecodeError, SyntaxError) as exc:
                raise AssertionError(f"语法错误: {path}: {exc}")
            count += 1
    assert count > 0


# ===========================================================================
# 以下为 R1/R2/R3/R5/R6 健壮性测试（纯离线，无网络依赖）
# 覆盖：日期解析、格式化、工作日/交易日判定、区间内构建 的「非法输入安全」行为。
# ===========================================================================


def test_parse_date_valid():
    """合法日期字符串 -> 期望的 date 对象。"""
    assert parse_date("2024-01-15") == date(2024, 1, 15)
    assert parse_date("2024/01/15") == date(2024, 1, 15)
    assert parse_date("20240115") == date(2024, 1, 15)


def test_parse_date_invalid_returns_none_no_raise():
    """非法 / None / 空串一律返回 None，且绝不抛异常。"""
    assert parse_date(None) is None
    assert parse_date("") is None
    assert parse_date("   ") is None
    assert parse_date("not-a-date") is None
    assert parse_date("2024-13-99") is None
    assert parse_date(12345) is None


def test_format_date_none_returns_empty():
    """None / 非法 -> ''；合法 date -> 字符串。"""
    assert format_date(None) == ""
    assert format_date("garbage") == ""
    assert format_date(date(2024, 1, 15)) == "2024-01-15"
    assert format_date("2024-01-15") == "2024-01-15"


def test_is_weekday_weekend_returns_false():
    """周六/周日 -> False；周一~周五 -> True；非法 -> None。"""
    # 2024-01-13 是周六，2024-01-14 是周日
    assert is_weekday(date(2024, 1, 13)) is False
    assert is_weekday("2024-01-14") is False
    # 2024-01-15 是周一
    assert is_weekday("2024-01-15") is True
    assert is_weekday(None) is None
    assert is_weekday("bad") is None


def test_is_trading_day_weekend_and_holiday():
    """周末非交易日；指定休市日亦非交易日；工作日默认交易日。"""
    # 周六
    assert is_trading_day(date(2024, 1, 13)) is False
    # 周一（交易日）
    assert is_trading_day(date(2024, 1, 15)) is True
    # 同一天被显式标记为休市
    assert is_trading_day(date(2024, 1, 15), holidays={date(2024, 1, 15)}) is False
    # 字符串形态的休市日同样生效
    assert is_trading_day("2024-01-15", holidays={"2024-01-15"}) is False
    # 非法输入 -> None
    assert is_trading_day(None) is None
    assert is_trading_day("bad") is None


def test_build_date_range_valid():
    """正常区间返回闭区间内的 date 列表。"""
    rng = build_date_range("2024-01-01", "2024-01-03")
    assert rng == [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]


def test_build_date_range_bad_handled_safely():
    """倒序 / 非法端点 / None 一律返回 []，且不抛异常。"""
    assert build_date_range("2024-01-03", "2024-01-01") == []   # 倒序
    assert build_date_range("bad", "2024-01-03") == []          # 起点非法
    assert build_date_range("2024-01-01", None) == []           # 终点 None
    assert build_date_range(None, None) == []                   # 双双 None

