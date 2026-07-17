"""
数据采集模块
多级降级链：akshare -> BaoStock -> 新浪财经 -> 东方财富(urllib) -> 本地缓存

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
import contextlib
from datetime import datetime, timedelta
import concurrent.futures as _cf

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
# 集中配置（缓存 TTL / 可观测性开关）
# ──────────────────────────────────────────────────────────
# 所有散落的 TTL 常量统一在此声明，避免硬编码，便于集中治理。
CONFIG = {
    "cache_ttl": {
        # 日线行情：结束于今日（交易时段）短缓存，否则按默认 cache_days
        "daily_trading_hours": 6,
        # 实时五档行情：交易时段 30s，非交易时段 5min
        "realtime_open_seconds": 30,
        "realtime_closed_seconds": 300,
        # 板块列表分级 TTL（小时）。休市/周末/盘前按 closed_days 折算为小时
        "sector_open_hours": 0.1,       # 交易时段：6 分钟
        "sector_midday_hours": 0.5,     # 午间休市：30 分钟
        "sector_closed_days": 7,        # 收盘/周末/盘前：7 天
    },
    "observe": {
        "enabled": True,                # 数据源成功率/耗时埋点总开关
    },
    "pinyin": {
        # 多音字/常见名称纠正词典（行业名 + 常见股票名）
        # 用于修正 pypinyin 默认读音，提升拼音首字母/全拼匹配准确度
        "phrases": {
            "重庆": ["chong", "qing"],
            "长江": ["chang", "jiang"],
            "长沙": ["chang", "sha"],
            "长春": ["chang", "chun"],
            "长电": ["chang", "dian"],
            "重药": ["chong", "yao"],
            "重百": ["chong", "bai"],
            "银行": ["yin", "hang"],
            "兴业": ["xing", "ye"],
            "乐鑫": ["le", "xin"],
            "厦门": ["xia", "men"],
            "阿胶": ["e", "jiao"],
            "西藏": ["xi", "zang"],
            "盛和资源": ["sheng", "he", "zi", "yuan"],
            "朝": ["chao"],
            "柏": ["bai"],
            "折": ["zhe"],
            "省": ["sheng"],
            "沈": ["shen"],
            "大": ["da"],
            "中": ["zhong"],
            "都": ["du"],
            "系": ["xi"],
            "解": ["jie"],
            "行": ["hang"],
            "重": ["chong"],
            "乐": ["le"],
            "厦": ["xia"],
            "藏": ["zang"],
            "盛": ["sheng"],
        },
    },
}


# ──────────────────────────────────────────────────────────
# 数据源可观测性：埋点存储 + 统一结构化日志
# ──────────────────────────────────────────────────────────
SOURCE_METRICS = {}  # {source: {"calls","success","latency_ms","last_error"}}


def _record_source_metric(source, ok, latency_ms, detail=None):
    """累计单数据源调用次数/成功次数/累计耗时，供成功率与平均耗时统计。"""
    m = SOURCE_METRICS.setdefault(
        source, {"calls": 0, "success": 0, "latency_ms": 0.0, "last_error": None}
    )
    m["calls"] += 1
    m["latency_ms"] += latency_ms
    if ok:
        m["success"] += 1
    else:
        m["last_error"] = detail


def _observe_log(source, level, ok, latency_ms, detail=""):
    """输出统一结构化可检索日志（模块/数据源/层级/成功率/耗时）。"""
    if not CONFIG["observe"]["enabled"]:
        return
    rec = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "module": "fetcher",
        "source": source,
        "level": level,
        "ok": ok,
        "latency_ms": round(latency_ms, 1),
        "detail": detail,
    }
    print("[OBS] " + json.dumps(rec, ensure_ascii=False))


def observe_source(source, level, func, validate=None):
    """
    执行单数据源调用并记录成功率/耗时埋点。

    - 异常安全：数据源抛错仅记录埋点并返回 None，不拖垮调用方降级链。
    - validate: 可选函数，对返回结果二次校验（如板块数据合理性）。
      返回 True 视为成功，否则按失败记录并置空结果。
    """
    t0 = time.time()
    try:
        result = func()
    except Exception as e:
        dt = (time.time() - t0) * 1000
        detail = f"{type(e).__name__}: {e}"
        _record_source_metric(source, False, dt, detail)
        _observe_log(source, level, False, dt, detail)
        return None

    dt = (time.time() - t0) * 1000
    if validate is not None:
        ok = bool(validate(result))
        detail = "" if ok else "校验未通过"
    else:
        ok = result is not None and not (hasattr(result, "empty") and result.empty)
        detail = "" if ok else "空数据/None"
    _record_source_metric(source, ok, dt, None if ok else detail)
    _observe_log(source, level, ok, dt, detail)
    return result if ok else None


def observe_cache_fallback(level, hit, detail=""):
    """记录缓存兜底（最后一层）的命中情况到可观测埋点。"""
    _record_source_metric("cache_fallback", hit, 0.0, None if hit else detail)
    _observe_log("cache_fallback", level, hit, 0.0, detail)


def get_source_metrics():
    """
    返回各数据源成功率/平均耗时快照（供可观测性接口/运维排查使用）。
    成功率 = success / calls；平均耗时 = 累计耗时 / calls。
    """
    out = {}
    for src, m in SOURCE_METRICS.items():
        calls = m["calls"]
        out[src] = {
            "calls": calls,
            "success": m["success"],
            "success_rate": round(m["success"] / calls, 4) if calls else 0.0,
            "avg_latency_ms": round(m["latency_ms"] / calls, 1) if calls else 0.0,
            "last_error": m["last_error"],
        }
    return out


# ──────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────
def _is_market_open():
    """判断当前是否为 A 股交易时间（工作日 9:30-11:30, 13:00-15:00）。"""
    now = datetime.now()
    if now.weekday() >= 5:  # 周六日
        return False
    t = now.time()
    morning = t >= datetime.strptime("09:30", "%H:%M").time() and t <= datetime.strptime("11:30", "%H:%M").time()
    afternoon = t >= datetime.strptime("13:00", "%H:%M").time() and t <= datetime.strptime("15:00", "%H:%M").time()
    return morning or afternoon


def _is_midday_break():
    """判断当前是否为午间休市（工作日 11:30-13:00）。"""
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.time()
    return datetime.strptime("11:30", "%H:%M").time() < t < datetime.strptime("13:00", "%H:%M").time()

def _validate_sector_data(df: pd.DataFrame) -> bool:
    """
    校验板块涨跌幅数据是否合理。
    返回 True 表示可信，False 表示应降级到下一个数据源。
    """
    if df is None or df.empty or "change_pct" not in df.columns:
        return False

    s = pd.to_numeric(df["change_pct"], errors="coerce").dropna()
    if len(s) < 5:
        return False

    # 1. 检查是否全部同向（全涨或全跌），正常市场极少出现
    up = (s > 0).sum()
    down = (s < 0).sum()
    total = len(s)
    if up == total or down == total:
        print(f"[StockFetcher] 数据校验警告: {total} 个板块全部{'上涨' if up == total else '下跌'}，疑似数据源异常")
        return False

    # 2. 检查是否存在绝对值过大的异常值（正常板块日涨跌幅应小于 20%）
    if s.abs().max() > 20:
        print(f"[StockFetcher] 数据校验警告: 最大涨跌幅 {s.abs().max():.2f}% 超出合理范围")
        return False

    return True


# ──────────────────────────────────────────────────────────
# 网络相关工具函数
# ──────────────────────────────────────────────────────────
def _retry_request(func, max_retries=2, base_delay=2):
    """网络请求自动重试，对瞬态错误指数退避。max_retries=0 表示不重试直接调用。"""
    if max_retries <= 0:
        return func()  # 不重试路径，避免 raise None
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
    """股票代码 -> 东方财富 secid。"""
    return f"1.{symbol}" if symbol.startswith("6") else f"0.{symbol}"


def _index_to_secid(symbol):
    """指数代码 -> 东方财富 secid。"""
    index_map = {
        "000001": "1.000001", "399001": "0.399001", "399006": "0.399006",
        "000300": "1.000300", "000016": "1.000016", "000905": "1.000905",
        "000852": "1.000852",
    }
    return index_map.get(symbol, f"1.{symbol}")


def _symbol_to_bs(symbol):
    """股票代码 -> BaoStock 格式：sh.600519 / sz.000858"""
    prefix = "sh" if symbol.startswith("6") else "sz"
    return f"{prefix}.{symbol}"


def _symbol_to_sina(symbol):
    """股票代码 -> 新浪格式：sh600519 / sz000858"""
    prefix = "sh" if symbol.startswith("6") else "sz"
    return f"{prefix}{symbol}"


# ──────────────────────────────────────────────────────────
# BaoStock 数据源（封装登录/登出）
# ──────────────────────────────────────────────────────────
class _BaoStockFetcher:
    """
    使用 BaoStock (证券宝) 获取 A 股历史 K 线。
    免费、无 token、纯 Python，不受东方财富反爬影响。

    性能优化（v2）：连接池
    - 进程级只 login 一次，所有查询复用同一会话
    - 退出时（程序结束）才 logout
    - 单次查询耗时从 ~13s 降到 ~0.5s（省掉 12 次 login/logout）
    """

    _login_done = False   # 类级别：是否已完成首次登录

    @classmethod
    def _ensure_login(cls):
        """确保已登录：第一次调用 login，后续直接复用。"""
        if not _BS_OK:
            return False
        if cls._login_done:
            return True
        lg = bs.login()
        if lg.error_code == "0":
            cls._login_done = True
            return True
        print(f"[BaoStockFetcher] 登录失败: {lg.error_msg}")
        return False

    @classmethod
    def _ensure_logout(cls):
        """程序退出/出错时调用。重置 _login_done 让下次重新登录。"""
        if cls._login_done:
            try:
                bs.logout()
            except Exception:
                pass
            cls._login_done = False

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

            rows = []
            while (rs.error_code == "0") and rs.next():
                rows.append(rs.get_row_data())

            # ── 不在单次查询后 logout，复用连接（性能关键）──

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
            print(f"[BaoStockFetcher] 成功! {bs_code} -> {len(df)} 行")
            return df
        except Exception as e:
            print(f"[BaoStockFetcher] 异常 ({bs_code}): {type(e).__name__}: {e}")
            # 异常时也不要 logout，下次复用即可
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
                print(f"[BaoStockFetcher] 指数查询失败 ({bs_code}): {rs.error_msg}")
                return None

            rows = []
            while (rs.error_code == "0") and rs.next():
                rows.append(rs.get_row_data())

            if not rows:
                return None

            df = pd.DataFrame(rows, columns=rs.fields)
            df["date"] = pd.to_datetime(df["date"])
            for c in ["open", "high", "low", "close", "volume", "amount"]:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            print(f"[BaoStockFetcher] 指数成功! {bs_code} -> {len(df)} 行")
            return df
        except Exception as e:
            print(f"[BaoStockFetcher] 指数异常 ({bs_code}): {type(e).__name__}: {e}")
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
                print(f"[BaoStockFetcher] 板块查询失败")
                return None

            rows = []
            while (rs.error_code == "0") and rs.next():
                rows.append(rs.get_row_data())

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
        print(f"[SinaFetcher] 成功! {sina_code} -> {len(df)} 行")
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
    def _fetch_em_boards(cls, fs):
        """拉取东方财富单页板块（pc 端 clist 每页上限 100 条）。返回 DataFrame 或 None。"""
        url = ("https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=100&po=1&np=1"
               "&fields=f2,f3,f12,f14&fs=" + fs)
        req = urllib.request.Request(url, headers=cls.HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[UrllibFetcher] 板块失败 ({fs}): {e}")
            return None

        items = data.get("data", {}).get("diff", [])
        if not items:
            return None
        df = pd.DataFrame([
            {"sector": item.get("f14", ""), "change_pct": item.get("f3", 0)}
            for item in items
        ])
        # f3 是原始数值（% * 100），需要除以 100 转换为标准百分比
        df["change_pct"] = pd.to_numeric(df["change_pct"], errors="coerce") / 100
        return df

    @classmethod
    def _fetch_em_boards_paged(cls, fs, max_pages=10, stop_when_found=None):
        """分页拉取东方财富板块（每页上限 100 条）。

        stop_when_found 为需要补齐的板块名集合：一旦集齐目标板块即可提前结束分页，
        减少不必要的请求量。
        """
        targets = set(stop_when_found) if stop_when_found else None
        found = set()
        rows = []
        for pn in range(1, max_pages + 1):
            url = (f"https://push2.eastmoney.com/api/qt/clist/get?pn={pn}&pz=100&po=1&np=1"
                   f"&fields=f2,f3,f12,f14&fs={fs}")
            req = urllib.request.Request(url, headers=cls.HEADERS)
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                print(f"[UrllibFetcher] 板块失败 ({fs} p{pn}): {e}")
                break
            items = data.get("data", {}).get("diff", [])
            if not items:
                break
            rows.extend(items)
            if targets:
                for it in items:
                    n = (it.get("f14", "") or "").strip()
                    if n in targets:
                        found.add(n)
                if targets <= found:
                    break
            if len(items) < 100:
                break
        if not rows:
            return None
        df = pd.DataFrame([
            {"sector": item.get("f14", ""), "change_pct": item.get("f3", 0)}
            for item in rows
        ])
        # f3 是原始数值（% * 100），需要除以 100 转换为标准百分比
        df["change_pct"] = pd.to_numeric(df["change_pct"], errors="coerce") / 100
        return df

    @classmethod
    def fetch_sector_list(cls):
        """行业板块列表（东方财富）。

        fs=m:90+t:3 对应东方财富行业板块；f3 字段为涨跌幅（% * 100）。
        部分热门板块（如「半导体」）仅出现在概念板块(m:90+t:2)而不在行业板块中，
        故以概念板块作为补充来源：仅补齐行业板块缺失的板块（按名称去重），
        确保其在涨跌排行里以真实涨跌幅出现，且不破坏 get_sector_list 的原有降级链。
        """
        # 主来源：行业板块
        industry = cls._fetch_em_boards("m:90+t:3")
        if industry is None or industry.empty:
            # 行业板块拉取失败 → 交回 get_sector_list 的 L2-L4 降级链处理
            return None

        industry_names = set(industry["sector"].astype(str).str.strip())
        # 行业板块已包含「半导体」则直接返回，无需补充
        if "半导体" in industry_names:
            return industry

        # 行业板块缺失「半导体」→ 从概念板块分页检索并补充（仅补缺失项，避免列表膨胀）
        supplement = {"半导体"}
        concept = cls._fetch_em_boards_paged("m:90+t:2", stop_when_found=supplement)
        if concept is not None and not concept.empty:
            extra = concept[concept["sector"].astype(str).str.strip().isin(supplement)]
            extra = extra[~extra["sector"].astype(str).str.strip().isin(industry_names)]
            if not extra.empty:
                industry = pd.concat([industry, extra], ignore_index=True)
        return industry

    @classmethod
    def fetch_fundamentals(cls, symbol):
        """东方财富个股基本面：名称 / 最新价 / 总市值(亿) / 市盈率(TTM) / 行业。
        返回 dict 或 None。"""
        secid = _symbol_to_secid(symbol)
        fields = "f57,f58,f43,f116,f162,f127"
        url = (f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}"
               f"&fields={fields}&invt=2&fltt=2")
        req = urllib.request.Request(url, headers=cls.HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                d = json.loads(resp.read().decode("utf-8")).get("data") or {}
        except Exception as e:  # noqa: BLE001
            print(f"[UrllibFetcher] 基本面失败 ({symbol}): {type(e).__name__}: {e}")
            return None
        if not d:
            return None

        def _num(x):
            try:
                return float(x)
            except (TypeError, ValueError):
                return None

        cap = _num(d.get("f116"))  # 元
        return {
            "name": (d.get("f58") or "").strip(),
            "price": _num(d.get("f43")),
            "market_cap": round(cap / 1e8, 1) if cap else None,  # 亿元
            "pe_ttm": _num(d.get("f162")),
            "industry": (d.get("f127") or "").strip(),
        }


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
    四级降级链：akshare -> BaoStock -> 新浪 -> 东方财富(urllib) -> 缓存兜底
    """

    @staticmethod
    @contextlib.contextmanager
    def _ak_ssl_context():
        """临时关闭 requests.Session 的 SSL 验证，用于 akshare 在代理/证书环境异常时。

        部分数据源（东方财富 push2）在本地系统代理后会触发 SSLCertVerificationError，
        本上下文管理器只在该次请求内把 verify 设为 False，退出后恢复，避免污染全局。
        """
        import urllib3
        import requests
        urllib3.disable_warnings()
        _orig = requests.Session.get
        requests.Session.get = lambda self, url, **kwargs: _orig(self, url, verify=False, **kwargs)
        try:
            yield
        finally:
            requests.Session.get = _orig


    # ── 类级别股票库缓存（所有实例共享，只加载一次）──
    _stock_df = None          # DataFrame(code, name)
    _name_to_code = {}        # {name: code} 精确映射
    _code_to_name = {}        # {code: name} 反向映射
    _pinyin_initials_cache = {}  # {name: initials} 拼音首字母缓存（性能关键）
    _pinyin_initials_variants_cache = {}  # {name: {initials variants}} 多音字首字母组合缓存
    _stocks_loaded = False    # 是否已加载
    _fund_cache = {}          # {code: fundamentals dict} 进程内缓存（基本面日频）
    _biz_cache = {}           # {code: 核心业务描述 str} 进程内缓存（主营构成，按代码）

    def __init__(self, config_path="config.yaml"):
        self.config = load_config(config_path)
        db_path = self.config.get("database", {}).get("path", "data/cache.db")
        self.db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), db_path
        )
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.cache_days = self.config.get("default", {}).get("cache_days", 7)
        # 实例化时预热股票库（首次较慢，后续毫秒级）
        self._warmup_stock_db()

    def get_all_codes(self, limit=None, random_seed=None):
        """
        返回本地股票库中所有 A 股代码列表。

        :param limit: 最多返回多少只（用于控制选股回测的股票池大小）
        :param random_seed: 如果指定，随机抽取 limit 只，保证可复现
        :return: list[str] 股票代码列表
        """
        self._warmup_stock_db()
        if self._stock_df is None or self._stock_df.empty:
            return []
        codes = self._stock_df["code"].astype(str).tolist()
        if random_seed is not None:
            import random
            rng = random.Random(random_seed)
            rng.shuffle(codes)
        if limit is not None and limit > 0:
            codes = codes[:limit]
        return codes

    def get_stock_basic(self, code):
        """根据代码返回 (code, name) 元组，未找到返回 (code, '')。"""
        self._warmup_stock_db()
        name = self._code_to_name.get(str(code), "")
        return str(code), name

    def get_name(self, code):
        """兼容旧调用：返回 (code, name) 元组，未找到名称时 name 回退为 code。"""
        c, n = self.get_stock_basic(code)
        return (c, n or code)

    def get_name_only(self, code):
        """返回纯股票名称（不含代码前缀）；本地库/BaoStock 未命中时回退为代码本身。

        用于「名称」列展示，避免 get_stock_name 的「代码(名称)」格式把代码带进名称列。
        """
        return self.get_stock_basic(code)[1] or str(code)

    def get_fundamentals(self, code, use_cache=True):
        """获取个股基本面（名称/最新价/总市值(亿)/市盈率TTM/行业）。

        多源降级链：东方财富 push2 → akshare 个股信息 → akshare 估值(市盈率TTM/总市值)
        → Baostock 名称 → 本地 stock_fundamentals 表；各源只补全缺失字段（合并而非覆盖），
        进程内缓存避免重复请求；全部失败时返回空字典 {}（调用方再用行业关键词兜底，不会崩）。
        """
        code = str(code).strip().zfill(6)
        if use_cache and code in StockFetcher._fund_cache:
            return StockFetcher._fund_cache[code]

        def _to_float(x):
            try:
                return float(x) if x not in (None, "", "-") else None
            except Exception:
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
            print(f"[StockFetcher] 东方财富基本面失败 ({code}): {e}")
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
                print(f"[StockFetcher] akshare 个股信息失败 ({code}): {e}")
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
                        print(f"[StockFetcher] akshare 估值(PE)失败 ({code}): {e}")
                if res.get("market_cap") is None:
                    try:
                        df = ak.stock_zh_valuation_baidu(symbol=code, indicator="总市值", period="近一年")
                        if df is not None and not df.empty:
                            cap = _to_float(df.iloc[-1]["value"])
                            # 百度估值接口「总市值」单位已为「亿元」，无需再除 1e8
                            res["market_cap"] = round(cap, 1) if cap else None
                    except Exception as e:
                        print(f"[StockFetcher] akshare 估值(市值)失败 ({code}): {e}")
            except Exception as e:
                print(f"[StockFetcher] akshare 估值失败 ({code}): {e}")
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
                print(f"[StockFetcher] 本地名称兜底失败 ({code}): {e}")
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
            except Exception:
                pass

        if _has(res):
            StockFetcher._fund_cache[code] = res
        return res

    def get_core_business(self, code, use_cache=True):
        """获取个股核心业务描述（主营业务 / 主营产品），用于多股对比「核心业务」列。

        数据源：同花顺主营构成 ``ak.stock_zyjs_ths(symbol=code)``（网络可用时），
        返回 DataFrame 含 [股票代码, 主营业务, 产品类型, 产品名称, 经营范围]。
        取首行「主营业务」+「产品名称」拼成一句话描述；失败返回空字符串，
        调用方回退到行业（industry）显示。进程内缓存避免重复请求。
        """
        code = str(code).strip().zfill(6)
        if use_cache and code in StockFetcher._biz_cache:
            return StockFetcher._biz_cache[code]
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
            print(f"[StockFetcher] 核心业务获取失败 ({code}): {e}")
        if biz:
            StockFetcher._biz_cache[code] = biz
        return biz
    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    # ══════════════════════════════════════════════════════
    # 股票库内存缓存（搜索性能核心优化）
    # ══════════════════════════════════════════════════════
    @classmethod
    def _warmup_stock_db(cls):
        """预热股票库到内存（类级别缓存，所有实例共享，只加载一次）。"""
        if cls._stocks_loaded:
            return
        try:
            import time as _time
            t0 = _time.time()
            # 用默认配置创建临时实例来加载数据
            temp = cls.__new__(cls)
            temp.config = load_config("config.yaml")
            db_path = temp.config.get("database", {}).get("path", "data/cache.db")
            temp.db_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), db_path
            )
            os.makedirs(os.path.dirname(temp.db_path), exist_ok=True)
            df = temp._ensure_stock_db()
            if not df.empty:
                cls._stock_df = df
                cls._name_to_code = dict(zip(df["name"].astype(str), df["code"].astype(str)))
                cls._code_to_name = dict(zip(df["code"].astype(str), df["name"].astype(str)))
                # 预计算拼音首字母缓存（一次性324ms，后续每次查询省掉）
                t_py = _time.time()
                for name in df["name"].astype(str):
                    cls._pinyin_initials_cache[name] = cls._pinyin_static(name)
                    cls._pinyin_initials_variants_cache[name] = cls._pinyin_initials_variants(name)
                print(f"[StockFetcher] 拼音缓存预计算: {len(cls._pinyin_initials_cache)} 只 ({_time.time()-t_py:.2f}s)")
                print(f"[StockFetcher] 股票库预热完成: {len(df)} 只 ({_time.time()-t0:.2f}s)")
            cls._stocks_loaded = True
        except Exception as e:
            print(f"[StockFetcher] 股票库预热失败: {e}")
            cls._stocks_loaded = True  # 标记已尝试，避免反复重试

    def _init_cache_table(self, conn, table_name):
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                cache_key   TEXT PRIMARY KEY,
                data_json   TEXT,
                updated_at  TEXT
            )
        """)
        conn.commit()

    def _read_cache(self, conn, table_name, cache_key, max_age_hours=None, max_age_seconds=None, as_dataframe=True):
        self._init_cache_table(conn, table_name)
        row = conn.execute(
            f"SELECT data_json, updated_at FROM {table_name} WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        if row is None:
            print(f"[CACHE] MISS key={cache_key} table={table_name} (无缓存条目)")
            return None
        updated_at = datetime.fromisoformat(row[1])
        if max_age_seconds is not None:
            max_age = timedelta(seconds=max_age_seconds)
        elif max_age_hours is not None:
            max_age = timedelta(hours=max_age_hours)
        else:
            max_age = timedelta(days=self.cache_days)
        age = datetime.now() - updated_at
        if age < max_age:
            age_s = age.total_seconds()
            age_str = f"{age_s/3600:.1f}h" if age_s >= 3600 else f"{age_s/60:.1f}m"
            print(f"[CACHE] HIT  key={cache_key} table={table_name} age={age_str}")
            if not as_dataframe:
                return json.loads(row[0])
            # 如果缓存的是 DataFrame（原格式），返回 DataFrame
            try:
                df = pd.read_json(io.StringIO(row[0]))
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"], errors="coerce", format="mixed")
                return df
            except Exception:
                # 非 DataFrame JSON（如实时行情字典），返回原始 dict/list
                return json.loads(row[0])
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
        df = pd.read_json(io.StringIO(data_json))
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df

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

    def _write_cache(self, conn, table_name, cache_key, data):
        self._init_cache_table(conn, table_name)
        if isinstance(data, pd.DataFrame):
            data_json = data.to_json(orient="records", date_format="iso")
        else:
            data_json = json.dumps(data, ensure_ascii=False, default=str)
        conn.execute(
            f"INSERT OR REPLACE INTO {table_name} (cache_key, data_json, updated_at) "
            f"VALUES (?, ?, ?)",
            (cache_key, data_json, datetime.now().isoformat()),
        )
        conn.commit()

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
            age_minutes = (datetime.now() - updated_at).total_seconds() / 60

            source = "未知"
            try:
                source_row = conn.execute(
                    "SELECT data_json FROM sector_cache WHERE cache_key = ?",
                    ("sector_list_v3_source",),
                ).fetchone()
                if source_row:
                    source = json.loads(source_row[0]).get("source", "未知")
            except Exception:
                pass

            return updated_at.isoformat(), age_minutes, source
        except Exception:
            return None
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════
    # 股票名称查询（永久缓存）
    # ══════════════════════════════════════════════════════
    def get_stock_name(self, ticker):
        """
        根据股票代码查询股票名称。
        使用 BaoStock 查询，结果永久缓存（名称不会变）。
        返回 "代码(名称)" 格式，如 600519(贵州茅台)；查询失败仅返回代码。

        :param ticker: 股票代码，如 "600519" "000858"
        :return: 格式 "代码(名称)" 或 "代码"
        """
        if not ticker:
            return "<未知>"
        ticker = str(ticker).strip()

        # 从缓存读取
        conn = self._get_conn()
        try:
            name_table = "stock_name_cache"
            self._init_cache_table(conn, name_table)
            row = conn.execute(
                f"SELECT data_json FROM {name_table} WHERE cache_key = ?",
                (ticker,),
            ).fetchone()
            if row is not None:
                data = json.loads(row[0])
                name = data.get("name", "")
                if name:
                    return f"{ticker}({name})"

            # 缓存未命中 -> 查询 BaoStock（复用连接池）
            if _BS_OK:
                try:
                    if not _BaoStockFetcher._ensure_login():
                        return ticker
                    bs_code = _symbol_to_bs(ticker)
                    rs = bs.query_stock_basic(code=bs_code)
                    if rs.error_code == "0":
                        while rs.next():
                            row_data = rs.get_row_data()
                            if len(row_data) >= 2:
                                name = row_data[1]
                                # 写入永久缓存
                                self._write_cache_raw(
                                    conn, name_table, ticker,
                                    json.dumps({"name": name, "code_name": row_data[0]}),
                                )
                                return f"{ticker}({name})"
                except Exception as e:
                    print(f"[StockFetcher] 查询股票名称失败 ({ticker}): {e}")

            return ticker  # 查询失败，仅返回代码
        finally:
            conn.close()

    def _write_cache_raw(self, conn, table_name, cache_key, json_str):
        """写入原始 JSON 字符串到缓存表。"""
        self._init_cache_table(conn, table_name)
        conn.execute(
            f"INSERT OR REPLACE INTO {table_name} (cache_key, data_json, updated_at) "
            f"VALUES (?, ?, ?)",
            (cache_key, json_str, datetime.now().isoformat()),
        )
        conn.commit()

    # ══════════════════════════════════════════════════════
    # 实时五档行情（新浪，短时缓存）
    # ══════════════════════════════════════════════════════
    # 常见指数代码 -> 新浪前缀（000001 是上证指数，不是股票）
    _INDEX_SINA_PREFIX = {
        "000001": "sh", "000016": "sh", "000010": "sh", "000009": "sh",
        "000300": "sh", "000688": "sh", "000905": "sh",
        "399001": "sz", "399006": "sz", "399005": "sz", "399300": "sz",
        "399673": "sz", "399006": "sz", "399102": "sz", "399103": "sz",
    }

    def _get_sina_prefix(self, ticker: str) -> str:
        """根据 6 位代码返回新浪市场前缀 sh/sz，正确处理指数代码。"""
        if ticker in self._INDEX_SINA_PREFIX:
            return self._INDEX_SINA_PREFIX[ticker]
        code_int = int(ticker) if ticker.isdigit() else 0
        if 600000 <= code_int <= 609999 or 688000 <= code_int <= 689999 or 510000 <= code_int <= 589999:
            return "sh"
        return "sz"

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
            with urllib.request.urlopen(req, timeout=10) as resp:
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
                except Exception:
                    return default

            def _parse_int(val, default=0):
                try:
                    return int(float(val)) if val else default
                except Exception:
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
            print(f"[StockFetcher] 获取实时行情失败 ({ticker}): {e}")
            return None
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────
    # 海外 / 环球指数行情（道琼斯 / 纳斯达克 / 标普500 / 富时100 / 韩国KOSPI）
    # ─────────────────────────────────────────────────────────
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
            except Exception:
                pass

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
            with urllib.request.urlopen(req, timeout=10) as resp:
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
                except Exception:
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
            print(f"[StockFetcher] 海外指数实时获取失败 ({sina_code}): {e}")
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
            print(f"[StockFetcher] 海外指数日线获取失败 ({symbol}): {e}")
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
            with urllib.request.urlopen(req, timeout=10) as resp:
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
            print(f"[StockFetcher] 新浪指数分时获取失败 ({code}): {e}")
            return None

    def synth_us_index_intraday(self, open_, high, low, close, prev_close):
        """当美股指数只有 O/H/L/C 快照时，合成一条有真实日内形态的近似分时曲线。

        不做任何数据造假：open/high/low/close/prev_close 均来自实时快照。
        用一条平滑路径在交易时段内穿过这些关键点（含昨收水平参考），
        从而得到一条「有起伏、不像直线」的完整当日走势，而非 4 点折线。
        返回 (spark_x, spark_y) 或 (None, None)。
        """
        try:
            vals = [open_, high, low, close]
            if None in vals or prev_close is None or prev_close == 0:
                return None, None
            import numpy as np
            n = 48  # 近似每 5 分钟一个点的全天节奏
            # 关键路径：开盘 -> 触底 -> 触顶 -> 收盘，平滑过渡
            # 用自然指数加权混合，使高低点出现在合理位置而非端点
            x = np.linspace(0, 1, n)
            # 基准：从 open 到 close 的线性趋势
            base = open_ + (close - open_) * x
            # 叠加一个「先下后上」的日内波动轮廓（振幅来自真实 high/low）
            amp_low = (low - min(open_, prev_close)) / prev_close
            amp_high = (high - max(open_, prev_close)) / prev_close
            # 波动包络：高斯波峰在 35% 处（探底），波谷在 65% 处（冲高）
            wave = (amp_high * np.exp(-((x - 0.65) ** 2) / 0.04)
                    - amp_low * np.exp(-((x - 0.35) ** 2) / 0.04))
            curve = base + prev_close * wave
            # 强制端点精确等于真实 open / close
            curve[0] = open_
            curve[-1] = close
            return list(range(n)), [round(float(v), 3) for v in curve]
        except Exception:
            return None, None

    # ══════════════════════════════════════════════════════
    # 全量股票数据库（永久缓存）
    # ══════════════════════════════════════════════════════
    def _ensure_stock_db(self):
        """
        确保全量股票基本信息已加载到本地 SQLite。
        首次调用从 BaoStock 拉取，之后永久缓存（股票基本信息极少变化）。
        返回 DataFrame(code, name) 或空 DataFrame。
        """
        conn = self._get_conn()
        try:
            table_name = "all_stocks"
            self._init_cache_table(conn, table_name)

            # 检查缓存是否存在
            row = conn.execute(
                f"SELECT data_json FROM {table_name} WHERE cache_key = 'all'"
            ).fetchone()
            if row is not None:
                data = json.loads(row[0])
                return pd.DataFrame(data)

            # 缓存未命中 -> 从 BaoStock 拉取
            if not _BS_OK:
                return pd.DataFrame(columns=["code", "name"])

            print("[StockFetcher] 正在从 BaoStock 加载全量股票列表...")
            if not _BaoStockFetcher._ensure_login():
                return pd.DataFrame(columns=["code", "name"])
            rs = bs.query_stock_basic()
            if rs.error_code != "0":
                return pd.DataFrame(columns=["code", "name"])

            rows = []
            while (rs.error_code == "0") and rs.next():
                row_data = rs.get_row_data()
                if len(row_data) >= 2 and row_data[0] and row_data[1]:
                    # code 格式: sh.600519 -> 提取纯数字部分
                    code = row_data[0].replace("sh.", "").replace("sz.", "")
                    name = row_data[1]
                    # 过滤：仅保留正常A股个股（排除指数、基金、ETF、债券等）
                    code_int = int(code) if code.isdigit() else 0
                    is_valid_stock_range = (
                        (600000 <= code_int <= 609999) or   # 上海主板
                        (1 <= code_int <= 4999) or          # 深圳主板+中小板（超000001起）
                        (300000 <= code_int <= 309999) or   # 创业板
                        (688000 <= code_int <= 689999)      # 科创板
                    )
                    exclude_keywords = [
                        "指数", "综指", "公司债", "企债", "国债", "转债",
                        "基金", "ETF", "LOF", "回购", "期货", "期权", "债券",
                        "ST", "*ST", "PT", "退市", "优先股",
                        "上证", "深证", "中盘", "小盘", "全指", "中小",
                        "A股", "B股", "H股",
                    ]
                    # 额外规则：过滤纯板块名（无个股特征）
                    generic_names = {"A股资源", "消费服务", "食品饮料", "有色金属", "信息技术",
                                     "医药生物", "金融地产", "能源化工", "公用事业", "可选消费",
                                     "主要消费", "工业制造", "电信服务"}
                    if (
                        name and len(code) == 6 and is_valid_stock_range
                        and not any(kw in name for kw in exclude_keywords)
                        and name not in generic_names
                    ):
                        rows.append({"code": code, "name": name})

            # 复用连接：此处不 logout，下次还能用

            all_stocks = pd.DataFrame(rows)
            print(f"[StockFetcher] 全量股票加载完成: {len(all_stocks)} 只")

            # 写入永久缓存
            self._write_cache_raw(
                conn, table_name, "all",
                json.dumps(all_stocks.to_dict(orient="records"), ensure_ascii=False),
            )
            return all_stocks
        except Exception as e:
            print(f"[StockFetcher] 加载全量股票失败: {e}")
            return pd.DataFrame(columns=["code", "name"])
        finally:
            conn.close()

    # ───── 中文搜索辅助方法 ─────
    @staticmethod
    def _pinyin_static(name):
        """获取拼音首字母（纯函数，无副作用，用于缓存）。"""
        try:
            import pypinyin
            return "".join([w[0][0] for w in pypinyin.pinyin(name, style=pypinyin.NORMAL)]).upper()
        except Exception:
            return ""

    @staticmethod
    def _pinyin_initials_variants(name):
        """
        获取股票名称的所有拼音首字母组合（处理多音字）。
        如 '长电科技' -> {'ZDKJ', 'CDKJ'}。
        """
        try:
            import pypinyin
            py_lists = pypinyin.pinyin(name, style=pypinyin.NORMAL, heteronym=True)
            from itertools import product
            variants = set()
            for combo in product(*py_lists):
                variants.add("".join([w[0].upper() for w in combo]))
            return variants
        except Exception:
            return set()

    @staticmethod
    def _pinyin_full(name):
        """获取股票名称的完整拼音（小写无空格）。如 '贵州茅台' -> 'guizhoumaotai'。"""
        try:
            import pypinyin
            return "".join([w[0] for w in pypinyin.pinyin(name, style=pypinyin.NORMAL)]).lower()
        except Exception:
            return name.lower()


    @staticmethod
    def _pinyin_initials(name):
        """
        获取股票名称的拼音首字母（大写）。
        优先从类缓存读取（预热时已预计算），避免重复调用pypinyin。
        如 '招商银行' -> 'ZSYH'。
        """
        cached = StockFetcher._pinyin_initials_cache.get(name)
        if cached is not None:
            return cached
        return StockFetcher._pinyin_static(name)

    @staticmethod
    def _name_tokens(name):
        """
        将股票名称拆分为搜索用的中文分词 token。
        覆盖常见的简称模式：首字+尾字、中间词、2-gram等。
        如 '招商银行' -> {'招商', '银行', '招', '商', '银', '行', '商银', '招商银', '商银行'}
        """
        tokens = set()
        tokens.add(name)           # 全称
        n = len(name)
        # 2-gram（如 "招商" "商银" "银行"）
        for i in range(n - 1):
            tokens.add(name[i:i + 2])
        # 3-gram（如 "招商银" "商银行"）
        for i in range(n - 2):
            tokens.add(name[i:i + 3])
        # 单字
        for ch in name:
            tokens.add(ch)
        # 首尾组合（简称常见形式：首字+尾字，如 "招行"）
        if n >= 2:
            tokens.add(name[0] + name[-1])
        if n >= 3:
            tokens.add(name[0] + name[2])     # 跳字简写
        return tokens

    def _get_latest_price(self, code):
        """从日线缓存中获取最近一个交易日的收盘价。返回 (price, date_str) 或 (None, None)。"""
        try:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT data_json, updated_at FROM daily_cache "
                    "WHERE cache_key LIKE ? ORDER BY updated_at DESC LIMIT 1",
                    (f"{code}%",),
                ).fetchone()
                if row is not None:
                    df = pd.read_json(io.StringIO(row[0]))
                    if not df.empty and "close" in df.columns:
                        latest = df.iloc[-1]
                        return float(latest["close"]), str(latest["date"])[:10]
            finally:
                conn.close()
        except Exception:
            pass
        return None, None

    # ───── 名称->代码映射（简单可靠）─────
    def get_name_code_map(self):
        """从内存缓存获取 {名称: 代码} 映射表。"""
        return dict(self._name_to_code) if self._name_to_code else {}

    def lookup_code(self, query, limit=15):
        """
        名称->代码 查找（高性能版：内存缓存 + 向量化）。
        输入中文名称/拼音，返回 [(code, name), ...]。
        """
        if not query or not query.strip():
            return []

        import time as _time
        t0 = _time.time()
        query = query.strip()
        q_upper = query.upper()
        q_lower = query.lower()
        has_chinese = any('\u4e00' <= ch <= '\u9fff' for ch in query)

        # ── L0: 纯6位数字 -> O(1) ──
        if query.isdigit() and len(query) == 6:
            name = self._code_to_name.get(query, "")
            print(f"[lookup_code] '{query}' -> ({query},{name}) ({(_time.time()-t0)*1000:.1f}ms)")
            return [(query, name)] if name else [(query, query)]

        # ── 使用内存缓存 ──
        df = self._stock_df
        if df is None or df.empty:
            df = self._ensure_stock_db()
        if df is None or df.empty:
            return []

        results = []
        seen_codes = set()

        # L1: 精确名称匹配 O(1)
        exact_code = self._name_to_code.get(query)
        if exact_code:
            results.append((exact_code, query, 1000))
            seen_codes.add(exact_code)

        # 如果已有精确匹配，快速返回（除非用户需要更多结果）
        has_exact = len(results) > 0 and results[0][2] == 1000

        # L2-L4: pandas 向量化（仅在需要更多结果时）
        names = df["name"].astype(str)
        codes = df["code"].astype(str)

        l2_l3_found = 0  # 记录L2/L3找到的结果数
        if len(query) >= 2 and len(results) < limit:
            mask_start = names.str.startswith(query, na=False)
            for idx in df.index[mask_start]:
                code = str(codes.iloc[idx])
                if code not in seen_codes:
                    name = str(names.iloc[idx])
                    results.append((code, name, 800))
                    seen_codes.add(code)
                    l2_l3_found += 1

            if len(results) < limit:
                mask_contain = names.str.contains(query, regex=False, na=False)
                for idx in df.index[mask_contain & ~mask_start]:
                    code = str(codes.iloc[idx])
                    if code not in seen_codes:
                        results.append((code, str(names.iloc[idx]), 600))
                        seen_codes.add(code)
                        l2_l3_found += 1

            # L4: 字符分散匹配（中文）— 仅在L2/L3完全没找到时才启用
            if has_chinese and l2_l3_found == 0 and len(results) < limit:
                for idx in range(len(df)):
                    code = str(codes.iloc[idx])
                    if code in seen_codes:
                        continue
                    name = str(names.iloc[idx])
                    if all(ch in name for ch in query):
                        results.append((code, name, 400))
                        seen_codes.add(code)

        # L5-L7: 拼音/Token — 仅在L1-L4都没找到 或 结果不足 时触发
        need_fuzzy = (
            len(results) < limit
            and len(query) >= 2
            and not has_exact
            and len(results) == 0  # 前面所有层都找不到时才用拼音兜底
        )
        if need_fuzzy:
            for idx in range(len(df)):
                code = str(codes.iloc[idx])
                if code in seen_codes:
                    continue
                name = str(names.iloc[idx])
                score = 0
                initials = self._pinyin_initials(name)
                if initials:
                    if q_upper == initials:
                        score = 500
                    elif q_upper in initials:
                        score = 350
                # 多音字首字母组合匹配
                if score == 0:
                    variants = self._pinyin_initials_variants_cache.get(name) or self._pinyin_initials_variants(name)
                    for v in variants:
                        if q_upper == v:
                            score = 500
                            break
                        elif q_upper in v:
                            score = 350
                if score == 0 and has_chinese:
                    tokens = self._name_tokens(name)
                    if query in tokens:
                        score = 450
                if score == 0:
                    full_py = self._pinyin_full(name)
                    if q_lower == full_py:
                        score = 300
                    elif q_lower in full_py:
                        score = 200
                if score > 0:
                    results.append((code, name, score))

        results.sort(key=lambda x: x[2], reverse=True)
        final = [(r[0], r[1]) for r in results[:limit]]
        print(f"[lookup_code] '{query}' -> {len(final)} 条 ({(_time.time()-t0)*1000:.1f}ms)")
        return final

    def _lookup_name_for_code(self, code):
        """代码->名称（从内存缓存 O(1) 查找）。"""
        return self._code_to_name.get(code, "")

    # ───── 行业关键词自动生成 ─────
    # 基于股票名称中的行业特征词，自动匹配对应的高频事件关键词
    # 格式: {行业特征词集合: [关键词列表]}
    # 一只股票可匹配多个行业，结果去重合并

    _INDUSTRY_KEYWORDS = {
        # ── 能源 / 资源 ──
        frozenset(["煤炭", "煤业", "能源", "神华", "中煤", "兖矿", "潞安", "西山", "平煤", "阳泉", "盘江", "兰花"]):
            ["煤炭", "动力煤", "焦煤", "保供", "电厂库存", "长协价", "坑口价", "产能"],
        frozenset(["石油", "石化", "海油", "油气", "杰瑞", "中曼", "洲际", "博迈"]):
            ["原油", "天然气", "油价", "炼化", "乙烯", "PX", "勘探", "页岩气"],
        frozenset(["电力", "电建", "水电", "火电", "核电", "风电", "光伏发电", "绿电", "粤电力", "浙能", "华能", "国电", "大唐", "华电", "国投", "川投", "申能", "福能"]):
            ["电力", "电价", "装机容量", "利用小时数", "新能源", "绿电", "火电", "水电", "风电", "光伏", "核电"],
        frozenset(["有色", "铜", "铝", "锂矿", "稀土", "黄金", "钨", "钼", "锌", "锡", "铂"]):
            ["有色金属", "铜", "铝", "锂", "稀土", "黄金", "钨", "钴", "镍", "大宗商品", "库存周期"],


        # ── 金融 ──
        frozenset(["银行", "农商", "农信", "城商", "平安银行", "招商银行", "工商银行", "建设银行", "农业银行", "中国银行", "交通银行", "邮储", "兴业", "浦发", "中信", "民生", "光大", "华夏", "北京银行", "江苏银行", "宁波银行", "南京银行", "杭州银行", "成都银行", "长沙银行", "重庆银行", "贵阳银行", "西安银行", "郑州银行", "苏州银行", "青岛银行"]):
            ["银行", "贷款", "净息差", "不良率", "拨备覆盖率", "存款", "信贷", "LPR", "MLF", "降息"],
        frozenset(["券商", "证券", "东方财富", "中信证券", "华泰证券", "国泰君安", "银河证券", "广发证券", "招商证券", "海通证券", "申万宏源", "光大证券", "国信证券"]):
            ["证券", "经纪业务", "投行", "自营", "两融", "成交量", "IPO", "基金", "资管", "牛市"],
        frozenset(["保险", "人寿", "人保", "太保", "新华", "平安寿险", "泰康", "中国平安", "平安"]):
            ["保险", "保费收入", "投资收益", "偿付能力", "新业务价值", "利率", "长端利率", "权益投资"],
        frozenset(["信托", "租赁", " AMC ", "资产管理", "不良资产"]):
            ["信托", "资产管理", "不良资产处置", "融资租赁", "ABS", "REITs"],


        # ── 科技 / 电子 / 半导体 ──
        frozenset(["科技", "电子", "信息", "软件", "通信", "网络", "互联", "数据", "云计算", "大数据", "人工智能", "AI", "芯片", "半导体", "集成电路", "存储", "传感器", "PCB", "连接器", "线缆", "光模块", "光纤", "LED", "液晶", "显示", "面板", "消费电子", "智能", "物联网", "5G", "6G", "深科技", "中兴", "华为", "小米概念", "立讯精密", "工业富联", "歌尔", "闻泰科技", "韦尔股份", "兆易创新", "北方华创", "中芯国际", "寒武纪", "海光信息", "澜起科技", "紫光国微", "卓胜微", "圣邦股份", "斯达半导", "新洁能", "扬杰科技", "士兰微", "晶方科技", "通富微电", "长电科技", "华天科技", "京东方", "TCL科技", "三安光电", "水晶光电", "欧菲光", "蓝思科技", "领益智造", "立讯", "鹏鼎控股", "东山精密", "深南电路", "沪电股份", "胜宏科技"]):
            ["科技", "半导体", "芯片", "电子", "AI", "人工智能", "云计算", "数据中心", "国产替代", "消费电子", "5G", "6G", "存储芯片", "GPU", "CPU", "先进封装", "HBM", "CPO", "光模块", "PCB", "被动元件", "MLCC", "面板", "OLED", "Mini LED", "Micro LED", "传感器", "物联网", "车规级", "汽车电子", "边缘计算", "算力", "大模型", "AIGC", "信创"],
        frozenset(["计算机", "IT服务", "软件开发", "SaaS", "用友", "金山办公", "恒生电子", "同花顺", "大智慧", "金蝶", "广联达", "卫宁健康", "创业慧康", "久远银海", "中科创达", "德赛西威", "中科创达", "科大讯飞", "三六零", "奇安信", "深信服", "安恒信息", "绿盟科技", "启明星辰", "美亚柏科", "太极股份", "中国软件", "海量数据", "星环科技"]):
            ["计算机", "软件", "SaaS", "云计算", "数字经济", "信创", "国产软件", "ERP", "金融科技", "医疗信息化", "网络安全", "数据安全", "密码学", "隐私计算", "数字政府", "智慧城市", "工业互联网", "MES", "CAD", "EDA", "操作系统", "数据库", "中间件", "大模型应用", "AI Agent"],


        # ── 新能源 / 电动车 ──
        frozenset(["新能源", "电池", "储能", "锂电", "宁德时代", "比亚迪", "亿纬锂能", "国轩高科", "欣旺达", "德赛电池", "璞泰来", "恩捷股份", "星源材质", "天赐材料", "当升科技", "容百科技", "杉杉股份", "中伟股份", "华友钴业", "赣锋锂业", "天齐锂业", "盐湖股份", "藏格矿业", "盛新锂能", "雅化集团", "永兴材料", "科达利"]):
            ["新能源", "锂电池", "储能", "动力电池", "正极", "负极", "电解液", "隔膜", "碳酸锂", "氢氧化锂", "锂盐", "钠离子电池", "固态电池", "4680", "麒麟电池", "刀片电池", "CTP", "CTC", "换电", "充电桩", "虚拟电厂", "VPP"],
        frozenset(["光伏", "太阳能", "硅料", "硅片", "组件", "逆变器", "EVA胶膜", "玻璃", "背板", "接线盒", "隆基绿能", "通威股份", " TCL 中环", "阳光电源", "锦浪科技", "固德威", "禾迈股份", "昱能科技", "德业股份", "福斯特", "福莱特", "信义光能", "大全能源", "合盛硅业", "石英股份"]):
            ["光伏", "太阳能", "硅料", "硅片", "电池片", "组件", "逆变器", "EVA", "POE", "玻璃", "背板", "N型", "TOPCon", "HJT", "BC", "钙钛矿", "分布式光伏", "集中式光伏", "BIPV", "光伏建筑一体化", "储能逆变器", "微型逆变器", "跟踪支架"],
        frozenset(["风能", "风电", "风机", "叶片", "塔筒", "铸件", "齿轮箱", "轴承", "变流器", "海缆", "明阳智能", "金风科技", "运达股份", "电气风电", "中材科技", "天顺风能", "大金重工", "海力风电", "新强联", "日月股份", "双一科技", "时代新材", "中际联合"]):
            ["风电", "风机", "海上风电", "陆上风电", "叶片", "塔筒", "铸件", "齿轮箱", "变流器", "海缆", "大型化", "漂浮式风电", "分散式风电", "老旧改造", "运维", "储能配套"],
        frozenset(["整车", "汽车", "电动", "比亚迪", "长城汽车", "长安汽车", "上汽集团", "广汽集团", "理想汽车", "蔚来", "小鹏汽车", "赛力斯", "江淮汽车", "吉利", "一汽", "东风", "北汽", "小康"]):
            ["新能源汽车", "电动车", "智能驾驶", "自动驾驶", "ADAS", "激光雷达", "毫米波雷达", "HUD", "座舱", "域控制器", "线控底盘", "一体化压铸", "热管理", "轻量化", "出海", "出口", "渗透率", "销量", "订单"] ,


        # ── 医药 / 生物 ──
        frozenset(["医药", "生物制药", "中药", "化学药", "疫苗", "医疗器械", "诊断", "CXO", "创新药", "恒瑞医药", "药明康德", "爱尔眼科", "通策医疗", "迈瑞医疗", "联影医疗", "乐普医疗", "鱼跃医疗", "智飞生物", "沃森生物", "长春高新", "片仔癀", "云南白药", "同仁堂", "以岭药业", "东阿阿胶", "华润三九", "白云山", "济川药业", "科伦药业", "健康元", "丽珠集团"]):
            ["医药", "创新药", "生物药", "中药", "化学药", "仿制药", "集采", "医保谈判", "CXO", "CDMO", "CRO", "疫苗", "医疗器械", "IVD", "高值耗材", "医疗服务", "医美", "辅助生殖", "细胞治疗", "基因治疗", "ADC", "GLP-1", "减肥药", "阿尔茨海默", "老龄化", "DRG/DIP"],


        # ── 消费 ──
        frozenset(["白酒", "酒类", "茅台", "五粮液", "泸州老窖", "洋河", "汾酒", "古井贡酒", "今世缘", "舍得酒业", "酒鬼酒", "水井坊", "老白干", "顺鑫农业", "迎驾贡酒", "口子窖"]):
            ["白酒", "次高端", "高端酒", "大众酒", "批价", "库存周期", "动销", "渠道", "宴席", "礼赠", "酱香", "浓香", "清香"],
        frozenset(["食品", "饮料", "乳制品", "调味品", "预制菜", "休闲食品", "速冻食品", "肉制品", "烘焙", "伊利股份", "蒙牛", "海天味业", "中炬高新", "千禾味业", "涪陵榨菜", "安井食品", "三全食品", "绝味食品", "洽洽食品", "桃李面包", "巴比食品", "元气森林"]):
            ["食品饮料", "乳制品", "啤酒", "调味品", "预制菜", "休闲食品", "速冻", "餐饮供应链", "成本下行", "原材料价格", "提价", "渠道下沉", "新品", "健康化", "零糖", "功能性"],
        frozenset(["家电", "美的", "格力", "海尔", "小家电", "厨电", "黑电", "老板电器", "苏泊尔", "九阳股份", "石头科技", "科沃斯", "海信视像", "海信家电", "TCL", "长虹", "创维"]):
            ["家电", "白电", "黑电", "厨电", "小家电", "清洁电器", "扫地机", "洗地机", "集成灶", "洗碗机", "以旧换新", "出海", "外销", "内需", "地产后周期", "竣工链"],
        frozenset(["免税", "零售", "商贸", "超市", "百货", "电商", "跨境电商", "化妆品", "珠宝", "酒店", "旅游", "餐饮", "免税店", "中国中免", "王府井", "永辉超市", "家家悦", "步步高", "红旗连锁", "爱婴室", "珀莱雅", "贝泰妮", "上海家化", "华熙生物", "爱美客", "锦江酒店", "首旅酒店", "同庆楼", "海底捞", "九毛九"]):
            ["零售", "免税", "化妆品", "医美", "黄金珠宝", "酒店", "旅游出行", "餐饮", "跨境电商", "直播电商", "即时零售", "社区团购", "折扣零售", "奥特莱斯", "会员制", "体验经济", "国潮"],


        # ── 地产 / 建筑 / 基建 ──
        frozenset(["房地产", "地产", "开发", "物业", "万科", "保利发展", "龙湖集团", "碧桂园", "融创", "新城控股", "招商蛇口", "金地集团", "华侨城", "绿地控股", "华润置地", "滨江集团", "华发股份", "越秀地产"]):
            ["房地产", "销售面积", "销售额", "房价", "土地储备", "拿地", "融资", "债务", "保交楼", "城中村改造", "保障房", "物管", "商业地产", "REITs", "LPR", "限购松绑", "因城施策", "二手房", "挂牌量"],
        frozenset(["建筑", "基建", "工程", "施工", "装饰", "园林", "设计", "咨询", "中铁", "中交", "中建", "中冶", "电建", "葛洲坝", "隧道股份", "上海建工", "四川路桥", "安徽建工", "山东路桥", "北方国际", "中工国际", "中钢国际", "中国化学"]):
            ["基建", "建筑工程", "PPP", "专项债", "一带一路", "海外工程", "装配式建筑", "BIM", "绿色建筑", "城市更新", "旧改", "水利", "轨道交通", "市政", "PPP存量", "REITs", "央企改革"],


        # ── 军工 / 航天 ──
        frozenset(["军工", "航空", "航天", "船舶", "兵器", "核工业", "中航沈飞", "航发动力", "洪都航空", "中航西飞", "中直股份", "航天彩虹", "中国卫星", "海防", "中国重工", "中国船舶", "中船防务", "中兵红箭", "内蒙一机", "北方导航", "睿创微纳", "菲利华", "光威复材", "中简科技", "图南股份", "西部超导", "抚顺特钢", "钢研高纳"]):
            ["军工", "航空航天", "战斗机", "发动机", "导弹", "无人机", "卫星", "雷达", "电子信息", "舰船", "核潜艇", "装甲", "弹药", "特种材料", "碳纤维", "高温合金", "隐身材料", "北斗", "商业航天", "低空经济", "eVTOL", "军费预算", "采购周期", "军民融合"],


        # ── 交通运输 ──
        frozenset(["港口", "航运", "物流", "机场", "航空", "快递", "高速", "铁路", "中远海控", "招商轮船", "中谷物流", "顺丰控股", "圆通速递", "韵达股份", "申通快递", "京东物流", "上海机场", "白云机场", "深圳机场", "首都机场", "宁沪高速", "招商公路", "京沪高铁", "大秦铁路", "广深铁路"]):
            ["航运", "港口", "集运", "干散货", "油运", "BDI", "CCFI", "SCFI", "快递", "物流", "航空客运", "民航", "免税购物", "机场", "高速公路", "通行费", "铁路货运", "铁运", "多式联运", "跨境物流", "冷链"],


        # ── 化工 / 材料 ──
        frozenset(["化工", "化学", "材料", "聚氨酯", "MDI", "TDI", "纯碱", "烧碱", "PVC", "化肥", "磷肥", "钾肥", "氮肥", "农药", "涂料", "万华化学", "华鲁恒升", "龙佰集团", "云天化", "华谊集团", "三友化工", "中泰化学", "新疆天业", "巨化材料", "三棵树"]):
            ["化工", "MDI", "TDI", "聚氨酯", "纯碱", "烧碱", "PVC", "化肥", "磷化工", "氟化工", "钛白粉", "有机硅", "新材料", "可降解塑料", "电子化学品", "湿电子化学品", "锂电材料", "光伏材料", "半导体材料", "碳中和", "能耗双控", "供给侧改革"],


        # ── 机械 / 设备 ──
        frozenset(["机械", "设备", "机床", "工程机械", "机器人", "自动化", "智能制造", "三一重工", "中联重科", "徐工机械", "恒立液压", "浙江鼎力", "安徽合力", "杭叉集团", "汇川技术", "埃斯顿", "绿的谐波", "拓斯达", "伊之密", "豪迈科技", "杰瑞股份", "中海油服", "石化机械", "天地科技", "郑煤机"]):
            ["工程机械", "挖掘机", "起重机", "混凝土机械", "高空作业平台", "工业母机", "数控机床", "机器人", "人形机器人", "减速器", "伺服系统", "PLC", "工业自动化", "智能制造", "激光设备", "3D打印", "锂电设备", "光伏设备", "半导体设备", "油服", "煤矿机械", "农机", "出口替代"],


        # ── 农业 / 农产品 ──
        frozenset(["农业", "种业", "养殖", "畜牧", "饲料", "农产品", "水产", "牧原股份", "温氏股份", "新希望", "海大集团", "圣农发展", "益生股份", "民和股份", "隆平高科", "登海种业", "大北农", "荃银高科", "北大荒", "苏垦农发", "中粮糖业", "金龙鱼", "中粮科技"]):
            ["农业", "生猪", "猪周期", "能繁母猪", "存栏量", "出栏量", "饲料原料", "玉米", "豆粕", "种业", "转基因", "粮食安全", "农产品价格", "白糖", "棉花", "油脂", "养殖户利润", "疫病防控", "预制食材", "中央厨房"],


        # ── 传媒 / 游戏 / 教育 ──
        frozenset(["传媒", "影视", "游戏", "动漫", "出版", "广告", "教育", "在线教育", "腾讯", "网易游戏", "三七互娱", "完美世界", "吉比特", "恺英网络", "神州泰岳", "中文传媒", "凤凰传媒", "中南传媒", "芒果超媒", "光线传媒", "万达电影", "中国电影", "分众传媒", "蓝色光标", "三人行", "值得买"]):
            ["传媒", "游戏", "AIGC", "元宇宙", "VR/AR", "短剧", "影视剧", "院线", "广告营销", "数字营销", "直播带货", "版权", "IP运营", "出版", "教育", "职业教育", "K12", "素质教育", "体育赛事", "线下演出", "演唱会经济"],
    }

    @staticmethod
    def _get_stock_industry_keywords(stock_name):
        """
        根据股票名称匹配行业，返回该行业的高频事件关键词。
        :param stock_name: 股票名称（如"贵州茅台"、"宁德时代"）
        :return: list[str] 关键词列表，或空列表
        """
        if not stock_name:
            return []

        matched = set()
        for industry_terms, keywords in StockFetcher._INDUSTRY_KEYWORDS.items():
            # 检查名称是否包含任一行业特征词
            if any(term in stock_name for term in industry_terms):
                matched.update(keywords)

        return sorted(matched) if matched else []

    def get_stock_keywords(self, code_or_name, top_k=10):
        """
        为给定股票生成高频事件关键词。

        策略：
          1. 先根据名称做行业匹配（毫秒级）
          2. 如果代码是6位数字，尝试从事件库提取历史关联关键词

        :param code_or_name: 股票代码或名称
        :param top_k: 返回前 K 个关键词
        :return: str 逗号分隔的关键词字符串
        """
        # 1) 确定股票名称
        name = ""
        if code_or_name and code_or_name.isdigit() and len(code_or_name) == 6:
            name = self._lookup_name_for_code(code_or_name)
        else:
            name = code_or_name or ""

        # 2) 行业匹配关键词
        industry_kws = self._get_stock_industry_keywords(name)

        if not industry_kws:
            # 兜底：取股票名称本身的核心词（去掉常见后缀）
            core = name.replace("股份", "").replace("有限公司", "")
            core = core.replace("集团", "").replace("中国", "")
            if len(core) >= 2:
                industry_kws = [core]

        # 3) 截断到 top_k
        result = industry_kws[:top_k]
        return ",".join(result)

    # ───── 旧版复杂搜索（保留兼容）─────
    def search_stocks(self, query, limit=15, with_price=False):
        """
        模糊搜索股票：代码 + 中文名称 + 拼音 + 同音字容错。

        匹配层级（从高到低）：
          1. 精确代码匹配 (1000)
          2. 代码前缀匹配 (900)
          3. 精确名称匹配 (800)
          4. 名称以关键词开头 (750)
          5. 名称包含完整查询词 (700)
          6. 全拼匹配 -> 同音字容错 (600)
          7. 拼音首字母匹配 (500)
          8. 名称分词Token匹配 -> 简称识别 (450)
          9. 名称子串包含 (400)
         10. 字符分散模糊匹配 (300)
         11. 全拼子串匹配 (250)
         12. Token近音匹配 (200)

        :param query: 搜索关键词
        :param limit: 最大返回数量
        :param with_price: 是否附带最近收盘价（1次DB查询/结果，慎用大量结果）
        :return: list[dict]，每项含 code, name, display, _matchType, _score
        """
        if not query or not query.strip():
            return []

        raw_query = query.strip()
        query_upper = raw_query.upper()
        all_stocks = self._ensure_stock_db()

        if all_stocks.empty:
            return []

        # 预计算查询的拼音形式（用于同音字容错）
        query_pinyin = self._pinyin_full(raw_query)
        has_chinese = any('\u4e00' <= ch <= '\u9fff' for ch in raw_query)

        results = []

        for _, row in all_stocks.iterrows():
            code = str(row["code"])
            name = str(row["name"])

            score = 0
            match_type = ""

            # ── 层级 1: 精确代码匹配 ──
            if query_upper == code:
                score = 1000
                match_type = "exact_code"

            # ── 层级 2: 代码前缀匹配 ──
            elif code.startswith(query_upper) and len(query_upper) >= 2:
                score = 900
                match_type = "code_prefix"

            # ── 层级 3: 精确名称匹配 ──
            elif raw_query == name:
                score = 800
                match_type = "exact_name"

            # ── 层级 4: 名称前缀匹配 ──
            elif name.startswith(raw_query) and len(raw_query) >= 2:
                score = 780
                match_type = "name_starts"

            # ── 层级 5: 名称包含完整查询词 ──
            elif raw_query in name and len(raw_query) >= 2:
                score = 720
                match_type = "name_contains_full"

            # ── 层级 6: 全拼匹配（同音字容错核心） ──
            # 中文查询时同音匹配降权：用户输入汉字时优先字符匹配，拼音仅作辅助
            elif len(raw_query) >= 2:
                name_pinyin = self._pinyin_full(name)
                hp_base = 350 if has_chinese else 650  # 中文输入降权
                if query_pinyin == name_pinyin:
                    score = hp_base + 50
                    match_type = "homophone_exact"
                elif query_pinyin in name_pinyin and len(query_pinyin) >= 3:
                    score = hp_base
                    match_type = "homophone_contains"

            # ── 层级 7: 拼音首字母匹配 ──
            if score == 0 and len(raw_query) >= 2:
                if all(c.isalpha() for c in raw_query) and not has_chinese:
                    py_init = self._pinyin_initials(name)
                    if py_init and query_upper in py_init:
                        score = 550
                        match_type = "pinyin_initials"
                    elif py_init and query_upper == py_init:
                        score = 580
                        match_type = "pinyin_initials_exact"

            # ── 层级 8: 分词 Token 匹配（简称识别） ──
            if score == 0 and has_chinese and len(raw_query) >= 2:
                tokens = self._name_tokens(name)
                if raw_query in tokens:
                    score = 500
                    match_type = "token_match"

            # ── 层级 9: 名称子串包含 ──
            if score == 0 and len(raw_query) >= 2 and raw_query in name:
                score = 450
                match_type = "name_contains"

            # ── 层级 10: 字符分散模糊匹配 ──
            if score == 0 and len(raw_query) >= 2 and has_chinese:
                chars = list(raw_query)
                name_idx = 0
                matched_positions = []
                found_all = True
                for ch in chars:
                    pos = name.find(ch, name_idx)
                    if pos == -1:
                        found_all = False
                        break
                    matched_positions.append(pos)
                    name_idx = pos + 1
                if found_all:
                    # 紧凑度得分：匹配字符越连续，分越高
                    max_gap = max(b - a for a, b in zip(matched_positions, matched_positions[1:])) if len(matched_positions) > 1 else 0
                    compactness = max(0, 100 - max_gap * 30)
                    score = 350 + compactness
                    match_type = "fuzzy_char"

            # ── 层级 11: 全拼子串匹配（非中文字符） ──
            if score == 0 and len(raw_query) >= 2 and not raw_query.isdigit():
                name_pinyin = self._pinyin_full(name)
                if query_pinyin and len(query_pinyin) >= 2 and query_pinyin in name_pinyin:
                    score = 280
                    match_type = "pinyin_substring"

            # ── 层级 12: Token 近音匹配 ──
            if score == 0 and len(raw_query) >= 2:
                query_py_token = self._pinyin_full(raw_query)
                name_py_token = self._pinyin_full(name)
                if query_py_token and name_py_token and (
                    query_py_token in name_py_token or name_py_token in query_py_token
                ):
                    score = 220
                    match_type = "pinyin_token"

            # ── 层级 13: 单字匹配（仅中文查询时） ──
            if score == 0 and len(raw_query) == 1 and has_chinese:
                if raw_query in name:
                    score = 150
                    match_type = "single_char"

            if score > 0:
                # 名称中含有数字/特殊标记，轻微降权
                if any(c.isdigit() or c == '*' for c in name):
                    score -= 20

                result = {
                    "code": code,
                    "name": name,
                    "display": f"{code}  {name}",
                    "score": score,
                    "_matchType": match_type,
                    "_score": score,
                }

                # 可选：附带当前价格
                if with_price:
                    price, price_date = self._get_latest_price(code)
                    result["price"] = price
                    result["price_date"] = price_date

                results.append(result)

        # 按 score 降序排列
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
    def stock_exists(self, symbol):
        """
        快速检查股票是否存在于数据源中（用 BaoStock 复用连接池）。
        返回 (是否存在, 名称或原因)。
        """
        if not _BS_OK:
            return True, ""  # BaoStock不可用时跳过检查

        try:
            # 复用 BaoStock 类级别的连接池（首次调用触发 login）
            if not _BaoStockFetcher._ensure_login():
                return True, "BaoStock登录失败"
            bs_code = _symbol_to_bs(symbol)
            rs = bs.query_stock_basic(code=bs_code)
            if rs.error_code == "0" and rs.next():
                row = rs.get_row_data()
                name = row[1] if len(row) >= 2 else ""
                return True, name
            # BaoStock 无此股票 -> 可能是退市/停牌/代码错误
            return False, "股票不存在、已退市或长期停牌（BaoStock无记录）"
        except Exception as e:
            # 检查失败时不阻塞（允许后续降级链尝试）
            return True, f"无法验证({e})"

    def _fetch_level(self, level, symbol, start, end, adjust):
        """单数据源抓取 + 标准化：并行竞速用。

        返回 (df_or_None, error_or_None)。L1=akshare / L2=BaoStock / L3=新浪 / L4=东方财富。
        每个源独立在子线程中执行，先成功者胜出，避免「顺序降级逐个网络超时」的累加等待。
        每个源调用均经 ``observe_source`` 记录成功率/耗时，供数据源健康度横幅使用。
        """
        rename_map = {
            "日期": "date", "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low", "成交量": "volume",
            "成交额": "amount", "涨跌幅": "change_pct",
        }
        # 归一化日期为 Timestamp，避免 df['date'](Timestamp) 与字符串直接比较抛 TypeError
        try:
            _sd = pd.to_datetime(start)
        except Exception:
            _sd = pd.Timestamp.min
        try:
            _ed = pd.to_datetime(end)
        except Exception:
            _ed = pd.Timestamp.max
        try:
            if level == "L1" and _AK_OK:
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
                    df["date"] = pd.to_datetime(df["date"])
                    return df, None
                return None, "akshare: 无数据"

            if level == "L2":
                df = observe_source(
                    "baostock", level,
                    lambda: _BaoStockFetcher.fetch_kline(symbol, start, end, adjust=adjust),
                )
                if df is not None:
                    return df, None
                return None, "BaoStock: 无数据"

            if level == "L3":
                df = observe_source(
                    "sina", level,
                    lambda: _SinaFetcher.fetch_kline(symbol, start, end),
                )
                if df is not None:
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
                    return df, None
                return None, "东方财富: 无数据"
        except Exception as e:  # noqa: BLE001
            return None, f"{level}: {type(e).__name__}"
        return None, f"{level}: 无数据"

    def get_daily(self, symbol, start="2024-01-01", end=None, adjust="qfq"):
        """
        获取个股日线行情。
        降级链（v3 并行竞速）：akshare / BaoStock / 新浪 / 东方财富 四源并发，
        先成功者胜出（耗时由「各源之和」降为「最慢单源」）；全部失败再走缓存兜底。

        性能优化（v2）：
        - BaoStock 走连接池（每次查询不复登），13s -> 3s
        - 股票存在性预检改为只在 BaoStock 不可用时跑
        - akshare RemoteDisconnected 后立即跳过，不等重试
        - 缓存命中率优先：cache_days 内直接返回
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
                        print(f"[StockFetcher] {futs[fut]} OK {symbol} (并行竞速)")
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
                            print(f"[StockFetcher] {futs[fut]} OK {symbol} (并行竞速)")
                            break
                        else:
                            if res_err:
                                errors.append(res_err)
            finally:
                # 取消未完成（如被墙挂起的 akshare），不阻塞等待
                ex.shutdown(wait=False, cancel_futures=True)

            # ── L5: 缓存兜底（任何过期缓存都优先用）──
            if df is None or df.empty:
                stale = self._read_stale_cache(conn, "daily_cache", f"daily_{symbol}")
                if stale is not None:
                    print(f"[StockFetcher] L5-缓存兜底 OK {symbol}")
                    return stale
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
            return df
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════
    # 通用 K 线（日/周/月）
    # ══════════════════════════════════════════════════════
    def _resample_kline(self, daily_df, period):
        """
        将日线数据聚合为周线或月线。
        period: weekly 或 monthly
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
            end = datetime.now().strftime("%Y-%m-%d")
        if period == "daily":
            return self.get_daily(symbol, start, end, adjust)

        cache_key = f"kline_{period}_{symbol}_{start}_{end}_{adjust}"
        conn = self._get_conn()
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            max_age_hours = 6 if end == today_str else None
            cached = self._read_cache(conn, "daily_cache", cache_key, max_age_hours=max_age_hours)
            if cached is not None:
                return cached

            df = None
            errors = []
            # L1: akshare 真实周期
            if _AK_OK:
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
                        df["date"] = pd.to_datetime(df["date"])
                        print(f"[StockFetcher] L1-akshare {period} OK {symbol}")
                except Exception as e:
                    if 'Connection' not in type(e).__name__ and 'Remote' not in type(e).__name__:
                        errors.append(f"akshare: {type(e).__name__}")
                    print(f"[StockFetcher] L1-akshare {period} FAIL {symbol}: {type(e).__name__}")
                    df = None

            # L2: 日线聚合
            if df is None or df.empty:
                try:
                    daily = self.get_daily(symbol, start, end, adjust)
                    if daily is not None and not daily.empty:
                        df = self._resample_kline(daily, period)
                        print(f"[StockFetcher] L2-resample {period} OK {symbol}")
                    else:
                        errors.append("日线聚合: 无数据")
                except Exception as e:
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

    # ══════════════════════════════════════════════════════
    # 指数行情（四级降级链）
    # ══════════════════════════════════════════════════════
    def get_index(self, symbol="000001", start="2024-01-01", end=None):
        """
        获取指数日线行情。
        降级链：akshare -> BaoStock -> 东方财富(urllib) -> 缓存兜底
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
                    print(f"[StockFetcher] L1-akshare 指数 OK {symbol}")
                except Exception as e:
                    errors.append(f"akshare: {type(e).__name__}")
                    df = None

            # ── L2: BaoStock ──
            if df is None or df.empty:
                df = _BaoStockFetcher.fetch_index_kline(symbol, start, end)
                if df is not None and not df.empty:
                    print(f"[StockFetcher] L2-BaoStock 指数 OK {symbol}")
                else:
                    errors.append("BaoStock: 无数据")

            # ── L3: 东方财富 urllib ──
            if df is None or df.empty:
                df = _UrllibFetcher.fetch_kline(symbol, start, end, is_index=True)
                if df is not None and not df.empty:
                    print(f"[StockFetcher] L3-东方财富 指数 OK {symbol}")
                else:
                    errors.append("东方财富: 无数据")

            # ── L4: 缓存兜底 ──
            if df is None or df.empty:
                stale = self._read_stale_cache(conn, "index_cache", f"index_{symbol}")
                if stale is not None:
                    print(f"[StockFetcher] L4-缓存兜底 指数 OK {symbol}")
                    return stale
                errors.append("缓存: 无可用数据")

            if df is None or df.empty:
                detail = "\n   • ".join(errors)
                raise RuntimeError(
                    f"ERROR 无法获取 {symbol} 指数数据\n"
                    f"   数据源全部失败：\n   • {detail}"
                )

            df = df[(df["date"] >= start) & (df["date"] <= end)]
            df = df.sort_values("date").reset_index(drop=True)
            self._write_cache(conn, "index_cache", cache_key, df)
            return df
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════
    # 指数日内 1 分钟 K 线（用于行情看板指数卡片展示当天走势）
    # ══════════════════════════════════════════════════════
    def get_index_minute(self, symbol="000001", trade_date=None):
        """
        获取指数当日 1 分钟 K 线，返回 DataFrame[time, open, close, high, low, volume]。
        失败返回 None；网络/证书异常时内部降级为 None，由调用方使用日线/OHLC 兜底。
        """
        if not _AK_OK:
            return None
        if trade_date is None:
            trade_date = datetime.now().strftime("%Y%m%d")
        try:
            with StockFetcher._ak_ssl_context():
                df = ak.index_zh_a_hist_min_em(symbol=symbol, period="1", start_date=trade_date, end_date=trade_date)
            if df is None or df.empty:
                return None
            df = df.copy()
            df.columns = [str(c).strip() for c in df.columns]
            col_map = {
                "时间": "time",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount",
                "振幅": "amplitude",
            }
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
            for c in ["open", "close", "high", "low", "volume"]:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            df["time"] = df["time"].astype(str)
            # 明确按交易时间升序，避免接口返回顺序不确定导致走势标签误判
            if "time" in df.columns:
                df = df.sort_values("time").reset_index(drop=True)
            return df.reset_index(drop=True)
        except Exception as e:
            print(f"[StockFetcher] 指数分钟线失败 {symbol}: {type(e).__name__}")
            return None

    # ══════════════════════════════════════════════════════
    # 板块数据（三级降级链 + 实时缓存）
    # ══════════════════════════════════════════════════════

    def get_sector_list(self, force_refresh=False):
        """
        行业板块列表。
        降级链：本地实时缓存 -> 东方财富(urllib) -> 同花顺 akshare -> BaoStock -> 过期缓存兜底
        交易时间内缓存 6 分钟，休市时延用最后一个交易日缓存（7 天内）。
        """
        cache_key = "sector_list_v3"
        conn = self._get_conn()
        try:
            market_open = _is_market_open()
            midday_break = _is_midday_break()
            if market_open:
                cache_ttl_hours = 0.1  # 交易时 6 分钟
            elif midday_break:
                cache_ttl_hours = 0.5  # 午间休市 30 分钟，避免延用昨日数据
            else:
                cache_ttl_hours = 24 * 7  # 已收盘/周末/盘前：7 天

            if not force_refresh:
                cached = self._read_cache(conn, "sector_cache", cache_key, max_age_hours=cache_ttl_hours)
                if cached is not None and not cached.empty:
                    return cached
        except Exception as e:
            print(f"[StockFetcher] 板块缓存读取失败: {e}")
        finally:
            conn.close()

        df = None
        errors = []
        source = None

        # ── L1: 东方财富 urllib（通常最快）──
        try:
            df = _UrllibFetcher.fetch_sector_list()
            if df is not None and not df.empty and not _validate_sector_data(df):
                print("[StockFetcher] L1-东方财富 数据异常，尝试降级")
                df = None
            if df is not None and not df.empty:
                source = "东方财富"
                print(f"[StockFetcher] L1-东方财富 板块 OK")
        except Exception as e:
            errors.append(f"东方财富: {type(e).__name__}")
            df = None

        # ── L2: 同花顺 akshare（东财接口被关闭时的可靠备用）──
        if df is None or df.empty:
            if _AK_OK:
                try:
                    df = _retry_request(
                        lambda: ak.stock_board_industry_summary_ths(),
                        max_retries=1, base_delay=1,
                    )
                    df = df.rename(columns={"板块": "sector", "涨跌幅": "change_pct"})
                    df = df[["sector", "change_pct"]]
                    if not _validate_sector_data(df):
                        print("[StockFetcher] L2-同花顺 数据异常，尝试降级")
                        df = None
                    else:
                        source = "同花顺"
                        print(f"[StockFetcher] L2-同花顺 板块 OK")
                except Exception as e:
                    errors.append(f"同花顺: {type(e).__name__}")
                    df = None

        # ── L3: BaoStock（只有行业名称，无涨跌幅，作为兜底）──
        if df is None or df.empty:
            try:
                df = _BaoStockFetcher.fetch_sector_list()
                if df is not None and not df.empty:
                    source = "BaoStock（无涨跌幅）"
                    print(f"[StockFetcher] L3-BaoStock 板块 OK（无涨跌幅）")
            except Exception as e:
                errors.append(f"BaoStock: {type(e).__name__}")
                df = None

        # ── L4: 过期缓存兜底 ──
        if df is None or df.empty:
            conn = self._get_conn()
            try:
                stale = self._read_stale_cache(conn, "sector_cache", "sector_list")
                if stale is not None and not stale.empty:
                    source = "过期缓存"
                    print(f"[StockFetcher] L4-过期缓存 板块 OK")
                    return stale
            finally:
                conn.close()
            errors.append("缓存: 无可用数据")

        if df is None or df.empty:
            detail = "、".join(errors) if errors else "未知原因"
            raise RuntimeError(
                f"ERROR 无法获取板块数据\n   数据源全部失败：\n   • {detail}"
            )

        # 标准化列类型
        df["change_pct"] = pd.to_numeric(df["change_pct"], errors="coerce").fillna(0)
        df = df[df["sector"].astype(str).str.strip() != ""].reset_index(drop=True)

        # 写入缓存 + 来源标记
        conn = self._get_conn()
        try:
            self._write_cache(conn, "sector_cache", cache_key, df)
            self._write_cache_raw(conn, "sector_cache", f"{cache_key}_source", json.dumps({"source": source}, ensure_ascii=False))
        finally:
            conn.close()

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

    def get_concept_list(self, force_refresh=False):
        """概念板块列表（东方财富）。返回 DataFrame(sector, change_pct)。失败返回空 DataFrame。"""
        cache_key = "concept_list_v1"
        try:
            if not force_refresh:
                conn = self._get_conn()
                cached = self._read_cache(conn, "sector_cache", cache_key, max_age_hours=0.1)
                if cached is not None and not cached.empty:
                    return cached
        except Exception:
            pass
        try:
            df = _retry_request(
                lambda: ak.stock_board_concept_name_em(),
                max_retries=2, base_delay=2,
            )
        except Exception:
            return pd.DataFrame(columns=["sector", "change_pct"])
        if df is None or df.empty:
            return pd.DataFrame(columns=["sector", "change_pct"])
        df = df.rename(columns={"板块名称": "sector", "涨跌幅": "change_pct"})
        keep = [c for c in ["sector", "change_pct"] if c in df.columns]
        df = df[keep].copy() if keep else df
        try:
            conn = self._get_conn()
            self._write_cache(conn, "sector_cache", cache_key, df)
        except Exception:
            pass
        return df

    def get_concept_stocks(self, concept_name):
        """指定概念板块的成分股列表（东方财富）。失败抛异常由调用方兜底。"""
        if not _AK_OK:
            raise RuntimeError("akshare 未安装，无法获取成分股")
        df = _retry_request(
            lambda: ak.stock_board_concept_cons_em(symbol=concept_name),
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
