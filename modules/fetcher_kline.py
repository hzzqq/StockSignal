"""fetcher_kline — 日/周/分钟 K 线方法（含 get_daily 降级链）"""

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


class KlineMixin:
    """Kline 领域方法 mixin（机械搬移自 fetcher.py，签名/降级语义不变）。"""

    def _fetch_level(self, level, symbol, start, end, adjust):
        """单数据源抓取 + 标准化：并行竞速用。

        返回 (df_or_None, error_or_None)。L1=akshare / L2=BaoStock / L3=新浪 / L4=东方财富。
        每个源独立在子线程中执行，先成功者胜出，避免「顺序降级逐个网络超时」的累加等待。
        每个源调用均经 ``observe_source`` 记录成功率/耗时，供数据源健康度横幅使用。
        任何单源的异常（含 TypeError）都会在此被吞掉并降级为「无数据」，由上层继续尝试其余源。
        """
        rename_map = {
            "日期": "date", "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low", "成交量": "volume",
            "成交额": "amount", "涨跌幅": "change_pct",
        }
        # 归一化日期为 Timestamp，避免 df['date'](Timestamp) 与字符串直接比较抛 TypeError
        try:
            _sd = pd.to_datetime(start)
        except Exception as e:
            logger.warning(f"[fetcher] 处理异常: {e}")
            _sd = pd.Timestamp.min
        try:
            _ed = pd.to_datetime(end)
        except Exception as e:
            logger.warning(f"[fetcher] 处理异常: {e}")
            _ed = pd.Timestamp.max
        try:
            if level == "L1" and _fetcher_mod._AK_OK:
                import akshare as ak  # 局部导入：与 _AK_OK 同源，可用时才引用
                df = observe_source(
                    "akshare", level,
                    lambda: _retry_request(
                        lambda: ak.stock_zh_a_hist(
                            symbol=symbol, period="daily",
                            start_date=start.replace("-", ""),
                            end_date=end.replace("-", ""),
                            adjust=adjust,
                        ),
                        max_retries=0,
                    ),
                )
                if df is not None:
                    df = df.rename(columns=rename_map)
                    df = self._safe_kline_df(df)
                    if df is not None:
                        return df, None
                return None, "akshare: 无数据"

            if level == "L2":
                df = observe_source(
                    "baostock", level,
                    lambda: _BaoStockFetcher.fetch_kline(symbol, start, end, adjust=adjust),
                )
                if df is not None:
                    df = self._safe_kline_df(df)
                    if df is not None:
                        return df, None
                return None, "BaoStock: 无数据"

            if level == "L3":
                df = observe_source(
                    "sina", level,
                    lambda: _SinaFetcher.fetch_kline(symbol, start, end),
                )
                if df is not None:
                    df = self._safe_kline_df(df)
                    if df is not None:
                        # date 已统一为 datetime，下面的比较绝不会再抛 TypeError
                        df = df[(df["date"] >= _sd) & (df["date"] <= _ed)]
                        if not df.empty:
                            return df, None
                return None, "新浪: 日期范围外/无数据"

            if level == "L4":
                df = observe_source(
                    "eastmoney", level,
                    lambda: _UrllibFetcher.fetch_kline(symbol, start, end, adjust=adjust),
                )
                if df is not None:
                    df = self._safe_kline_df(df)
                    if df is not None:
                        return df, None
                return None, "东方财富: 无数据"
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[fetcher] 处理异常: {e}")
            return None, f"{level}: {type(e).__name__}"
        return None, f"{level}: 无数据"

    def get_daily(self, symbol, start="2024-01-01", end=None, adjust="qfq",
                  meta_out=None):
        """
        获取个股日线行情。
        降级链（v3 并行竞速）：akshare / BaoStock / 新浪 / 东方财富 四源并发，
        先成功者胜出（耗时由「各源之和」降为「最慢单源」）；全部失败再走缓存兜底。

        T-248 诚实元数据出口：``meta_out`` 传 dict 时回填
        ``{source: live|cache|cache_fallback, is_stale: bool, as_of: 内容日期}``——
        L5 旧缓存兜底命中时 ``source=cache_fallback / is_stale=True``，调用方据此
        如实标注「数据截至 X 日」而非拿旧数据当新数据。不传（默认 None）行为零变化。

        性能优化（v2）：
        - BaoStock 走连接池（每次查询不复登），13s -> 3s
        - 股票存在性预检改为只在 BaoStock 不可用时跑
        - akshare RemoteDisconnected 后立即跳过，不等重试
        - 缓存命中率优先：cache_days 内直接返回
        """
        if end is None:
            end = now_cst_str("%Y-%m-%d")

        def _meta(source, is_stale, df):
            if isinstance(meta_out, dict):
                meta_out.clear()
                meta_out.update({"source": source, "is_stale": is_stale,
                                 "as_of": _df_last_date(df)})

        cache_key = f"daily_{symbol}_{start}_{end}_{adjust}"
        # L0 key 必须带库身份：多实例（测试 tmp 库 / 多 data dir）同 key 不得串库
        l0_key = f"{getattr(self, 'db_path', id(self))}|{cache_key}"

        # ── T-257 L0 内存缓存：重复交互免 SQLite 重读+JSON 重解析（SS_L0_TTL=0 关闭）──
        if _fetcher_mod._L0_TTL > 0:
            with _fetcher_mod._L0_LOCK:
                ent = _fetcher_mod._L0_CACHE.get(l0_key)
            if ent is not None and time.monotonic() - ent["ts"] <= _fetcher_mod._L0_TTL:
                observe_cache_hit("L0", True)  # T-272①：L0 命中计数
                if ent["is_stale"]:
                    # L0 回放缓存兜底数据时重放埋点：每次「用旧数据」都如实计数
                    _fetcher_mod.observe_cache_fallback("L5", True, f"{symbol} as_of={ent['as_of']}(L0)")
                if isinstance(meta_out, dict):
                    meta_out.clear()
                    meta_out.update({"source": ent["source"],
                                     "is_stale": ent["is_stale"],
                                     "as_of": ent["as_of"]})
                return ent["df"].copy()
            # T-272①：L0 未命中（含无记录与已过期两种）
            observe_cache_hit("L0", False)
            if ent is not None:
                with _fetcher_mod._L0_LOCK:
                    _fetcher_mod._L0_CACHE.pop(l0_key, None)

        def _l0_put(df, source, is_stale):
            """命中成功路径写 L0（存副本防调用方原地改写污染；容量满按最旧逐出）。"""
            if _fetcher_mod._L0_TTL <= 0:
                return
            with _fetcher_mod._L0_LOCK:
                _fetcher_mod._L0_CACHE[l0_key] = {"df": df.copy(), "source": source,
                                     "is_stale": is_stale,
                                     "as_of": _df_last_date(df),
                                     "ts": time.monotonic()}
                while len(_fetcher_mod._L0_CACHE) > _fetcher_mod._L0_MAX:
                    _fetcher_mod._L0_CACHE.pop(min(_fetcher_mod._L0_CACHE, key=lambda k: _fetcher_mod._L0_CACHE[k]["ts"]), None)

        conn = self._get_conn()
        try:
            # 缓存优先
            today_str = now_cst_str("%Y-%m-%d")
            max_age_hours = 6 if end == today_str else None
            cached = self._read_cache(conn, "daily_cache", cache_key, max_age_hours=max_age_hours)
            if cached is not None:
                observe_cache_hit("L1", True)  # T-272①：L1 SQLite 命中计数
                _meta("cache", False, cached)
                _l0_put(cached, "cache", False)
                return cached
            observe_cache_hit("L1", False)  # T-272①：L1 未命中（进入四源竞速）

            df = None
            errors = []

            # ── 并行竞速：四源（akshare / BaoStock / 新浪 / 东方财富）并发，先成功者胜出 ──
            levels = ["L1", "L2", "L3", "L4"]
            ex = _cf.ThreadPoolExecutor(max_workers=4)
            try:
                futs = {ex.submit(self._fetch_level, lv, symbol, start, end, adjust): lv for lv in levels}
                # 第一轮：任一源完成即检查（成功立即采用，不再等慢源）
                done, not_done = _cf.wait(futs, timeout=10, return_when=_cf.FIRST_COMPLETED)
                for fut in done:
                    res_df, res_err = fut.result()
                    if res_df is not None and not res_df.empty:
                        df = res_df
                        logger.debug(f"[StockFetcher] {futs[fut]} OK {symbol} (并行竞速)")
                        break
                    else:
                        if res_err:
                            errors.append(res_err)
                # 若第一轮未命中（先完成的是失败源），再等剩余源（最多再 10s）
                if df is None and not_done:
                    done2, _ = _cf.wait(not_done, timeout=10)
                    for fut in done2:
                        res_df, res_err = fut.result()
                        if res_df is not None and not res_df.empty:
                            df = res_df
                            logger.debug(f"[StockFetcher] {futs[fut]} OK {symbol} (并行竞速)")
                            break
                        else:
                            if res_err:
                                errors.append(res_err)
            finally:
                # 取消未完成（如被墙挂起的 akshare），不阻塞等待
                ex.shutdown(wait=False, cancel_futures=True)

            # ── L5: 缓存兜底（T-248：复权一致过滤 + 窗口裁剪 + 行数下限）──
            if df is None or df.empty:
                stale = self._read_stale_cache(conn, "daily_cache", f"daily_{symbol}",
                                               adjust=adjust, start=start, end=end,
                                               min_rows=60)
                if stale is not None:
                    logger.debug(f"[StockFetcher] L5-缓存兜底 OK {symbol}")
                    _fetcher_mod.observe_cache_fallback("L5", True,
                                           f"{symbol} as_of={_df_last_date(stale)}")
                    _meta("cache_fallback", True, stale)
                    _l0_put(stale, "cache_fallback", True)
                    return stale
                _fetcher_mod.observe_cache_fallback("L5", False, f"{symbol} 无可用兜底缓存")
                errors.append("缓存: 无可用数据")

            # ── 全部失败 -> 仍然抛出，但用更友好的中文错误 ──
            if df is None or df.empty:
                detail = "、".join(errors) if errors else "未知原因"
                stock_name = self._code_to_name.get(symbol, "未知")
                raise RuntimeError(
                    f"无法获取 {stock_name}({symbol}) 的K线数据，请确认代码正确。\n"
                    f"原因：{detail}。建议用 600519(贵州茅台) 等大盘股验证网络，或稍后重试。"
                )

            # 标准化输出列
            required = ["date", "open", "close", "high", "low", "volume"]
            available = [c for c in required if c in df.columns]
            df = df[available + [c for c in ["amount", "change_pct"] if c in df.columns]]
            df = df.sort_values("date").reset_index(drop=True)
            self._write_cache(conn, "daily_cache", cache_key, df)
            _meta("live", False, df)
            _l0_put(df, "live", False)
            return df
        finally:
            conn.close()

    def get_kline(self, symbol, start="2024-01-01", end=None, period="daily", adjust="qfq"):
        """
        获取个股日/周/月 K 线。
        period: daily | weekly | monthly
        降级链：优先 akshare 真实周期；失败时由日线聚合。
        """
        period = (period or "daily").lower()
        if period not in ("daily", "weekly", "monthly"):
            raise ValueError("period 必须是 daily/weekly/monthly 之一")
        if end is None:
            end = now_cst_str("%Y-%m-%d")
        if period == "daily":
            return self.get_daily(symbol, start, end, adjust)

        cache_key = f"kline_{period}_{symbol}_{start}_{end}_{adjust}"
        conn = self._get_conn()
        try:
            today_str = now_cst_str("%Y-%m-%d")
            max_age_hours = 6 if end == today_str else None
            cached = self._read_cache(conn, "daily_cache", cache_key, max_age_hours=max_age_hours)
            if cached is not None:
                return cached

            df = None
            errors = []
            # L1: akshare 真实周期
            if _fetcher_mod._AK_OK:
                import akshare as ak  # 局部导入：与 _AK_OK 同源
                try:
                    df = _retry_request(
                        lambda: ak.stock_zh_a_hist(
                            symbol=symbol, period=period,
                            start_date=start.replace("-", ""),
                            end_date=end.replace("-", ""),
                            adjust=adjust,
                        ),
                        max_retries=0,
                    )
                    if df is not None and not df.empty:
                        df = df.rename(columns={
                            "日期": "date", "开盘": "open", "收盘": "close",
                            "最高": "high", "最低": "low", "成交量": "volume",
                            "成交额": "amount", "涨跌幅": "change_pct",
                        })
                        # 防御式标准化：日期解析异常 / 缺列 直接降级，不让 TypeError 中断 L1
                        df = self._safe_kline_df(df)
                        if df is not None:
                            logger.debug(f"[StockFetcher] L1-akshare {period} OK {symbol}")
                        else:
                            df = None
                except Exception as e:
                    if 'Connection' not in type(e).__name__ and 'Remote' not in type(e).__name__:
                        errors.append(f"akshare: {type(e).__name__}")
                    logger.info(f"[StockFetcher] L1-akshare {period} FAIL {symbol}: {type(e).__name__}")
                    df = None

            # L2: 日线聚合
            if df is None or df.empty:
                try:
                    daily = self.get_daily(symbol, start, end, adjust)
                    if daily is not None and not daily.empty:
                        df = self._resample_kline(daily, period)
                        logger.debug(f"[StockFetcher] L2-resample {period} OK {symbol}")
                    else:
                        errors.append("日线聚合: 无数据")
                except Exception as e:
                    logger.warning(f"[fetcher] 处理异常: {e}")
                    errors.append(f"日线聚合: {type(e).__name__}")

            if df is None or df.empty:
                detail = "、".join(errors) if errors else "未知原因"
                stock_name = self._code_to_name.get(symbol, "未知")
                raise RuntimeError(
                    f"无法获取 {stock_name}({symbol}) 的{period}K线数据，请确认代码正确。\n"
                    f"原因：{detail}。建议用 600519(贵州茅台) 等大盘股验证网络，或稍后重试。"
                )

            required = ["date", "open", "close", "high", "low", "volume"]
            available = [c for c in required if c in df.columns]
            df = df[available + [c for c in ["amount", "change_pct"] if c in df.columns]]
            df = df.sort_values("date").reset_index(drop=True)
            self._write_cache(conn, "daily_cache", cache_key, df)
            return df
        finally:
            conn.close()

    def get_index(self, symbol="000001", start="2024-01-01", end=None):
        """指数日线行情（实现见 modules._market_data_io.fetch_index）。"""
        return _mdi.fetch_index(self, symbol, start, end)

    def get_index_minute(self, symbol="000001", trade_date=None):
        """指数当日 1 分钟 K 线（实现见 modules._market_data_io.fetch_index_minute）。"""
        return _mdi.fetch_index_minute(self, symbol, trade_date)

