"""fetcher_health — 数据源健康探测方法"""

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


class HealthMixin:
    """Health 领域方法 mixin（机械搬移自 fetcher.py，签名/降级语义不变）。"""

    def data_source_health(self):
        """数据源健康度探测（#锐评整改：数据源单点+静默降级不可观测）。

        返回结构化健康报告：各路数据源的「依赖可用性 + 本地缓存状态」。
        仅做静态/本地探测（import 能力、缓存表行数），**不发任何网络请求**，
        保证秒回、离线可用；网络实时可达性由调用方按需另做（避免探测本身卡死）。

        返回形如::

            {
              "timestamp": "2026-08-21 12:54:50",
              "summary": "4/5 可用",
              "sources": {
                "akshare":   {"ok": True,  "label": "akshare",  "detail": "依赖可用 (1.16.x)"},
                "baostock":  {"ok": False, "label": "BaoStock", "detail": "依赖缺失"},
                "sina":      {"ok": True,  "label": "新浪财经", "detail": "fetcher 就绪"},
                "eastmoney": {"ok": True,  "label": "东方财富", "detail": "fetcher 就绪"},
                "cache":     {"ok": True,  "label": "本地缓存", "detail": "6 表 / 12,345 条"},
              },
            }
        """
        import importlib.util
        from datetime import datetime
        from modules import _feed_io as _fi  # 延迟 import：本模块仅 re-export 其符号，无 _feed_io 名称

        def _spec(name):
            try:
                return importlib.util.find_spec(name) is not None
            except Exception as e:
                logger.warning(f"[fetcher] 处理异常: {e}")
                return False

        sources = {}

        # ── akshare：_AK_OK 信号 + 实际可导入 ──
        ak_spec = _spec("akshare")
        ak_ok = bool(getattr(_fi, "_AK_OK", False)) and ak_spec
        ak_ver = ""
        if ak_spec:
            try:
                import akshare as _ak
                ak_ver = getattr(_ak, "__version__", "")
            except Exception as e:
                logger.warning(f"[fetcher] 处理异常: {e}")
        sources["akshare"] = {
            "ok": ak_ok, "label": "akshare",
            "detail": f"依赖可用 ({ak_ver})" if ak_ok
                      else ("依赖缺失" if not ak_spec else "信号关闭(_AK_OK=False)"),
        }

        # ── BaoStock ──
        bs_spec = _spec("baostock")
        bs_ok = bool(getattr(_fi, "_BS_OK", False)) and bs_spec
        sources["baostock"] = {
            "ok": bs_ok, "label": "BaoStock",
            "detail": "依赖可用" if bs_ok
                      else ("依赖缺失" if not bs_spec else "信号关闭(_BS_OK=False)"),
        }

        # ── 新浪 / 东方财富：fetcher 类就绪（真实可达性依赖网络，不做探测）──
        sources["sina"] = {
            "ok": hasattr(_fi, "_SinaFetcher"), "label": "新浪财经",
            "detail": "fetcher 就绪" if hasattr(_fi, "_SinaFetcher") else "fetcher 缺失",
        }
        sources["eastmoney"] = {
            "ok": hasattr(_fi, "_UrllibFetcher"), "label": "东方财富",
            "detail": "fetcher 就绪" if hasattr(_fi, "_UrllibFetcher") else "fetcher 缺失",
        }

        # ── 本地缓存：表存在性 + 总行数 ──
        try:
            conn = self._get_conn()
            try:
                tables = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
                table_names = [t[0] for t in tables]
                total_rows = 0
                per_table = {}
                for tname in table_names:
                    # 标识符来自 sqlite_master，仍做白名单校验后再拼接（纵深防御）
                    if not isinstance(tname, str) or not self._SAFE_IDENT_RE.match(tname):
                        continue
                    try:
                        n = conn.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()[0]
                        per_table[tname] = n
                        total_rows += n
                    except Exception as e:
                        logger.warning(f"[fetcher] 处理异常: {e}")
                cache_ok = len(table_names) > 0
                sources["cache"] = {
                    "ok": cache_ok, "label": "本地缓存",
                    "detail": f"{len(table_names)} 表 / {total_rows:,} 条",
                    "tables": per_table,
                }
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"[fetcher] 处理异常: {e}")
            sources["cache"] = {
                "ok": False, "label": "本地缓存",
                "detail": f"缓存库不可读: {type(e).__name__}",
            }

        ok_n = sum(1 for v in sources.values() if v.get("ok"))
        total_n = len(sources)
        return {
            "timestamp": now_cst_str("%Y-%m-%d %H:%M:%S"),
            "summary": f"{ok_n}/{total_n} 可用",
            "sources": sources,
        }

