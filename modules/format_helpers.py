"""
modules/format_helpers.py
=========================
数值安全格式化与运算的**集中式**小工具集。

为什么需要：
- 行情/资金流接口经常返回 ``NaN`` / ``inf`` / ``None`` / 空字符串，
  直接 ``float()`` + 格式化会在页面上显示 “nan” / “inf”，属于隐性UX缺陷；
- 各模块散落着 ``float(x) if x not in (None, "") else None`` 之类的重复守卫，
  本模块把它们收敛为单一可信实现（DRY + 可观测）。

全部为纯函数，无网络/IO 依赖，可直接单元测试。
"""
from __future__ import annotations

import math
from typing import Optional


def to_float(x, default: Optional[float] = None) -> Optional[float]:
    """把任意值安全转为 float；无法转换（None/空/非数字/NaN/inf）返回 default。"""
    if x is None:
        return default
    if isinstance(x, str):
        s = x.strip()
        if s == "":
            return default
        try:
            x = float(s)
        except (ValueError, TypeError):
            return default
    try:
        x = float(x)
    except (ValueError, TypeError):
        return default
    if math.isnan(x) or math.isinf(x):
        return default
    return x


def safe_div(num, den, default: float = 0.0) -> float:
    """除零 / None / NaN / inf 安全的除法，结果非法时返回 default。"""
    n = to_float(num, default=None)
    d = to_float(den, default=None)
    if n is None or d is None:
        return default
    if d == 0:
        return default
    try:
        r = n / d
    except (ValueError, TypeError, ZeroDivisionError):
        return default
    if math.isnan(r) or math.isinf(r):
        return default
    return r


def format_amount(x) -> str:
    """把金额（元）格式化为 亿 / 万 文本；非法值返回「—」。

    与历史 ``fundflow._to_wan_yi`` 行为一致，但额外屏蔽 NaN / inf / None。
    """
    v = to_float(x, default=None)
    if v is None:
        return "—"
    if abs(v) >= 1e8:
        return f"{v / 1e8:.2f}亿"
    if abs(v) >= 1e4:
        return f"{v / 1e4:.1f}万"
    return f"{v:.0f}"


def format_pct(x, dp: int = 2) -> str:
    """把比率/百分点格式化为 ``x.xx%``；非法值返回「—」。"""
    v = to_float(x, default=None)
    if v is None:
        return "—"
    return f"{v:.{dp}f}%"


def safe_pct(numerator, denominator, default: float = 0.0) -> float:
    """计算百分比 ``numerator / denominator * 100``，全程防 NaN / inf / 除零。

    用于盈亏率、贡献率等场景：分母缺数据、分子出现 NaN、或分母为 0 时
    一律返回 ``default``（以百分比原值返回，不再二次缩放），避免 ``nan`` /
    ``inf`` 静默污染汇总与报告。
    """
    ratio = safe_div(numerator, denominator, default=float("nan"))
    if math.isnan(ratio):
        return default
    return ratio * 100


def safe_int(value, default: int = 0) -> int:
    """把任意值安全转为 int；无法转换（None/空/非数字）返回 default。

    用于替换散落的 ``int(x.get(k, 0) or 0)`` 写法，避免接口返回 ``None`` /
    空串 / 非数字字符串时抛 ``TypeError`` / ``ValueError`` 导致页面崩溃。
    对 ``float`` 先转 ``float`` 再截断取整（与 ``int(float(value))`` 一致）。
    """
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default


def safe_float(value, default: float = 0.0) -> float:
    """把任意值安全转为 float；无法转换（None/空/非数字）返回 default。

    与 :func:`safe_int` 同源，处理行情/资金流接口常见的缺值/脏值。
    """
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
