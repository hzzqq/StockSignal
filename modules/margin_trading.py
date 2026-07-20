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
import time

import pandas as pd
import plotly.graph_objects as go

# 复用 fundflow 的代理/SSL 补丁，确保 akshare 经本地代理访问
from modules.fundflow import _ensure_proxy_and_ssl

_ensure_proxy_and_ssl()

# 简易 TTL 缓存
_MARGIN_CACHE = {}


def _cached(ttl, key, fn):
    now = time.time()
    hit = _MARGIN_CACHE.get(key)
    if hit and (now - hit[0]) < ttl:
        return hit[1]
    val = fn()
    _MARGIN_CACHE[key] = (now, val)
    return val


def _retry(max_retries=3, base_delay=1.0):
    """指数退避重试，缓解偶发连接中断。"""
    def deco(fn):
        def wrapper(*args, **kwargs):
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
    if pd.isna(d):
        return None
    if isinstance(d, pd.Timestamp):
        return d.strftime("%Y-%m-%d")
    if isinstance(d, datetime):
        return d.strftime("%Y-%m-%d")
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
        sh = _fetch_margin_sh()
        sz = _fetch_margin_sz()
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

        # 合并三大指数
        idx000001 = _fetch_index("sh000001")
        idx399001 = _fetch_index("sz399001")
        idx399006 = _fetch_index("sz399006")
        for idx_df in (idx000001, idx399001, idx399006):
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
            import logging
            logging.getLogger(__name__).warning(f"get_margin_trading_data 最终失败：{e}")
            return pd.DataFrame()
    return _cached(600, f"margin_trading_{days}", _fn)


def _to_yi(x):
    """把 元 转换为 亿元 文本。"""
    try:
        return float(x) / 1e8
    except Exception:
        return None


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


def plot_margin_trend(df, dark_mode=False, metric="rzmr"):
    """绘制融资趋势图。

    metric:
      - "rzmr": 融资买入额（默认，与 zip 标题「融资买入额趋势图」一致）
      - "rzye": 融资余额
    返回 Plotly Figure（双 Y 轴：左轴金额，右轴指数）。
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

    colors = {
        "amount": "#ee2a2a" if metric == "rzmr" else "#2b8aef",
        "sh": "#f59e0b",
        "sz": "#10b981",
        "000001": "#7c5cff",
        "399001": "#ef5da8",
        "399006": "#2b8aef",
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

    # 指数（右轴）
    for idx_symbol, idx_col in [("上证", "sh000001"), ("深证成指", "sz399001"), ("创业板指", "sz399006")]:
        if idx_col in df.columns:
            fig.add_trace(go.Scatter(
                x=df["日期"], y=df[idx_col], name=idx_symbol,
                mode="lines", line=dict(width=1.6),
                hovertemplate="%{x}<br>%{data.name}：%{y:.2f}<extra></extra>",
                yaxis="y2",
            ))

    title = "融资买入额趋势（沪+深）" if metric == "rzmr" else "融资余额趋势（沪+深）"
    layout = _fig_base(dark_mode)
    layout.update(
        title=title,
        height=420,
        yaxis=dict(title="金额（亿元）", side="left", showgrid=True),
        yaxis2=dict(title="指数点位", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", yanchor="top", y=-0.22, x=0.5, xanchor="center"),
    )
    fig.update_layout(**layout)
    fig.update_xaxes(tickangle=-30)
    return fig


def get_latest_margin_summary():
    """返回最近一个交易日的融资 summary 字典，用于页面顶部指标卡。"""
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
        "rzmr_change_yi": _to_yi(row.get("total_rzmr")) - _to_yi(prev.get("total_rzmr")),
        "rzye_change_yi": _to_yi(row.get("total_rzye")) - _to_yi(prev.get("total_rzye")),
    }
