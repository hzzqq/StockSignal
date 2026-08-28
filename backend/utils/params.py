"""
backend/utils/params.py
-----------------------
共享的安全查询参数解析工具。

替代 `int(request.args.get(...))` 这类会在传入非数字时直接抛 500 的写法，
对缺失 / 非数字 / 越界统一做兜底。保持依赖极简，仅用到 Flask 的 `request`。
"""
from __future__ import annotations

import re

from flask import request

# A 股代码：6 位纯数字（沪市 60xxxx / 68xxxx，深市 00xxxx / 30xxxx 等）
_TICKER_RE = re.compile(r"^\d{6}$")


def validate_stock_code(code):
    """校验 A 股股票代码（6 位纯数字），返回 ``(ok: bool, normalized: str)``。

    ``normalized`` 为去空格后的原始输入；校验失败时为 ``""``。
    供各 API 边界复用，统一「股票代码须为 6 位数字」契约，避免每处重复正则。
    """
    if not isinstance(code, str):
        return False, ""
    normalized = code.strip()
    if not _TICKER_RE.match(normalized):
        return False, ""
    return True, normalized


def parse_int_param(name, default=0, lo=None, hi=None, source=None):
    """
    从查询参数（或任意 dict-like 的 `source`）中安全解析一个整数。

    - 键缺失 -> 返回 default
    - 非数字（TypeError / ValueError）-> 返回 default
    - 低于 lo -> 钳制为 lo
    - 高于 hi -> 钳制为 hi

    ⚠️ 分页场景请勿直接用本函数解析 limit/per_page：只钳 hi 不钳 lo 时，
    负数会穿透上限（见 `parse_limit_param` 的说明）。用 `parse_limit_param`。
    """
    if source is None:
        source = request.args
    try:
        v = int(source.get(name, default))
    except (TypeError, ValueError):
        return default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def parse_limit_param(name="limit", default=50, hi=200, source=None):
    """
    安全解析分页条数（limit / per_page），强制下界为 1。

    ⚠️ 为什么必须钳下界：SQLite（以及 MySQL 的 `LIMIT -1` 语义差异）中
    `LIMIT` 取负值表示「不限制行数」。若只写 `min(int(...), 200)`，
    请求 `?limit=-1` 会得到 -1 -> `LIMIT -1` -> **200 条上限被完全绕过，
    整表被一次性拉出**（用户表 / 帖子 / 告警全量泄露 + 内存打满的 DoS 面）。
    因此分页条数一律走本函数，lo 恒为 1。
    """
    return parse_int_param(name, default=default, lo=1, hi=hi, source=source)


def parse_page_param(name="page", default=1, source=None):
    """安全解析页码，强制下界为 1（避免 offset 为负导致的越界/无意义查询）。"""
    return parse_int_param(name, default=default, lo=1, source=source)


def parse_str_param(name, default="", max_len=128, source=None):
    """
    安全解析一个字符串查询/表单参数，统一做 strip + 长度钳制。

    防止超长字符串（恶意/误用）直接透传到下游 akshare / DB 查询，
    导致资源占用或日志刷屏。缺失 / 非字符串 -> 返回 default。
    """
    if source is None:
        source = request.args
    raw = source.get(name)
    if not isinstance(raw, str):
        return default
    return raw.strip()[:max_len]
