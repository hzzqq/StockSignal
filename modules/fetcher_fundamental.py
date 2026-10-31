"""fetcher_fundamental — 基本面/宏观/商品/财务方法"""

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



# R75 锁：flag 必须延迟读 modules.fetcher 模块对象（与 _feed_io._is_bs_available 同模式），
# 禁止 from _feed_io import _AK_OK（值拷贝会让 monkeypatch fetcher._AK_OK 失效）。
import modules.fetcher as _fetcher_mod


class FundamentalMixin:
    """Fundamental 领域方法 mixin（机械搬移自 fetcher.py，签名/降级语义不变）。"""

    def get_fundamentals(self, code, use_cache=True):
        """获取个股基本面（名称/最新价/总市值(亿)/市盈率TTM/行业）。

        多源降级链：东方财富 push2 → akshare 个股信息 → akshare 估值(市盈率TTM/总市值)
        → Baostock 名称 → 本地 stock_fundamentals 表；各源只补全缺失字段（合并而非覆盖），
        进程内缓存避免重复请求；全部失败时返回空字典 {}（调用方再用行业关键词兜底，不会崩）。
        """
        code = str(code).strip().zfill(6)
        if use_cache:
            _ttl = CONFIG["cache_ttl"]["fundamentals_seconds"]
            _hit = self._proc_cache_get(_fetcher_mod.StockFetcher._fund_cache, code, _ttl)
            if _hit is not None:
                return _hit

        def _to_float(x):
            try:
                return float(x) if x not in (None, "", "-") else None
            except Exception as e:
                logger.warning(f"[fetcher] 处理异常: {e}")
                return None

        def _has(d):
            return bool(d) and (d.get("market_cap") or d.get("pe_ttm")
                                or d.get("industry") or d.get("name"))

        def _merge(target, src):
            """把 src 中非空的字段补全进 target（只填 target 缺失的键）。"""
            if not isinstance(src, dict):
                return target
            for k, v in src.items():
                if v in (None, ""):
                    continue
                # 数值型指标：0 视为缺失（避免 akshare 偶发返回 0 污染有效数据）
                if k in ("market_cap", "pe_ttm", "price") and v == 0:
                    continue
                if target.get(k) in (None, ""):
                    target[k] = v
            return target

        res = {}  # 始终为 dict，绝不返回 None（避免调用方 .get 崩溃）
        # L1: 东方财富 push2
        try:
            r = _UrllibFetcher.fetch_fundamentals(code)
            if isinstance(r, dict):
                _merge(res, r)
        except Exception as e:
            logger.info(f"[StockFetcher] 东方财富基本面失败 ({code}): {e}")
        # L2: akshare 东方财富个股信息
        if not _has(res):
            try:
                import akshare as ak
                df = ak.stock_individual_info_em(symbol=code)
                info = dict(zip(df["item"], df["value"]))
                cap = _to_float(info.get("总市值"))
                r = {
                    "name": (info.get("股票名称") or "").strip(),
                    "price": _to_float(info.get("最新价")),
                    "market_cap": round(cap / 1e8, 1) if cap else None,
                    "pe_ttm": _to_float(info.get("市盈率")),
                    "industry": (info.get("行业") or "").strip(),
                }
                _merge(res, r)
            except Exception as e:
                logger.info(f"[StockFetcher] akshare 个股信息失败 ({code}): {e}")
        # L3: akshare 估值百度（市盈率TTM / 总市值）补全
        if res.get("pe_ttm") is None or res.get("market_cap") is None:
            try:
                import akshare as ak
                if res.get("pe_ttm") is None:
                    try:
                        df = ak.stock_zh_valuation_baidu(symbol=code, indicator="市盈率(TTM)", period="近一年")
                        if df is not None and not df.empty:
                            res["pe_ttm"] = _to_float(df.iloc[-1]["value"])
                    except Exception as e:
                        logger.info(f"[StockFetcher] akshare 估值(PE)失败 ({code}): {e}")
                if res.get("market_cap") is None:
                    try:
                        df = ak.stock_zh_valuation_baidu(symbol=code, indicator="总市值", period="近一年")
                        if df is not None and not df.empty:
                            cap = _to_float(df.iloc[-1]["value"])
                            # 百度估值接口「总市值」单位已为「亿元」，无需再除 1e8
                            res["market_cap"] = round(cap, 1) if cap else None
                    except Exception as e:
                        logger.info(f"[StockFetcher] akshare 估值(市值)失败 ({code}): {e}")
            except Exception as e:
                logger.info(f"[StockFetcher] akshare 估值失败 ({code}): {e}")
        # L4: 本地股票库名称兜底（免登录）
        # 直接查内存/本地 SQLite all_stocks 缓存，避免 BaoStock 被墙(黑名单)时
        # 走 bs.login 失败导致基本面名称缺失。get_name_only 命中返回纯名称，
        # 未命中返回代码本身，需排除「名称==代码」的假命中。
        if not res.get("name"):
            try:
                local_name = self.get_name_only(code)
                if local_name and local_name != str(code):
                    res["name"] = local_name
            except Exception as e:
                logger.info(f"[StockFetcher] 本地名称兜底失败 ({code}): {e}")
        # L5: 本地库 stock_fundamentals 表兜底
        if not _has(res):
            try:
                conn = self._get_conn()
                cur = conn.cursor()
                cur.execute(
                    "SELECT name,market_cap,pe_ttm,industry FROM stock_fundamentals WHERE code=?",
                    (code,),
                )
                row = cur.fetchone()
                if row:
                    _merge(res, {
                        "name": row[0], "market_cap": row[1],
                        "pe_ttm": row[2], "industry": row[3],
                    })
                conn.close()
            except Exception as e:
                logger.warning(f"[fetcher] 处理异常: {e}")

        if _has(res):
            self._proc_cache_set(_fetcher_mod.StockFetcher._fund_cache, code, res)
        return res

    def get_core_business(self, code, use_cache=True):
        """获取个股核心业务描述（主营业务 / 主营产品），用于多股对比「核心业务」列。

        数据源：同花顺主营构成 ``ak.stock_zyjs_ths(symbol=code)``（网络可用时），
        返回 DataFrame 含 [股票代码, 主营业务, 产品类型, 产品名称, 经营范围]。
        取首行「主营业务」+「产品名称」拼成一句话描述；失败返回空字符串，
        调用方回退到行业（industry）显示。进程内缓存避免重复请求。
        """
        code = str(code).strip().zfill(6)
        if use_cache:
            _ttl = CONFIG["cache_ttl"]["biz_seconds"]
            _hit = self._proc_cache_get(_fetcher_mod.StockFetcher._biz_cache, code, _ttl)
            if _hit is not None:
                return _hit
        biz = ""
        try:
            import akshare as ak
            df = ak.stock_zyjs_ths(symbol=code)
            if df is not None and not df.empty:
                cols = list(df.columns)
                main = ""
                products = ""
                for c in cols:
                    if "主营业务" in c:
                        main = str(df.iloc[0][c] or "")
                        break
                for c in cols:
                    if "产品名称" in c:
                        products = str(df.iloc[0][c] or "")
                        break
                parts = []
                for v in (main, products):
                    v = (v or "").strip()
                    if v and v not in ("-", "None", "nan") and v not in parts:
                        parts.append(v)
                biz = "；".join(parts)
        except Exception as e:  # noqa: BLE001
            logger.info(f"[StockFetcher] 核心业务获取失败 ({code}): {e}")
        if biz:
            self._proc_cache_set(_fetcher_mod.StockFetcher._biz_cache, code, biz)
        return biz

    def get_macro(self, indicator="pmi_mfg"):
        """宏观数据（实现见 modules._market_data_io.fetch_macro）。"""
        return _mdi.fetch_macro(self, indicator)

    def get_commodity_price(self, name="煤炭"):
        """大宗商品（实现见 modules._market_data_io.fetch_commodity_price）。"""
        return _mdi.fetch_commodity_price(self, name)

    def get_financial(self, symbol="600519", report_type="income"):
        """财务三表（实现见 modules._market_data_io.fetch_financial）。"""
        return _mdi.fetch_financial(self, symbol, report_type)

