"""
线性表达组件（趋势线 / 面积线）

把以下功能模块统一实现为「线性表达」（趋势线 / 面积线 / 多线对比）：
1. 北向资金历史序列（当日成交净买额 + 历史累计净买额）——多周期趋势线
2. 个股主力资金逐日趋势（逐日主力净流入）——逐日趋势线
3. 三大指数走势对比（上证 / 深证成指 / 创业板指，归一化）——多线对比
4. 大盘主力资金累计净流入（累计求和）——累计面积 / 趋势线
5. 行业板块指数价格趋势（行业指数日线收盘价，归一化多线对比）
6. ETF 价格趋势（宽基 / 行业 / 跨境 ETF 日线收盘价，归一化多线对比）

所有线性图均支持「区间选择 date_range」与「均线叠加 ma_periods」交互（见 _slice_date_range / _add_ma_traces）。

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


def _slice_date_range(df, date_range):
    """按 (start, end) 字符串/日期切片；date_range 为 None 或非法则原样返回。"""
    if not date_range:
        return df
    try:
        start, end = date_range
    except Exception:
        return df
    s = _parse_date(start)
    e = _parse_date(end)
    if s is None and e is None:
        return df
    d = df.copy()
    if "date" not in d.columns:
        return d
    if s is not None:
        d = d[d["date"] >= s]
    if e is not None:
        d = d[d["date"] <= e]
    return d.reset_index(drop=True)


def _add_ma_traces(fig, x, y, name, color, ma_periods, visible_default=True, ma_type="sma"):
    """在原序列上叠加均线（虚线、降透明度）。ma_type: 'sma' | 'ema'。"""
    if not ma_periods:
        return
    s = pd.to_numeric(y, errors="coerce")
    ma_label = "EMA" if ma_type == "ema" else "MA"
    for p in ma_periods:
        try:
            p = int(p)
        except Exception:
            continue
        if p <= 1:
            continue
        minp = max(2, p // 2)
        if ma_type == "ema":
            ma = s.ewm(span=p, adjust=False, min_periods=minp).mean()
        else:
            ma = s.rolling(p, min_periods=minp).mean()
        fig.add_trace(go.Scatter(
            x=x, y=ma, name=f"{name}·{ma_label}{p}",
            mode="lines", line=dict(color=color, width=1.2, dash="dot"),
            opacity=0.7,
            hovertemplate="%{x}<br>" + str(name) + f"·{ma_label}{p}：%{{y:.2f}}<extra></extra>",
            visible=("legendonly" if not visible_default else True),
        ))


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


def plot_northbound_history(df, dark_mode=False, date_range=None, ma_periods=(),
                             ma_type="sma", show_baseline=True):
    """北向资金历史趋势：净买额（面积线，左轴） + 历史累计净买额（线，右轴）。

    支持 date_range=(start,end) 区间切片与 ma_periods=(5,20,...) 均线叠加。
    ma_type: 'sma' | 'ema'；show_baseline: 是否绘制零线（净买额可为负）。
    """
    fig = go.Figure()
    if df is None or df.empty:
        fig.update_layout(title="暂无北向资金历史数据", **_fig_base(dark_mode), height=360)
        return fig
    d = _slice_date_range(df, date_range)
    if d is None or d.empty:
        fig.update_layout(title="暂无北向资金历史数据（区间内）", **_fig_base(dark_mode), height=360)
        return fig
    fig.add_trace(go.Scatter(
        x=d["date"], y=d["net_buy_yi"], name="当日净买额(亿)",
        mode="lines", fill="tozeroy",
        line=dict(color="#7c5cff", width=1.8),
        fillcolor="rgba(124,92,255,0.12)",
        hovertemplate="%{x}<br>当日净买额：%{y:.2f}亿<extra></extra>",
        yaxis="y",
    ))
    _add_ma_traces(fig, d["date"], d["net_buy_yi"], "当日净买额(亿)", "#7c5cff", ma_periods,
                   visible_default=True, ma_type=ma_type)
    if "cumulative_yi" in d.columns and d["cumulative_yi"].notna().any():
        fig.add_trace(go.Scatter(
            x=d["date"], y=d["cumulative_yi"], name="历史累计净买额(亿)",
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
    if show_baseline:
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.35,
                      annotation_text="零线", annotation_position="bottom right")
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


def plot_individual_series(df, name="", code="", dark_mode=False, date_range=None, ma_periods=(),
                           ma_type="sma", show_baseline=True):
    """个股主力资金逐日趋势：主力净流入（面积线，主） + 超大单/大单（虚线，默认隐藏）。

    支持 date_range 区间切片与 ma_periods 均线叠加（对主力净流入序列）。
    ma_type: 'sma' | 'ema'；show_baseline: 是否绘制零线。
    """
    fig = go.Figure()
    if df is None or df.empty or "main_net" not in df.columns:
        fig.update_layout(title="暂无个股资金趋势数据", **_fig_base(dark_mode), height=360)
        return fig
    d = _slice_date_range(df, date_range)
    if d is None or d.empty or "main_net" not in d.columns:
        fig.update_layout(title="暂无个股资金趋势数据（区间内）", **_fig_base(dark_mode), height=360)
        return fig
    has_main = d["main_net"].notna().any()
    fig.add_trace(go.Scatter(
        x=d["date"], y=d["main_net"], name="主力净流入(元)",
        mode="lines", fill="tozeroy" if has_main else None,
        line=dict(color=UP, width=2.2),
        fillcolor="rgba(238,42,42,0.10)",
        hovertemplate="%{x}<br>主力净流入：%{y:,.0f}元<extra></extra>",
    ))
    _add_ma_traces(fig, d["date"], d["main_net"], "主力净流入(元)", UP, ma_periods,
                   visible_default=True, ma_type=ma_type)
    if "super_net" in d.columns and d["super_net"].notna().any():
        fig.add_trace(go.Scatter(
            x=d["date"], y=d["super_net"], name="超大单净流入(元)",
            mode="lines", line=dict(width=1.4, dash="dot"),
            hovertemplate="%{x}<br>超大单：%{y:,.0f}元<extra></extra>",
            visible="legendonly",
        ))
    if "big_net" in d.columns and d["big_net"].notna().any():
        fig.add_trace(go.Scatter(
            x=d["date"], y=d["big_net"], name="大单净流入(元)",
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
    if show_baseline:
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.35,
                      annotation_text="零线", annotation_position="bottom right")
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


def plot_index_series(df, dark_mode=False, date_range=None, ma_periods=(),
                       ma_type="sma", show_baseline=True):
    """三大指数走势对比（归一化，起点=100），多线对比。

    支持 date_range 区间切片（起点=区间内首值）与 ma_periods 均线叠加。
    ma_type: 'sma' | 'ema'；show_baseline: 是否绘制 100 基准线。
    """
    fig = go.Figure()
    if df is None or df.empty:
        fig.update_layout(title="暂无指数走势数据", **_fig_base(dark_mode), height=360)
        return fig
    d = _slice_date_range(df, date_range)
    if d is None or d.empty:
        fig.update_layout(title="暂无指数走势数据（区间内）", **_fig_base(dark_mode), height=360)
        return fig
    base = _fig_base(dark_mode)
    for sym in ("sh000001", "sz399001", "sz399006"):
        if sym not in d.columns:
            continue
        s = pd.to_numeric(d[sym], errors="coerce").dropna()
        if s.empty:
            continue
        first = s.iloc[0]
        if not first or pd.isna(first):
            continue
        norm = (s / first * 100.0).round(2)
        dates = d.loc[s.index, "date"]
        disp = _IDX_NAMES.get(sym, sym)
        color = _IDX_COLORS.get(sym, "#888")
        fig.add_trace(go.Scatter(
            x=dates, y=norm, name=disp,
            mode="lines", line=dict(color=color, width=2),
            hovertemplate="%{x}<br>" + disp + "：%{y:.2f}<extra></extra>",
        ))
        _add_ma_traces(fig, dates, norm, disp, color, ma_periods, visible_default=True, ma_type=ma_type)
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
    if show_baseline:
        fig.add_hline(y=100, line_dash="dash", line_color="gray", opacity=0.35,
                      annotation_text="基准 100", annotation_position="bottom right")
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


def plot_market_cumulative(df, dark_mode=False, date_range=None, ma_periods=(),
                           ma_type="sma", show_baseline=True):
    """大盘主力资金累计净流入（面积线，主） + 逐日主力净流入（细线，右轴）。

    支持 date_range 区间切片与 ma_periods 均线叠加（对累计序列）。
    ma_type: 'sma' | 'ema'；show_baseline: 是否绘制零线。
    """
    fig = go.Figure()
    if df is None or df.empty or "cumulative" not in df.columns:
        fig.update_layout(title="暂无大盘累计资金数据", **_fig_base(dark_mode), height=360)
        return fig
    d = _slice_date_range(df, date_range)
    if d is None or d.empty or "cumulative" not in d.columns:
        fig.update_layout(title="暂无大盘累计资金数据（区间内）", **_fig_base(dark_mode), height=360)
        return fig
    last = d["cumulative"].iloc[-1]
    cum_color = UP if (last is not None and last >= 0) else DOWN
    fig.add_trace(go.Scatter(
        x=d["date"], y=d["cumulative"], name="累计主力净流入(亿)",
        mode="lines", fill="tozeroy",
        line=dict(color=cum_color, width=2.4),
        fillcolor="rgba(238,42,42,0.10)" if cum_color == UP else "rgba(26,162,96,0.10)",
        hovertemplate="%{x}<br>累计净流入：%{y:.2f}亿<extra></extra>",
        yaxis="y",
    ))
    _add_ma_traces(fig, d["date"], d["cumulative"], "累计主力净流入(亿)", cum_color, ma_periods,
                   visible_default=True, ma_type=ma_type)
    if "main_net" in d.columns and d["main_net"].notna().any():
        fig.add_trace(go.Scatter(
            x=d["date"], y=d["main_net"], name="当日主力净流入(亿)",
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
    if show_baseline:
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.35,
                      annotation_text="零线", annotation_position="bottom right")
    fig.update_xaxes(tickangle=-30)
    return fig


# ───────────────────────── 5. 行业板块指数价格趋势（线性表达） ─────────────────────────
# 行业板块无「逐日资金流」时间序列 API，改用行业指数日线收盘价做归一化多线对比，
# 更能反映板块相对强弱走势。数据：ak.stock_board_industry_hist_em(period="日k")。
_FALLBACK_INDUSTRIES = [
    "半导体", "软件开发", "银行", "证券", "白酒", "医药", "新能源",
    "汽车", "煤炭", "房地产", "有色金属", "电力",
]


@_retry_with_backoff(max_retries=2, base_delay=1.0)
def _fetch_industry_names():
    import akshare as ak
    df = ak.stock_board_industry_name_em()
    if df is None or df.empty:
        return []
    for col in ("板块名称", "行业", "name"):
        if col in df.columns:
            return [str(x) for x in df[col].dropna().tolist()]
    if len(df.columns) >= 1:
        return [str(x) for x in df.iloc[:, 0].dropna().tolist()]
    return []


@_retry_with_backoff(max_retries=2, base_delay=1.0)
def _fetch_industry_hist(symbol, start_date, end_date):
    import akshare as ak
    df = ak.stock_board_industry_hist_em(
        symbol=symbol, period="日k", start_date=start_date, end_date=end_date, adjust="")
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    close = pd.to_numeric(df["收盘"], errors="coerce") if "收盘" in df.columns else pd.Series([None] * len(df))
    out = pd.DataFrame({
        "date": df["日期"].apply(_parse_date) if "日期" in df.columns else pd.Series([None] * len(df)),
        symbol: close,
    })
    return out.dropna(subset=["date"]).reset_index(drop=True)


def get_industry_index_series(top_n=8, days=120):
    """行业板块指数日线收盘价（多行业），合并为宽表。

    返回 DataFrame(date, 行业A, 行业B, ...)。优先取硬编常见行业，再从全量行业名补足到 top_n。
    网络/接口失败返回空 DataFrame。
    """
    def _fn():
        try:
            names = _fetch_industry_names()
        except Exception as e:
            _logger.warning(f"行业名获取失败：{e}")
            names = []
        if not names:
            names = list(_FALLBACK_INDUSTRIES)
        selected = []
        for x in _FALLBACK_INDUSTRIES:
            if x in names and x not in selected:
                selected.append(x)
        for x in names:
            if x not in selected:
                selected.append(x)
        selected = selected[:top_n]
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=int(days * 1.6))).strftime("%Y%m%d")
        frames = {}
        for nm in selected:
            try:
                h = _fetch_industry_hist(nm, start, end)
            except Exception as e:
                _logger.warning(f"行业指数 {nm} 获取失败：{e}")
                h = None
            if h is None or h.empty:
                continue
            frames[nm] = h
        if not frames:
            return pd.DataFrame()
        base = None
        for nm, s in frames.items():
            base = s if base is None else base.merge(s, on="date", how="outer")
        base = base.sort_values("date").reset_index(drop=True)
        if len(base) > days:
            base = base.tail(days).reset_index(drop=True)
        return base
    return _cached(1800, f"industry_index_series_{top_n}_{days}", _fn)


# ───────────────────────── 6. ETF 价格趋势（线性表达） ─────────────────────────
# ETF 价格走势天然适合线性表达：宽基 / 行业 / 跨境 ETF 归一化多线对比。
# 数据：ak.fund_etf_hist_em(period="daily")。
_ETF_LIST = [
    ("510300", "沪深300ETF"),
    ("510500", "中证500ETF"),
    ("159915", "创业板ETF"),
    ("512660", "军工ETF"),
    ("512010", "医药ETF"),
    ("515030", "新能源ETF"),
    ("513100", "纳指ETF"),
    ("513180", "恒生科技ETF"),
]
ETF_NAMES_MAP = {code: nm for code, nm in _ETF_LIST}


@_retry_with_backoff(max_retries=2, base_delay=1.0)
def _fetch_etf_hist(symbol, start_date, end_date):
    import akshare as ak
    df = ak.fund_etf_hist_em(
        symbol=symbol, period="daily", start_date=start_date, end_date=end_date, adjust="")
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    close = pd.to_numeric(df["收盘"], errors="coerce") if "收盘" in df.columns else pd.Series([None] * len(df))
    out = pd.DataFrame({
        "date": df["日期"].apply(_parse_date) if "日期" in df.columns else pd.Series([None] * len(df)),
        symbol: close,
    })
    return out.dropna(subset=["date"]).reset_index(drop=True)


def get_etf_series(days=180):
    """ETF 日线收盘价（多只），合并为宽表。

    返回 DataFrame(date, etf_code1, etf_code2, ...)，列为 ETF 代码。
    网络/接口失败返回空 DataFrame。
    """
    def _fn():
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=int(days * 1.6))).strftime("%Y%m%d")
        frames = {}
        for code, _nm in _ETF_LIST:
            try:
                h = _fetch_etf_hist(code, start, end)
            except Exception as e:
                _logger.warning(f"ETF {code} 获取失败：{e}")
                h = None
            if h is None or h.empty:
                continue
            frames[code] = h
        if not frames:
            return pd.DataFrame()
        base = None
        for code, s in frames.items():
            base = s if base is None else base.merge(s, on="date", how="outer")
        base = base.sort_values("date").reset_index(drop=True)
        if len(base) > days:
            base = base.tail(days).reset_index(drop=True)
        return base
    return _cached(1800, f"etf_series_{days}", _fn)


# ───────────────────────── 共享：归一化多线对比（含区间切片 + 均线叠加 + 增强标注） ─────────────────────────
_PALETTE = ["#7c5cff", "#ef5da8", "#2b8aef", "#1aa260", "#f5a623", "#ee2a2a",
            "#16c2c2", "#8b5cf6", "#0ea5e9", "#f97316", "#84cc16", "#e11d48"]


def _golden_death_cross(xs, y, short_p, long_p):
    """检测两条均线的金叉/死叉点，返回 [(x, y), ...] 元组 (golden, death)。

    xs / y 为对齐的同索引序列；short_p < long_p。
    """
    s = pd.to_numeric(y, errors="coerce").reset_index(drop=True)
    xs2 = xs.reset_index(drop=True)
    minp = max(2, short_p // 2)
    short = s.rolling(short_p, min_periods=minp).mean()
    long = s.rolling(long_p, min_periods=max(2, long_p // 2)).mean()
    diff = short - long
    golden, death = [], []
    for i in range(1, len(diff)):
        if pd.isna(diff.iloc[i]) or pd.isna(diff.iloc[i - 1]):
            continue
        if diff.iloc[i - 1] <= 0 < diff.iloc[i]:
            golden.append((xs2.iloc[i], float(s.iloc[i])))
        elif diff.iloc[i - 1] >= 0 > diff.iloc[i]:
            death.append((xs2.iloc[i], float(s.iloc[i])))
    return golden, death


def _max_drawdown_idx(s):
    """返回 (peak_idx, trough_idx, mdd_ratio) 或 None。s 为带原始索引的数值序列。"""
    s = pd.to_numeric(s, errors="coerce")
    valid = s.dropna()
    if len(valid) < 2:
        return None
    peak_val = valid.iloc[0]
    peak_i = valid.index[0]
    mdd = 0.0
    mdd_peak_i = peak_i
    mdd_trough_i = peak_i
    for i in valid.index[1:]:
        v = s.loc[i]
        if v > peak_val:
            peak_val = v
            peak_i = i
        dd = (v - peak_val) / peak_val if peak_val != 0 else 0.0
        if dd < mdd:
            mdd = dd
            mdd_peak_i = peak_i
            mdd_trough_i = i
    if mdd >= 0:
        return None
    return mdd_peak_i, mdd_trough_i, mdd


def plot_normalized_multi(df, names_map=None, colors_map=None, title="",
                          y_title="归一化点位（起点=100）", dark_mode=False,
                          date_range=None, ma_periods=(), selected=None,
                          mode="normalized", show_baseline=True,
                          show_cross=False, show_drawdown=False, ma_type="sma"):
    """归一化多线对比（起点=100），支持区间切片、均线叠加与多种增强标注。

    参数：
      df        : 宽表，含 'date' 列 + 每个序列一列（列名为序列 key）。
      names_map : {key: 显示名}
      colors_map: {key: 颜色}
      date_range: (start, end) 区间切片
      ma_periods: 均线周期元组，如 (5, 20)
      selected  : 仅显示这些 key（序列多选）；None 显示全部
      mode      : 'normalized'（起点=100）| 'raw'（原始价格）
      show_baseline: 是否绘制基准线（归一化=100 / 原始=0）
      show_cross: 是否标注金叉/死叉（需 ma_periods 至少 2 个周期）
      show_drawdown: 是否标注最大回撤区间
      ma_type   : 'sma' | 'ema'
    序列数 ≤ 3 时均线默认可见；> 3 时均线默认进图例（legendonly）避免拥挤。
    """
    fig = go.Figure()
    if df is None or df.empty or "date" not in df.columns:
        fig.update_layout(title=title or "暂无数据", **_fig_base(dark_mode), height=360)
        return fig
    d = _slice_date_range(df, date_range)
    if d is None or d.empty:
        fig.update_layout(title=title or "暂无数据（区间内）", **_fig_base(dark_mode), height=360)
        return fig
    keys = [c for c in d.columns if c != "date"]
    if selected:
        keys = [k for k in keys if k in selected]
    ma_visible_default = len(keys) <= 3
    any_line = False
    for i, key in enumerate(keys):
        s = pd.to_numeric(d[key], errors="coerce").dropna()
        if s.empty:
            continue
        first = s.iloc[0]
        if mode == "normalized":
            if not first or pd.isna(first):
                continue
            y = (s / first * 100.0).round(2)
        else:
            y = s.round(4)
        xs = d.loc[s.index, "date"]
        disp = (names_map or {}).get(key, key)
        color = (colors_map or {}).get(key, _PALETTE[i % len(_PALETTE)])
        fig.add_trace(go.Scatter(
            x=xs, y=y, name=str(disp), mode="lines",
            line=dict(color=color, width=2),
            hovertemplate="%{x}<br>" + str(disp) + "：%{y:.2f}<extra></extra>",
        ))
        _add_ma_traces(fig, xs, y, str(disp), color, ma_periods,
                       visible_default=ma_visible_default, ma_type=ma_type)
        any_line = True
        # 最大回撤标注：基于原始价格序列，标记在区间图上
        if show_drawdown:
            dd = _max_drawdown_idx(s)
            if dd is not None:
                peak_i, trough_i, mdd = dd
                try:
                    px = d.loc[peak_i, "date"]
                    tx = d.loc[trough_i, "date"]
                except Exception:
                    px = xs.loc[peak_i] if peak_i in xs.index else None
                    tx = xs.loc[trough_i] if trough_i in xs.index else None
                if px is not None and tx is not None:
                    fig.add_vrect(x0=px, x1=tx, fillcolor="rgba(238,42,42,0.10)",
                                  line_width=0, layer="below", opacity=0.6)
                    fig.add_annotation(x=tx, y=float(y.loc[trough_i]),
                                       text=f"最大回撤 {mdd * 100:.1f}%",
                                       showarrow=True, arrowhead=2, ax=0, ay=30,
                                       font=dict(color="#ee2a2a", size=11))
        # 金叉/死叉标注（需至少两条均线）
        if show_cross and len(ma_periods) >= 2:
            sps = sorted(int(p) for p in ma_periods if int(p) > 1)
            if len(sps) >= 2:
                golden, death = _golden_death_cross(xs, y, sps[0], sps[1])
                for gx, gy in golden:
                    fig.add_trace(go.Scatter(x=[gx], y=[gy], mode="markers",
                        marker=dict(symbol="triangle-up", size=11, color="#1aa260"),
                        name="金叉", showlegend=False,
                        hovertemplate="金叉 %{x}<extra></extra>"))
                for dx, dy in death:
                    fig.add_trace(go.Scatter(x=[dx], y=[dy], mode="markers",
                        marker=dict(symbol="triangle-down", size=11, color="#ee2a2a"),
                        name="死叉", showlegend=False,
                        hovertemplate="死叉 %{x}<extra></extra>"))
    if not any_line:
        fig.update_layout(title=title or "暂无数据", **_fig_base(dark_mode), height=360)
        return fig
    if show_baseline:
        base_y = 100 if mode == "normalized" else 0
        fig.add_hline(y=base_y, line_dash="dash", line_color="gray", opacity=0.4,
                      annotation_text="基准线" if mode == "normalized" else "零线",
                      annotation_position="bottom right")
    layout = _fig_base(dark_mode)
    yt = "价格（元）" if mode == "raw" else y_title
    layout.update(
        title=title,
        height=420,
        yaxis=dict(title=yt, side="left", showgrid=True),
        legend=dict(orientation="h", yanchor="top", y=-0.24, x=0.5, xanchor="center"),
    )
    fig.update_layout(**layout)
    fig.update_xaxes(tickangle=-30)
    return fig


def to_trend_csv(df, names_map=None, selected=None, date_range=None):
    """把宽表按区间切片 + 过滤序列列后导出为 CSV 字符串（带 UTF-8 BOM，Excel 友好）。"""
    if df is None or df.empty:
        return ""
    d = _slice_date_range(df, date_range)
    if d is None or d.empty:
        return ""
    keys = [c for c in d.columns if c != "date"]
    if selected:
        keys = [k for k in keys if k in selected]
    if not keys:
        return ""
    out = d[["date"] + keys].copy()
    if names_map:
        out = out.rename(columns={k: names_map.get(k, k) for k in keys})
    return out.to_csv(index=False, encoding="utf-8-sig")


def plot_correlation_heatmap(df, names_map=None, selected=None, date_range=None,
                             dark_mode=False, title="收益率相关性热力图"):
    """所选序列的日收益率相关性热力图（颜色 RdBu，红=正相关，蓝=负相关）。"""
    fig = go.Figure()
    if df is None or df.empty or "date" not in df.columns:
        fig.update_layout(title=title or "暂无数据", **_fig_base(dark_mode), height=300)
        return fig
    d = _slice_date_range(df, date_range)
    if d is None or d.empty:
        fig.update_layout(title=title or "暂无数据", **_fig_base(dark_mode), height=300)
        return fig
    keys = [c for c in d.columns if c != "date"]
    if selected:
        keys = [k for k in keys if k in selected]
    keys = [k for k in keys if pd.to_numeric(d[k], errors="coerce").notna().any()]
    if len(keys) < 2:
        fig.update_layout(title="相关性需至少 2 个有效序列", **_fig_base(dark_mode), height=300)
        return fig
    rets = pd.DataFrame({k: pd.to_numeric(d[k], errors="coerce").pct_change() for k in keys}).dropna()
    if rets.empty or len(rets) < 2:
        fig.update_layout(title="样本不足，无法计算相关性", **_fig_base(dark_mode), height=300)
        return fig
    corr = rets.corr()
    labels = [(names_map or {}).get(k, k) for k in keys]
    heat = go.Heatmap(
        z=corr.values, x=labels, y=labels,
        colorscale="RdBu", zmid=0, zmin=-1, zmax=1,
        text=[[f"{v:.2f}" for v in row] for row in corr.values],
        texttemplate="%{text}", colorbar=dict(title="相关系数"),
    )
    fig.add_trace(heat)
    layout = _fig_base(dark_mode)
    layout.update(title=title or "收益率相关性热力图", height=420,
                  margin=dict(l=60, r=20, t=50, b=60))
    fig.update_layout(**layout)
    return fig

