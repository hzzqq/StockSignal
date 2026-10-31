"""fetcher_storage — storage/cache 公开方法"""

import io
import json
import os
import re
import sqlite3
import threading
import time
import warnings
import logging as _logging
import urllib.request
import urllib.error
import urllib.parse
import contextlib
import socket  # 捕获瞬时网络错误（超时/连接重置/DNS）做重试兜底
from datetime import datetime, timedelta
import concurrent.futures as _cf
import yaml  # load_config 用到；原在抽离块内，抽到 _feed_io 后在此补回
import pandas as pd  # 原在抽离块内，StockFetcher 大量使用 DataFrame
import numpy as np  # 原在抽离块内，StockFetcher 用到 np.

from modules.time_utils import now_cst_str, now_cst_naive


# 底层 I/O 层已抽到 modules._feed_io（P2-1 降耦），此处 re-export 保持全站 import 兼容
from modules._feed_io import (  # noqa: F401
    _safe_urlopen,
    logger,
    _AK_OK,
    _BS_OK,
    CONFIG,
    SOURCE_METRICS,
    _record_source_metric,
    _observe_log,
    observe_source,
    observe_cache_fallback,
    observe_cache_hit,
    get_source_metrics,
    _is_market_open,
    _is_midday_break,
    _validate_sector_data,
    _retry_request,
    _symbol_to_secid,
    _index_to_secid,
    _symbol_to_bs,
    _symbol_to_sina,
    _BaoStockFetcher,
    _SinaFetcher,
    _UrllibFetcher,
)

# 市场数据 I/O 叶子模块（#锐评整改：从 StockFetcher 下沉，零循环依赖）
import modules._market_data_io as _mdi

# T-247 Tier1.1：纯函数真身迁 modules.fetcher_core，此处 re-export 同一对象
# （调用点零改动；AST 守卫 tests/test_fetcher_core_tier11.py 锁死防本地定义回潮）
from modules.fetcher_core import (  # noqa: F401
    _df_last_date,
    _get_sina_prefix,
    _get_stock_industry_keywords,
    _proc_cache_get,
    _proc_cache_set,
    _resample_kline,
    _resolve_cache_db_path,
    _safe_ident,
    _safe_kline_df,
    _synth_us_index_intraday,
    SAFE_IDENT_RE,
)

# 代理 IP 池（免费，best-effort 抗封禁）：仅当 SS_PROXY_POOL=1 时启用。
# 通过进程级 HTTPS_PROXY/HTTP_PROXY 让 akshare / requests 继承轮换出口 IP。
# 初始化失败绝不影响主流程（akshare 仍可直连）。baostock 是账号级限流，不受本池影响。
try:
    from modules.proxy_pool import get_proxy_pool as _get_proxy_pool
    _pp = _get_proxy_pool()
    if _pp.enabled:
        _pp.apply_to_env()
except Exception as _pp_err:  # noqa: BLE001
    logger.warning("代理 IP 池初始化失败（已忽略，回退直连）: %s", _pp_err)


# Tier1.1 安全拆分 pilot：纯函数 _safe_json_loads 迁入 modules.fetcher_core，
# 此处 re-export 保持行为零变化（fetcher.py 内部 509/519/547/1174 行调用不受影响）。
from modules.fetcher_core import _safe_json_loads  # noqa: F401

_L0_CACHE: dict = {}
_L0_LOCK = threading.Lock()
_L0_TTL = float(os.environ.get("SS_L0_TTL", "300"))
_L0_MAX = int(os.environ.get("SS_L0_MAX", "600"))

# R75 锁：flag 必须延迟读 modules.fetcher 模块对象（与 _feed_io._is_bs_available 同模式），
# 禁止 from _feed_io import _AK_OK（值拷贝会让 monkeypatch fetcher._AK_OK 失效）。
import modules.fetcher as _fetcher_mod


class StorageMixin:
    """Storage 领域方法 mixin（机械搬移自 fetcher.py，签名/降级语义不变）。"""

    def clear_cache(self, table_name=None, cache_key=None):
        """清空指定缓存表（或表中某个 cache_key 的记录）。

        返回**实际删除的行数**（int），供调用方如实反馈"清了几条"而非无条件报成功。

        ⚠️ 这里曾用 ``except sqlite3.OperationalError: pass`` 静默吞掉删除失败，
        导致"库被锁 / 磁盘 I/O 错误 / 无写权限"时缓存并未清空，调用方（如
        pages/11 的「强制刷新数据」）却照报"缓存已清除"，用户拿着旧缓存当新数据。
        现改为：表不存在属预期（降级 debug），其余 OperationalError 一律 warning 留痕。
        """
        # 先校验标识符再开连接（fail-fast）：非法表名不做任何 DB 操作，绝不拼进 SQL
        tables = (
            [table_name] if table_name
            else ["daily_cache", "index_cache", "macro_cache", "commodity_cache"]
        )
        tables = [self._safe_ident(t) for t in tables]
        # T-257：清缓存必须同步失效 L0 内存层，否则「强制刷新」后页面还在吃内存旧数据
        with _L0_LOCK:
            _L0_CACHE.clear()
        conn = self._get_conn()
        deleted = 0
        try:
            for t in tables:
                try:
                    if cache_key:
                        cur = conn.execute(
                            f"DELETE FROM {t} WHERE cache_key = ?", (cache_key,)
                        )
                    else:
                        cur = conn.execute(f"DELETE FROM {t}")
                    deleted += max(cur.rowcount or 0, 0)
                except sqlite3.OperationalError as e:
                    if "no such table" in str(e).lower():
                        # 该表首次运行从未写过 → 无表可删，属预期
                        logger.debug(f"[StockFetcher] 缓存表 {t} 尚未创建，跳过删除")
                    else:
                        logger.warning(
                            f"[StockFetcher] 清空缓存表 {t} 失败，缓存未清空: {e}"
                        )
            conn.commit()
        finally:
            conn.close()
        return deleted

    def get_sector_cache_info(self):
        """返回板块缓存的更新时间（ISO 字符串）、距今分钟数、数据来源；无缓存返回 None。"""
        conn = self._get_conn()
        try:
            self._init_cache_table(conn, "sector_cache")
            row = conn.execute(
                "SELECT updated_at FROM sector_cache WHERE cache_key = ?",
                ("sector_list_v3",),
            ).fetchone()
            if row is None:
                return None
            updated_at = datetime.fromisoformat(row[0])
            age_minutes = (now_cst_naive() - updated_at).total_seconds() / 60

            source = "未知"
            try:
                source_row = conn.execute(
                    "SELECT data_json FROM sector_cache WHERE cache_key = ?",
                    ("sector_list_v3_source",),
                ).fetchone()
                if source_row:
                    source = json.loads(source_row[0]).get("source", "未知")
            except Exception as e:
                logger.warning(f"[fetcher] 处理异常: {e}")

            return updated_at.isoformat(), age_minutes, source
        except Exception as e:
            logger.warning(f"[fetcher] 处理异常: {e}")
            return None
        finally:
            conn.close()

