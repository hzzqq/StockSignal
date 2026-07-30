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

import html as _html
import math
import re as _re
from typing import Optional


_PCT_RE = _re.compile(r"(-?\d+(?:\.\d+)?)\s*%")

def extract_pct(s, default: float = float("-inf")) -> float:
    """从标题/文本提取涨跌幅数值（"%" 前的浮点数），用于排序或上色。

    常见场景：消息/异动标题形如 "贵州茅台(600519) 大涨 +3.45%"，
    但社区帖 / 系统消息标题（如 "💬 无标题"、"⚠️ 部分数据源不可用"）并不含数字涨跌幅。
    旧实现用 ``title.split('%')[0].split(' ')[-1]`` 强转 float，遇到无 "%" 的标题会抛
    ValueError，且在排序 lambda 中抛错会让**整个排序静默失效**。

    本函数：
    - 用正则匹配第一个 ``-?\\d+(\\.\\d+)?%``；
    - 提取失败（None/无 "%"/数字非法）返回 ``default``（默认 ``-inf``，便于排序时沉底）；
    - 绝不抛异常，调用方可放心用于 sort key。
    """
    if s is None:
        return default
    text = s if isinstance(s, str) else str(s)
    m = _PCT_RE.search(text)
    if not m:
        return default
    val = to_float(m.group(1), default)
    if val is None:
        return default
    return val


def safe_html_text(x, default: str = "") -> str:
    """把任意外部数据安全转义为可嵌入 HTML 的纯文本。

    使用场景：页面用 ``st.markdown(..., unsafe_allow_html=True)`` 拼接 HTML 时，
    任何来自外部（新闻标题、股吧正文、接口字段）的内容都必须先经本函数转义，
    否则内容里的 ``<script>`` / ``<img onerror=...>`` / 未闭合标签会被浏览器当作
    真实 HTML 解析——轻则页面标签泄露、排版错乱，重则构成 XSS。

    - ``None`` / 空值 → 返回 ``default``（不返回字面量 "None"）；
    - 同时转义引号（``quote=True``），支持嵌入属性值内。
    """
    if x is None:
        return default
    s = x if isinstance(x, str) else str(x)
    if s == "":
        return default
    return _html.escape(s, quote=True)


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
