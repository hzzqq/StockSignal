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
import os
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


# ── Tier1.1 第三批（T-247 续）：缓存库路径解析 / 新浪市场前缀 ──
# ⚠️ __file__ 层级语义：本文件位于 modules/fetcher_core/__init__.py，
# 项目根 = dirname ×3（fetcher.py 在 modules/ 下是 dirname ×2）——迁移时必须校正，
# 否则「真实 data/ 重定向」判定基于错误根目录，SS_DATA_DIR 测试隔离会静默失效。

def _resolve_cache_db_path(explicit):
    """解析缓存库路径，落实「测试隔离但不破坏显式配置」语义。

    - 生产（不设 SS_DATA_DIR）：用显式 config 路径，缺省回落 "data/cache.db"（行为不变）。
    - 测试（conftest 设 SS_DATA_DIR=临时目录）：仅当解析后的路径会落进**真实项目 data/**
      时才重定向到 SS_DATA_DIR/cache.db，避免测试写穿真实 data/；
      显式指向其他位置（如测试 tmp_path、生产自定义绝对路径）一律保留，不破坏测试对库位置的控制。
    """
    _env_db = os.environ.get("SS_DATA_DIR")
    if not _env_db:
        return explicit or "data/cache.db"
    _candidate = explicit or "data/cache.db"
    _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _abs = os.path.abspath(_candidate if os.path.isabs(_candidate) else os.path.join(_root, _candidate))
    _real_data = os.path.abspath(os.path.join(_root, "data"))
    if _abs == _real_data or _abs.startswith(_real_data + os.sep):
        return os.path.join(_env_db, "cache.db")
    return _candidate


def _get_sina_prefix(ticker: str, index_map: dict) -> str:
    """根据 6 位代码返回新浪市场前缀 sh/sz，正确处理指数代码。

    :param index_map: 指数代码 -> 前缀映射（fetcher.StockFetcher._INDEX_SINA_PREFIX，
        领域常量留 fetcher.py，本函数只消费）。
    """
    if ticker in index_map:
        return index_map[ticker]
    code_int = int(ticker) if ticker.isdigit() else 0
    if 600000 <= code_int <= 609999 or 688000 <= code_int <= 689999 or 510000 <= code_int <= 589999:
        return "sh"
    return "sz"


# ── Tier2 第一批（T-247 续）：K线清洗 / 行业关键词 / 周期重采样 ──

def _safe_kline_df(df):
    """将任一数据源返回的 K 线 df 统一标准化（防御式，杜绝单源 TypeError 拖垮整条链路）：

    - 非 DataFrame / 空 / 缺失必备列（date/open/close/high/low/volume）→ 视为无效返回 None
    - ``date`` 强制转为 datetime（解析失败 coerce 为 NaT 并丢弃该行），
      避免「Timestamp 与字符串直接比较」在 L3 过滤时抛 ``TypeError``（即 #352 的 L1-L4 TypeError 根因之一）
    - 其余列（amount / change_pct 等）原样保留
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return None
    need = ["date", "open", "close", "high", "low", "volume"]
    if not all(c in df.columns for c in need):
        return None
    try:
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"])
        return df if not df.empty else None
    except Exception as e:
        logger.warning(f"[fetcher] 处理异常: {e}")
        return None


def _get_stock_industry_keywords(stock_name, industry_map):
    """根据股票名称匹配行业，返回该行业的高频事件关键词。

    :param stock_name: 股票名称（如"贵州茅台"、"宁德时代"）
    :param industry_map: 行业特征词 -> 关键词列表 映射
        （fetcher.StockFetcher._INDUSTRY_KEYWORDS，领域常量留 fetcher.py，本函数只消费）
    :return: list[str] 关键词列表，或空列表
    """
    if not stock_name:
        return []

    matched = set()
    for industry_terms, keywords in industry_map.items():
        # 检查名称是否包含任一行业特征词
        if any(term in stock_name for term in industry_terms):
            matched.update(keywords)

    return sorted(matched) if matched else []


def _resample_kline(daily_df, period):
    """将日线数据聚合为周线或月线。

    :param daily_df: 日线 DataFrame（含 date/open/close/high/low/volume）
    :param period: "weekly"（W-FRI 聚合）或 "monthly"（自然月 ME 聚合）
    """
    daily = daily_df.copy()
    daily["date"] = pd.to_datetime(daily["date"])
    daily = daily.set_index("date").sort_index()
    rule = "W-FRI" if period == "weekly" else "ME"
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    if "amount" in daily.columns:
        agg["amount"] = "sum"
    resampled = daily.resample(rule).agg(agg).dropna()
    resampled = resampled.reset_index()
    # 计算周期涨跌幅（相对于上一周期）
    if "close" in resampled.columns:
        resampled["change_pct"] = resampled["close"].pct_change() * 100
    return resampled
