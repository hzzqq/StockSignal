"""
市场驱动力多因子面板（资金 / 情绪 / 估值 / 宏观 / 技术 五维）

背景：用户给了一份 21 指标表（table_20260721.csv），要求
  1) 先给「融资买入额」线型图右侧 y 轴加几个新指标；
  2) 高阶方案（推荐）：分维度子图面板，按 资金/情绪/估值/宏观/技术 分 5 个子图，
     每个子图含大盘指数作参考线，因量纲差异严禁原始数值裸叠同一轴 → 统一归一化到起点=100。

数据层设计：
- 21 个指标注册表（INDICATORS），每个含 维度/单位/数据源/计算逻辑。
- 每个数据源用防御式列解析（按关键字找列，不依赖精确列名），单源失败优雅降级（列缺/标"暂未接入"），绝不抛红错。
- 数据源：复用 margin_trading / linear_trends 已有取数；新增 akshare 直接抓取
  （涨跌家数 stock_market_activity_legu、新高新低 stock_a_high_low_statistics、VIX index_option_50etf_qvix、
   涨停池 stock_zt_pool_em、市场 PE stock_market_pe_lg、M2 macro_china_m2_yearly、
   社融 macro_china_bank_financing、国债利差 bond_china_yield、PMI macro_china_pmi）。
- 技术类（MA/RSI/布林带/乖离率）由上证日线本地计算，无需外部源。

注意：本环境（沙箱）本地代理 127.0.0.1:26561 未起，akshare 网络抓取会失败；
真实用户环境（代理在线）上述源可正常返回。代码对失败做优雅降级，
并在 meta 中标注每个指标"可用 / 暂未接入(原因)"，便于页面提示。
"""
import time
import logging

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from modules.fundflow import _ensure_proxy_and_ssl
_ensure_proxy_and_ssl()
from modules.margin_trading import get_margin_trading_data
from modules.linear_trends import get_index_series, get_northbound_history_series

logger = logging.getLogger(__name__)

DIMS = ["资金", "情绪", "估值", "宏观", "技术"]

# 21 个指标注册表（MA 含 5/20 双周期，故实际 22 条线，对应 CSV 21 指标口径）
# src 取值：
#   margin_rzye / margin_net / north_hist / activity / high_low / qvvix /
#   zt / pe / div / m2 / financing / yield / pmi / idx_*（技术，本地计算）
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

# 已知无可行数据源的指标（避免无谓网络重试，直接标注）
KNOWN_UNAVAILABLE = {
    "margin_buy_ratio": "需两市成交额数据，暂未接入",
    "margin_balance_ratio": "需流通市值数据，暂未接入",
    "pcr": "认沽/认购比需个股期权明细，暂未接入",
}

# 简易 TTL 缓存
_CACHE = {}
_CACHE_TTL = 600


def _cached(ttl, key, fn):
    now = time.time()
    hit = _CACHE.get(key)
    if hit and (now - hit[0]) < ttl:
        return hit[1]
    val = fn()
    _CACHE[key] = (now, val)
    return val


def _retry(max_retries=3, base_delay=1.0):
    def deco(fn):
        def wrapper(*args, **kwargs):
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
    except Exception:
        return pd.NaT


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


# ────────────────────────────────────────────────────────────
# 各数据源抓取（每个返回 [(ind_key, display_name, pd.Series), ...]，失败返回 []）
# Series 以 datetime 为索引，数值为 float。
# ────────────────────────────────────────────────────────────
@_retry()
def _fetch_margin_raw(days=180):
    """取融资融券原始宽表（含融资买入额/余额，若源含偿还额则一并保留）。"""
    return get_margin_trading_data(days=days)


def _src_margin_rzye(days):
    df = _fetch_margin_raw(days)
    if df is None or df.empty or "total_rzye" not in df.columns:
        return []
    s = pd.to_numeric(df["total_rzye"], errors="coerce") / 1e8  # 元→亿元
    s.index = _pdate(df["日期"])
    s = s.dropna()
    return [("margin_balance", "融资余额", s)] if not s.empty else []


def _src_margin_net(days):
    df = _fetch_margin_raw(days)
    if df is None or df.empty:
        return []
    buy = pd.to_numeric(df.get("total_rzmr"), errors="coerce")
    # 尝试取偿还额（列名不确定，防御式）
    repay_col = _col(df, "偿还", "repay", "偿还额")
    if repay_col is None:
        return []  # 源无偿还额 → 净买入额不可得
    repay = pd.to_numeric(df[repay_col], errors="coerce")
    net = (buy - repay) / 1e8  # 元→亿元
    net.index = _pdate(df["日期"])
    net = net.dropna()
    return [("margin_net", "融资净买入额", net)] if not net.empty else []


def _src_north_hist(days):
    try:
        df = get_northbound_history_series()
    except Exception as e:  # noqa
        logger.warning("north_hist 失败：%s", e)
        return []
    if df is None or df.empty:
        return []
    col = _col(df, "当日成交净买额", "净买额", "north")
    if col is None:
        return []
    dt = df["date"] if "date" in df.columns else df.index
    s = pd.to_numeric(df[col], errors="coerce") / 1e8
    s.index = _pdate(dt)
    s = s.dropna()
    if days and len(s) > days:
        s = s.tail(days)
    return [("north_net", "北向资金净流入", s)] if not s.empty else []


@_retry()
def _src_activity(days):
    import akshare as ak
    df = ak.stock_market_activity_legu()
    if df is None or df.empty:
        return []
    up = pd.to_numeric(df[_col(df, "上涨", "up")], errors="coerce")
    dn = pd.to_numeric(df[_col(df, "下跌", "down")], errors="coerce")
    dt = _pdate(df[_col(df, "日期", "date", "时间")])
    up.index = dn.index = dt
    adl = (up - dn).fillna(0).cumsum()
    adr = (up / dn.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
    out = []
    if not adl.dropna().empty:
        out.append(("adl", "腾落指数(ADL)", adl.dropna()))
    if not adr.dropna().empty:
        out.append(("adr", "涨跌比率(ADR)", adr.dropna()))
    return out


@_retry()
def _src_high_low(days):
    import akshare as ak
    df = ak.stock_a_high_low_statistics()
    if df is None or df.empty:
        return []
    nh = pd.to_numeric(df[_col(df, "新高", "new_high", "52周新高")], errors="coerce")
    nl = pd.to_numeric(df[_col(df, "新低", "new_low", "52周新低")], errors="coerce")
    dt = _pdate(df[_col(df, "日期", "date", "时间")])
    nh.index = nl.index = dt
    s = (nh - nl).dropna()
    return [("nhnl", "新高新低指标", s)] if not s.empty else []


@_retry()
def _src_qvvix(days):
    import akshare as ak
    df = ak.index_option_50etf_qvix()
    if df is None or df.empty:
        return []
    col = _col(df, "vix", "qvix", "恐慌")
    if col is None:
        return []
    s = pd.to_numeric(df[col], errors="coerce")
    s.index = _pdate(df[_col(df, "日期", "date", "时间")])
    s = s.dropna()
    return [("vix", "VIX恐慌指数", s)] if not s.empty else []


@_retry()
def _src_zt(days):
    import akshare as ak
    df = ak.stock_zt_pool_em()
    if df is None or df.empty:
        return []
    dt = _pdate(df[_col(df, "日期", "date", "时间")])
    # 涨停家数占全市场近似比（全市场约 5000 只，分母用常量近似并标注）
    n = pd.Series(len(df), index=[dt] if pd.notna(dt) else [pd.Timestamp.now()])
    s = (n / 5000.0 * 100.0)
    s.index = pd.to_datetime(s.index, errors="coerce")
    s = s.dropna()
    return [("zt_ratio", "涨停家数占比", s)] if not s.empty else []


@_retry()
def _src_pe(days):
    import akshare as ak
    df = ak.stock_market_pe_lg()
    if df is None or df.empty:
        return []
    col = _col(df, "pe", "市盈率")
    if col is None:
        return []
    s = pd.to_numeric(df[col], errors="coerce")
    s.index = _pdate(df[_col(df, "日期", "date", "时间")])
    s = s.dropna()
    if s.empty:
        return []
    # PE 历史百分位（当前 PE 在自身历史分布中的位置）
    pct = s.rank(pct=True) * 100.0
    return [("pe_pct", "PE历史百分位", pct.dropna())]


@_retry()
def _src_div(days):
    import akshare as ak
    df = ak.stock_market_pe_lg()
    if df is None or df.empty:
        return []
    col = _col(df, "股息", "dividend", "yield")
    if col is None:
        return []
    s = pd.to_numeric(df[col], errors="coerce")
    s.index = _pdate(df[_col(df, "日期", "date", "时间")])
    s = s.dropna()
    return [("div_yield", "股息率", s)] if not s.empty else []


@_retry()
def _src_m2(days):
    import akshare as ak
    df = ak.macro_china_m2_yearly()
    if df is None or df.empty:
        return []
    col = _col(df, "m2", "货币", "同比")
    if col is None:
        return []
    s = pd.to_numeric(df[col], errors="coerce")
    s.index = _pdate(df[_col(df, "日期", "date", "时间")])
    s = s.dropna()
    return [("m2_yoy", "M2同比增速", s)] if not s.empty else []


@_retry()
def _src_financing(days):
    import akshare as ak
    df = ak.macro_china_bank_financing()
    if df is None or df.empty:
        return []
    col = _col(df, "社融", "融资规模", "增量")
    if col is None:
        return []
    s = pd.to_numeric(df[col], errors="coerce") / 1e8  # 元→亿元
    s.index = _pdate(df[_col(df, "日期", "date", "时间")])
    s = s.dropna()
    return [("shr_zgm", "社会融资规模", s)] if not s.empty else []


@_retry()
def _src_yield(days):
    import akshare as ak
    df = ak.bond_china_yield()
    if df is None or df.empty:
        return []
    dcol = _col(df, "日期", "date", "时间")
    # 找到 10年 与 2年 行
    name_col = _col(df, "期限", "name", "类型")
    val_col = _col(df, "收益率", "yield", "利率")
    if dcol is None or name_col is None or val_col is None:
        return []
    long = pd.to_numeric(df.loc[df[name_col].astype(str).str.contains("10"), val_col], errors="coerce")
    short = pd.to_numeric(df.loc[df[name_col].astype(str).str.contains("2"), val_col], errors="coerce")
    if long.empty or short.empty:
        return []
    ldt = _pdate(df.loc[df[name_col].astype(str).str.contains("10"), dcol])
    sdt = _pdate(df.loc[df[name_col].astype(str).str.contains("2"), dcol])
    long.index = ldt
    short.index = sdt
    spread = (long - short).dropna()
    return [("yield_spread", "长短期利差", spread)] if not spread.empty else []


@_retry()
def _src_pmi(days):
    import akshare as ak
    df = ak.macro_china_pmi()
    if df is None or df.empty:
        return []
    col = _col(df, "pmi", "制造业", "指数")
    if col is None:
        return []
    s = pd.to_numeric(df[col], errors="coerce")
    s.index = _pdate(df[_col(df, "日期", "date", "时间")])
    s = s.dropna()
    return [("pmi", "PMI(采购经理指数)", s)] if not s.empty else []


# 技术类：基于上证日线本地计算，返回 (close_series, )
def _get_index_close(days):
    idx = get_index_series(days=days)
    if idx is None or idx.empty or "sh000001" not in idx.columns:
        return None
    s = pd.to_numeric(idx["sh000001"], errors="coerce")
    s.index = _pdate(idx["date"])
    return s.dropna()


def _src_idx_ma(days, period=20):
    close = _get_index_close(days)
    if close is None or close.empty:
        return []
    ma = close.rolling(period, min_periods=max(2, period // 2)).mean()
    ma = ma.dropna()
    return [(f"idx_ma{period}", f"MA{period}", ma)] if not ma.empty else []


def _src_idx_rsi(days, period=14):
    close = _get_index_close(days)
    if close is None or len(close) < period + 1:
        return []
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    ag = gain.rolling(period, min_periods=period).mean()
    al = loss.rolling(period, min_periods=period).mean()
    rs = ag / al.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    rsi = rsi.dropna()
    return [("rsi", "RSI", rsi)] if not rsi.empty else []


def _src_idx_boll(days, period=20, k=2):
    close = _get_index_close(days)
    if close is None or len(close) < period:
        return []
    mid = close.rolling(period, min_periods=period // 2).mean()
    std = close.rolling(period, min_periods=period // 2).std()
    up = (mid + k * std).dropna()
    return [("boll", "布林带(BB)", up)] if not up.empty else []


def _src_idx_bias(days, period=20):
    close = _get_index_close(days)
    if close is None or len(close) < period:
        return []
    ma = close.rolling(period, min_periods=period // 2).mean()
    bias = (close - ma) / ma.replace(0, np.nan) * 100.0
    bias = bias.dropna()
    return [("bias", "价格乖离率", bias)] if not bias.empty else []


_SRC_DISPATCH = {
    "margin_rzye": _src_margin_rzye,
    "margin_net": _src_margin_net,
    "north_hist": _src_north_hist,
    "activity": _src_activity,
    "high_low": _src_high_low,
    "qvvix": _src_qvvix,
    "zt": _src_zt,
    "pe": _src_pe,
    "div": _src_div,
    "m2": _src_m2,
    "financing": _src_financing,
    "yield": _src_yield,
    "pmi": _src_pmi,
}


def _fetch_src(ind, days):
    """返回 (rows, reason_or_None)。rows=[(ind_key, name, series)]。"""
    src = ind["src"]
    reason = KNOWN_UNAVAILABLE.get(ind["key"])
    if reason:
        return [], reason
    if src == "margin_buy_ratio":
        return [], KNOWN_UNAVAILABLE["margin_buy_ratio"]
    if src == "margin_balance_ratio":
        return [], KNOWN_UNAVAILABLE["margin_balance_ratio"]
    if src == "pcr":
        return [], KNOWN_UNAVAILABLE["pcr"]
    if src.startswith("idx_"):
        try:
            if src == "idx_ma":
                return _src_idx_ma(days, ind.get("period", 20)), None
            if src == "idx_rsi":
                return _src_idx_rsi(days), None
            if src == "idx_boll":
                return _src_idx_boll(days), None
            if src == "idx_bias":
                return _src_idx_bias(days), None
        except Exception as e:  # noqa
            logger.warning("技术指标 %s 失败：%s", src, e)
            return [], "本地计算失败"
    fn = _SRC_DISPATCH.get(src)
    if fn is None:
        return [], "数据源未实现"
    try:
        return fn(days), None
    except Exception as e:  # noqa
        logger.warning("src %s 失败：%s", src, e)
        return [], "抓取失败（网络/代理受限）"


def get_market_drivers(days=180):
    """返回 (df, meta)。

    df：宽表，列 = ['date'] + 各可用指标 key（已对齐到 common 日期索引）。
    meta：{dim: {'available':[key...], 'unavailable':[(key, reason)...]}}。
    单源失败不影响其他源；无任何数据返回空 df + 全 unavailable。
    """
    def _build():
        meta = {d: {"available": [], "unavailable": []} for d in DIMS}
        collected = {}  # key -> series
        names = {}      # key -> display name
        for ind in INDICATORS:
            rows, reason = _fetch_src(ind, days)
            if rows:
                for k, nm, s in rows:
                    collected[k] = s
                    names[k] = nm
                    if k not in meta[ind["dim"]]["available"]:
                        meta[ind["dim"]]["available"].append(k)
            else:
                meta[ind["dim"]]["unavailable"].append((ind["key"], reason or "抓取失败"))

        # 大盘指数参考线（上证，归一化对比用）
        ref = _get_index_close(days)
        if ref is not None and not ref.empty:
            collected["ref"] = ref
            names["ref"] = "上证(参考)"

        # 合并到宽表
        if not collected:
            return pd.DataFrame(columns=["date"]), meta
        aligned = {}
        for k, s in collected.items():
            s = pd.Series(s.values, index=pd.to_datetime(s.index, errors="coerce"))
            aligned[k] = s
        df = pd.DataFrame(aligned)
        df.index.name = "date"
        df = df.reset_index().rename(columns={"index": "date"})
        df = df.sort_values("date").reset_index(drop=True)
        return df, meta

    try:
        return _cached(_CACHE_TTL, f"drivers_{days}", _build)
    except Exception as e:  # noqa
        logger.warning("get_market_drivers 最终失败：%s", e)
        meta = {d: {"available": [], "unavailable": [(i["key"], "抓取失败") for i in INDICATORS if i["dim"] == d]} for d in DIMS}
        return pd.DataFrame(columns=["date"]), meta


# ────────────────────────────────────────────────────────────
# 绘图：5 维归一化子图面板
# ────────────────────────────────────────────────────────────
_DIM_COLORS = {
    "资金": "#ee2a2a", "情绪": "#7c5cff", "估值": "#2b8aef",
    "宏观": "#f59e0b", "技术": "#10b981",
}
_REF_COLOR = "#8a8a8a"


def _fig_theme(dark_mode):
    if dark_mode:
        return dict(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e6e6e6"),
            xaxis=dict(gridcolor="#2a2a3a"),
        )
    return dict(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#1a1a1a"),
        xaxis=dict(gridcolor="#ececec"),
    )


def plot_drivers_panel(df, meta=None, dark_mode=False, dims=None,
                       date_range=None, selected=None, title="核心指标与大盘趋势关联性全景图"):
    """5 维归一化子图面板。

    - 每个维度一子图；子图内所有指标与大盘指数(上证)均归一化到起点=100 叠加，
      彻底规避量纲差异（融资余额万亿级 vs RSI 0-100）造成的失真。
    - 上证作为虚线参考线，置于每个子图，直观看指标与大盘的领先/背离。
    - dims：显示的维度列表（默认全部 5 维）。
    - selected：跨维度勾选的 key 列表（None=显示各维全部可用）。
    - date_range：(start, end) 或 None。
    """
    if dims is None:
        dims = list(DIMS)
    dims = [d for d in dims if d in DIMS]
    if df is None or df.empty:
        fig = go.Figure()
        fig.update_layout(title="暂无市场驱动力数据（网络/代理受限或数据源暂未接入）",
                         **_fig_theme(dark_mode), height=360)
        return fig

    # 区间切片
    work = df.copy()
    if date_range is not None:
        s, e = date_range
        work["date"] = pd.to_datetime(work["date"], errors="coerce")
        mask = (work["date"] >= pd.to_datetime(s, errors="coerce")) & \
               (work["date"] <= pd.to_datetime(e, errors="coerce"))
        work = work[mask]
    if work.empty:
        fig = go.Figure()
        fig.update_layout(title="所选区间无数据", **_fig_theme(dark_mode), height=360)
        return fig

    # 各维度可用 key
    dim_keys = {}
    for d in dims:
        if meta and d in meta:
            av = meta[d]["available"]
        else:
            av = [c for c in work.columns if c not in ("date", "ref")]
        if selected is not None:
            av = [k for k in av if k in selected]
        dim_keys[d] = av

    n = len(dims)
    if n == 0:
        fig = go.Figure()
        fig.update_layout(title="暂无可显示的指标（数据源未接入）", **_fig_theme(dark_mode), height=360)
        return fig

    fig = make_subplots(
        rows=n, cols=1, shared_xaxes=True, vertical_spacing=0.06,
        subplot_titles=[f"{d}（{len(dim_keys[d])} 项）" for d in dims],
        row_heights=[1] * n,
    )

    ref_pair = None
    if "ref" in work.columns:
        ref_pair = _norm100_aligned(work["date"], work["ref"])

    for i, d in enumerate(dims, start=1):
        keys = dim_keys[d]
        base_color = _DIM_COLORS.get(d, "#2b8aef")
        has_any = False
        for k in keys:
            if k not in work.columns:
                continue
            xs, ys = _norm100_aligned(work["date"], work[k])
            if len(xs) == 0:
                continue
            has_any = True
            fig.add_trace(go.Scatter(
                x=xs, y=ys, name=k, mode="lines",
                line=dict(width=1.8, color=base_color),
                hovertemplate=f"%{{x}}<br>{k}（归一化）：%{{y:.1f}}<extra></extra>",
                legendgroup=d,
            ), row=i, col=1)
        # 参考线：上证
        if ref_pair is not None and len(ref_pair[0]) > 0:
            has_any = True
            rx, ry = ref_pair
            fig.add_trace(go.Scatter(
                x=rx, y=ry, name="上证(参考)",
                mode="lines", line=dict(width=1.6, color=_REF_COLOR, dash="dash"),
                hovertemplate="%{x}<br>上证(归一化)：%{y:.1f}<extra></extra>",
                legendgroup="ref",
            ), row=i, col=1)
        if not has_any:
            fig.add_annotation(text="（本环境该维度数据源暂未接入）", showarrow=False,
                              xref=f"x{i} domain", yref=f"y{i} domain",
                              x=0.5, y=0.5, font=dict(size=12, color="#999999"),
                              row=i, col=1)

    # 布局
    layout = _fig_theme(dark_mode)
    layout.update(
        title=title,
        height=max(320, 230 * n + 90),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.5, xanchor="center", font=dict(size=10)),
        margin=dict(l=55, r=25, t=70, b=40),
        hovermode="x unified",
    )
    # 每个子图 y 轴标题（归一化）
    for i in range(1, n + 1):
        fig.update_yaxes(title_text="归一化(起点=100)", row=i, col=1, showgrid=True)
        fig.update_xaxes(tickangle=-30, row=i, col=1)
    fig.update_layout(**layout)
    return fig
