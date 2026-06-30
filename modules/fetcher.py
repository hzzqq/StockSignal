"""
数据采集模块
多级降级链：akshare → BaoStock → 新浪财经 → 东方财富(urllib) → 本地缓存

所有请求默认走本地 SQLite 缓存，cache_days 内不重复请求网络。
"""

import io
import json
import os
import sqlite3
import time
import warnings
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta

import pandas as pd
import yaml

# ──────────────────────────────────────────────────────────
# 数据源可用性检测
# ──────────────────────────────────────────────────────────
try:
    import akshare as ak
    _AK_OK = True
except ImportError:
    _AK_OK = False

try:
    import baostock as bs
    _BS_OK = True
except ImportError:
    _BS_OK = False


# ──────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────
def _retry_request(func, max_retries=2, base_delay=2):
    """网络请求自动重试，对瞬态错误指数退避。"""
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except (ConnectionError, TimeoutError, OSError) as e:
            last_err = e
            err_msg = str(e).lower()
            is_transient = any(kw in err_msg for kw in [
                "remote disconnected", "connection aborted", "reset by peer",
                "timed out", "connection refused", "broken pipe",
                "remote end closed", "temporary failure"
            ])
            if not is_transient or attempt == max_retries:
                raise
            time.sleep(base_delay * (2 ** (attempt - 1)))
        except Exception:
            raise
    raise last_err


def _symbol_to_secid(symbol):
    """股票代码 → 东方财富 secid。"""
    return f"1.{symbol}" if symbol.startswith("6") else f"0.{symbol}"


def _index_to_secid(symbol):
    """指数代码 → 东方财富 secid。"""
    index_map = {
        "000001": "1.000001", "399001": "0.399001", "399006": "0.399006",
        "000300": "1.000300", "000016": "1.000016", "000905": "1.000905",
        "000852": "1.000852",
    }
    return index_map.get(symbol, f"1.{symbol}")


def _symbol_to_bs(symbol):
    """股票代码 → BaoStock 格式：sh.600519 / sz.000858"""
    prefix = "sh" if symbol.startswith("6") else "sz"
    return f"{prefix}.{symbol}"


def _symbol_to_sina(symbol):
    """股票代码 → 新浪格式：sh600519 / sz000858"""
    prefix = "sh" if symbol.startswith("6") else "sz"
    return f"{prefix}{symbol}"


# ──────────────────────────────────────────────────────────
# BaoStock 数据源（封装登录/登出）
# ──────────────────────────────────────────────────────────
class _BaoStockFetcher:
    """
    使用 BaoStock (证券宝) 获取 A 股历史 K 线。
    免费、无 token、纯 Python，不受东方财富反爬影响。
    """

    @classmethod
    def _ensure_login(cls):
        """确保已登录，返回是否成功。"""
        if not _BS_OK:
            return False
        lg = bs.login()
        if lg.error_code == "0":
            return True
        print(f"[BaoStockFetcher] 登录失败: {lg.error_msg}")
        return False

    @staticmethod
    def _ensure_logout():
        try:
            bs.logout()
        except Exception:
            pass

    @classmethod
    def fetch_kline(cls, symbol, start_date, end_date, adjust="qfq"):
        """
        获取个股/指数日 K 线。
        adjust: qfq=前复权(2), hfq=后复权(1), none=不复权(3)
        返回 DataFrame 或 None。
        """
        if not _BS_OK:
            return None

        # 调整复权类型
        adjustflag = {"qfq": "2", "hfq": "1"}.get(adjust, "3")

        bs_code = _symbol_to_bs(symbol)
        try:
            if not cls._ensure_login():
                return None

            fields = "date,open,high,low,close,volume,amount"
            rs = bs.query_history_k_data_plus(
                bs_code, fields,
                start_date=start_date,
                end_date=end_date,
                frequency="d", adjustflag=adjustflag,
            )

            if rs.error_code != "0":
                print(f"[BaoStockFetcher] 查询失败 ({bs_code}): {rs.error_msg}")
                cls._ensure_logout()
                return None

            rows = []
            while (rs.error_code == "0") and rs.next():
                rows.append(rs.get_row_data())

            cls._ensure_logout()

            if not rows:
                print(f"[BaoStockFetcher] 空结果 ({bs_code})")
                return None

            df = pd.DataFrame(rows, columns=rs.fields)
            df["date"] = pd.to_datetime(df["date"])
            numeric_cols = ["open", "high", "low", "close", "volume", "amount"]
            for c in numeric_cols:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            df["change_pct"] = df["close"].pct_change() * 100
            print(f"[BaoStockFetcher] 成功! {bs_code} → {len(df)} 行")
            return df
        except Exception as e:
            print(f"[BaoStockFetcher] 异常 ({bs_code}): {type(e).__name__}: {e}")
            cls._ensure_logout()
            return None

    @classmethod
    def fetch_index_kline(cls, index_symbol, start_date, end_date):
        """
        获取指数 K 线。
        index_symbol: 000001(上证), 399001(深证), 399006(创业板) 等
        """
        if not _BS_OK:
            return None

        prefix = "sh" if index_symbol.startswith(("000", "600")) else "sz"
        bs_code = f"{prefix}.{index_symbol}"

        try:
            if not cls._ensure_login():
                return None

            fields = "date,open,high,low,close,volume,amount"
            rs = bs.query_history_k_data_plus(
                bs_code, fields,
                start_date=start_date,
                end_date=end_date,
                frequency="d", adjustflag="3",  # 指数不复权
            )

            if rs.error_code != "0":
                cls._ensure_logout()
                return None

            rows = []
            while (rs.error_code == "0") and rs.next():
                rows.append(rs.get_row_data())

            cls._ensure_logout()

            if not rows:
                return None

            df = pd.DataFrame(rows, columns=rs.fields)
            df["date"] = pd.to_datetime(df["date"])
            for c in ["open", "high", "low", "close", "volume", "amount"]:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            print(f"[BaoStockFetcher] 指数成功! {bs_code} → {len(df)} 行")
            return df
        except Exception as e:
            print(f"[BaoStockFetcher] 指数异常 ({bs_code}): {type(e).__name__}: {e}")
            cls._ensure_logout()
            return None

    @classmethod
    def fetch_sector_list(cls):
        """
        获取行业板块列表（申万一级行业）。
        返回 DataFrame(sector, change_pct) 或 None。
        """
        if not _BS_OK:
            return None

        try:
            if not cls._ensure_login():
                return None

            rs = bs.query_stock_industry()
            if rs.error_code != "0":
                cls._ensure_logout()
                return None

            rows = []
            while (rs.error_code == "0") and rs.next():
                rows.append(rs.get_row_data())

            cls._ensure_logout()

            if not rows:
                return None

            df = pd.DataFrame(rows, columns=rs.fields)
            # 按行业分组统计
            sectors = df.groupby("industry").size().reset_index(name="count")
            sectors = sectors.rename(columns={"industry": "sector"})
            sectors["change_pct"] = 0.0  # BaoStock 不提供涨跌幅
            print(f"[BaoStockFetcher] 板块成功! {len(sectors)} 个行业")
            return sectors[["sector", "change_pct"]]
        except Exception as e:
            print(f"[BaoStockFetcher] 板块异常: {type(e).__name__}: {e}")
            cls._ensure_logout()
            return None


# ──────────────────────────────────────────────────────────
# 新浪财经数据源
# ──────────────────────────────────────────────────────────
class _SinaFetcher:
    """
    使用新浪财经免费 JSONP API 获取日 K 线。
    新浪接口稳定，不受东方财富反爬影响。
    """

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://finance.sina.com.cn/",
    }

    @classmethod
    def fetch_kline(cls, symbol, _start_date=None, _end_date=None):
        """
        获取个股日 K 线（最近 N 条，新浪接口默认返回全部可用数据）。
        注意：新浪接口不支持按日期范围过滤，返回最近约 2000 条。
        """
        sina_code = _symbol_to_sina(symbol)
        url = (
            "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            f"CN_MarketData.getKLineData?symbol={sina_code}&scale=240&ma=no&datalen=800"
        )
        req = urllib.request.Request(url, headers=cls.HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f"[SinaFetcher] 请求失败 ({sina_code}): {type(e).__name__}: {e}")
            return None

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"[SinaFetcher] JSON 解析失败 ({sina_code}): {e}")
            return None

        if not data or not isinstance(data, list):
            return None

        rows = []
        for item in data:
            try:
                rows.append({
                    "date": item["day"],
                    "open": float(item["open"]),
                    "high": float(item["high"]),
                    "low": float(item["low"]),
                    "close": float(item["close"]),
                    "volume": int(float(item["volume"])),
                    "amount": 0.0,  # 新浪日K线不含成交额
                })
            except (KeyError, ValueError, TypeError):
                continue

        if not rows:
            return None

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df["change_pct"] = df["close"].pct_change() * 100
        df = df.sort_values("date").reset_index(drop=True)
        print(f"[SinaFetcher] 成功! {sina_code} → {len(df)} 行")
        return df


# ──────────────────────────────────────────────────────────
# 东方财富 urllib 兜底数据源（保留作为第四层）
# ──────────────────────────────────────────────────────────
class _UrllibFetcher:
    """使用标准库 urllib 直连东方财富 API。"""

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://quote.eastmoney.com/",
        "Accept": "*/*",
    }

    @classmethod
    def fetch_kline(cls, symbol, start_date, end_date, adjust="qfq", is_index=False):
        """东方财富 K 线接口，返回 DataFrame 或 None。"""
        secid = _index_to_secid(symbol) if is_index else _symbol_to_secid(symbol)
        fqt = {"qfq": "1", "hfq": "2"}.get(adjust, "0")
        params = {
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": "101", "fqt": fqt,
            "secid": secid,
            "beg": start_date.replace("-", ""),
            "end": end_date.replace("-", ""),
        }
        url = "https://push2.eastmoney.com/api/qt/stock/kline/get?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=cls.HEADERS)

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[UrllibFetcher] K线失败 ({symbol}): {type(e).__name__}: {e}")
            return None

        klines = data.get("data", {}).get("klines", [])
        if not klines:
            return None

        rows = []
        for line in klines:
            parts = line.split(",")
            try:
                rows.append({
                    "date": parts[0], "open": float(parts[1]), "close": float(parts[2]),
                    "high": float(parts[3]), "low": float(parts[4]),
                    "volume": int(float(parts[5])), "amount": float(parts[6]),
                    "change_pct": float(parts[8]) if len(parts) > 8 else 0.0,
                })
            except (ValueError, IndexError):
                continue

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        return df.sort_values("date").reset_index(drop=True)

    @classmethod
    def fetch_sector_list(cls):
        """行业板块列表（东方财富）。"""
        url = ("https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=100&po=1&np=1"
               "&fields=f2,f3,f12,f14&fs=m:90+t:2")
        req = urllib.request.Request(url, headers=cls.HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[UrllibFetcher] 板块失败: {e}")
            return None

        items = data.get("data", {}).get("diff", [])
        if not items:
            return None
        return pd.DataFrame([
            {"sector": item.get("f14", ""), "change_pct": item.get("f3", 0)}
            for item in items
        ])


# ──────────────────────────────────────────────────────────
# 配置加载
# ──────────────────────────────────────────────────────────
def load_config(config_path="config.yaml"):
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ══════════════════════════════════════════════════════════
# 主数据采集器
# ══════════════════════════════════════════════════════════
class StockFetcher:
    """
    股票行情与宏观数据采集器。
    四级降级链：akshare → BaoStock → 新浪 → 东方财富(urllib) → 缓存兜底
    """

    def __init__(self, config_path="config.yaml"):
        self.config = load_config(config_path)
        db_path = self.config.get("database", {}).get("path", "data/cache.db")
        self.db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), db_path
        )
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.cache_days = self.config.get("default", {}).get("cache_days", 7)

    # ══════════════════════════════════════════════════════
    # 缓存管理
    # ══════════════════════════════════════════════════════
    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def _init_cache_table(self, conn, table_name):
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                cache_key   TEXT PRIMARY KEY,
                data_json   TEXT,
                updated_at  TEXT
            )
        """)
        conn.commit()

    def _read_cache(self, conn, table_name, cache_key, max_age_hours=None):
        self._init_cache_table(conn, table_name)
        row = conn.execute(
            f"SELECT data_json, updated_at FROM {table_name} WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        if row is None:
            return None
        updated_at = datetime.fromisoformat(row[1])
        max_age = (
            timedelta(hours=max_age_hours) if max_age_hours is not None
            else timedelta(days=self.cache_days)
        )
        if datetime.now() - updated_at < max_age:
            return pd.read_json(io.StringIO(row[0]))
        return None

    def _read_stale_cache(self, conn, table_name, prefix):
        """读取过期缓存（用于降级兜底）。"""
        self._init_cache_table(conn, table_name)
        rows = conn.execute(
            f"SELECT data_json, updated_at FROM {table_name} "
            f"WHERE cache_key LIKE ? ORDER BY updated_at DESC LIMIT 1",
            (f"{prefix}%",),
        ).fetchall()
        if not rows:
            return None
        data_json, updated_at_str = rows[0]
        age_hours = (
            datetime.now() - datetime.fromisoformat(updated_at_str)
        ).total_seconds() / 3600
        print(f"[StockFetcher] 使用过期缓存 (已过期 {age_hours:.1f} 小时)")
        warnings.warn(
            f"数据源不可用，正在使用 {age_hours:.1f} 小时前的缓存数据",
            UserWarning, stacklevel=4,
        )
        return pd.read_json(io.StringIO(data_json))

    def clear_cache(self, table_name=None, cache_key=None):
        conn = self._get_conn()
        try:
            tables = (
                [table_name] if table_name
                else ["daily_cache", "index_cache", "macro_cache", "commodity_cache"]
            )
            for t in tables:
                try:
                    if cache_key:
                        conn.execute(f"DELETE FROM {t} WHERE cache_key = ?", (cache_key,))
                    else:
                        conn.execute(f"DELETE FROM {t}")
                except sqlite3.OperationalError:
                    pass
            conn.commit()
        finally:
            conn.close()

    def _write_cache(self, conn, table_name, cache_key, df):
        self._init_cache_table(conn, table_name)
        conn.execute(
            f"INSERT OR REPLACE INTO {table_name} (cache_key, data_json, updated_at) "
            f"VALUES (?, ?, ?)",
            (cache_key, df.to_json(orient="records", date_format="iso"), datetime.now().isoformat()),
        )
        conn.commit()

    # ══════════════════════════════════════════════════════
    # 个股行情（四级降级链）
    # ══════════════════════════════════════════════════════
    def get_daily(self, symbol, start="2024-01-01", end=None, adjust="qfq"):
        """
        获取个股日线行情。
        降级链：akshare → BaoStock → 新浪财经 → 东方财富(urllib) → 缓存兜底
        """
        if end is None:
            end = datetime.now().strftime("%Y-%m-%d")

        cache_key = f"daily_{symbol}_{start}_{end}_{adjust}"
        conn = self._get_conn()
        try:
            # 缓存优先
            today_str = datetime.now().strftime("%Y-%m-%d")
            max_age_hours = 6 if end == today_str else None
            cached = self._read_cache(conn, "daily_cache", cache_key, max_age_hours=max_age_hours)
            if cached is not None:
                return cached

            df = None
            errors = []

            # ── L1: akshare ──
            if _AK_OK:
                try:
                    df = _retry_request(
                        lambda: ak.stock_zh_a_hist(
                            symbol=symbol, period="daily",
                            start_date=start.replace("-", ""),
                            end_date=end.replace("-", ""),
                            adjust=adjust,
                        ),
                        max_retries=2, base_delay=2,
                    )
                    df = df.rename(columns={
                        "日期": "date", "开盘": "open", "收盘": "close",
                        "最高": "high", "最低": "low", "成交量": "volume",
                        "成交额": "amount", "涨跌幅": "change_pct",
                    })
                    df["date"] = pd.to_datetime(df["date"])
                    print(f"[StockFetcher] L1-akshare ✓ {symbol}")
                except Exception as e:
                    errors.append(f"akshare: {type(e).__name__}")
                    print(f"[StockFetcher] L1-akshare ✗ {symbol}: {e}")
                    df = None

            # ── L2: BaoStock ──
            if df is None or df.empty:
                df = _BaoStockFetcher.fetch_kline(symbol, start, end, adjust=adjust)
                if df is not None and not df.empty:
                    print(f"[StockFetcher] L2-BaoStock ✓ {symbol}")
                else:
                    errors.append("BaoStock: 无数据")
                    print(f"[StockFetcher] L2-BaoStock ✗ {symbol}")

            # ── L3: 新浪财经 ──
            if df is None or df.empty:
                df_sina = _SinaFetcher.fetch_kline(symbol, start, end)
                if df_sina is not None and not df_sina.empty:
                    # 按日期范围裁剪
                    df_sina = df_sina[(df_sina["date"] >= start) & (df_sina["date"] <= end)]
                    if not df_sina.empty:
                        df = df_sina
                        print(f"[StockFetcher] L3-新浪 ✓ {symbol}")
                    else:
                        errors.append("新浪: 日期范围外")
                        df = None
                else:
                    errors.append("新浪: 无数据")
                    print(f"[StockFetcher] L3-新浪 ✗ {symbol}")

            # ── L4: 东方财富 urllib ──
            if df is None or df.empty:
                df = _UrllibFetcher.fetch_kline(symbol, start, end, adjust=adjust)
                if df is not None and not df.empty:
                    print(f"[StockFetcher] L4-东方财富 ✓ {symbol}")
                else:
                    errors.append("东方财富: 无数据")
                    print(f"[StockFetcher] L4-东方财富 ✗ {symbol}")

            # ── L5: 缓存兜底 ──
            if df is None or df.empty:
                stale = self._read_stale_cache(conn, "daily_cache", f"daily_{symbol}")
                if stale is not None:
                    print(f"[StockFetcher] L5-缓存兜底 ✓ {symbol}")
                    return stale
                errors.append("缓存: 无可用数据")

            # ── 全部失败 ──
            if df is None or df.empty:
                detail = "\n   • ".join(errors)
                raise RuntimeError(
                    f"❌ 无法获取 {symbol} 行情数据\n"
                    f"   四级数据源全部失败：\n"
                    f"   • {detail}\n\n"
                    f"   建议：稍后重试或点击「强制刷新」清除缓存"
                )

            # 标准化输出列
            required = ["date", "open", "close", "high", "low", "volume"]
            available = [c for c in required if c in df.columns]
            df = df[available + [c for c in ["amount", "change_pct"] if c in df.columns]]
            df = df.sort_values("date").reset_index(drop=True)
            self._write_cache(conn, "daily_cache", cache_key, df)
            return df
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════
    # 指数行情（四级降级链）
    # ══════════════════════════════════════════════════════
    def get_index(self, symbol="000001", start="2024-01-01", end=None):
        """
        获取指数日线行情。
        降级链：akshare → BaoStock → 东方财富(urllib) → 缓存兜底
        """
        if end is None:
            end = datetime.now().strftime("%Y-%m-%d")

        cache_key = f"index_{symbol}_{start}_{end}"
        conn = self._get_conn()
        try:
            cached = self._read_cache(conn, "index_cache", cache_key)
            if cached is not None:
                return cached

            df = None
            errors = []

            # ── L1: akshare ──
            if _AK_OK:
                try:
                    df = _retry_request(
                        lambda: ak.stock_zh_index_daily(
                            symbol=f"sh{symbol}" if symbol.startswith("000") else f"sz{symbol}"
                        ),
                        max_retries=2, base_delay=2,
                    )
                    df = df.rename(columns={
                        "date": "date", "open": "open", "close": "close",
                        "high": "high", "low": "low", "volume": "volume",
                    })
                    df["date"] = pd.to_datetime(df["date"])
                    print(f"[StockFetcher] L1-akshare 指数 ✓ {symbol}")
                except Exception as e:
                    errors.append(f"akshare: {type(e).__name__}")
                    df = None

            # ── L2: BaoStock ──
            if df is None or df.empty:
                df = _BaoStockFetcher.fetch_index_kline(symbol, start, end)
                if df is not None and not df.empty:
                    print(f"[StockFetcher] L2-BaoStock 指数 ✓ {symbol}")
                else:
                    errors.append("BaoStock: 无数据")

            # ── L3: 东方财富 urllib ──
            if df is None or df.empty:
                df = _UrllibFetcher.fetch_kline(symbol, start, end, is_index=True)
                if df is not None and not df.empty:
                    print(f"[StockFetcher] L3-东方财富 指数 ✓ {symbol}")
                else:
                    errors.append("东方财富: 无数据")

            # ── L4: 缓存兜底 ──
            if df is None or df.empty:
                stale = self._read_stale_cache(conn, "index_cache", f"index_{symbol}")
                if stale is not None:
                    print(f"[StockFetcher] L4-缓存兜底 指数 ✓ {symbol}")
                    return stale
                errors.append("缓存: 无可用数据")

            if df is None or df.empty:
                detail = "\n   • ".join(errors)
                raise RuntimeError(
                    f"❌ 无法获取 {symbol} 指数数据\n"
                    f"   数据源全部失败：\n   • {detail}"
                )

            df = df[(df["date"] >= start) & (df["date"] <= end)]
            df = df.sort_values("date").reset_index(drop=True)
            self._write_cache(conn, "index_cache", cache_key, df)
            return df
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════
    # 板块数据（三级降级链）
    # ══════════════════════════════════════════════════════
    def get_sector_list(self):
        """
        行业板块列表。
        降级链：akshare → BaoStock → 东方财富(urllib)
        """
        df = None
        errors = []

        # ── L1: akshare ──
        if _AK_OK:
            try:
                df = _retry_request(
                    lambda: ak.stock_board_industry_name_em(),
                    max_retries=2, base_delay=2,
                )
                df = df.rename(columns={"板块名称": "sector", "涨跌幅": "change_pct"})
                df = df[["sector", "change_pct"]]
                print(f"[StockFetcher] L1-akshare 板块 ✓")
            except Exception as e:
                errors.append(f"akshare: {type(e).__name__}")
                df = None

        # ── L2: BaoStock ──
        if df is None or df.empty:
            df = _BaoStockFetcher.fetch_sector_list()
            if df is not None and not df.empty:
                print(f"[StockFetcher] L2-BaoStock 板块 ✓")
            else:
                errors.append("BaoStock: 无数据")

        # ── L3: 东方财富 urllib ──
        if df is None or df.empty:
            df = _UrllibFetcher.fetch_sector_list()
            if df is not None and not df.empty:
                print(f"[StockFetcher] L3-东方财富 板块 ✓")
            else:
                errors.append("东方财富: 无数据")

        if df is None or df.empty:
            detail = "\n   • ".join(errors)
            raise RuntimeError(
                f"❌ 无法获取板块数据\n   数据源全部失败：\n   • {detail}"
            )
        return df

    def get_sector_stocks(self, sector_name):
        """指定行业的成分股列表（仅 akshare）。"""
        if not _AK_OK:
            raise RuntimeError("akshare 未安装，无法获取成分股")
        df = _retry_request(
            lambda: ak.stock_board_industry_cons_em(symbol=sector_name),
            max_retries=2, base_delay=2,
        )
        df = df.rename(columns={
            "代码": "code", "名称": "name", "涨跌幅": "change_pct",
            "最新价": "close", "总市值": "market_cap",
        })
        return df[["code", "name", "close", "change_pct", "market_cap"]]

    # ══════════════════════════════════════════════════════
    # 宏观数据
    # ══════════════════════════════════════════════════════
    def get_macro(self, indicator="pmi_mfg"):
        indicator_map = {
            "pmi_mfg": ("macro_china_pmi", {}),
            "cpi": ("macro_china_cpi_monthly", {}),
            "m2": ("macro_china_money_supply", {}),
        }
        if indicator not in indicator_map:
            raise ValueError(f"不支持的指标: {indicator}")

        func_name, kwargs = indicator_map[indicator]
        cache_key = f"macro_{indicator}"
        conn = self._get_conn()
        try:
            cached = self._read_cache(conn, "macro_cache", cache_key)
            if cached is not None:
                return cached

            if not _AK_OK:
                raise RuntimeError("akshare 未安装")

            func = getattr(ak, func_name)
            df = _retry_request(lambda: func(**kwargs), max_retries=2, base_delay=3)
            df = df.rename(columns={
                "月份": "date", "日期": "date",
                "制造业-Loss": "pmi_mfg", "全国-当月": "cpi_yoy",
                "M2-数量": "m2", "M2-同比增长": "m2_yoy",
            })
            df = df.tail(60).reset_index(drop=True)
            self._write_cache(conn, "macro_cache", cache_key, df)
            return df
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════
    # 大宗商品
    # ══════════════════════════════════════════════════════
    def get_commodity_price(self, name="煤炭"):
        cache_key = f"commodity_{name}"
        conn = self._get_conn()
        try:
            cached = self._read_cache(conn, "commodity_cache", cache_key)
            if cached is not None:
                return cached

            if not _AK_OK:
                raise RuntimeError("akshare 未安装")

            df = _retry_request(
                lambda: ak.spot_price_qsx(symbol="全部"),
                max_retries=2, base_delay=3,
            )
            df = df[df["品种"].str.contains(name, na=False)]
            df = df.rename(columns={"日期": "date", "品种": "name", "价格": "price"})
            df["date"] = pd.to_datetime(df["date"])
            df = df[["date", "name", "price"]].sort_values("date").reset_index(drop=True)
            self._write_cache(conn, "commodity_cache", cache_key, df)
            return df
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════
    # 财务数据
    # ══════════════════════════════════════════════════════
    def get_financial(self, symbol="600519", report_type="income"):
        if not _AK_OK:
            raise RuntimeError("akshare 未安装")

        func_map = {
            "income": ak.stock_financial_report_sina,
            "balance": ak.stock_financial_report_sina,
            "cash": ak.stock_financial_report_sina,
        }
        report_map = {"income": "利润表", "balance": "资产负债表", "cash": "现金流量表"}
        df = func_map[report_type](stock=f"sh{symbol}", symbol=report_map[report_type])
        return df.head(8)
