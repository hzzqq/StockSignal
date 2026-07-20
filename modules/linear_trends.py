"""
线性表达组件（趋势线 / 面积线）

把以下功能模块统一实现为「线性表达」（趋势线 / 面积线 / 多线对比）：
1. 北向资金历史序列（当日成交净买额 + 历史累计净买额）——多周期趋势线
2. 个股主力资金逐日趋势（逐日主力净流入）——逐日趋势线
3. 三大指数走势对比（上证 / 深证成指 / 创业板指，归一化）——多线对比
4. 大盘主力资金累计净流入（累计求和）——累计面积 / 趋势线

全部：经本地代理 + 关闭证书校验（复用 modules.fundflow 的代理补丁）、
TTL 缓存、网络失败兜底空 DataFrame，避免页面红错。
适配项目亮/暗主题（自包含 _fig_base，与 F_资金流向 / margin_trading 配色一致）。
A股配色：净流入 / 涨 = 红，净流出 / 跌 = 绿。
"""
from datetime import datetime, timedelta
import logging

import pandas as pd
import plotly.graph_objects as go

from modules.fundflow import (
    _ensure_proxy_and_ssl,
    _cached,
    _retry_with_backoff,
)
from modules.fetcher import StockFetcher

_ensure_proxy_and_ssl()

_logger = logging.getLogger(__name__)

# A股配色：净流入/涨=红、净流出/跌=绿
UP = "#ee2a2a"      # 红（流入 / 涨）
DOWN = "#1aa260"    # 绿（流出 / 跌）

# 指数配色
_IDX_COLORS = {
    "sh000001": "#7c5cff",   # 上证
    "sz399001": "#ef5da8",   # 深证成指
    "sz399006": "#2b8aef",   # 创业板指
}
_IDX_NAMES = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
}


def _parse_date(d):
    try:
        if d is None or (isinstance(d, float) and pd.isna(d)):
            return None
        if isinstance(d, pd.Timestamp):
            return d.strftime("%Y-%m-%d")
        if isinstance(d, datetime):
            return d.strftime("%Y-%m-%d")
        return str(d)[:10]
    except Exception:
        return None


def _to_yi(x):
    """把 元 转换为 亿元（float）。失败返回 None。"""
    try:
        return float(x) / 1e8
    except Exception:
        return None


def _fig_base(dark_mode):
    base = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=60, r=60, t=50, b=40),
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


# ───────────────────────── 1. 北向资金历史序列 ─────────────────────────
@_retry_with_backoff(max_retries=3, base_delay=1.0)
def _fetch_northbound_hist_raw():
    import akshare as ak
    df = ak.stock_hsgt_hist_em(symbol="北向资金")
    if df is None or df.empty:
        return pd.DataFrame()
    return df.copy()


def get_northbound_history_series():
    """北向资金历史序列（东方财富 stock_hsgt_hist_em）。

    返回 DataFrame(date, net_buy_yi, cumulative_yi)：
      - net_buy_yi   : 当日成交净买额（亿元，可正可负）
      - cumulative_yi: 历史累计净买额（亿元）
    交易所自 2024-08-16 起停止披露实时净买额，但历史序列在该日前仍有真实数值，
    本函数返回完整时间序列，供线性趋势图使用。
    网络最终失败返回空 DataFrame。
    """
    def _fn():
        try:
            df = _fetch_northbound_hist_raw()
        except Exception as e:
            _logger.warning(f"get_northbound_history_series 获取失败：{e}")
            return pd.DataFrame()
        if df is None or df.empty:
            return pd.DataFrame()
        out = pd.DataFrame()
        try:
            if "日期" in df.columns:
                out["date"] = df["日期"].apply(_parse_date)
        except Exception:
            return pd.DataFrame()
        if out.empty:
            return pd.DataFrame()
        if "当日成交净买额" in df.columns:
            out["net_buy_yi"] = pd.to_numeric(df["当日成交净买额"], errors="coerce").apply(_to_yi)
        else:
            out["net_buy_yi"] = pd.NA
        if "历史累计净买额" in df.columns:
            out["cumulative_yi"] = pd.to_numeric(df["历史累计净买额"], errors="coerce").apply(_to_yi)
        else:
            out["cumulative_yi"] = pd.NA
        out = out.dropna(subset=["date"]).reset_index(drop=True)
        return out
    return _cached(1800, "northbound_hist_series", _fn)


def plot_northbound_history(df, dark_mode=False):
    """北向资金历史趋势：净买额（面积线，左轴） + 历史累计净买额（线，右轴）。"""
    fig = go.Figure()
    if df is None or df.empty:
        fig.update_layout(title="暂无北向资金历史数据", **_fig_base(dark_mode), height=360)
        return fig
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["net_buy_yi"], name="当日净买额(亿)",
        mode="lines", fill="tozeroy",
        line=dict(color="#7c5cff", width=1.8),
        fillcolor="rgba(124,92,255,0.12)",
        hovertemplate="%{x}<br>当日净买额：%{y:.2f}亿<extra></extra>",
        yaxis="y",
    ))
    if "cumulative_yi" in df.columns and df["cumulative_yi"].notna().any():
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["cumulative_yi"], name="历史累计净买额(亿)",
            mode="lines", line=dict(color="#2b8aef", width=2.2),
            hovertemplate="%{x}<br>历史累计：%{y:.0f}亿<extra></extra>",
            yaxis="y2",
        ))
    layout = _fig_base(dark_mode)
    layout.update(
        title="北向资金历史趋势（净买额 / 累计净买额）",
        height=380,
        yaxis=dict(title="当日净买额(亿)", side="left", showgrid=True),
        yaxis2=dict(title="历史累计(亿)", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", yanchor="top", y=-0.22, x=0.5, xanchor="center"),
    )
    fig.update_layout(**layout)
    fig.update_xaxes(tickangle=-30)
    return fig


# ───────────────────────── 2. 个股主力资金逐日趋势 ─────────────────────────
@_retry_with_backoff(max_retries=3, base_delay=1.0)
def _fetch_individual_real(code6, market):
    import akshare as ak
    df = ak.stock_individual_fund_flow(stock=code6, market=market)
    if df is None or df.empty:
        return pd.DataFrame()
    return df.copy()


def _estimate_individual_series(code, days):
    """量价模型估算逐日主力净流入（离线兜底，明确标注估算）。"""
    try:
        f = StockFetcher()
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=days + 5)).strftime("%Y-%m-%d")
        df = f.get_daily(code, start=start, end=end)
        if df is None or df.empty or len(df) < 2:
            return pd.DataFrame()
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
            return pd.DataFrame()
        df = df.tail(days).reset_index(drop=True)
        rows = []
        for _, r in df.iterrows():
            high, low, close, vol = r["high"], r["low"], r["close"], r["volume"]
            d = r["date"]
            try:
                d = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)
            except Exception:
                d = str(d)
            if high == low or vol in (0, None):
                rows.append({"date": d, "main_net": 0.0, "super_net": 0.0, "big_net": 0.0})
                continue
            vwap = (high + low + close) / 3.0
            mf = ((close - low) - (high - close)) / (high - low) * vol * vwap
            sign = 1 if mf >= 0 else -1
            rows.append({
                "date": d,
                "main_net": mf,
                "super_net": abs(mf) * 0.35 * sign,
                "big_net": abs(mf) * 0.65 * sign,
            })
        return pd.DataFrame(rows)
    except Exception as e:
        _logger.warning(f"_estimate_individual_series 失败：{e}")
        return pd.DataFrame()


def get_individual_fund_flow_series(code, days=60):
    """个股主力资金逐日趋势（真实优先 + 量价估算兜底）。

    返回 DataFrame(date, main_net, super_net, big_net)：
      - main_net : 主力净流入（元）
      - super_net: 超大单净流入（元，估算时按经验比例拆分）
      - big_net  : 大单净流入（元）
      - source   : 在 attrs 中标记（'akshare' / 'estimate' / 'none'）
    网络/接口失败返回空 DataFrame。
    """
    code6 = str(code).zfill(6)
    market = "sh" if code6.startswith(("6", "9")) else "sz"

    def _real_fn():
        try:
            df = _fetch_individual_real(code6, market)
        except Exception as e:
            _logger.warning(f"个股真实资金流获取失败 {code6}：{e}")
            return None
        if df is None or df.empty:
            return None
        out = pd.DataFrame()
        out["date"] = df["日期"].apply(_parse_date) if "日期" in df.columns else pd.Series([None] * len(df))
        for src, dst in (("主力净流入-净额", "main_net"), ("主力净流入", "main_net"),
                          ("超大单净流入-净额", "super_net"), ("超大单净流入", "super_net"),
                          ("大单净流入-净额", "big_net"), ("大单净流入", "big_net")):
            if src in df.columns:
                out[dst] = pd.to_numeric(df[src], errors="coerce")
        out = out.dropna(subset=["date"]).reset_index(drop=True)
        if out.empty:
            return None
        return out

    def _fn():
        real = _real_fn()
        if real is not None and not real.empty:
            real.attrs["source"] = "akshare"
            return real
        est = _estimate_individual_series(code6, days)
        if est is not None and not est.empty:
            est.attrs["source"] = "estimate"
            return est
        empty = pd.DataFrame(columns=["date", "main_net", "super_net", "big_net"])
        empty.attrs["source"] = "none"
        return empty

    df = _cached(600, f"individual_series_{code6}_{days}", _fn)
    return df


def plot_individual_series(df, name="", code="", dark_mode=False):
    """个股主力资金逐日趋势：主力净流入（面积线，主） + 超大单/大单（虚线，默认隐藏）。"""
    fig = go.Figure()
    if df is None or df.empty or "main_net" not in df.columns:
        fig.update_layout(title="暂无个股资金趋势数据", **_fig_base(dark_mode), height=360)
        return fig
    has_main = df["main_net"].notna().any()
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["main_net"], name="主力净流入(元)",
        mode="lines", fill="tozeroy" if has_main else None,
        line=dict(color=UP, width=2.2),
        fillcolor="rgba(238,42,42,0.10)",
        hovertemplate="%{x}<br>主力净流入：%{y:,.0f}元<extra></extra>",
    ))
    if "super_net" in df.columns and df["super_net"].notna().any():
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["super_net"], name="超大单净流入(元)",
            mode="lines", line=dict(width=1.4, dash="dot"),
            hovertemplate="%{x}<br>超大单：%{y:,.0f}元<extra></extra>",
            visible="legendonly",
        ))
    if "big_net" in df.columns and df["big_net"].notna().any():
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["big_net"], name="大单净流入(元)",
            mode="lines", line=dict(width=1.4, dash="dot"),
            hovertemplate="%{x}<br>大单：%{y:,.0f}元<extra></extra>",
            visible="legendonly",
        ))
    title = f"{name} {code} 主力资金逐日趋势".strip()
    layout = _fig_base(dark_mode)
    layout.update(
        title=title or "个股主力资金逐日趋势",
        height=380,
        yaxis=dict(title="主力净流入(元)", side="left", showgrid=True),
        legend=dict(orientation="h", yanchor="top", y=-0.22, x=0.5, xanchor="center"),
    )
    fig.update_layout(**layout)
    fig.update_xaxes(tickangle=-30)
    return fig


# ───────────────────────── 3. 三大指数走势对比 ─────────────────────────
@_retry_with_backoff(max_retries=3, base_delay=1.0)
def _fetch_index(symbol):
    import akshare as ak
    df = ak.stock_zh_index_daily(symbol=symbol)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["date"] = df["date"].apply(_parse_date)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df[["date", "close"]].rename(columns={"date": "date", "close": symbol})


def get_index_series(days=180):
    """三大指数日线收盘价（上证 sh000001 / 深证成指 sz399001 / 创业板指 sz399006）。

    返回 DataFrame(date, sh000001, sz399001, sz399006)。
    网络失败返回空 DataFrame。
    """
    def _fn():
        try:
            idx000001 = _fetch_index("sh000001")
            idx399001 = _fetch_index("sz399001")
            idx399006 = _fetch_index("sz399006")
        except Exception as e:
            _logger.warning(f"get_index_series 获取失败：{e}")
            return pd.DataFrame()
        dfs = [d for d in (idx000001, idx399001, idx399006) if not d.empty]
        if not dfs:
            return pd.DataFrame()
        df = dfs[0]
        for d in dfs[1:]:
            df = df.merge(d, on="date", how="outer")
        df = df.sort_values("date").reset_index(drop=True)
        if len(df) > days:
            df = df.tail(days).reset_index(drop=True)
        return df
    return _cached(900, f"index_series_{days}", _fn)


def plot_index_series(df, dark_mode=False):
    """三大指数走势对比（归一化，起点=100），多线对比。"""
    fig = go.Figure()
    if df is None or df.empty:
        fig.update_layout(title="暂无指数走势数据", **_fig_base(dark_mode), height=360)
        return fig
    base = _fig_base(dark_mode)
    for sym in ("sh000001", "sz399001", "sz399006"):
        if sym not in df.columns:
            continue
        s = pd.to_numeric(df[sym], errors="coerce").dropna()
        if s.empty:
            continue
        first = s.iloc[0]
        if not first or pd.isna(first):
            continue
        norm = (s / first * 100.0).round(2)
        dates = df.loc[s.index, "date"]
        fig.add_trace(go.Scatter(
            x=dates, y=norm, name=_IDX_NAMES.get(sym, sym),
            mode="lines", line=dict(color=_IDX_COLORS.get(sym, "#888"), width=2),
            hovertemplate="%{x}<br>" + _IDX_NAMES.get(sym, sym) + "：%{y:.2f}<extra></extra>",
        ))
    if not fig.data:
        fig.update_layout(title="暂无指数走势数据", **base, height=360)
        return fig
    layout = base
    layout.update(
        title="三大指数走势对比（归一化，起点=100）",
        height=380,
        yaxis=dict(title="归一化点位", side="left", showgrid=True),
        legend=dict(orientation="h", yanchor="top", y=-0.22, x=0.5, xanchor="center"),
    )
    fig.update_layout(**layout)
    fig.update_xaxes(tickangle=-30)
    return fig


# ───────────────────────── 4. 大盘主力资金累计净流入 ─────────────────────────
def get_market_cumulative_series(days=60):
    """大盘主力资金累计净流入序列。

    复用 fundflow.get_market_fund_flow 获取逐日 主力净流入-净额（亿元），
    做累计求和得到累计净流入（亿元）。
    返回 DataFrame(date, main_net, cumulative)。
    """
    from modules.fundflow import get_market_fund_flow
    def _fn():
        try:
            df = get_market_fund_flow(days=days)
        except Exception as e:
            _logger.warning(f"get_market_cumulative_series 获取失败：{e}")
            return pd.DataFrame()
        if df is None or df.empty or "主力净流入-净额" not in df.columns:
            return pd.DataFrame()
        out = pd.DataFrame()
        out["date"] = df["日期"].apply(_parse_date) if "日期" in df.columns else pd.Series([None] * len(df))
        out["main_net"] = pd.to_numeric(df["主力净流入-净额"], errors="coerce")
        out = out.dropna(subset=["date"]).reset_index(drop=True)
        if out.empty:
            return pd.DataFrame()
        out["cumulative"] = out["main_net"].cumsum()
        return out
    return _cached(600, f"market_cumulative_{days}", _fn)


def plot_market_cumulative(df, dark_mode=False):
    """大盘主力资金累计净流入（面积线，主） + 逐日主力净流入（细线，右轴）。"""
    fig = go.Figure()
    if df is None or df.empty or "cumulative" not in df.columns:
        fig.update_layout(title="暂无大盘累计资金数据", **_fig_base(dark_mode), height=360)
        return fig
    last = df["cumulative"].iloc[-1]
    cum_color = UP if (last is not None and last >= 0) else DOWN
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["cumulative"], name="累计主力净流入(亿)",
        mode="lines", fill="tozeroy",
        line=dict(color=cum_color, width=2.4),
        fillcolor="rgba(238,42,42,0.10)" if cum_color == UP else "rgba(26,162,96,0.10)",
        hovertemplate="%{x}<br>累计净流入：%{y:.2f}亿<extra></extra>",
        yaxis="y",
    ))
    if "main_net" in df.columns and df["main_net"].notna().any():
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["main_net"], name="当日主力净流入(亿)",
            mode="lines", line=dict(width=1.2, color="#f5a623"),
            hovertemplate="%{x}<br>当日净流入：%{y:.2f}亿<extra></extra>",
            yaxis="y2",
        ))
    layout = _fig_base(dark_mode)
    layout.update(
        title="大盘主力资金累计净流入趋势",
        height=380,
        yaxis=dict(title="累计净流入(亿)", side="left", showgrid=True),
        yaxis2=dict(title="当日净流入(亿)", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", yanchor="top", y=-0.22, x=0.5, xanchor="center"),
    )
    fig.update_layout(**layout)
    fig.update_xaxes(tickangle=-30)
    return fig
