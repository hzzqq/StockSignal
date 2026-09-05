"""time_utils（R12 时区债单一真理源）单元测试。

验证：
- now_cst 返回带 +08:00 时区的中国标准时间；
- now_cst_naive 返回朴素（naive）但日期为中国的本地时间（可与朴素 datetime 相减）；
- now_cst_str / today_cst_str 默认给出中国日期字符串；
- 与本地朴素 datetime 相减不抛 TypeError（避免 session._parse_iso 的 tz 混合坑）。
"""

from datetime import datetime, timedelta, timezone

from modules.time_utils import now_cst, now_cst_naive, now_cst_str, today_cst_str


def test_now_cst_is_china_aware():
    t = now_cst()
    assert t.tzinfo is not None
    # 中国标准时间固定 UTC+8，无夏令时
    assert t.utcoffset() == timedelta(hours=8)
    assert t.strftime("%Y-%m-%d") == today_cst_str()


def test_now_cst_naive_is_naive_but_china_date():
    n = now_cst_naive()
    assert n.tzinfo is None
    # 朴素分支的日期应与 now_cst 的日期一致（同一时刻）
    assert n.strftime("%Y-%m-%d") == now_cst().strftime("%Y-%m-%d")


def test_now_cst_str_default_format():
    s = now_cst_str()
    assert len(s) == 10
    assert s[4] == "-" and s[7] == "-"
    assert s == now_cst_str("%Y-%m-%d")


def test_today_cst_str_matches_now_cst_str():
    assert today_cst_str() == now_cst_str("%Y-%m-%d")


def test_now_cst_naive_subtract_naive_no_typeerror():
    # 复现 session._parse_iso 的 tz 混合坑：naive 与 naive 相减不抛 TypeError
    dt = datetime(2026, 1, 1, 9, 30, 0)  # 朴素
    delta = now_cst_naive() - dt
    assert isinstance(delta, timedelta)


def test_now_cst_aware_subtract_aware_ok():
    # tz-aware 与 tz-aware 相减也成立（备用路径）
    delta = now_cst() - datetime(2026, 1, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert isinstance(delta, timedelta)
