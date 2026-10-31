"""fetcher_realtime — 实时行情方法"""

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


class RealtimeMixin:
    """Realtime 领域方法 mixin（机械搬移自 fetcher.py，签名/降级语义不变）。"""

    def get_realtime_quote(self, ticker):
        """
        获取 A 股/指数实时五档行情。
        数据源：新浪财经（需要 Referer）。指数代码同样支持。
        返回字典，包含：
          - name: 股票名称
          - open, prev_close, current, high, low
          - volume, amount
          - bid: [{price, volume}, ...] 买一到买五
          - ask: [{price, volume}, ...] 卖一到卖五
          - datetime: 行情时间
        获取失败返回 None。
        """
        if not ticker:
            return None
        ticker = str(ticker).strip().zfill(6)

        # 短缓存：交易时间 30 秒，非交易时间 5 分钟
        cache_key = f"rt_quote_{ticker}"
        conn = self._get_conn()
        try:
            max_age_seconds = 30 if _is_market_open() else 300
            cached = self._read_cache(
                conn, "rt_quote_cache", cache_key,
                max_age_seconds=max_age_seconds, as_dataframe=False
            )
            if cached is not None:
                return cached

            # 构造新浪代码
            sina_code = f"{self._get_sina_prefix(ticker)}{ticker}"

            url = f"https://hq.sinajs.cn/list={sina_code}"
            req = urllib.request.Request(
                url,
                headers={
                    "Referer": "https://finance.sina.com.cn",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                },
            )
            with _safe_urlopen(req, timeout=10) as resp:
                text = resp.read().decode("gbk", errors="replace")

            # 解析：var hq_str_sh601088="...";
            start = text.find('"')
            end = text.find('"', start + 1)
            if start == -1 or end == -1:
                return None
            data = text[start + 1:end].split(",")
            if len(data) < 32:
                return None

            def _parse_float(val, default=0.0):
                try:
                    return float(val) if val else default
                except Exception as e:
                    logger.warning(f"[fetcher] 处理异常: {e}")
                    return default

            def _parse_int(val, default=0):
                try:
                    return int(float(val)) if val else default
                except Exception as e:
                    logger.warning(f"[fetcher] 处理异常: {e}")
                    return default

            quote = {
                "ticker": ticker,
                "name": data[0],
                "open": _parse_float(data[1]),
                "prev_close": _parse_float(data[2]),
                "current": _parse_float(data[3]),
                "high": _parse_float(data[4]),
                "low": _parse_float(data[5]),
                "volume": _parse_int(data[8]),
                "amount": _parse_float(data[9]),
                "bid": [
                    {"price": _parse_float(data[11]), "volume": _parse_int(data[10])},
                    {"price": _parse_float(data[13]), "volume": _parse_int(data[12])},
                    {"price": _parse_float(data[15]), "volume": _parse_int(data[14])},
                    {"price": _parse_float(data[17]), "volume": _parse_int(data[16])},
                    {"price": _parse_float(data[19]), "volume": _parse_int(data[18])},
                ],
                "ask": [
                    {"price": _parse_float(data[21]), "volume": _parse_int(data[20])},
                    {"price": _parse_float(data[23]), "volume": _parse_int(data[22])},
                    {"price": _parse_float(data[25]), "volume": _parse_int(data[24])},
                    {"price": _parse_float(data[27]), "volume": _parse_int(data[26])},
                    {"price": _parse_float(data[29]), "volume": _parse_int(data[28])},
                ],
                "datetime": f"{data[30]} {data[31]}",
            }

            self._write_cache(conn, "rt_quote_cache", cache_key, quote)
            return quote
        except Exception as e:
            logger.info(f"[StockFetcher] 获取实时行情失败 ({ticker}): {e}")
            # 数据源不可用 → 回退到「过期缓存」兜底（与 daily/index/sector 同策略）。
            # 避免 akshare/新浪全路挂时实时行情直接变 None，页面行情卡白。
            try:
                stale = self._read_stale_cache(conn, "rt_quote_cache", cache_key, as_dataframe=False)
                if stale is not None:
                    logger.info(f"[StockFetcher] 实时行情回退过期缓存 ({ticker})")
                    return stale
            except Exception as e:
                logger.warning(f"[fetcher] 处理异常: {e}")
            return None
        finally:
            conn.close()

    def get_global_index_quote(self, info):
        """获取海外指数行情，返回绘图所需的统一字段字典；全部失败返回 None。

        info 约定字段：
          - name:       显示名称（如 "道琼斯"）
          - sina_rt:    新浪实时代码（美股用，如 "gb_$dji"），可选
          - sina_hist:  新浪日线历史符号（富时/韩国用，如 "英国富时100指数"），可选

        返回 dict：name, current, change, change_pct, open, high, low,
                   prev_close, spark_x, spark_y

        数据源策略：
          - 美股 -> 新浪实时快照（hq.sinajs.cn）取最新点位/涨跌；走势 sparkline
                    用实时 OHLC 合成（美股日线不在本地可用）。
          - 富时100 / 韩国KOSPI -> 新浪日线历史（ak.index_global_hist_sina）：
                    最新收盘为当前点位、前收盘为昨收，sparkline 取近 30 日收盘。
        任意来源失败都优雅降级，最坏返回 None（由调用方显示 "暂无数据"）。
        """
        name = info.get("name", "")
        current = change = change_pct = open_ = high = low = prev_close = None
        spark_x = spark_y = None

        # 1) 美股：新浪实时快照
        rt = None
        sina_rt = info.get("sina_rt")
        if sina_rt:
            rt = self._get_sina_global_rt(sina_rt)
            if rt:
                current = rt.get("current")
                open_ = rt.get("open")
                high = rt.get("high")
                low = rt.get("low")
                prev_close = rt.get("prev_close")
                change = rt.get("change")
                change_pct = rt.get("change_pct")

        # 2) 富时/韩国：新浪日线历史
        sym = info.get("sina_hist")
        hist = None
        if sym:
            hist = self._get_sina_global_hist(sym)
        if hist is not None and not hist.empty:
            closes = [float(x) for x in hist["close"].tolist()]
            spark_y = closes[-30:]
            spark_x = list(range(len(spark_y)))
            if current is None and closes:
                current = closes[-1]
            if prev_close is None and len(closes) >= 2:
                prev_close = closes[-2]
            last = hist.iloc[-1]
            try:
                if open_ is None:
                    open_ = float(last.get("open", current) or current)
                if high is None:
                    high = float(last.get("high", current) or current)
                if low is None:
                    low = float(last.get("low", current) or current)
            except Exception as e:
                logger.warning(f"[fetcher] 处理异常: {e}")

        # 美股无日线历史 -> 用实时 OHLC 合成 4 点 sparkline（与 A 股无分钟线兜底一致）
        if spark_y is None and None not in (open_, high, low, current):
            spark_x = [0, 1, 2, 3]
            spark_y = [open_, high, low, current]

        # 兜底：实时给了 current 但没算涨跌 -> 用昨收推算
        if current is not None and prev_close:
            if change is None:
                change = current - prev_close
            if change_pct is None:
                change_pct = (change / prev_close) * 100 if prev_close else 0.0
        elif current is not None and change is not None and prev_close is None:
            prev_close = current - change
            change_pct = (change / prev_close) * 100 if prev_close else 0.0

        if current is None:
            return None

        return {
            "name": name,
            "current": float(current),
            "change": float(change) if change is not None else None,
            "change_pct": float(change_pct) if change_pct is not None else None,
            "open": float(open_) if open_ is not None else None,
            "high": float(high) if high is not None else None,
            "low": float(low) if low is not None else None,
            "prev_close": float(prev_close) if prev_close is not None else None,
            "spark_x": spark_x,
            "spark_y": spark_y,
        }

    def _get_sina_global_rt(self, sina_code):
        """新浪海外指数实时快照解析（美股 DJI/IXIC/INX 等）。返回 dict 或 None。"""
        if not sina_code:
            return None
        try:
            url = f"https://hq.sinajs.cn/list={sina_code}"
            req = urllib.request.Request(
                url,
                headers={
                    "Referer": "https://finance.sina.com.cn",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                },
            )
            with _safe_urlopen(req, timeout=10) as resp:
                text = resp.read().decode("gbk", errors="replace")
            start = text.find('"')
            end = text.find('"', start + 1)
            if start == -1 or end == -1:
                return None
            arr = text[start + 1:end].split(",")
            if len(arr) < 9:
                return None

            def _pf(v, default=0.0):
                try:
                    return float(v) if v not in ("", "-") else default
                except Exception as e:
                    logger.warning(f"[fetcher] 处理异常: {e}")
                    return default

            # 实测字段顺序（2026-07）：
            #   0 名称 | 1 最新 | 2 涨跌幅% | 3 时间
            #   4 涨跌额 | 5 昨收 | 6 今开 | 7 最低 | 8 最高
            return {
                "name": arr[0].strip(),
                "current": _pf(arr[1]),
                "change_pct": _pf(arr[2]),
                "change": _pf(arr[4]),
                "prev_close": _pf(arr[5]),
                "open": _pf(arr[6]),
                "low": _pf(arr[7]),
                "high": _pf(arr[8]),
            }
        except Exception as e:
            logger.info(f"[StockFetcher] 海外指数实时获取失败 ({sina_code}): {e}")
            return None

    def _get_sina_global_hist(self, symbol):
        """新浪日线历史（ak.index_global_hist_sina）。返回 DataFrame 或 None。"""
        if not symbol:
            return None
        try:
            import akshare as ak
            df = ak.index_global_hist_sina(symbol=symbol)
            if df is None or df.empty:
                return None
            return df
        except Exception as e:
            logger.info(f"[StockFetcher] 海外指数日线获取失败 ({symbol}): {e}")
            return None

    def get_index_kline_sina(self, code, scale: int = 5, datalen: int = 48):
        """获取 A 股指数当日/近期分钟级 K 线（新浪 K 线接口，走代理可用）。

        返回 DataFrame[time, open, high, low, close] 或 None。
        code 为纯数字指数代码（000001 / 399001 / 399006 等），
        自动映射新浪前缀：6 开头 -> sh，其余 -> sz。
        该接口在 Eastmoney 被代理拦截的本环境下，是唯一可用的指数分时来源。
        """
        if not code:
            return None
        prefix = "sh" if code.startswith("6") else "sz"
        sym = f"{prefix}{code}"
        url = (
            "https://quotes.sina.cn/cn/api/json_v2.php/"
            f"CN_MarketDataService.getKLineData?symbol={sym}&scale={scale}"
            f"&ma=no&datalen={datalen}"
        )
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "Referer": "https://finance.sina.com.cn",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                },
            )
            with _safe_urlopen(req, timeout=10) as resp:
                text = resp.read().decode("gbk", errors="replace")
            import json as _json
            data = _json.loads(text)
            if not data:
                return None
            rows = []
            for d in data:
                try:
                    rows.append({
                        "time": str(d.get("day", "")),
                        "open": float(d["open"]),
                        "high": float(d["high"]),
                        "low": float(d["low"]),
                        "close": float(d["close"]),
                    })
                except (TypeError, ValueError, KeyError):
                    continue
            if not rows:
                return None
            df = pd.DataFrame(rows)
            return df.sort_values("time").reset_index(drop=True)
        except Exception as e:
            logger.info(f"[StockFetcher] 新浪指数分时获取失败 ({code}): {e}")
            return None

    def get_stock_intraday_sina(self, symbol, trade_date=None):
        """获取 A 股个股当日/近期分时数据（新浪分钟 K 线接口，走代理可用）。

        返回 (DataFrame[time, open, high, low, close, volume, amount], prev_close, trade_date)
        或 (None, None, None)。

        symbol 为 6 位股票代码；自动映射新浪前缀：6 开头 -> sh，其余 -> sz。
        trade_date 为空时取最近交易日；prev_close 为所选交易日的前一交易日收盘价
        （用于分时图昨收基准线）。新浪分时接口 day 字段形如 '2026-07-24 15:00:00'，
        在 Eastmoney 被代理拦截的本环境下，这是唯一可用的个股分时来源。
        """
        code = str(symbol) if symbol is not None else ""
        if not (code.isdigit() and len(code) == 6):
            return None, None, None
        prefix = "sh" if code.startswith("6") else "sz"
        sym = f"{prefix}{code}"
        url = (
            "https://quotes.sina.cn/cn/api/json_v2.php/"
            f"CN_MarketDataService.getKLineData?symbol={sym}&scale=1"
            f"&ma=no&datalen=480"
        )
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "Referer": "https://finance.sina.com.cn",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                },
            )
            with _safe_urlopen(req, timeout=10) as resp:
                text = resp.read().decode("gbk", errors="replace")
            import json as _json
            data = _json.loads(text)
            if not data:
                return None, None, None
            rows = []
            for d in data:
                try:
                    day = str(d.get("day", ""))
                    rows.append({
                        "time": day,
                        "open": float(d["open"]),
                        "high": float(d["high"]),
                        "low": float(d["low"]),
                        "close": float(d["close"]),
                        "volume": float(d.get("volume", 0) or 0),
                        "amount": float(d.get("amount", 0) or 0),
                    })
                except (TypeError, ValueError, KeyError):
                    continue
            if not rows:
                return None, None, None
            df = pd.DataFrame(rows).sort_values("time").reset_index(drop=True)
            # 按交易日分桶：取最近交易日为 trade_date（多日桶在客户端按 day[:10] 分）
            df["_date"] = df["time"].str[:10]
            dates = sorted(df["_date"].unique().tolist(), reverse=True)
            if not dates:
                return None, None, None
            target = trade_date if trade_date in dates else dates[0]
            sub = df[df["_date"] == target].copy().drop(columns=["_date"])
            if sub.empty:
                return None, None, None
            # prev_close：前一交易日收盘（取不到时用当日首笔开盘近似）
            prev_close = None
            idx = dates.index(target)
            if idx + 1 < len(dates):
                prev_df = df[df["_date"] == dates[idx + 1]]
                if not prev_df.empty:
                    prev_close = float(prev_df.iloc[-1]["close"])
            if prev_close is None:
                prev_close = float(sub.iloc[0]["open"])
            return sub, prev_close, target
        except Exception as e:
            logger.info(f"[StockFetcher] 新浪个股分时获取失败 ({symbol}): {e}")
            return None, None, None

    def synth_us_index_intraday(self, open_, high, low, close, prev_close):
        """当美股指数只有 O/H/L/C 快照时，合成一条有真实日内形态的近似分时曲线。

        真身迁 modules.fetcher_core._synth_us_index_intraday（T-247 Tier2 第二批），
        本薄壳仅委托，签名与返回语义零变化。返回 (spark_x, spark_y) 或 (None, None)。
        """
        return _synth_us_index_intraday(open_, high, low, close, prev_close)

