"""
资金流向 / 财报日历 数据层。

代理策略（#407 / #659）：akshare 走 requests，只认 HTTP_PROXY/HTTPS_PROXY 环境变量。
本模块在导入时统一处理「代理 + 证书校验」，保证取数可用；所有函数带 TTL 缓存，
并对失败做优雅降级。

- 显式配置 STOCKSIGNAL_PROXY -> 无条件使用该代理（部署机有代理时）。
- 否则探测默认本地代理 127.0.0.1:26561 是否可达：可达则用，不可达则清空遗留的
  本地代理变量、改走直连（避免把请求指向一个没监听的代理导致全挂）。
- 证书校验默认恢复（安全红线）；仅当 STOCKSIGNAL_SSL_BYPASS=1（本机代理做 TLS 拦截的开发环境）才临时关闭 requests 的 verify。

已验证可用接口（直连或代理下）：
- stock_fund_flow_industry       板块/行业资金流向
- stock_hsgt_fund_flow_summary_em 北向资金（沪股通/深股通/北向）
- stock_market_fund_flow         大盘主力/超大单/大单净流入（历史序列）
- stock_yjbb_em                  业绩报表（每股收益/营收/净利润/同比）
"""
import os
import socket
import time
import functools
from datetime import datetime, timedelta
from urllib.parse import urlparse
import threading

import logging

logger = logging.getLogger(__name__)

# 集中配置（代理 / 超时 / 测试密钥）统一从 modules.site_config 读取，避免散落硬编码
from modules.site_config import REQUEST_TIMEOUT, PROXY_DEFAULT
from modules.timeout_exec import run_with_timeout
from modules.fetch_parallel import fetch_many  # R78：共享有界线程池并发取数

# 别名：保持下方 _patch_requests_timeout 与下游模块的引用不变
_REQUEST_TIMEOUT = REQUEST_TIMEOUT


def _patch_requests_timeout():
    """给 requests 注入默认超时，避免 akshare 等库的网络调用无限挂起。幂等。

    双层兜底：
    - requests 层：给 Session.request 注入默认 timeout（覆盖 akshare 走 requests 的接口）。
    - socket 层：socket.setdefaulttimeout 覆盖 akshare 走 **urllib**（东方财富）的接口——
      这类调用不经过 requests，上面那层拦不住，上游/代理挂起时会无限阻塞（资金流向页
      就是典型受害者，表现为「卡住」）。socket 默认超时把「永久挂起」变成「≤N 秒失败」。
    """
    import requests
    if getattr(requests.Session.request, "_ss_timeout_patched", False):
        return
    _orig = requests.Session.request

    def _patched(self, *a, **k):
        k.setdefault("timeout", _REQUEST_TIMEOUT)
        return _orig(self, *a, **k)

    _patched._ss_timeout_patched = True
    requests.Session.request = _patched

    # socket 层兜底：仅当尚无更严格的全局默认超时时设置，避免覆盖用户显式配置
    cur = socket.getdefaulttimeout()
    if cur is None or cur > _REQUEST_TIMEOUT:
        try:
            socket.setdefaulttimeout(_REQUEST_TIMEOUT)
        except Exception:
            pass


_patch_requests_timeout()  # 导入即生效（瞬时、无网络）

import pandas as pd

from modules.format_helpers import format_amount

# 本机代理地址：默认 http://127.0.0.1:26561，可用环境变量 STOCKSIGNAL_PROXY 覆盖
# （#407 集中魔法值：换机器/换端口时不必改代码）。
_PROXY = PROXY_DEFAULT
_patch_done = False


def _proxy_reachable(proxy_url, timeout=2.0):
    """探测代理地址（host:port）是否可连通；不可达返回 False。"""
    try:
        parsed = urlparse(proxy_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception as e:
        logger.warning(f"[fundflow] 处理异常: {e}")
        return False


def _ensure_proxy_and_ssl():
    """统一处理「代理 + 证书校验」；幂等，仅执行一次。

    代理策略见模块 docstring：显式配置优先；否则探测默认本地代理可达性，
    不可达则清掉遗留的本地代理变量走直连。
    """
    global _patch_done
    if _patch_done:
        return

    explicit = os.environ.get("STOCKSIGNAL_PROXY")
    if explicit:
        _proxy = explicit
        _use_proxy = True
    elif _proxy_reachable(_PROXY):
        _proxy = _PROXY
        _use_proxy = True
    else:
        _proxy = None
        _use_proxy = False

    if _use_proxy:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            if not os.environ.get(key):
                os.environ[key] = _proxy
    else:
        # 走直连：清掉任何指向本地未监听代理（127.0.0.1/localhost:26561）的遗留变量
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            val = os.environ.get(key, "")
            if "127.0.0.1:26561" in val or "localhost:26561" in val:
                os.environ.pop(key, None)

    # 证书校验：默认恢复（安全红线）。
    # 仅当 STOCKSIGNAL_SSL_BYPASS=1（本机代理做 TLS 拦截的开发环境）才临时关闭。
    if os.environ.get("STOCKSIGNAL_SSL_BYPASS") == "1":
        import urllib3
        import requests
        urllib3.disable_warnings()
        _orig = requests.Session.request

        def _patched(self, *a, **k):
            k.setdefault("verify", False)
            return _orig(self, *a, **k)

        requests.Session.request = _patched
        logger.warning(
            "fundflow: SSL 校验已按 STOCKSIGNAL_SSL_BYPASS=1 临时关闭"
            "（仅用于本机代理 TLS 拦截环境）"
        )
    _patch_done = True


def _cache(ttl=300):
    def deco(fn):
        @functools.lru_cache(maxsize=32)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)
        wrapper._ttl = ttl
        return wrapper
    return deco


def _now_ts():
    return time.time()


# 简易 TTL 缓存：用 (函数名+参数) -> (timestamp, value)
_CACHE = {}
_CACHE_LOCK = threading.Lock()


def _cached(ttl, key, fn):
    """基于时间戳的轻量缓存，避免对同一昂贵 akshare 调用短时间内重复请求。

    惰性触发代理/SSL 设置：原实现在模块导入时即同步执行 _proxy_reachable 的
    socket 探测（默认本地代理 127.0.0.1:26561，timeout 2s），导致每个 import
    fundflow 的页面在加载时都要先等这次最多 2 秒的网络探测——这正是「几乎所有
    模块加载极慢」的隐藏根因之一。现改为在首次真实网络请求前惰性执行一次
    （_patch_done 幂等守卫），import 不再阻塞，页面非网络部分可即时渲染。

    R85 double-check：fn() 在锁**外**执行——此前 fn() 在锁内，一路慢速网络
    调用会串行化**所有**键的缓存访问（并发预取时严重放大等待）。现改为
    锁内快速读（未命中即释放），锁外执行 fn()，再锁内写回。同一 key 并发
    miss 会重复计算（可接受权衡，且 fn 有 _run_with_timeout 硬边界）。
    """
    _ensure_proxy_and_ssl()  # 惰性、幂等；仅首次网络请求前执行一次 socket 探测
    now = time.time()
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and (now - hit[0]) < ttl:
            return hit[1]
    # 锁外执行昂贵取数：不阻塞其他键的缓存访问
    val = fn()
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), val)
    return val


def _retry_with_backoff(max_retries=3, base_delay=1.0):
    """对 akshare 网络调用做指数退避重试，缓解偶发 RemoteDisconnected / Connection aborted。"""
    def deco(fn):
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    err_str = str(e).lower()
                    # 仅对网络层错误重试；业务错误立即抛出
                    if any(k in err_str for k in ("connection aborted", "remotedisconnected",
                                                   "connection reset", "timeout", "timed out")):
                        if attempt < max_retries - 1:
                            time.sleep(base_delay * (2 ** attempt))
                            continue
                    raise
            raise last_exc
        return wrapper
    return deco


def _to_wan_yi(x):
    """把金额(元)格式化为 亿/万 文本（委托给 format_amount，屏蔽 NaN/inf/None）。"""
    return format_amount(x)


# 兼容别名：实现已迁移到 modules.timeout_exec.run_with_timeout（进程级共享有界线程池，
# 底层网络超时 < 每调用硬边界，阻塞调用被传输层先唤醒、线程正常回池，从根上消除线程泄漏）。
# 保留此别名是为了不动 linear_trends / margin_trading 等下游 import。
_run_with_timeout = run_with_timeout


# ───────────────────────── 板块资金流向 ─────────────────────────
def get_industry_fund_flow():
    """行业/板块资金流向。返回 DataFrame(行业, 涨跌幅, 流入资金, 流出资金, 净额, 领涨股, 领涨股涨跌幅)。

    对网络层错误做指数退避重试；最终失败返回空 DataFrame，避免页面红错。
    """
    @_retry_with_backoff(max_retries=3, base_delay=1.0)
    def _fetch():
        import akshare as ak
        df = ak.stock_fund_flow_industry()
        if df is None or df.empty:
            return pd.DataFrame()
        rename = {
            "行业": "行业", "行业-涨跌幅": "涨跌幅", "流入资金": "流入资金",
            "流出资金": "流出资金", "净额": "净额", "领涨股": "领涨股",
            "领涨股-涨跌幅": "领涨股涨跌幅",
        }
        df = df.rename(columns=rename)
        keep = [c for c in ["行业", "涨跌幅", "流入资金", "流出资金", "净额", "领涨股", "领涨股涨跌幅"] if c in df.columns]
        return df[keep].copy()

    def _fn():
        try:
            return _fetch()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"get_industry_fund_flow 最终失败：{e}")
            return pd.DataFrame()

    # 强边界：东方财富 urllib 路径可能无限挂起，12s 硬超时后返回空 DF，由 UI 兜底
    def _safe():
        res = _run_with_timeout(_fn, 12)
        return res if res is not None else pd.DataFrame()
    return _cached(300, "industry_ff", _safe)


# ───────────────────────── 北向资金（历史真实值兜底） ─────────────────────────
def get_northbound_history():
    """北向资金历史序列（东方财富 stock_hsgt_hist_em）。

    交易所自 2024-08-16 起停止披露实时「北向资金净买额」，summary 接口长期为 0。
    但历史序列（当日成交净买额 / 历史累计净买额）在该停披露日前仍有真实数值，
    可作为「最近一次真实披露」与「历史累计净买入」展示，避免页面全空。

    返回 dict: last_net_buy(元), last_net_buy_date(str), cumulative(元), cumulative_date(str)。
    取各列最后一个非 NaN 值（动态，不硬编码日期）。
    """
    def _fn():
        import akshare as ak
        try:
            df = ak.stock_hsgt_hist_em(symbol="北向资金")
        except Exception as e:
            logger.warning(f"[fundflow] 处理异常: {e}")
            return {}
        if df is None or df.empty:
            return {}
        res = {}
        try:
            if "当日成交净买额" in df.columns:
                s = pd.to_numeric(df["当日成交净买额"], errors="coerce")
                idx = s.last_valid_index()
                if idx is not None:
                    res["last_net_buy"] = float(s[idx])
                    d = df.loc[idx, "日期"]
                    res["last_net_buy_date"] = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)
        except Exception as e:
            logger.warning(f"[fundflow] 处理异常: {e}")
            pass
        try:
            if "历史累计净买额" in df.columns:
                s2 = pd.to_numeric(df["历史累计净买额"], errors="coerce")
                idx2 = s2.last_valid_index()
                if idx2 is not None:
                    res["cumulative"] = float(s2[idx2])
                    d2 = df.loc[idx2, "日期"]
                    res["cumulative_date"] = d2.strftime("%Y-%m-%d") if hasattr(d2, "strftime") else str(d2)
        except Exception as e:
            logger.warning(f"[fundflow] 处理异常: {e}")
            pass
        return res
    return _cached(1800, "northbound_hist", _fn)


# ───────────────────────── 北向资金 ─────────────────────────
def get_northbound_fund_flow():
    """北向资金（沪股通/深股通/北向）。

    返回 dict: boards(list), trade_date, total_inflow, sh_inflow, sz_inflow,
               northbound_net_available(bool),
               last_net_buy, last_net_buy_date, cumulative, cumulative_date。

    说明：东方财富自 2024-08 起停止披露「北向资金净买额」实时数据，
    stock_hsgt_fund_flow_summary_em() 的 沪股通/深股通 北向 行 成交净买额/资金净流入
    长期为 0。因此当实时净额确为 0/NaN（数据源未提供）时，
    返回 None 并附带历史真实值（last_net_buy / cumulative），
    由 UI 明确区分「实时未披露」与「最近一次真实披露」，避免空白或误导性的 0。
    板块涨跌家数 / 指数涨跌幅 / 港股通南向 仍为实时真实数据。
    """
    @_retry_with_backoff(max_retries=3, base_delay=1.0)
    def _fetch_summary():
        import akshare as ak
        return ak.stock_hsgt_fund_flow_summary_em()

    def _fn():
        import akshare as ak
        try:
            df = _fetch_summary()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"get_northbound_fund_flow 初始接口最终失败：{e}")
            return {"boards": [], "trade_date": None, "total_inflow": None,
                    "sh_inflow": None, "sz_inflow": None,
                    "northbound_net_available": False}
        if df is None or df.empty:
            return {"boards": [], "trade_date": None, "total_inflow": None,
                    "sh_inflow": None, "sz_inflow": None,
                    "northbound_net_available": False}
        boards = []
        sh = sz = total = None
        for _, r in df.iterrows():
            rec = {
                "板块": r.get("板块"),
                "资金方向": r.get("资金方向"),
                "成交净买额": r.get("成交净买额"),
                "资金净流入": r.get("资金净流入"),
                "上涨数": r.get("上涨数"),
                "下跌数": r.get("下跌数"),
                "指数涨跌幅": r.get("指数涨跌幅"),
            }
            boards.append(rec)
            try:
                val = float(r.get("资金净流入") or 0)
            except Exception as e:
                logger.warning(f"[fundflow] 处理异常: {e}")
                val = 0.0
            if str(r.get("板块")) == "沪股通":
                sh = val
            elif str(r.get("板块")) == "深股通":
                sz = val
            elif str(r.get("资金方向")) == "北向":
                total = val
        # 实时分钟级净额作为补充来源（若汇总为 0/NaN 时尝试）
        if (sh in (0.0, None)) or (sz in (0.0, None)) or (total in (0.0, None)):
            try:
                fm = ak.stock_hsgt_fund_min_em(symbol="北向")
                fm["沪股通"] = pd.to_numeric(fm["沪股通"], errors="coerce")
                fm["深股通"] = pd.to_numeric(fm["深股通"], errors="coerce")
                fm["北向资金"] = pd.to_numeric(fm["北向资金"], errors="coerce")
                valid = fm.dropna(subset=["沪股通", "深股通", "北向资金"], how="all")
                if not valid.empty:
                    last = valid.iloc[-1]
                    if sh in (0.0, None):
                        sh = float(last["沪股通"])
                    if sz in (0.0, None):
                        sz = float(last["深股通"])
                    if total in (0.0, None):
                        total = float(last["北向资金"])
            except Exception as e:
                logger.warning(f"[fundflow] 处理异常: {e}")
                pass
        if total in (0.0, None) and sh not in (0.0, None) and sz not in (0.0, None):
            total = sh + sz
        td = None
        try:
            td = df.iloc[0].get("交易日")
            td = td.strftime("%Y-%m-%d") if hasattr(td, "strftime") else str(td)
        except Exception as e:
            logger.warning(f"[fundflow] 处理异常: {e}")
            td = None
        # 净额是否真实可用：三个通道都为 0/None 视为数据源未提供
        available = not ((sh in (0.0, None)) and (sz in (0.0, None)) and (total in (0.0, None)))
        if not available:
            sh = sz = total = None
        # 历史真实值兜底（交易所 2024-08-16 后停止披露实时净买额，但历史序列仍有真实值）
        hist = {}
        try:
            hist = get_northbound_history() or {}
        except Exception as e:
            logger.warning(f"[fundflow] 处理异常: {e}")
            hist = {}
        return {"boards": boards, "trade_date": td, "total_inflow": total,
                "sh_inflow": sh, "sz_inflow": sz,
                "northbound_net_available": available,
                "last_net_buy": hist.get("last_net_buy"),
                "last_net_buy_date": hist.get("last_net_buy_date"),
                "cumulative": hist.get("cumulative"),
                "cumulative_date": hist.get("cumulative_date")}

    _EMPTY = {"boards": [], "trade_date": None, "total_inflow": None,
              "sh_inflow": None, "sz_inflow": None,
              "northbound_net_available": False}
    # 强边界：东方财富 urllib 路径可能无限挂起，12s 硬超时后返回空结构，由 UI 兜底
    def _safe():
        res = _run_with_timeout(_fn, 12)
        return res if res is not None else _EMPTY
    return _cached(300, "northbound_ff", _safe)


# ───────────────────────── 大盘资金流向 ─────────────────────────
def get_market_fund_flow(days=30):
    """大盘主力/超大单/大单净流入历史序列。返回 DataFrame(日期, 上证-涨跌幅, 主力净流入-净额, 超大单净流入-净额, 大单净流入-净额)。

    对 akshare 做指数退避重试，缓解偶发 RemoteDisconnected / Connection aborted。
    若最终仍失败则返回空 DataFrame，由页面展示兜底提示而非报错。
    """
    @_retry_with_backoff(max_retries=3, base_delay=1.0)
    def _fetch():
        import akshare as ak
        df = ak.stock_market_fund_flow()
        if df is None or df.empty:
            return pd.DataFrame()
        keep = [c for c in ["日期", "上证-涨跌幅", "主力净流入-净额", "主力净流入-净占比",
                            "超大单净流入-净额", "大单净流入-净额", "中单净流入-净额"] if c in df.columns]
        df = df[keep].copy()
        # 仅保留最近 days 天
        if "日期" in df.columns and len(df) > days:
            df = df.tail(days).reset_index(drop=True)
        return df

    def _fn():
        try:
            return _fetch()
        except Exception as e:
            # 网络最终失败：记录日志并返回空 DataFrame，避免页面红错
            import logging
            logging.getLogger(__name__).warning(f"get_market_fund_flow 最终失败：{e}")
            return pd.DataFrame()

    # 强边界：东方财富 urllib 路径可能无限挂起，12s 硬超时后返回空 DF，由 UI 兜底
    def _safe():
        res = _run_with_timeout(_fn, 12)
        return res if res is not None else pd.DataFrame()
    return _cached(600, f"market_ff_{days}", _safe)


# ───────────────────────── 个股资金流向（真实优先 + 量价估算兜底） ─────────────────────────
def get_individual_fund_flow(code, use_estimate_fallback=True, timeout=12.0):
    """个股资金流向。

    优先尝试 akshare 真实接口（stock_fund_flow_individual / stock_main_fund_flow），
    失败则用日线量价模型估算主力净流入（标注 估算）。
    返回 dict: {source, main_net(元), main_net_pct, big_net, super_net, latest_date}

    强边界：整体用 _run_with_timeout 包 timeout 硬超时（默认 12s，与全局
    CALL_TIMEOUT_CAP 一致；底层网络超时 10s 恒小于边界，线程回池不泄漏）。
    akshare 个股接口在本机代理下常挂起（底层 requests 不设 timeout），若无此
    边界会导致调用方（盯盘页并行抓全自选股）一直转圈「卡住」。超时/异常一律
    返回 source='none'，由 UI 优雅降级。

    R87：入口显式 _ensure_proxy_and_ssl()——本函数不走 _cached（由页面
    st.cache_data 包裹），此前若用户只进个股资金流页、从未触发其他预取，
    首次 akshare 请求会因代理/SSL 未设置而失败。
    """
    _ensure_proxy_and_ssl()  # 惰性、幂等；仅首次网络请求前执行一次 socket 探测
    def _compute():
        real = _real(code)
        if real is not None:
            return real
        if use_estimate_fallback:
            return _estimate_individual_fund_flow(code)
        return {"source": "none", "main_net": None, "main_net_pct": None,
                "big_net": None, "super_net": None, "latest_date": None}

    res = _run_with_timeout(_compute, timeout)
    if res is None:
        # 超时或异常：返回 none 占位，避免调用方死等
        return {"source": "none", "main_net": None, "main_net_pct": None,
                "big_net": None, "super_net": None, "latest_date": None}
    return res


def _real(code):
    import akshare as ak
    # 注意：stock_fund_flow_individual / stock_main_fund_flow 是「全市场排名」接口，
    # 传入个股代码会返回错误数据，不能用于个股。真正的个股接口是
    # stock_individual_fund_flow(stock, market)，但它在本机代理下常返回 None，
    # 失败时由下方量价估算兜底。
    code6 = str(code).zfill(6)
    market = "sh" if code6.startswith(("6", "9")) else "sz"
    try:
        df = ak.stock_individual_fund_flow(stock=code6, market=market)
        if df is not None and not df.empty:
            return _normalize_individual_df(df)
    except Exception as e:
        logger.warning(f"[fundflow] 处理异常: {e}")
        pass
    return None


def _normalize_individual_df(df):
    """把 akshare 个股资金流 df 规范成统一 dict。"""
    # 取最新一行
    row = df.iloc[-1]
    # 常见列名
    def _g(*names):
        for n in names:
            if n in df.columns:
                return row.get(n)
        return None
    main = _g("主力净流入-净额", "主力净流入", "main_net")
    big = _g("大单净流入-净额", "大单净流入")
    super_ = _g("超大单净流入-净额", "超大单净流入")
    pct = _g("主力净流入-净占比", "主力净流入-净占比")
    date = _g("日期")
    try:
        date = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)
    except Exception as e:
        logger.warning(f"[fundflow] 处理异常: {e}")
        date = None
    return {
        "source": "akshare",
        "main_net": float(main) if main not in (None, "") else None,
        "main_net_pct": float(pct) if pct not in (None, "") else None,
        "big_net": float(big) if big not in (None, "") else None,
        "super_net": float(super_) if super_ not in (None, "") else None,
        "latest_date": date,
    }


def _estimate_individual_fund_flow(code):
    """量价模型估算主力净流入（仅作离线兜底，明确标注 估算）。

    估算模式下无法拆出真实超大单/大单，但为了不留下空白卡片，
    采用经验拆分：超大单≈35%、大单≈65%（机构与大单合计），与 main_net 同正负号，
    并在返回中标注 source='estimate'，由 UI 明确提示这是估算值。
    """
    try:
        from .fetcher import StockFetcher
        f = StockFetcher()
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
        df = f.get_daily(code, start=start, end=end)
        if df is None or df.empty or len(df) < 2:
            return {"source": "none", "main_net": None, "main_net_pct": None,
                    "big_net": None, "super_net": None, "latest_date": None}
        # 归一化列
        df = df.copy()
        colmap = {}
        for c in df.columns:
            cl = str(c)
            if cl in ("date", "日期"):
                colmap[c] = "date"
            elif cl in ("open", "开盘"):
                colmap[c] = "open"
            elif cl in ("high", "最高"):
                colmap[c] = "high"
            elif cl in ("low", "最低"):
                colmap[c] = "low"
            elif cl in ("close", "收盘", "收盘价"):
                colmap[c] = "close"
            elif cl in ("volume", "成交量"):
                colmap[c] = "volume"
        df = df.rename(columns=colmap)
        if not all(k in df.columns for k in ("open", "high", "low", "close", "volume")):
            return {"source": "none", "main_net": None, "main_net_pct": None,
                    "big_net": None, "super_net": None, "latest_date": None}
        df = df.tail(20)
        total_mf = 0.0
        for _, r in df.iterrows():
            high, low, close, vol = r["high"], r["low"], r["close"], r["volume"]
            if high == low:
                continue
            vwap = (high + low + close) / 3.0
            # Chaikin 风格单日资金流（close 靠 high 为正）
            mf = ((close - low) - (high - close)) / (high - low) * vol * vwap
            total_mf += mf
        latest = df.iloc[-1]["date"]
        try:
            latest = latest.strftime("%Y-%m-%d") if hasattr(latest, "strftime") else str(latest)
        except Exception as e:
            logger.warning(f"[fundflow] 处理异常: {e}")
            latest = str(latest)
        # 经验拆分：保持与主力净流入同号，避免 blank 卡片
        super_est = round(total_mf * 0.35, 2) if total_mf != 0 else None
        big_est = round(total_mf * 0.65, 2) if total_mf != 0 else None
        return {
            "source": "estimate",
            "main_net": round(total_mf, 2),
            "main_net_pct": None,
            "big_net": big_est,
            "super_net": super_est,
            "latest_date": latest,
        }
    except Exception as e:
        logger.warning(f"[fundflow] 处理异常: {e}")
        return {"source": "none", "main_net": None, "main_net_pct": None,
                "big_net": None, "super_net": None, "latest_date": None}


# ───────────────────────── 财报 / 业绩 ─────────────────────────
def get_earnings_report(period="20260331"):
    """业绩报表。period 形如 20260331（报告期，如 一季报=0331）。返回 DataFrame。"""
    def _fn():
        import akshare as ak
        df = ak.stock_yjbb_em(date=period)
        if df is None or df.empty:
            return pd.DataFrame()
        keep = [c for c in ["序号", "股票代码", "股票简称", "每股收益", "营业总收入-营业总收入",
                            "营业总收入-同比增长", "净利润-净利润", "净利润-同比增长",
                            "净利润-季度环比增长", "每股净资产", "净资产收益率", "披露日期", "上市时间"] if c in df.columns]
        rename = {
            "股票代码": "代码", "股票简称": "名称", "每股收益": "每股收益",
            "营业总收入-营业总收入": "营业总收入", "营业总收入-同比增长": "营收同比%",
            "净利润-净利润": "净利润", "净利润-同比增长": "净利润同比%",
            "净利润-季度环比增长": "净利润环比%", "每股净资产": "每股净资产",
            "净资产收益率": "ROE%", "披露日期": "披露时间", "上市时间": "上市时间",
        }
        df = df[keep].rename(columns=rename)
        return df
    return _cached(1800, f"yjbb_{period}", _fn)


def get_earnings_forecast(period="20260331"):
    """业绩预告（best-effort，接口不稳定时返回空 DataFrame）。"""
    def _fn():
        import akshare as ak
        try:
            df = ak.stock_yjyg_em(date=period)
            if df is None or df.empty:
                return pd.DataFrame()
            return df
        except Exception as e:
            logger.warning(f"[fundflow] 处理异常: {e}")
            return pd.DataFrame()
    return _cached(1800, f"yjyg_{period}", _fn)


def get_disclosure_calendar(market="沪市", period="2025年报"):
    """财报披露日历（best-effort）。返回 DataFrame(股票代码, 股票简称, 报告期, 披露时间, 披露状态, ...)。

    说明：akshare 的 stock_report_disclosure 目前仅支持年报，季报/中报会 KeyError；
    本函数对季报参数做 best-effort 映射到同一年年报，并把不支持的“京市”回退为“沪深京”。
    """
    import re as _re

    # 京市不是 stock_report_disclosure 支持的 market 参数，回退到沪深京
    if market == "京市":
        market = "沪深京"

    # 季报/中报映射到同一年年报（接口仅支持年报披露日历）
    if "季报" in period or "中报" in period:
        m = _re.search(r"(\d{4})年?([一二三四1234])季[报告]", period)
        if m:
            period = f"{m.group(1)}年报"
        elif "中报" in period:
            m = _re.search(r"(\d{4})年?中报", period)
            if m:
                period = f"{m.group(1)}年报"

    def _fn():
        import akshare as ak
        try:
            df = ak.stock_report_disclosure(market=market, period=period)
            if df is None or df.empty:
                return pd.DataFrame()
            # 统一披露日期列名为「披露时间」
            for src, dst in (("预约披露日期", "披露时间"), ("披露日期", "披露时间"),
                             ("实际披露日期", "披露时间"), ("披露时间", "披露时间")):
                if src in df.columns and dst not in df.columns:
                    df = df.rename(columns={src: dst})
                    break
            return df
        except Exception as e:
            logger.warning(f"[fundflow] 处理异常: {e}")
            return pd.DataFrame()
    return _cached(1800, f"disclosure_{market}_{period}", _fn)


def clear_fundflow_cache():
    """清空缓存（调试用）。"""
    with _CACHE_LOCK:
        _CACHE.clear()


# ───────────────────────── 启动预热 / 并行快照（性能加速） ─────────────────────────
def get_market_wide_snapshot():
    """并行预取行业 / 北向 / 大盘三类全市场资金流，并填充各自 getter 的缓存。

    首次调用并行拉取（约 2s），缓存命中时近乎瞬时返回。
    返回 dict: {industry, northbound, market}（各为 getter 的原始返回值）。
    用于资金流向页首屏冷启动加速：一次并行替代三次串行。
    R78 改造：原每次调用新建 ThreadPoolExecutor(max_workers=3)（线程创建/销毁
    开销 + 无硬边界），改为共享有界线程池 fetch_many（信号量限流 + 整批硬边界，
    超时/异常项自动置 None，与页面其他并发取数共用同一池）。
    """
    res = fetch_many(
        [
            ("industry", get_industry_fund_flow),
            ("northbound", get_northbound_fund_flow),
            ("market", lambda: get_market_fund_flow(30)),
        ],
        max_workers=3,
        # timeout 不传：用全局 CALL_TIMEOUT_CAP（12s），与单取数硬边界一致；
        # 底层网络超时(10s)恒小于边界，线程回池不泄漏。
    )
    return {
        "industry": res.get("industry"),
        "northbound": res.get("northbound"),
        "market": res.get("market"),
    }


_warm_started = False


def warm_fundflow_caches():
    """应用启动时于后台守护线程预取全市场资金流，避免首个页面访问冷启动。

    幂等：仅执行一次。在 app.py 顶部 require_auth() 之后非阻塞调用即可。
    """
    global _warm_started
    if _warm_started:
        return
    _warm_started = True
    import threading

    def _job():
        try:
            get_market_wide_snapshot()
        except Exception as e:
            logger.warning(f"[fundflow] 处理异常: {e}")
            pass

    threading.Thread(target=_job, daemon=True).start()