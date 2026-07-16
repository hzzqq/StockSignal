"""
资金流向 / 财报日历 数据层。

环境约束（关键）：本机访问东方财富 / 同花顺等数据源需经本地代理
(127.0.0.1:26561) 且关闭证书校验。akshare 走 requests，只认 HTTP_PROXY/HTTPS_PROXY
环境变量而不认系统 WinHTTP 代理，因此本模块在导入时确保代理环境变量 + 全局关闭
requests 证书校验，保证取数可用。所有函数带 TTL 缓存，并对失败做优雅降级。

已验证可用接口（本机代理下）：
- stock_fund_flow_industry       板块/行业资金流向
- stock_hsgt_fund_flow_summary_em 北向资金（沪股通/深股通/北向）
- stock_market_fund_flow         大盘主力/超大单/大单净流入（历史序列）
- stock_yjbb_em                  业绩报表（每股收益/营收/净利润/同比）
"""
import os
import time
import functools
from datetime import datetime, timedelta

import pandas as pd

_PROXY = "http://127.0.0.1:26561"
_patch_done = False


def _ensure_proxy_and_ssl():
    """确保 akshare 能经本地代理访问数据源；幂等，仅执行一次。"""
    global _patch_done
    if _patch_done:
        return
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        if not os.environ.get(key):
            os.environ[key] = _PROXY
    import urllib3
    import requests
    urllib3.disable_warnings()
    _orig = requests.Session.request

    def _patched(self, *a, **k):
        k.setdefault("verify", False)
        return _orig(self, *a, **k)

    requests.Session.request = _patched
    _patch_done = True


_ensure_proxy_and_ssl()


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


def _cached(ttl, key, fn):
    """基于时间戳的轻量缓存，避免对同一昂贵 akshare 调用短时间内重复请求。"""
    now = time.time()
    hit = _CACHE.get(key)
    if hit and (now - hit[0]) < ttl:
        return hit[1]
    val = fn()
    _CACHE[key] = (now, val)
    return val


def _to_wan_yi(x):
    """把金额(元)格式化为 亿/万 文本。"""
    try:
        x = float(x)
    except Exception:
        return "—"
    if abs(x) >= 1e8:
        return f"{x/1e8:.2f}亿"
    if abs(x) >= 1e4:
        return f"{x/1e4:.1f}万"
    return f"{x:.0f}"


# ───────────────────────── 板块资金流向 ─────────────────────────
def get_industry_fund_flow():
    """行业/板块资金流向。返回 DataFrame(行业, 涨跌幅, 流入资金, 流出资金, 净额, 领涨股, 领涨股涨跌幅)。"""
    def _fn():
        import akshare as ak
        df = ak.stock_fund_flow_industry()
        if df is None or df.empty:
            return pd.DataFrame()
        cols = ["行业", "行业-涨跌幅", "流入资金", "流出资金", "净额", "领涨股", "领涨股-涨跌幅"]
        rename = {
            "行业": "行业", "行业-涨跌幅": "涨跌幅", "流入资金": "流入资金",
            "流出资金": "流出资金", "净额": "净额", "领涨股": "领涨股",
            "领涨股-涨跌幅": "领涨股涨跌幅",
        }
        df = df.rename(columns=rename)
        keep = [c for c in ["行业", "涨跌幅", "流入资金", "流出资金", "净额", "领涨股", "领涨股涨跌幅"] if c in df.columns]
        return df[keep].copy()
    return _cached(300, "industry_ff", _fn)


# ───────────────────────── 北向资金 ─────────────────────────
def get_northbound_fund_flow():
    """北向资金（沪股通/深股通/北向）。返回 dict: boards(list), trade_date, total_inflow, sh_inflow, sz_inflow。"""
    def _fn():
        import akshare as ak
        df = ak.stock_hsgt_fund_flow_summary_em()
        if df is None or df.empty:
            return {"boards": [], "trade_date": None, "total_inflow": None,
                    "sh_inflow": None, "sz_inflow": None}
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
            except Exception:
                val = 0.0
            if str(r.get("板块")) == "沪股通":
                sh = val
            elif str(r.get("板块")) == "深股通":
                sz = val
            elif str(r.get("资金方向")) == "北向":
                total = val
        if total is None and sh is not None and sz is not None:
            total = sh + sz
        td = None
        try:
            td = df.iloc[0].get("交易日")
            td = td.strftime("%Y-%m-%d") if hasattr(td, "strftime") else str(td)
        except Exception:
            td = None
        return {"boards": boards, "trade_date": td, "total_inflow": total,
                "sh_inflow": sh, "sz_inflow": sz}
    return _cached(300, "northbound_ff", _fn)


# ───────────────────────── 大盘资金流向 ─────────────────────────
def get_market_fund_flow(days=30):
    """大盘主力/超大单/大单净流入历史序列。返回 DataFrame(日期, 上证-涨跌幅, 主力净流入-净额, 超大单净流入-净额, 大单净流入-净额)。"""
    def _fn():
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
    return _cached(600, f"market_ff_{days}", _fn)


# ───────────────────────── 个股资金流向（真实优先 + 量价估算兜底） ─────────────────────────
def get_individual_fund_flow(code, use_estimate_fallback=True):
    """个股资金流向。

    优先尝试 akshare 真实接口（stock_fund_flow_individual / stock_main_fund_flow），
    失败则用日线量价模型估算主力净流入（标注 估算）。
    返回 dict: {source, main_net(元), main_net_pct, big_net, super_net, latest_date}
    """
    def _real():
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
        except Exception:
            pass
        return None

    real = _real()
    if real is not None:
        return real

    if use_estimate_fallback:
        return _estimate_individual_fund_flow(code)
    return {"source": "none", "main_net": None, "main_net_pct": None,
            "big_net": None, "super_net": None, "latest_date": None}


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
    except Exception:
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
    """量价模型估算主力净流入（仅作离线兜底，明确标注 估算）。"""
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
            high, low, close, open_, vol = r["high"], r["low"], r["close"], r["open"], r["volume"]
            if high == low:
                continue
            vwap = (high + low + close) / 3.0
            # Chaikin 风格单日资金流（close 靠 high 为正）
            mf = ((close - low) - (high - close)) / (high - low) * vol * vwap
            total_mf += mf
        latest = df.iloc[-1]["date"]
        try:
            latest = latest.strftime("%Y-%m-%d") if hasattr(latest, "strftime") else str(latest)
        except Exception:
            latest = str(latest)
        return {
            "source": "estimate",
            "main_net": round(total_mf, 2),
            "main_net_pct": None,
            "big_net": None,
            "super_net": None,
            "latest_date": latest,
        }
    except Exception:
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
                            "净利润-季度环比增长", "每股净资产", "净资产收益率", "上市时间"] if c in df.columns]
        rename = {
            "股票代码": "代码", "股票简称": "名称", "每股收益": "每股收益",
            "营业总收入-营业总收入": "营业总收入", "营业总收入-同比增长": "营收同比%",
            "净利润-净利润": "净利润", "净利润-同比增长": "净利润同比%",
            "净利润-季度环比增长": "净利润环比%", "每股净资产": "每股净资产",
            "净资产收益率": "ROE%", "上市时间": "上市时间",
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
        except Exception:
            return pd.DataFrame()
    return _cached(1800, f"yjyg_{period}", _fn)


def get_disclosure_calendar(market="沪市", period="2026一季报"):
    """财报披露日历（best-effort）。返回 DataFrame(market, stock_code, stock_name, report_date, report_type)。"""
    def _fn():
        import akshare as ak
        try:
            df = ak.stock_report_disclosure(market=market, period=period)
            if df is None or df.empty:
                return pd.DataFrame()
            return df
        except Exception:
            return pd.DataFrame()
    return _cached(1800, f"disclosure_{market}_{period}", _fn)


def clear_fundflow_cache():
    """清空缓存（调试用）。"""
    _CACHE.clear()
