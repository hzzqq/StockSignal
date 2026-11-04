"""市场驱动力 —— 缓存与工具基元（market_drivers 拆分·叶子底座）。

职责：维度/指标常量登记、TTL 缓存与 SWR 单飞刷新、重试装饰器、列名与数值归一工具。
R-07 委托共享 TTL 缓存层（cache_utils._CACHE / _CACHE_LOCK / cached_ttl），
_cached_swr / _kick_refresh 仍直接操作 _CACHE / _CACHE_LOCK（SWR 专属语义保留）。
零业务逻辑改动：源码自 ``modules/market_drivers.py`` 原样搬运。
"""
from __future__ import annotations  # noqa: I001

import logging
import os
import threading
import time

import numpy as np
import pandas as pd

from modules.fundflow import _ensure_proxy_and_ssl
from modules.cache_utils import _CACHE, _CACHE_LOCK, cached_ttl

# 与主入口共用同名 logger（getLogger 单例），保证既有按名打补丁/过滤继续生效
logger = logging.getLogger("modules.market_drivers")

DIMS = ["资金", "情绪", "估值", "宏观", "技术"]

INDICATORS = [
    # ── 资金 ──
    dict(key="margin_balance", dim="资金", name="融资余额", unit="亿元", src="margin_rzye",
         note="两市融资存量，正相关助推上涨"),
    dict(key="margin_net", dim="资金", name="融资净买入额", unit="亿元", src="margin_net",
         note="买入额-偿还额，连续净流入是上涨直接推力"),
    dict(key="margin_buy_ratio", dim="资金", name="融资买入额/成交额", unit="%", src="margin_buy_ratio",
         note="杠杆资金参与占比，>9%警惕过热，<6%偏冷清"),
    dict(key="margin_balance_ratio", dim="资金", name="融资余额/流通市值", unit="%", src="margin_balance_ratio",
         note="杠杆相对规模，过高预示卸杠杆风险"),
    dict(key="north_net", dim="资金", name="北向资金净流入", unit="亿元", src="north_hist",
         note="沪/深股通净额，风向标；2024-08 起停披露实时值，仅历史段真实"),
    dict(key="adl", dim="资金", name="腾落指数(ADL)", unit="累积", src="activity", derive="adl",
         note="上涨家数-下跌家数累积，同步确认指数健康度"),
    dict(key="adr", dim="资金", name="涨跌比率(ADR)", unit="比值", src="activity", derive="adr",
         note="上涨/下跌家数，>1.2偏强，<0.8偏弱"),
    dict(key="nhnl", dim="资金", name="新高新低指标", unit="差值", src="high_low",
         note="创52周新高-新低家数，正值扩大支持上行"),
    # ── 情绪 ──
    dict(key="vix", dim="情绪", name="VIX恐慌指数", unit="指数", src="qvvix",
         note="期权隐含波动率，飙升常对应指数短期底部"),
    dict(key="pcr", dim="情绪", name="PCR(认沽/认购比)", unit="比值", src="pcr",
         note="认沽量/认购量，异常高位往往对应指数底部"),
    dict(key="zt_ratio", dim="情绪", name="涨停家数占比", unit="%", src="zt",
         note="涨停数/交易总数，赚钱效应温度计"),
    # ── 估值 ──
    dict(key="pe_pct", dim="估值", name="PE历史百分位", unit="%", src="pe", derive="pct",
         note="当前PE在历史中位置，>80%高估，<20%低估"),
    dict(key="div_yield", dim="估值", name="股息率", unit="%", src="div",
         note="股息/股价，指数跌则股息率升（配置价值凸显）"),
    # ── 宏观 ──
    dict(key="m2_yoy", dim="宏观", name="M2同比增速", unit="%", src="m2",
         note="广义货币供应，增速上行利好股市"),
    dict(key="shr_zgm", dim="宏观", name="社会融资规模", unit="亿元", src="financing",
         note="实体融资总量，领先指标，连续多增指数滞后走强"),
    dict(key="yield_spread", dim="宏观", name="长短期利差", unit="%", src="yield", derive="spread",
         note="10Y-2Y国债，倒挂预示衰退风险（压制指数）"),
    dict(key="pmi", dim="宏观", name="PMI(采购经理指数)", unit="指数", src="pmi",
         note="制造业景气，连续>50扩张区间支撑上行"),
    # ── 技术 ──（以下均基于上证日线本地计算，无需外部源）
    dict(key="idx_ma5", dim="技术", name="MA5", unit="点位", src="idx_ma", period=5,
         note="5日均价线，方向锚点"),
    dict(key="idx_ma20", dim="技术", name="MA20", unit="点位", src="idx_ma", period=20,
         note="20日均价线，方向锚点"),
    dict(key="rsi", dim="技术", name="RSI", unit="0-100", src="idx_rsi",
         note=">70超买易回调，<30超卖易反弹"),
    dict(key="boll", dim="技术", name="布林带(BB)", unit="点位", src="idx_boll",
         note="MA±2倍标准差，触碰上轨抛压重"),
    dict(key="bias", dim="技术", name="价格乖离率", unit="%", src="idx_bias",
         note="(收盘价-MA20)/MA20，偏离过大有拉回动力"),
]

KNOWN_UNAVAILABLE = {
    "margin_buy_ratio": "需两市成交额数据，暂未接入",
    "margin_balance_ratio": "需流通市值数据，暂未接入",
}

_CACHE_TTL = 600  # 业务语义常量，暂不进 site_config（批次 4 可选）

_SWR_INFLIGHT: set = set()   # 正在后台刷新的 key（单飞去重）

_SWR_LOCK = threading.Lock()

def _cached(ttl, key, fn):
    return cached_ttl(ttl, key, fn)

def _cached_swr(ttl, key, fn):
    """TTL 缓存 + stale-while-revalidate。返回 (value, swr_info_or_None)。

    swr_info = {"age_s": 旧值年龄秒数}；无 SWR 发生（新鲜命中/冷启动）时为 None。
    后台刷新成功静默换新（下次调用生效）；失败 logger 留痕，下次调用重试。
    """
    now = time.time()
    stale = None
    stale_ts = None
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and (now - hit[0]) < ttl:
            return hit[1], None          # 新鲜命中：语义与原 _cached 一致
        if hit is not None:
            stale, stale_ts = hit[1], hit[0]

    if stale is not None:
        _kick_refresh(key, fn)
        return stale, {"age_s": int(now - stale_ts)}

    val = fn()                            # 冷启动：无旧值，同步取（行为不变）
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), val)
    return val, None

def _kick_refresh(key, fn):
    """后台单飞刷新：inflight 去重后 daemon 线程执行，fn 在锁外跑（不阻塞读）。"""
    with _SWR_LOCK:
        if key in _SWR_INFLIGHT:
            return
        _SWR_INFLIGHT.add(key)

    def _worker():
        try:
            val = fn()
            with _CACHE_LOCK:
                _CACHE[key] = (time.time(), val)
            logger.info("[market_drivers] SWR 后台刷新完成: %s", key)
        except Exception as e:  # noqa: BLE001 - 刷新失败如实留痕，绝不静默
            logger.warning("[market_drivers] SWR 后台刷新失败 (%s): %s", key, e)
        finally:
            with _SWR_LOCK:
                _SWR_INFLIGHT.discard(key)

    threading.Thread(target=_worker, daemon=True, name=f"swr-{key}").start()

def _retry(max_retries=3, base_delay=1.0):
    def deco(fn):
        def wrapper(*args, **kwargs):
            # 惰性、幂等：首次网络请求前确保代理/SSL 补丁就绪（不在导入期阻塞）
            _ensure_proxy_and_ssl()
            last = None
            for i in range(max_retries):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:  # noqa
                    last = e
                    err = str(e).lower()
                    if any(k in err for k in ("connection aborted", "remotedisconnected",
                                               "connection reset", "timeout", "timed out",
                                               "proxyerror")):
                        if i < max_retries - 1:
                            time.sleep(base_delay * (2 ** i))
                            continue
                    raise
            raise last
        return wrapper
    return deco

def _col(df, *keys):
    """按关键字（不区分大小写）在 DataFrame 列中找第一个匹配列名。"""
    if df is None or not hasattr(df, "columns"):
        return None
    low = {str(c).lower(): c for c in df.columns}
    for k in keys:
        lk = str(k).lower()
        for lcol, col in low.items():
            if lk in lcol:
                return col
    return None

def _pdate(x):
    try:
        return pd.to_datetime(x, errors="coerce")
    except Exception as e:
        logger.warning(f"[market_drivers] 处理异常: {e}")
        return pd.NaT

def _read_last_cached_value(key: str):
    """从 SQLite 持久缓存读取某指标最近一个日期的数值（用于 ADL 等累积指标的跨日拼接）。

    直接读 market_cache 的 DB 文件，避免与 market_cache 形成循环导入。
    读不到返回 None。
    """
    import sqlite3 as _sq
    try:
        _here = os.path.dirname(os.path.abspath(__file__))
        # 跟随 SS_DATA_DIR 隔离，与 market_cache._DB_PATH 指向同一目录（测试不读穿真实 data/）
        _db = os.path.join(
            os.environ.get("SS_DATA_DIR") or os.path.join(_here, "..", "data"),
            "market_cache.db")
        if not os.path.exists(_db):
            return None
        conn = _sq.connect(_db, timeout=10)
        cur = conn.execute(
            "SELECT value FROM market_indicator_cache WHERE key=? "
            "ORDER BY date DESC LIMIT 1",
            (key,),
        )
        row = cur.fetchone()
        conn.close()
        return float(row[0]) if row else None
    except Exception as e:  # noqa
        logger.warning(f"[market_drivers] 处理异常: {e}")
        return None

def _pdate_cn(x):
    """解析中文月度 '2026年06月份' -> datetime 序列；其余走 _pdate。"""
    s = pd.Series(list(x)) if not isinstance(x, pd.Series) else x
    out = []
    for v in s.astype(str):
        v = v.replace("月份", "").replace("年", "-").replace("月", "-01").strip()
        out.append(pd.to_datetime(v, errors="coerce"))
    return pd.Series(out)

def _norm100(s: pd.Series):
    """归一化到起点=100（首个有效值）。"""
    s = pd.to_numeric(s, errors="coerce")
    s = s.dropna()
    if s.empty:
        return s
    base = s.iloc[0]
    if base == 0 or pd.isna(base):
        return s
    return s / base * 100.0

def _norm100_aligned(dates, values):
    """归一化到起点=100，并与 dates 对齐返回 (date_arr, norm_arr)。

    关键点：plot_drivers_panel 列 Series 的 index 是行位置而非日期，
    若直接用 s.index 作 x 轴会得到整数位置（被 Plotly 当成 epoch 纳秒）。
    这里显式用传入的 dates 对齐，确保时间轴正确。
    自动剔除 values/日期为 NaN 的位置。
    """
    vals = pd.to_numeric(values, errors="coerce")
    dts = pd.to_datetime(pd.Series(list(dates)), errors="coerce")
    keep = vals.notna() & dts.notna()
    if not keep.any():
        return np.array([], dtype="datetime64[ns]"), np.array([])
    vals = vals[keep]
    dts = dts[keep]
    base = vals.iloc[0]
    if base == 0 or pd.isna(base):
        y = vals.values.astype(float)
    else:
        y = (vals / base * 100.0).values.astype(float)
    return dts.values, y
