"""
页面级共用 UI 助手（跨页面复用，避免重复定义）。

从 F_资金流向 抽取：区间/均线/序列交互控件、章节标题、涨跌配色、交易时段判定等。
A股配色：净流入/上涨=红(UP)，净流出/下跌=绿(DOWN)。
注意：本模块只定义函数与常量，不调用 st.set_page_config，可被任意页面 import。
"""
import streamlit as st
from datetime import datetime, timedelta

# A股配色：净流入红、净流出绿
UP = "#ee2a2a"      # 红（流入 / 涨）
DOWN = "#1aa260"    # 绿（流出 / 跌）

_PRESET_OPTS = ["近7天", "近30天", "近60天", "近90天", "近180天", "年初至今", "全部", "自定义"]


def _in_trading_hours():
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    hm = now.hour * 60 + now.minute
    return (570 <= hm <= 690) or (780 <= hm <= 900)


def _fig_layout(dark_mode):
    base = dict(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=50, r=20, t=30, b=30), hovermode="x unified",
    )
    if dark_mode:
        base.update(font=dict(color="#e6e6e6"),
                    xaxis=dict(gridcolor="#2a2a3a"), yaxis=dict(gridcolor="#2a2a3a"))
    else:
        base.update(font=dict(color="#1a1a1a"),
                    xaxis=dict(gridcolor="#ececec"), yaxis=dict(gridcolor="#ececec"))
    return base


def _section_title(text, accent="#2b8aef"):
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:8px;margin:6px 0 10px;">'
        f'<span style="width:4px;height:18px;background:{accent};border-radius:2px;display:inline-block;"></span>'
        f'<span style="font-size:16px;font-weight:600;">{text}</span></div>',
        unsafe_allow_html=True,
    )


def _fmt_yi(x):
    try:
        x = float(x)
    except Exception:
        return "—"
    if abs(x) >= 1e8:
        return f"{x/1e8:.2f}亿"
    if abs(x) >= 1e4:
        return f"{x/1e4:.1f}万"
    return f"{x:.0f}"


def _trend_controls(key_prefix, days_default=120, series_options=None,
                    preset_default="近90天", mode_toggle=False, show_ma=True):
    """线性图交互控件：区间预设 + 区间选择 + 均线叠加/类型 + 序列多选 + 数值模式。

    返回 (date_range, ma_periods, selected_keys, mode, ma_type)：
      - date_range   : (start, end) 或 None（全部）
      - ma_periods   : 均线周期元组
      - selected_keys: 显示序列 key 列表（仅 series_options 时有效，否则 None）
      - mode         : 'normalized' | 'raw'
      - ma_type      : 'sma' | 'ema'
    数据走缓存不触网，仅重跑所在 fragment。
    """
    preset = st.radio(
        "区间预设", _PRESET_OPTS,
        index=_PRESET_OPTS.index(preset_default) if preset_default in _PRESET_OPTS else 2,
        horizontal=True, key=f"{key_prefix}_preset",
    )
    end_d = datetime.now().date()
    date_range = None
    if preset != "自定义":
        if preset == "近7天":
            start = end_d - timedelta(days=6)
        elif preset == "近30天":
            start = end_d - timedelta(days=29)
        elif preset == "近60天":
            start = end_d - timedelta(days=59)
        elif preset == "近90天":
            start = end_d - timedelta(days=89)
        elif preset == "近180天":
            start = end_d - timedelta(days=179)
        elif preset == "年初至今":
            start = datetime(end_d.year, 1, 1).date()
        else:
            start = None  # 全部
        date_range = (start, end_d) if start is not None else None

    mode = "normalized"
    if mode_toggle:
        msel = st.radio(
            "数值模式", ["归一化", "原始价格"], horizontal=True,
            index=0, key=f"{key_prefix}_mode",
        )
        mode = "normalized" if msel == "归一化" else "raw"

    # 动态列布局：自定义区间 / 均线 / 均线类型 / 序列多选
    cells_spec = []
    if preset == "自定义":
        cells_spec.append(("dr", 2))
    if show_ma:
        cells_spec.append(("ma", 1))
        cells_spec.append(("matype", 1))
    if series_options:
        cells_spec.append(("sel", 2))
    cells = st.columns([w for _, w in cells_spec]) if cells_spec else []
    ci = 0
    ma = []
    ma_type = "sma"
    if preset == "自定义":
        with cells[ci]:
            dr = st.date_input(
                "区间", value=(end_d - timedelta(days=days_default), end_d),
                max_value=end_d, key=f"{key_prefix}_dr",
            )
            if isinstance(dr, (tuple, list)) and len(dr) == 2:
                date_range = (dr[0], dr[1])
            elif dr is not None:
                date_range = (dr, dr)
        ci += 1
    if show_ma:
        with cells[ci]:
            ma = st.multiselect(
                "均线叠加", options=[5, 10, 20, 60], default=[],
                format_func=lambda x: f"MA{x}", key=f"{key_prefix}_ma",
                help="叠加移动平均线（虚线，图例中可单独开关）",
            )
            ci += 1
    if show_ma:
        with cells[ci]:
            ma_type = st.radio(
                "均线类型", ["SMA", "EMA"], horizontal=True,
                index=0, key=f"{key_prefix}_matype",
            )
            ma_type = "ema" if ma_type == "EMA" else "sma"
            ci += 1
    selected = None
    if series_options:
        with cells[ci]:
            opts = list(series_options)
            sel = st.multiselect(
                "显示序列", options=[k for k, _ in opts],
                default=[k for k, _ in opts],
                format_func=lambda k: dict(opts).get(k, k),
                key=f"{key_prefix}_sel", help="勾选要显示的序列",
            )
            selected = sel
    return date_range, (tuple(ma) if show_ma else ()), selected, mode, (ma_type if show_ma else "sma")
