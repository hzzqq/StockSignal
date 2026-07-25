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


def clamp(x, lo, hi):
    """把数值限制在 [lo, hi] 区间。

    替代散落的 ``max(lo, min(hi, x))``：后者在 x 为 NaN / inf 时（NaN 与任何数比较
    恒 False、inf 参与比较会泄漏）会原样返回非法值，污染分数/比例等下游计算。
    处理约定：None / NaN -> lo（未知，按最保守下界）；+inf -> hi；-inf -> lo。
    """
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return lo
    if math.isinf(xf):
        return hi if xf > 0 else lo
    if math.isnan(xf):
        return lo
    return max(lo, min(hi, xf))


def safe_delta(a, b, default: float = 0.0) -> float:
    """安全地计算 ``a - b``；任一为 None / NaN / inf 时返回 default。

    替代裸 ``a - b``：当 a 或 b 来自行情接口可能为 None/NaN 时，裸减法会抛 TypeError
    或产出 NaN 污染价差/变化量计算。
    """
    x = to_float(a, default=None)
    y = to_float(b, default=None)
    if x is None or y is None:
        return default
    r = x - y
    if math.isnan(r) or math.isinf(r):
        return default
    return r


def to_percent_str(x, dp: int = 2) -> str:
    """把已是百分点原值的数值（如 12.34 表示 12.34%）格式化为 ``12.34%``。

    与 ``format_pct`` 区别：``format_pct`` 用于「比率」（0.1234->12.34%），
    本函数用于「已为百分点的数值」，避免二次乘 100 的口径错误。非法值返回「—」。
    """
    v = to_float(x, default=None)
    if v is None:
        return "—"
    return f"{v:.{dp}f}%"
