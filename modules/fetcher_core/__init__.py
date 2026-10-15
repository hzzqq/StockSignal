"""fetcher_core — fetcher.py 的纯函数拆分包（Tier1.1，安全法）。

首轮 pilot：迁入 ``_safe_json_loads``（缓存读取容错，无 StockFetcher 依赖）。
原 ``fetcher.py`` 通过 ``from modules.fetcher_core import _safe_json_loads`` re-export，
行为零变化；后续批次按同范式逐个迁入纯函数（URL 构建 / 缓存键归一化 / 日期工具等）。

设计红线（Tier1.1）：
- 本包**绝不 import ``modules.fetcher``**，避免循环依赖；
- 迁入函数必须保持签名与返回语义一致，且仅依赖标准库 + 本包内定义；
- ``fetcher.py`` 一律 re-export，不得再本地定义（由 AST 守卫锁死）。
"""
import json
import logging
import re
import time

import pandas as pd

logger = logging.getLogger(__name__)


def _safe_json_loads(s, default=None):
    """安全解析 JSON：损坏/空/非字符串一律返回 default，绝不抛异常。

    用于缓存读取路径的容错——缓存数据可能因磁盘写半截、版本变更而损坏，
    直接 json.loads 会抛 JSONDecodeError 炸到调用方；此处降级为 default，
    让上层走缓存未命中/空结果分支，而不是崩溃。
    """
    if not s or not isinstance(s, str):
        return default
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning(f"[fetcher] 缓存 JSON 解析失败，降级返回默认: {type(s).__name__}")
        return default


# ── Tier1.1 第二批（T-247 续）：日期工具 / 进程缓存 / SQL 标识符守卫 ──

def _df_last_date(df):
    """取 DataFrame 的内容日期（date 列最大值，YYYY-MM-DD）；不可得返回 None。

    T-248：as_of 必须用**内容日期**而非缓存写入时间（mtime），防止假新鲜。
    """
    try:
        if isinstance(df, pd.DataFrame) and "date" in df.columns and len(df):
            return str(pd.to_datetime(df["date"]).max())[:10]
    except Exception:  # noqa: BLE001 - 元数据尽力而为，绝不影响主数据路径
        pass
    return None


def _proc_cache_get(cache: dict, key, ttl_seconds):
    """进程内 TTL 缓存读：{key: (存入时刻 monotonic, value)}，超 ttl 判 MISS 并清除。"""
    item = cache.get(key)
    if item is None:
        return None
    ts, value = item
    if (time.monotonic() - ts) > ttl_seconds:
        cache.pop(key, None)  # 过期清除
        return None
    return value


def _proc_cache_set(cache: dict, key, value):
    """进程内 TTL 缓存写：记录 monotonic 时刻供 _proc_cache_get 判过期。"""
    cache[key] = (time.monotonic(), value)


# SQLite 参数绑定只支持「值」占位（?），不支持标识符占位，因此拼接表名不可避免。
# 用白名单正则兜底：任何含 ; 空格 引号 -- / 等字符的注入载荷一律拒绝。
SAFE_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(name: str) -> str:
    """校验 SQLite 标识符（表名），非法标识符直接抛 ValueError，绝不拼接进 SQL。"""
    if not isinstance(name, str) or not SAFE_IDENT_RE.match(name):
        raise ValueError(f"非法的 SQLite 标识符: {name!r}")
    return name
