"""
数据采集模块
多级降级链：akshare -> BaoStock -> 新浪财经 -> 东方财富(urllib) -> 本地缓存

所有请求默认走本地 SQLite 缓存，cache_days 内不重复请求网络。
"""

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

from modules.fetcher_base import BaseFetcher, load_config  # noqa: F401
from modules.fetcher_storage import StorageMixin  # noqa: F401
from modules.fetcher_realtime import RealtimeMixin  # noqa: F401
from modules.fetcher_kline import KlineMixin  # noqa: F401
from modules.fetcher_search import SearchMixin  # noqa: F401
from modules.fetcher_sector import SectorMixin  # noqa: F401
from modules.fetcher_fundamental import FundamentalMixin  # noqa: F401
from modules.fetcher_health import HealthMixin  # noqa: F401

# _L0_* 缓存基础设施：模块级单一真源（原 fetcher.py 顶部常量），
# 各 mixin 方法体经 _fetcher_mod._L0_* 惰性引用，避免缓存/锁分片。
_L0_CACHE: dict = {}
_L0_LOCK = threading.Lock()
_L0_TTL = float(os.environ.get("SS_L0_TTL", "300"))
_L0_MAX = int(os.environ.get("SS_L0_MAX", "600"))

# T-247：StockFetcher = 共享基类 + 7 个领域 mixin 多继承组合。
# 所有公开方法签名/返回类型/降级语义由 FETCHER_CONTRACT.md 冻结，本文件仅做组合，零行为变更。
class StockFetcher(BaseFetcher, StorageMixin, RealtimeMixin, KlineMixin,
                   SearchMixin, SectorMixin, FundamentalMixin, HealthMixin):
    """股票行情与宏观数据采集器。领域方法见各 fetcher_* mixin，见 FETCHER_CONTRACT.md。
    以下两个为影子名薄壳（真身迁 fetcher_core，由 fetcher_core_tier11 守卫锁定必须留在本层）。
    """
    def _get_stock_industry_keywords(stock_name):
        """根据股票名称匹配行业，返回该行业的高频事件关键词。

        真身迁 modules.fetcher_core（T-247 Tier2，industry_map 作参数注入）；
        领域常量 _INDUSTRY_KEYWORDS 留本类（仅此消费）。
        """
        return _get_stock_industry_keywords(stock_name, StockFetcher._INDUSTRY_KEYWORDS)

    def synth_us_index_intraday(self, open_, high, low, close, prev_close):
        """当美股指数只有 O/H/L/C 快照时，合成一条有真实日内形态的近似分时曲线。

        真身迁 modules.fetcher_core._synth_us_index_intraday（T-247 Tier2 第二批），
        本薄壳仅委托，签名与返回语义零变化。返回 (spark_x, spark_y) 或 (None, None)。
        """
        return _synth_us_index_intraday(open_, high, low, close, prev_close)


