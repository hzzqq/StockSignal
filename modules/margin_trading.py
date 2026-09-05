"""
融资买入额 / 融资融券余额趋势组件

功能：复刻「融资买入额趋势图_独立版」的核心能力——
- 沪/深两地每日融资买入额（自动求和）
- 叠加三大指数（上证 000001 / 深证成指 399001 / 创业板指 399006）收盘价
- 线性表达（双 Y 轴线图），适配项目亮/暗主题

数据源：
- 融资数据：akshare macro_china_market_margin_sh / macro_china_market_margin_sz（元）
- 指数数据：akshare stock_zh_index_daily（本地 Baostock/缓存源，稳定）

说明：akshare 暂无独立北交所（BJ）融资融券宏观序列，因此组件展示沪+深合计，
并在图表副标题注明；若未来有可靠 BJ 源可扩展为三地求和。
"""
from datetime import datetime
from modules.time_utils import now_cst
import logging
import math
import threading
import time

import pandas as pd
import plotly.graph_objects as go

logger = logging.getLogger(__name__)

# 复用 fundflow 的代理/SSL 补丁，确保 akshare 经本地代理访问
# 注意：代理/SSL 探测改为「首次真实网络请求前惰性执行」（见 _retry 包裹器），
# 绝不在模块导入期同步跑 socket 探测（否则会阻塞所有 import 本模块的页面）。
from modules.fundflow import _ensure_proxy_and_ssl, _run_with_timeout
from modules.fetch_parallel import fetch_many  # R78：共享有界线程池并行取数
from modules.linear_trends import get_northbound_history_series

# 简易 TTL 缓存
_MARGIN_CACHE = {}
_MARGIN_CACHE_LOCK = threading.Lock()


def _cached(ttl, key, fn, skip_empty=False):
    """TTL 缓存。

    skip_empty=True 时不缓存空结果（None / 空 DataFrame），避免把网络瞬时
    失败的结果缓存一整个 TTL，导致页面长时间空白。

    R86 double-check：fn() 在锁**外**执行——此前 fn() 在 _MARGIN_CACHE_LOCK 内，
    一路慢速网络调用会串行化所有键的缓存访问；改为锁内快速读（miss 即释放）、
    锁外执行 fn、锁内写回（与 fundflow._cached 的 R85 改造一致）。
    """
    now = time.time()
    with _MARGIN_CACHE_LOCK:
        hit = _MARGIN_CACHE.get(key)
        if hit and (now - hit[0]) < ttl:
            return hit[1]
    # 锁外执行昂贵取数：不阻塞其他键的缓存访问
    val = fn()
    empty = val is None or (isinstance(val, pd.DataFrame) and val.empty)
    if not (skip_empty and empty):
        with _MARGIN_CACHE_LOCK:
            _MARGIN_CACHE[key] = (time.time(), val)
    return val


def _retry(max_retries=3, base_delay=1.0):
    """指数退避重试，缓解偶发连接中断。"""
    def deco(fn):
        def wrapper(*args, **kwargs):
            # 惰性、幂等：首次网络请求前确保代理/SSL 补丁就绪（不在导入期阻塞）
            _ensure_proxy_and_ssl()
            last_exc = None
            for attempt in range(max_retries):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    err = str(e).lower()
                    if any(k in err for k in ("connection aborted", "remotedisconnected",
                                               "connection reset", "timeout", "timed out")):
                        if attempt < max_retries - 1:
                            time.sleep(base_delay * (2 ** attempt))
                            continue
                    raise
            raise last_exc
        return wrapper
    return deco


def _parse_date(d):
    if d is None:
        return None
    if pd.isna(d):
        return None
    if isinstance(d, pd.Timestamp):
        return d.strftime("%Y-%m-%d")
    if isinstance(d, datetime):
        return d.strftime("%Y-%m-%d")
    if isinstance(d, str):
        # 非法日期字符串（如 'garbage'）不再抛错，统一回退 None
        ts = pd.to_datetime(d, errors="coerce")
        if pd.isna(ts):
            return None
        return ts.strftime("%Y-%m-%d")
    # 其它类型保持原 str[:10] 行为，避免误伤
    return str(d)[:10]


@_retry(max_retries=3, base_delay=1.0)
def _fetch_margin_sh():
    import akshare as ak
    df = ak.macro_china_market_margin_sh()
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["日期"] = df["日期"].apply(_parse_date)
    # 融资买入额、融资余额 转为数值（元）
    for col in ["融资买入额", "融资余额"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["日期"])
    return df[["日期", "融资买入额", "融资余额"]].rename(
        columns={"融资买入额": "sh_rzmr", "融资余额": "sh_rzye"}
    )


@_retry(max_retries=3, base_delay=1.0)
def _fetch_margin_sz():
    import akshare as ak
    df = ak.macro_china_market_margin_sz()
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["日期"] = df["日期"].apply(_parse_date)
    for col in ["融资买入额", "融资余额"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["日期"])
    return df[["日期", "融资买入额", "融资余额"]].rename(
        columns={"融资买入额": "sz_rzmr", "融资余额": "sz_rzye"}
    )


@_retry(max_retries=3, base_delay=1.0)
def _fetch_index(symbol):
    import akshare as ak
    df = ak.stock_zh_index_daily(symbol=symbol)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["date"] = df["date"].apply(_parse_date)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df[["date", "close"]].rename(columns={"date": "日期", "close": symbol})


def get_margin_trading_data(days=180):
    """返回 DataFrame(日期, sh_rzmr, sz_rzmr, total_rzmr, sh_rzye, sz_rzye, total_rzye, sh000001, sz399001, sz399006)。

    金额单位为 元；返回值直接用于绘图时可在展示层转换为 亿元。
    网络最终失败时返回空 DataFrame，避免页面红错。
    """
    def _fetch_all():
        # 并行抓取 5 个独立数据源（沪/深融资 + 3 指数），替代原来串行 10-25s
        # R78 起走共享有界线程池 fetch_many，不再每次新建 ThreadPoolExecutor
        t0 = time.perf_counter()
        res = fetch_many(
            [
                ("sh", _fetch_margin_sh),
                ("sz", _fetch_margin_sz),
                ("idx000001", lambda: _fetch_index("sh000001")),
                ("idx399001", lambda: _fetch_index("sz399001")),
                ("idx399006", lambda: _fetch_index("sz399006")),
            ],
            max_workers=5,
            timeout=20,
        )
        logger.info(
            "[margin] 融资融券并行抓取完成，总耗时 %.2fs",
            time.perf_counter() - t0,
        )

        # fetch_many 超时/异常项为 None；空 DataFrame 是合法值，不能 or（会触发歧义）
        sh = res.get("sh")
        sz = res.get("sz")
        sh = sh if sh is not None else pd.DataFrame()
        sz = sz if sz is not None else pd.DataFrame()
        if sh.empty and sz.empty:
            return pd.DataFrame()
        if sh.empty:
            df = sz.copy()
        elif sz.empty:
            df = sh.copy()
        else:
            df = sh.merge(sz, on="日期", how="outer")
        df = df.sort_values("日期").reset_index(drop=True)

        # 合计沪+深
        df["sh_rzmr"] = pd.to_numeric(df.get("sh_rzmr"), errors="coerce").fillna(0)
        df["sz_rzmr"] = pd.to_numeric(df.get("sz_rzmr"), errors="coerce").fillna(0)
        df["sh_rzye"] = pd.to_numeric(df.get("sh_rzye"), errors="coerce").fillna(0)
        df["sz_rzye"] = pd.to_numeric(df.get("sz_rzye"), errors="coerce").fillna(0)
        df["total_rzmr"] = df["sh_rzmr"] + df["sz_rzmr"]
        df["total_rzye"] = df["sh_rzye"] + df["sz_rzye"]

        # 合并三大指数（已在并行阶段获取）
        for idx_key in ("idx000001", "idx399001", "idx399006"):
            idx_df = res.get(idx_key, pd.DataFrame())
            if not idx_df.empty:
                df = df.merge(idx_df, on="日期", how="left")

        # 仅保留最近 days 天
        if len(df) > days:
            df = df.tail(days).reset_index(drop=True)
        return df

    def _fn():
        try:
            return _fetch_all()
        except Exception as e:
            logger.warning(f"get_margin_trading_data 最终失败：{e}")
            return pd.DataFrame()
    # 强边界：东方财富 urllib 路径可能无限挂起，12s 硬超时后返回空 DF，由 UI 兜底
    # 注意：_run_with_timeout 可能返回 None（超时）或空 DataFrame，不能用「or」
    # （空 DataFrame 的 bool 值有歧义 → ValueError），必须显式判 None。
    _result = _run_with_timeout(_fn, 12)
    return _cached(600, f"margin_trading_{days}",
                   lambda: _result if _result is not None else pd.DataFrame(), skip_empty=True)


def safe_yuan_to_yi(x):
    """元 -> 亿元；NaN / inf / None / '' / 非法输入统一返回 0.0（有限兜底）。

    作为金额换算的单一可信源，避免 pd.to_numeric(coerce) 产生的 NaN 经
    ``float(nan)/1e8`` 后渲染成图表/卡片上的 "nan"；缺失值以 0.0 兜底而非 None，
    防止下游算术出现 None 减数值的 TypeError。
    """
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(v):
        return 0.0
    return v / 1e8


def _to_yi(x):
    """把 元 转换为 亿元。向后兼容别名，统一走 safe_yuan_to_yi。"""
    return safe_yuan_to_yi(x)


def _delta_pct(cur, prev):
    """两期环比百分比变化：(cur-prev)/|prev|*100。

    cur/prev 为 None/NaN/非数值或 prev=0 时返回 0.0（避免除零与 nan，给出有限兜底值）。
    """
    try:
        c = float(cur)
        p = float(prev)
    except (TypeError, ValueError):
        return 0.0
    if not (math.isfinite(c) and math.isfinite(p)):
        return 0.0
    if p == 0:
        return 0.0
    return (c - p) / abs(p) * 100.0


def _safe_delta_yi(cur, prev):
    """两期绝对差额（亿元），任一为 None/NaN/非数值时返回 0.0（避免崩溃，给出有限兜底）。"""
    try:
        va = safe_yuan_to_yi(cur)
        vb = safe_yuan_to_yi(prev)
    except Exception as e:
        logger.warning(f"[margin_trading] 处理异常: {e}")
        return 0.0
    if va is None or vb is None:
        return 0.0
    return va - vb


def _fig_base(dark_mode):
    base = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=60, r=60, t=60, b=40),
        hovermode="x unified",
    )
    if dark_mode:
        base.update(
            font=dict(color="#e6e6e6"),
            xaxis=dict(gridcolor="#2a2a3a", zerolinecolor="#2a2a3a"),
            yaxis=dict(gridcolor="#2a2a3a", zerolinecolor="#2a2a3a"),
            yaxis2=dict(gridcolor="rgba(0,0,0,0)", zerolinecolor="rgba(0,0,0,0)"),
        )
    else:
        base.update(
            font=dict(color="#1a1a1a"),
            xaxis=dict(gridcolor="#ececec", zerolinecolor="#ececec"),
            yaxis=dict(gridcolor="#ececec", zerolinecolor="#ececec"),
            yaxis2=dict(gridcolor="rgba(0,0,0,0)", zerolinecolor="rgba(0,0,0,0)"),
        )
    return base


def plot_margin_trend(df, dark_mode=False, metric="rzmr", show_extra=True):
    """绘制融资趋势图。

    metric:
      - "rzmr": 融资买入额（默认）
      - "rzye": 融资余额
    show_extra: 是否叠加 CSV 表里杠杆/资金类新指标（严守量纲，不裸叠同轴）：
      - 北向资金净流入：与融资买入额同"亿元"量纲 → 叠左轴 y1（直接可比，无失真）
      - 融资余额（仅 metric=rzmr 时）：万亿级 → 独立右轴 y3（不与指数 y2 抢位、
        也不与买入额 y1 压扁）
    返回 Plotly Figure（最多三 Y 轴：左=金额，右1=指数，右2=融资余额）。
    """
    fig = go.Figure()
    if df is None or df.empty:
        fig.update_layout(
            title="暂无融资数据",
            **_fig_base(dark_mode), height=360,
        )
        return fig

    # 金额列
    if metric == "rzye":
        amount_col = "total_rzye"
        amount_name = "融资余额(亿元)"
        sh_col, sz_col = "sh_rzye", "sz_rzye"
        sh_name, sz_name = "沪市融资余额", "深市融资余额"
    else:
        amount_col = "total_rzmr"
        amount_name = "融资买入额(亿元)"
        sh_col, sz_col = "sh_rzmr", "sz_rzmr"
        sh_name, sz_name = "沪市融资买入额", "深市融资买入额"

    df = df.copy()
    df["amount_yi"] = df[amount_col].apply(_to_yi)
    df["sh_yi"] = df[sh_col].apply(_to_yi)
    df["sz_yi"] = df[sz_col].apply(_to_yi)
    df["日期_dt"] = pd.to_datetime(df["日期"], errors="coerce")

    colors = {
        "amount": "#ee2a2a" if metric == "rzmr" else "#2b8aef",
        "sh": "#f59e0b",
        "sz": "#10b981",
        "000001": "#7c5cff",
        "399001": "#ef5da8",
        "399006": "#2b8aef",
        "north": "#16c2c2",
        "balance": "#e67e22",
    }

    # 主指标：合计（粗线）
    fig.add_trace(go.Scatter(
        x=df["日期"], y=df["amount_yi"], name=amount_name,
        mode="lines", line=dict(color=colors["amount"], width=2.8),
        hovertemplate="%{x}<br>%{data.name}：%{y:.2f}亿<extra></extra>",
        yaxis="y",
    ))
    # 拆分：沪市 / 深市
    fig.add_trace(go.Scatter(
        x=df["日期"], y=df["sh_yi"], name=sh_name,
        mode="lines", line=dict(color=colors["sh"], width=1.4, dash="dot"),
        hovertemplate="%{x}<br>%{data.name}：%{y:.2f}亿<extra></extra>",
        yaxis="y", visible="legendonly",
    ))
    fig.add_trace(go.Scatter(
        x=df["日期"], y=df["sz_yi"], name=sz_name,
        mode="lines", line=dict(color=colors["sz"], width=1.4, dash="dot"),
        hovertemplate="%{x}<br>%{data.name}：%{y:.2f}亿<extra></extra>",
        yaxis="y", visible="legendonly",
    ))

    # ── CSV 新增杠杆/资金指标（右侧 / 左轴，严守量纲）──
    if show_extra:
        # 北向资金净流入：与融资买入额同"亿元"量纲 → 左轴 y1
        try:
            nb = get_northbound_history_series()
            if nb is not None and not nb.empty and "当日成交净买额" in nb.columns:
                nb = nb.copy()
                nb["date"] = pd.to_datetime(nb["date"], errors="coerce")
                nb["north"] = pd.to_numeric(nb["当日成交净买额"], errors="coerce") / 1e8
                merged = df.merge(
                    nb[["date", "north"]], left_on="日期_dt", right_on="date", how="left"
                )
                if merged["north"].notna().any():
                    fig.add_trace(go.Scatter(
                        x=merged["日期"], y=merged["north"], name="北向资金净流入(亿)",
                        mode="lines", line=dict(color=colors["north"], width=1.6, dash="dot"),
                        hovertemplate="%{x}<br>北向净流入：%{y:.2f}亿<extra></extra>",
                        yaxis="y",
                    ))
        except Exception as e:
            logger.warning(f"[margin_trading] 处理异常: {e}")
            pass
        # 融资余额：万亿级，仅 metric=rzmr 时独立右轴 y3（避免与指数 y2 抢位 / 与买入额 y1 压扁）
        if metric == "rzmr" and "total_rzye" in df.columns:
            bal = df["total_rzye"].apply(_to_yi)
            fig.add_trace(go.Scatter(
                x=df["日期"], y=bal, name="融资余额(亿)",
                mode="lines", line=dict(color=colors["balance"], width=1.8),
                hovertemplate="%{x}<br>融资余额：%{y:.2f}亿<extra></extra>",
                yaxis="y3",
            ))

    # 指数（右轴 y2）
    for idx_symbol, idx_col in [("上证", "sh000001"), ("深证成指", "sz399001"), ("创业板指", "sz399006")]:
        if idx_col in df.columns:
            fig.add_trace(go.Scatter(
                x=df["日期"], y=df[idx_col], name=idx_symbol,
                mode="lines", line=dict(width=1.6),
                hovertemplate="%{x}<br>%{data.name}：%{y:.2f}<extra></extra>",
                yaxis="y2",
            ))

    title = "融资买入额趋势（沪+深）" if metric == "rzmr" else "融资余额趋势（沪+深）"
    gx = "#2a2a3a" if dark_mode else "#ececec"
    layout = _fig_base(dark_mode)
    if metric == "rzmr":
        # 三轴：左=金额，右1=指数，右2=融资余额
        layout.update(
            title=title,
            height=440,
            xaxis=dict(domain=[0, 0.90], gridcolor=gx),
            yaxis=dict(title="金额（亿元）", side="left", gridcolor=gx),
            yaxis2=dict(title="指数点位", overlaying="y", side="right", anchor="x", position=1.0,
                       gridcolor="rgba(0,0,0,0)"),
            yaxis3=dict(title="融资余额(亿)", overlaying="y", side="right", anchor="free",
                       position=0.965, gridcolor="rgba(0,0,0,0)"),
            legend=dict(orientation="h", yanchor="top", y=-0.22, x=0.5, xanchor="center"),
        )
    else:
        layout.update(
            title=title,
            height=420,
            yaxis=dict(title="金额（亿元）", side="left", gridcolor=gx),
            yaxis2=dict(title="指数点位", overlaying="y", side="right", gridcolor="rgba(0,0,0,0)"),
            legend=dict(orientation="h", yanchor="top", y=-0.22, x=0.5, xanchor="center"),
        )
    fig.update_layout(**layout)
    fig.update_xaxes(tickangle=-30)
    return fig


def get_latest_margin_summary():
    """返回最近一个交易日的融资 summary 字典，用于页面顶部指标卡。

    新增 rzmr_change_pct / rzye_change_pct：环比百分比变化，
    供指标卡同时展示绝对变动与相对变动。
    """
    df = get_margin_trading_data(days=5)
    if df is None or df.empty:
        return {}
    row = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else row
    return {
        "date": row.get("日期"),
        "total_rzmr_yi": _to_yi(row.get("total_rzmr")),
        "total_rzye_yi": _to_yi(row.get("total_rzye")),
        "sh_rzmr_yi": _to_yi(row.get("sh_rzmr")),
        "sz_rzmr_yi": _to_yi(row.get("sz_rzmr")),
        "rzmr_change_yi": _safe_delta_yi(row.get("total_rzmr"), prev.get("total_rzmr")),
        "rzye_change_yi": _safe_delta_yi(row.get("total_rzye"), prev.get("total_rzye")),
        "rzmr_change_pct": _delta_pct(row.get("total_rzmr"), prev.get("total_rzmr")),
        "rzye_change_pct": _delta_pct(row.get("total_rzye"), prev.get("total_rzye")),
    }


# ------------------------------------------------------------------ 逐股融资买入额（智能条件单用）
@_retry(max_retries=3, base_delay=1.0)
def _fetch_margin_detail(date_str: str):
    """抓取某交易日的沪深两市融资融券明细（逐股）。

    date_str: YYYYMMDD。返回 DataFrame（含 代码/名称/融资买入额 列）或 None。
    """
    import akshare as ak
    frames = []
    # 沪市明细
    try:
        df_sh = ak.stock_margin_detail_sse(date=date_str)
        if df_sh is not None and not df_sh.empty:
            frames.append(df_sh)
    except Exception as e:
        logger.warning(f"[margin_trading] 处理异常: {e}")
        pass
    # 深市明细
    try:
        df_sz = ak.stock_margin_detail_szse(date=date_str)
        if df_sz is not None and not df_sz.empty:
            frames.append(df_sz)
    except Exception as e:
        logger.warning(f"[margin_trading] 处理异常: {e}")
        pass
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def get_stock_margin_buy(code: str, days_back: int = 7):
    """取单只股票最近一个可用交易日的融资买入额（元）。

    融资明细为 T+1 披露（今日只能看到上一交易日数据），
    因此从昨天起往前找最多 days_back 天，命中即止。
    返回 dict {"date": "YYYY-MM-DD", "rzmr": float 元} 或 None（无数据/非两融标的）。
    """
    code = str(code).strip().zfill(6)

    def _fn():
        from datetime import timedelta
        today = now_cst()
        for i in range(1, days_back + 1):
            d = today - timedelta(days=i)
            if d.weekday() >= 5:  # 跳过周末
                continue
            ds = d.strftime("%Y%m%d")
            try:
                df = _cached(3600, f"margin_detail_{ds}", lambda: _fetch_margin_detail(ds))
            except Exception as e:
                logger.warning(f"[margin_trading] 处理异常: {e}")
                df = None
            if df is None or df.empty:
                continue
            # 兼容沪(标的证券代码/融资买入额)与深(证券代码/融资买入额)列名
            code_col = next((c for c in df.columns if "证券代码" in str(c) or "标的证券代码" in str(c)), None)
            buy_col = next((c for c in df.columns if "融资买入额" in str(c)), None)
            if not code_col or not buy_col:
                continue
            sub = df[df[code_col].astype(str).str.zfill(6) == code]
            if sub.empty:
                continue
            try:
                rzmr = float(pd.to_numeric(sub.iloc[0][buy_col], errors="coerce"))
            except Exception as e:
                logger.warning(f"[margin_trading] 处理异常: {e}")
                continue
            if pd.isna(rzmr):
                continue
            return {"date": d.strftime("%Y-%m-%d"), "rzmr": rzmr}
        return None

    try:
        return _cached(1800, f"stock_margin_buy_{code}", _fn)
    except Exception as e:
        logger.warning(f"[margin_trading] 处理异常: {e}")
        return None