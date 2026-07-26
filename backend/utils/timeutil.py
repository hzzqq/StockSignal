"""
时间工具
========
统一生成「naive UTC」时间，规避 ``datetime.utcnow()`` / ``datetime.utcfromtimestamp()``
在 Python 3.12+ 的弃用警告。

约定：
- 本项目的 SQLAlchemy ``DateTime`` 列按 **naive UTC** 存储与比较。
- 因此这些辅助函数返回 ``tzinfo=None`` 的 UTC 时间，与既有逻辑（及弃用前的
  ``datetime.utcnow()``）行为完全等价，可安全替换。
"""
from __future__ import annotations

from datetime import datetime, timezone, date
from typing import Iterable, Optional


def utc_now() -> datetime:
    """返回 naive UTC 时间（等价于已弃用的 ``datetime.utcnow()``）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_fromtimestamp(ts: float) -> datetime:
    """UTC 时区**感知**的时间戳转换（替代已弃用的 ``datetime.utcfromtimestamp``）。"""
    return datetime.fromtimestamp(ts, tz=timezone.utc)


# ---------------------------------------------------------------------------
# 以下为日期解析 / 格式化 / 交易日 / 区间构建工具。
# 设计原则（R1/R2）：对一切非法输入（None、空串、格式错误、类型错误、倒序区间）
# 一律安全返回 ``None`` / ``""`` / ``[]``，绝不抛出 ``ValueError``。
# ---------------------------------------------------------------------------

# 常见日期字符串格式兜底，按顺序尝试，避免单一格式失败就崩溃。
_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y-%m-%d %H:%M:%S")


def _to_date(value) -> Optional[date]:
    """把多种形态的输入统一成 ``date``；无法解析时返回 ``None``。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return None
    return None


def parse_date(value, fmt: str = "%Y-%m-%d") -> Optional[date]:
    """解析日期为 ``date`` 对象。

    支持 ``date`` / ``datetime`` / 日期字符串；非法或 ``None`` 一律返回 ``None``，
    不抛出 ``ValueError``。指定 ``fmt`` 时优先用该格式，失败再尝试内置兜底格式。
    """
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, fmt).date()
    except (ValueError, TypeError):
        # 退回到内置多格式兜底，仍失败则返回 None（安全）
        return _to_date(s)


def format_date(value, fmt: str = "%Y-%m-%d") -> str:
    """把 ``date`` / ``datetime`` / 字符串格式化为目标格式字符串。

    ``None`` / 空串 / 非法输入一律返回 ``""``，不抛出 ``ValueError``。
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        d: Optional[date] = value.date()
    elif isinstance(value, date):
        d = value
    else:
        d = parse_date(value, fmt)
    if d is None:
        return ""
    try:
        return d.strftime(fmt)
    except (ValueError, TypeError):
        return ""


def is_weekday(value) -> Optional[bool]:
    """判断是否为工作日（周一~周五）。

    输入非法或 ``None`` 时返回 ``None``（表示「未知」），而非抛异常。
    """
    d = _to_date(value)
    if d is None:
        return None
    return d.weekday() < 5


def is_trading_day(value, holidays: Optional[Iterable] = None) -> Optional[bool]:
    """判断是否为 A 股交易日。

    规则：周一~周五 且 不在 ``holidays`` 休市集合中。
    - 周末返回 ``False``。
    - 传入 ``holidays``（含 ``date``/``datetime``/字符串）时，命中即返回 ``False``。
    - 输入非法或 ``None`` 返回 ``None``（未知），绝不抛异常。
    """
    d = _to_date(value)
    if d is None:
        return None
    if d.weekday() >= 5:
        return False
    if holidays:
        hol = set()
        for h in holidays:
            hd = _to_date(h)
            if hd is not None:
                hol.add(hd)
        if d in hol:
            return False
    return True


def build_date_range(start, end, fmt: str = "%Y-%m-%d"):
    """构建闭区间 ``[start, end]`` 内的日期列表（``date`` 对象）。

    - ``start`` / ``end`` 可为 ``date`` / ``datetime`` / 字符串。
    - 任意一端非法、或 ``start > end``（倒序/空区间）一律返回 ``[]``，不抛异常。
    - 内置循环上限，防止超大范围导致长时间阻塞。
    """
    sd = _to_date(start)
    ed = _to_date(end)
    if sd is None or ed is None:
        return []
    if sd > ed:
        return []
    out: list[date] = []
    cur = sd
    guard = 0
    while cur <= ed:
        out.append(cur)
        guard += 1
        if guard > 100000:
            break
        try:
            cur = date.fromordinal(cur.toordinal() + 1)
        except (ValueError, OverflowError):
            break
    return out
