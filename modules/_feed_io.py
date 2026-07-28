"""底层数据采集 I/O 层（从 fetcher.py 抽离，P2-1 降耦）。

包含：带重试的 urllib 取数、源可观测性埋点、symbol 转换、
三级源抓取类（BaoStock / 新浪 / 东方财富 urllib）。
与 fetcher.StockFetcher 编排层解耦，公开名由 fetcher 重新导出以保持兼容。
"""
import io
import json
import os
import time
import logging as _logging
import urllib.request
import urllib.error
import urllib.parse
import contextlib
import socket  # 捕获瞬时网络错误（超时/连接重置/DNS）做重试兜底
from datetime import datetime, timedelta
import concurrent.futures as _cf

def _safe_urlopen(req, timeout, retries=2, backoff=0.5):
    """带重试的 urllib 取数（瞬时故障兜底，加法式增强）。

    对超时 / 连接重置 / DNS 失败等瞬时网络错误自动重试，避免单点抖动直接命中
    上层 fallback 链导致数据缺失；HTTP 业务响应（4xx/5xx）不重试，立即交给调用方
    的 except 兜底（返回 None 并由降级链处理）。返回可读的响应对象，调用约定与
    ``urllib.request.urlopen`` 完全一致，因此所有调用点只改函数名、行为不变。
    """
    last_exc = None
    for attempt in range(retries + 1):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError:
            # 业务层响应（401/403/404/5xx 等），不重试，交给调用方按失败处理
            raise
        except (urllib.error.URLError, socket.timeout, TimeoutError,
                ConnectionError, OSError) as e:
            last_exc = e
            if attempt < retries:
                logger.warning(
                    f"[fetcher] urlopen 瞬时失败(第{attempt + 1}次)，{backoff * (attempt + 1):.1f}s 后重试: {e}"
                )
                time.sleep(backoff * (attempt + 1))
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise urllib.error.URLError("urlopen 未知失败")


# ──────────────────────────────────────────────────────────
# 模块日志（#403）：数据源诊断统一走 logger，同时落盘 logs/fetcher.log。
# 历史上这些诊断只 print 到 stdout，而生产环境经 pythonw.exe 后台启动，
# stdout 无处可见 → 数据源接口一变、失败被“静默吞掉”难以排查。
# 这里保留控制台输出（前台调试行为不变），并额外写入日志文件以便追溯。
# ──────────────────────────────────────────────────────────
logger = _logging.getLogger("stocksignal.fetcher")
if not logger.handlers:
    _sh = _logging.StreamHandler()
    _sh.setFormatter(_logging.Formatter("%(message)s"))
    logger.addHandler(_sh)
    try:
        _LOG_DIR = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"
        )
        os.makedirs(_LOG_DIR, exist_ok=True)
        _fh = _logging.FileHandler(
            os.path.join(_LOG_DIR, "fetcher.log"), encoding="utf-8"
        )
        _fh.setFormatter(_logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(_fh)
    except Exception as e:
        logger.warning(f"[fetcher] 处理异常: {e}")
        pass
    logger.setLevel(_logging.INFO)
    logger.propagate = False

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


def _is_bs_available():
    """读取 BaoStock 可用性开关的权威来源（modules.fetcher._BS_OK）。

    开关定义在 fetcher 模块并重新导出，测试通过 ``monkeypatch.setattr`` 覆盖
    ``fetcher._BS_OK`` 来模拟“未安装”场景；此处延迟读取 fetcher 模块，保证
    monkeypatch 生效（避免 re-export 值拷贝导致覆盖无效）。
    """
    try:
        import modules.fetcher as _fetcher_mod
        return bool(getattr(_fetcher_mod, "_BS_OK", True))
    except Exception:
        return True


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
        # 进程内缓存 TTL（秒）。#406：统一进程缓存的过期策略，避免长驻进程数据陈旧
        "fundamentals_seconds": 21600,  # 基本面（PE/市值/行业）：6 小时（日频）
        "biz_seconds": 604800,          # 核心业务/主营构成：7 天（季频，变动慢）
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
    logger.debug("[OBS] " + json.dumps(rec, ensure_ascii=False))


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
        logger.info(f"[StockFetcher] 数据校验警告: {total} 个板块全部{'上涨' if up == total else '下跌'}，疑似数据源异常")
        return False

    # 3. 检查是否全为零（休市/接口返回空数据时的兜底不应展示全零涨跌）
    if up == 0 and down == 0:
        logger.info("[StockFetcher] 数据校验警告: 所有板块涨跌幅均为 0，疑似空数据或非交易时段缓存")
        return False

    # 2. 检查是否存在绝对值过大的异常值（正常板块日涨跌幅应小于 20%）
    if s.abs().max() > 20:
        logger.info(f"[StockFetcher] 数据校验警告: 最大涨跌幅 {s.abs().max():.2f}% 超出合理范围")
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
        except Exception as e:
            logger.warning(f"[fetcher] 处理异常: {e}")
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
        if not _is_bs_available():
            return False
        if cls._login_done:
            return True
        lg = bs.login()
        if lg.error_code == "0":
            cls._login_done = True
            return True
        logger.info(f"[BaoStockFetcher] 登录失败: {lg.error_msg}")
        return False

    @classmethod
    def _ensure_logout(cls):
        """程序退出/出错时调用。重置 _login_done 让下次重新登录。"""
        if cls._login_done:
            try:
                bs.logout()
            except Exception as e:
                logger.warning(f"[fetcher] 处理异常: {e}")
                pass
            cls._login_done = False

    @classmethod
    def fetch_kline(cls, symbol, start_date, end_date, adjust="qfq"):
        """
        获取个股/指数日 K 线。
        adjust: qfq=前复权(2), hfq=后复权(1), none=不复权(3)
        返回 DataFrame 或 None。
        """
        if not _is_bs_available():
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
                logger.info(f"[BaoStockFetcher] 空结果 ({bs_code})")
                return None

            df = pd.DataFrame(rows, columns=rs.fields)
            df["date"] = pd.to_datetime(df["date"])
            numeric_cols = ["open", "high", "low", "close", "volume", "amount"]
            for c in numeric_cols:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            df["change_pct"] = df["close"].pct_change() * 100
            logger.debug(f"[BaoStockFetcher] 成功! {bs_code} -> {len(df)} 行")
            return df
        except Exception as e:
            logger.warning(f"[BaoStockFetcher] 异常 ({bs_code}): {type(e).__name__}: {e}")
            # 异常时也不要 logout，下次复用即可
            return None

    @classmethod
    def fetch_index_kline(cls, index_symbol, start_date, end_date):
        """
        获取指数 K 线。
        index_symbol: 000001(上证), 399001(深证), 399006(创业板) 等
        """
        if not _is_bs_available():
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
                logger.info(f"[BaoStockFetcher] 指数查询失败 ({bs_code}): {rs.error_msg}")
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
            logger.debug(f"[BaoStockFetcher] 指数成功! {bs_code} -> {len(df)} 行")
            return df
        except Exception as e:
            logger.info(f"[BaoStockFetcher] 指数异常 ({bs_code}): {type(e).__name__}: {e}")
            return None

    @classmethod
    def fetch_sector_list(cls):
        """
        获取行业板块列表（申万一级行业）。
        返回 DataFrame(sector, change_pct) 或 None。
        """
        if not _is_bs_available():
            return None

        try:
            if not cls._ensure_login():
                return None

            rs = bs.query_stock_industry()
            if rs.error_code != "0":
                logger.info("[BaoStockFetcher] 板块查询失败")
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
            logger.debug(f"[BaoStockFetcher] 板块成功! {len(sectors)} 个行业")
            return sectors[["sector", "change_pct"]]
        except Exception as e:
            logger.info(f"[BaoStockFetcher] 板块异常: {type(e).__name__}: {e}")
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
            with _safe_urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            logger.info(f"[SinaFetcher] 请求失败 ({sina_code}): {type(e).__name__}: {e}")
            return None

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.info(f"[SinaFetcher] JSON 解析失败 ({sina_code}): {e}")
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
        logger.debug(f"[SinaFetcher] 成功! {sina_code} -> {len(df)} 行")
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
            with _safe_urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.info(f"[UrllibFetcher] K线失败 ({symbol}): {type(e).__name__}: {e}")
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
            with _safe_urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.info(f"[UrllibFetcher] 板块失败 ({fs}): {e}")
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
                with _safe_urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                logger.info(f"[UrllibFetcher] 板块失败 ({fs} p{pn}): {e}")
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
            with _safe_urlopen(req, timeout=12) as resp:
                d = json.loads(resp.read().decode("utf-8")).get("data") or {}
        except Exception as e:  # noqa: BLE001
            logger.info(f"[UrllibFetcher] 基本面失败 ({symbol}): {type(e).__name__}: {e}")
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


