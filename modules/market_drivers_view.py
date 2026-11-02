"""市场驱动力 —— 面板渲染与温度评分（market_drivers 拆分·展示域）。

职责：五维情绪面板绘图（plot_drivers_panel）、市场温度合成与档位（_market_temp 等）。
零业务逻辑改动：源码自 ``modules/market_drivers.py`` 原样搬运。
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from modules.market_drivers_core import DIMS, _norm100_aligned

logger = logging.getLogger("modules.market_drivers")

_DIM_COLORS = {
    "资金": "#ee2a2a", "情绪": "#7c5cff", "估值": "#2b8aef",
    "宏观": "#f59e0b", "技术": "#10b981",
}

_REF_COLOR = "#8a8a8a"

_MARKET_TEMP_DEFAULT = 50.0

_DIR = {
    "adl": 1, "adr": 1, "nhnl": 1,
    "margin_balance": 1, "margin_net": 1, "north_net": 1,
    "vix": -1, "pcr": -1, "zt_ratio": 1,
    "pe_pct": 1, "div_yield": -1,
    "m2_yoy": 1, "shr_zgm": 1, "yield_spread": 1, "pmi": 1,
    "rsi": 1, "bias": 1, "boll": 0, "idx_ma5": 0, "idx_ma20": 0,
}

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

def _score_one_dim(series, direction):
    """单指标方向得分（隔离出的纯 helper，便于单测）。

    取最新值在自身历史分布中的分位（0-100）：方向为正时越高越热，
    方向为负时越高越冷。样本不足(<3)或非有限返回 None。
    """
    try:
        s = pd.to_numeric(series, errors="coerce").dropna()
    except Exception as e:  # noqa
        logger.warning(f"[market_drivers] 处理异常: {e}")
        return None
    if len(s) < 3:
        return None
    try:
        pct = float(s.rank(pct=True).iloc[-1])
    except Exception as e:  # noqa
        logger.warning(f"[market_drivers] 处理异常: {e}")
        return None
    if not np.isfinite(pct):
        return None
    return float(pct * 100.0) if direction > 0 else float((1.0 - pct) * 100.0)

def _market_temp(df):
    """综合「市场温度」0-100。

    对 _DIR 中每个有数据且方向非零的指标，取其在历史分布中的分位并加权，
    返回各指标得分的均值。退化输入（df 为 None/非 DataFrame/空、所有指标
    缺列或样本不足、出现非有限均值）一律返回安全默认 _MARKET_TEMP_DEFAULT，
    绝不抛错。
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return _MARKET_TEMP_DEFAULT
    subs = []
    for k, d in _DIR.items():
        if d == 0 or k not in df.columns:
            continue
        sc = _score_one_dim(df[k], d)
        if sc is not None:
            subs.append(sc)
    if not subs:
        return _MARKET_TEMP_DEFAULT
    try:
        m = float(np.mean(subs))
    except Exception as e:  # noqa
        logger.warning(f"[market_drivers] 处理异常: {e}")
        return _MARKET_TEMP_DEFAULT
    return m if np.isfinite(m) else _MARKET_TEMP_DEFAULT

def _temp_level(t):
    """将温度值(0-100)映射为 (等级, emoji, 颜色)。

    输入非有限或 None 时返回安全中性默认，不抛错。
    """
    if t is None or not isinstance(t, (int, float)) or not np.isfinite(t):
        return ("未知", "—", "#888888")
    if t >= 75:
        return ("过热", "🚨", "#ee2a2a")
    if t >= 60:
        return ("偏热", "🔥", "#f59e0b")
    if t >= 40:
        return ("中性", "⚖️", "#2b8aef")
    if t >= 20:
        return ("偏冷", "🌡️", "#16c2c2")
    return ("冰点", "🥶", "#3b82f6")
