import logging
from modules.ui_kit import xc_success_box, xc_warn_box, info_banner
logger = logging.getLogger(__name__)
"""
页面级共用 UI 助手（跨页面复用，避免重复定义）。

从 F_资金流向 抽取：区间/均线/序列交互控件、章节标题、涨跌配色、交易时段判定等。
A股配色：净流入/上涨=红(UP)，净流出/下跌=绿(DOWN)。
注意：本模块只定义函数与常量，不调用 st.set_page_config，可被任意页面 import。
"""
import html
import streamlit as st
from contextlib import contextmanager
from datetime import datetime, timedelta

# A股配色：净流入红、净流出绿（复用 modules.colors 权威调色板，消除色值漂移）
from modules.colors import UP_COLOR, DOWN_COLOR
from modules._widgets_base import render_empty_state
UP = UP_COLOR      # 红（流入 / 涨）
DOWN = DOWN_COLOR  # 绿（流出 / 跌）

_PRESET_OPTS = ["近7天", "近30天", "近60天", "近90天", "近180天", "年初至今", "全部", "自定义"]


def _now_cst() -> "datetime":
    """返回当前「北京时间(Asia/Shanghai)」时刻，用于 A 股交易时段判定。

    隐式修正（R2）：原 is_trading_now 直接用 datetime.now()（服务器本地时区），
    若部署机不在 CST 时区，交易时段判定会整体错位，导致自动刷新在错误时间触发。
    优先用 zoneinfo 取上海时区；不可用时回退到本地朴素时间（行为与原实现一致）。
    """
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Shanghai"))
    except Exception as e:
        logger.warning(f"[page_widgets] 处理异常: {e}")
        return datetime.now()


_TRADING_START = 9 * 60 + 30    # 09:30
_TRADING_MID = 11 * 60 + 30     # 11:30
_TRADING_RESUME = 13 * 60       # 13:00
_TRADING_END = 15 * 60          # 15:00


def is_trading_now(now: "datetime | None" = None) -> bool:
    """A股交易时段判定（统一来源，基于北京时间）。

    工作日 09:30-11:30 / 13:00-15:00 返回 True，周末与午休/收盘返回 False。
    替代各页散落的 4 份重复实现（session.trading_autorefresh / widgets._index_market_status
    / C_自选股监控._is_trading_now / 本模块 _in_trading_hours）。
    now 可注入（测试 / 跨时区复用），缺省用北京时间。
    """
    now = now or _now_cst()
    if now.weekday() >= 5:
        return False
    hm = now.hour * 60 + now.minute
    return (_TRADING_START <= hm <= _TRADING_MID) or (_TRADING_RESUME <= hm <= _TRADING_END)


def current_trading_session(now: "datetime | None" = None) -> str:
    """返回更细粒度的交易时段标签（新能力，供 UI 文案 / 调度判断复用）：
    weekend / pre_open / morning / lunch / afternoon / after_close。
    """
    now = now or _now_cst()
    if now.weekday() >= 5:
        return "weekend"
    hm = now.hour * 60 + now.minute
    if hm < _TRADING_START:
        return "pre_open"
    if hm <= _TRADING_MID:
        return "morning"
    if hm < _TRADING_RESUME:
        return "lunch"
    if hm <= _TRADING_END:
        return "afternoon"
    return "after_close"


def _in_trading_hours():
    """兼容别名，统一走 is_trading_now()。"""
    return is_trading_now()


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


def _section_title_html(text, accent="#2b8aef") -> str:
    """PURE: 返回章节标题 HTML 字符串（调用方自行 markdown 渲染）。

    数据派生文本 text / accent 做 html.escape，避免标签/颜色值注入；
    None/空 -> 安全空默认，绝不抛异常。
    """
    text = "" if text is None else str(text)
    accent = accent or "#2b8aef"
    return (
        f'<div style="display:flex;align-items:center;gap:8px;margin:6px 0 10px;">'
        f'<span style="width:4px;height:18px;background:{html.escape(accent, quote=True)};'
        f'border-radius:2px;display:inline-block;"></span>'
        f'<span style="font-size:16px;font-weight:600;">{html.escape(text)}</span></div>'
    )


def _section_title(text, accent="#2b8aef"):
    st.markdown(_section_title_html(text, accent), unsafe_allow_html=True)


def _fmt_yi(x):
    try:
        x = float(x)
    except Exception as e:
        logger.warning(f"[page_widgets] 处理异常: {e}")
        return "—"
    if x != x:  # NaN
        return "—"
    if abs(x) >= 1e8:
        return f"{x/1e8:.2f}亿"
    if abs(x) >= 1e4:
        return f"{x/1e4:.1f}万"
    return f"{x:.0f}"


def _trend_controls(key_prefix, days_default=120, series_options=None,
                    preset_default="近90天", mode_toggle=False, show_ma=True,
                    radio_pills=False):
    """线性图交互控件：区间预设 + 区间选择 + 均线叠加/类型 + 序列多选 + 数值模式。

    返回 (date_range, ma_periods, selected_keys, mode, ma_type)：
      - date_range   : (start, end) 或 None（全部）
      - ma_periods   : 均线周期元组
      - selected_keys: 显示序列 key 列表（仅 series_options 时有效，否则 None）
      - mode         : 'normalized' | 'raw'
      - ma_type      : 'sma' | 'ema'
    数据走缓存不触网，仅重跑所在 fragment。

    新增 radio_pills（默认 False）：开启后使用 Streamlit 原生 ``st.segmented_control``
    渲染区间预设 / 数值模式 / 均线类型，呈现按钮式分段选择器；关闭时保持原
    ``st.radio`` 行为。纯加法式，不影响现有页面默认行为。
    """

    def _radio(label, options, default=None, key=None):
        if radio_pills:
            return st.segmented_control(
                label, options, selection_mode="single", default=default,
                key=key,
            )
        # 原 radio 行为：default 由 index 决定
        index = options.index(default) if default in options else 0
        return st.radio(label, options, index=index, horizontal=True, key=key)

    preset = _radio(
        "区间预设", _PRESET_OPTS,
        default=preset_default if preset_default in _PRESET_OPTS else _PRESET_OPTS[2],
        key=f"{key_prefix}_preset",
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
        msel = _radio(
            "数值模式", ["归一化", "原始价格"],
            default="归一化", key=f"{key_prefix}_mode",
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
                "均线叠加", options=[5, 10, 20, 60], default=[20],
                format_func=lambda x: f"MA{x}", key=f"{key_prefix}_ma",
                help="叠加移动平均线（虚线，图例中可单独开关）",
            )
            ci += 1
    if show_ma:
        with cells[ci]:
            ma_type = _radio(
                "均线类型", ["SMA", "EMA"],
                default="SMA", key=f"{key_prefix}_matype",
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


def _loading_html(text: str = "加载中…") -> str:
    """PURE: 返回加载占位 HTML 字符串（调用方自行 markdown 渲染）。

    text 为数据派生文本时做 html.escape；None/空 -> 安全默认，绝不抛异常。
    """
    text = "加载中…" if text is None else str(text)
    return (
        '<style>@keyframes ssspin{to{transform:rotate(360deg)}}</style>'
        f'<div style="text-align:center;color:#8a8a8a;padding:14px 0;font-size:13px;">'
        f'<span style="display:inline-block;width:13px;height:13px;margin-right:6px;vertical-align:-2px;'
        f'border:2px solid #cfcfcf;border-top-color:#666;border-radius:50%;'
        f'animation:ssspin 0.8s linear infinite;"></span>{html.escape(text)}</div>'
    )


@contextmanager
def _loading(text: str = "加载中…"):
    """数据加载占位（UI-only）：在 with 块期间显示居中旋转提示，结束自动清空。

    用于「取数前」先占位的场景，避免裸空白或突兀的 st.info。
    不改变任何逻辑/布局，仅视觉提示。
    """
    ph = st.empty()
    with ph.container():
        st.markdown(_loading_html(text), unsafe_allow_html=True)
        try:
            yield
        finally:
            pass
    ph.empty()


def _empty_info_html(text: str = "暂无数据") -> str:
    """PURE: 返回空数据态 HTML 字符串（调用方自行 markdown 渲染）。

    text 为数据派生文本时做 html.escape；None/空 -> 安全默认，绝不抛异常。
    R73 统一：委托 ``_widgets_base.render_empty_state``（CSS 变量自适应暗/亮主题，
    旧实现硬编码 #8a8a8a 在深色主题下可读性差），保留 🗂️ 图标语义。
    """
    text = "暂无数据" if text is None else str(text)
    return render_empty_state(text, icon="🗂️")


def _empty_info(text: str = "暂无数据"):
    """空数据态（UI-only）：居中、弱化提示，统一替代散落的 info_banner("暂无…")。"""
    st.markdown(_empty_info_html(text), unsafe_allow_html=True)


def _fmt_num(x, nd: int = 2, sign: bool = False) -> str:
    """数值格式化（显示 only）：None/NaN/异常 → "—"；可选正负号；不自带量级缩写。"""
    try:
        x = float(x)
    except Exception as e:
        logger.warning(f"[page_widgets] 处理异常: {e}")
        return "—"
    if x != x:  # NaN
        return "—"
    s = f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"
    return s


def _fmt_pct(x, nd: int = 2, sign: bool = True) -> str:
    """百分比格式化（显示 only）：None/异常 → "—"；自动 ×100 加 %；默认带正负号。"""
    try:
        x = float(x)
    except Exception as e:
        logger.warning(f"[page_widgets] 处理异常: {e}")
        return "—"
    if x != x:
        return "—"
    s = f"{x*100:+.{nd}f}%" if sign else f"{x*100:.{nd}f}%"
    return s


def _delta_color(delta, inverse: bool = False) -> str:
    """涨跌配色：A股红涨绿跌。inverse=True（如跌幅越小越好）时翻转语义。

    :returns: UP(红) / DOWN(绿) / ""（0 或 None）
    """
    try:
        d = float(delta)
    except Exception as e:
        logger.warning(f"[page_widgets] 处理异常: {e}")
        return ""
    if d == 0 or d != d:
        return ""
    is_up = d > 0
    if inverse:
        is_up = not is_up
    return UP if is_up else DOWN


def _delta_html(delta, is_pct: bool = True, nd: int = 2, inverse: bool = False) -> str:
    """涨跌 chips（UI-only，返回 HTML 字符串，调用方自行 markdown 渲染）。

    A股红涨绿跌；delta 为 None/0 时返回灰色的「—」。
    """
    try:
        d = float(delta)
    except Exception as e:
        logger.warning(f"[page_widgets] 处理异常: {e}")
        d = None
    if d is None or d != d:
        return '<span style="color:#9aa0a6;">—</span>'
    if d == 0:
        return '<span style="color:#9aa0a6;">0.00%</span>' if is_pct else '<span style="color:#9aa0a6;">0</span>'
    color = _delta_color(d, inverse=inverse)
    txt = f"{d*100:+.{nd}f}%" if is_pct else f"{d:+.{nd}f}"
    return f'<span style="color:{color};font-weight:600;">{txt}</span>'


def _data_card_html(label: str, value: str, delta_html: str = "", accent: str = "#2b8aef",
                    unit: str = "") -> str:
    """PURE: 返回紧凑指标卡 HTML 字符串（调用方自行 markdown 渲染）。

    标签/数值/单位均为数据派生文本，统一 html.escape 防止注入；
    None/空 -> 安全空默认，绝不抛异常。delta_html 为内部受信 HTML 片段，原样保留。
    """
    label = "" if label is None else str(label)
    value = "" if value is None else str(value)
    unit = "" if unit is None else str(unit)
    delta_html = delta_html or ""
    accent = accent or "#2b8aef"
    delta_block = f'<div style="margin-top:2px;font-size:13px;">{delta_html}</div>' if delta_html else ""
    return (
        f'<div style="border:1px solid rgba(128,128,128,0.22);border-left:3px solid {html.escape(accent, quote=True)};'
        f'border-radius:10px;padding:10px 12px;background:rgba(128,128,128,0.04);">'
        f'<div style="font-size:12px;color:#8a8a8a;margin-bottom:2px;">{html.escape(label)}</div>'
        f'<div style="font-size:20px;font-weight:700;line-height:1.2;">{html.escape(value)}'
        f'<span style="font-size:12px;color:#8a8a8a;font-weight:400;margin-left:3px;">{html.escape(unit)}</span></div>'
        f'{delta_block}</div>'
    )


def _data_card(label: str, value: str, delta_html: str = "", accent: str = "#2b8aef",
               unit: str = "") -> None:
    """紧凑指标卡（UI-only，HTML）：标签 + 大值 + 可选涨跌 chips。

    用于替换散落的 st.metric / markdown 拼装，统一视觉。
    """
    st.markdown(_data_card_html(label, value, delta_html, accent, unit), unsafe_allow_html=True)


def _auto_refresh(sec: int = 60, key: str = "auto_refresh") -> None:
    """交易时段自动刷新（fragment 内可用）：委托 session.trading_autorefresh。

    非交易时段静默跳过；放在 @safe_fragment 内可只重跑该片段，不整页重跑。
    """
    try:
        from modules.session import trading_autorefresh
        trading_autorefresh(interval_ms=sec * 1000, key=key)
    except Exception as e:
        logger.warning(f"[page_widgets] 处理异常: {e}")
        pass


def _toast(msg: str, icon: str = "✅"):
    """轻量提示（UI-only）：优先 st.toast，异常则降级为 st.success 短提示。"""
    try:
        st.toast(f"{icon} {msg}")
    except Exception as e:
        logger.warning(f"[page_widgets] 处理异常: {e}")
        xc_success_box(msg)
