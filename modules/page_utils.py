import logging
from modules.ui_kit import page_hero
logger = logging.getLogger(__name__)

def latest_quote_time(quote_times):
    """返回行情报价时间列表中的【最新】一条（用于"行情更新于"等展示）。
    空列表返回 "—"。quote_times 为 ISO 字符串时字典序即时间序，max 取最新。
    锐评 R11：自选股监控页曾误用 min（取最早），系统性低估数据新鲜度。
    """
    if not quote_times:
        return "—"
    return max(quote_times)
"""页面公共骨架：消除 40+ 页面重复的样板代码。

提供高频复用的页面级工具，取代各页面里复制粘贴的头部初始化：

- ``render_standard_page(title, icon, caption, layout)``：
    统一执行 ``apply_page_config`` + 标记活跃页 + ``require_auth`` + 用户徽章 +
    主题判断 + 仪表盘 CSS + 标题 + 副标题；返回 ``dark(bool)`` 供后续图表使用。
- ``get_fetcher()``：模块级 ``@st.cache_resource`` 的 ``StockFetcher`` 单例。

错误边界（safe_fragment / safe_section / page_error_boundary）已在 ``page_guard``
中统一提供，本模块不重复。
"""
import inspect

import streamlit as st
from streamlit.runtime.caching import cache_resource

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge
from modules.fetcher import StockFetcher
from modules.ui_icons import svg_icon  # 统一 SVG 图标，替代 emoji（📝 真人视角：emoji 不专业/不可缩放）


def render_standard_page(title, icon="📊", caption=None, layout="wide", auth=True):
    """渲染页面标准头部，返回 dark(bool)。

    自动标记调用方页面为活跃页（用于侧边栏高亮），无需每个页面手写
    ``st.session_state["_active_page"] = __file__``。

    ``auth`` 默认 True（执行 require_auth + 用户徽章）。管理员页若已调用
    ``require_admin()``（内部已含 require_auth），传 ``auth=False`` 避免双重
    注入全局组件（重复 key 异常）。
    """
    apply_page_config(page_title=title, page_icon=icon, layout=layout)
    try:
        caller_file = inspect.stack()[1].filename
    except Exception as e:
        logger.warning(f"[page_utils] 处理异常: {e}")
        caller_file = __file__
    st.session_state["_active_page"] = caller_file
    if auth:
        require_auth()
    render_user_badge(sidebar=True)
    dark = _theme_is_dark()
    st.markdown(dashboard_sf_css(), unsafe_allow_html=True)
    # 签名页头：图标 + 标题 + 副标题 + 实时状态胶囊（主题 / 交易时段）
    chips = _build_status_chips(dark)
    page_hero(title=title, icon=icon, subtitle=caption, chips=chips)
    # 全局组件：Zen 专注模式（G11）——单点注入，全站 41 页自动生效；
    # 失败静默（含嵌入态/重复 key），绝不影响页面主流程。
    try:
        from modules.zen_mode import render_zen_toggle
        render_zen_toggle()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[page_utils] zen_mode 注入失败: {e}")
    return dark


def _build_status_chips(dark: bool) -> list:
    """构造页头右侧状态胶囊：主题模式 + A股交易时段。UI-only，无业务副作用。

    ★ chip 完全 inline style —— 不依赖外部 .ss-pill CSS class：
    streamlit 冷启动竞态下即便 ui_kit._KIT_CSS 未生效、chip 也照常可见。

    ★ 单一真理源 = 入参 ``dark``：不再读 session_state，调用方（render_standard_page
    已传入 ``_theme_is_dark()``）是唯一权威，避免「传参改了 chip 却没变」的隐 bug。
    """
    chips = []
    # 主题胶囊（☀️ 浅色 / 🌙 深色）—— 依据 dark 参数直接判定
    # 用太阳/月亮 SVG 图标避免与「白天/交易中」时间状态词混淆（语义明确：app 主题，非北京时间）。
    # 颜色全走 --ss-* 令牌（暗/亮自动适配），废除硬编码 hex（P1a：跨主题不一致根因）。
    try:
        _accent = "var(--ss-accent)"
        _line = "color-mix(in srgb,var(--ss-accent) 30%,var(--ss-line))"
        _dot = "var(--ss-text-muted)"
        if dark:
            theme_html = (
                f'<span style="display:inline-flex;align-items:center;gap:6px;font-size:12px;'
                f'font-weight:600;padding:5px 12px;border-radius:999px;'
                f'border:1px solid {_line};'
                f'background:color-mix(in srgb,var(--ss-accent) 14%,var(--ss-surface));'
                f'color:{_accent}">'
                f'<span style="display:inline-block;width:7px;height:7px;border-radius:50%;'
                f'background:{_dot}"></span>{svg_icon("moon", size=12)} 深色</span>'
            )
        else:
            theme_html = (
                f'<span style="display:inline-flex;align-items:center;gap:6px;font-size:12px;'
                f'font-weight:600;padding:5px 12px;border-radius:999px;'
                f'border:1px solid {_line};background:var(--ss-surface-2);color:{_accent}">'
                f'<span style="display:inline-block;width:7px;height:7px;border-radius:50%;'
                f'background:{_dot}"></span>{svg_icon("sun", size=12)} 浅色</span>'
            )
        chips.append(theme_html)
    except Exception as e:
        logger.warning(f"[page_utils] 处理异常: {e}")
    # 交易时段胶囊（已休市 / 交易中）
    try:
        from modules.page_widgets import is_trading_now
        if is_trading_now():
            session_html = (
                '<span style="display:inline-flex;align-items:center;gap:6px;font-size:12px;'
                'font-weight:600;padding:5px 12px;border-radius:999px;'
                'border:1px solid #ff4d4f;background:rgba(255,77,79,.10);color:#dc2626">'
                '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;'
                'background:#ff4d4f;box-shadow:0 0 0 3px rgba(255,77,79,.25)"></span>交易中</span>'
            )
        else:
            session_html = (
                '<span style="display:inline-flex;align-items:center;gap:6px;font-size:12px;'
                'font-weight:600;padding:5px 12px;border-radius:999px;'
                'border:1px solid #00d486;background:rgba(0,212,134,.10);color:#166534">'
                '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;'
                'background:#00d486"></span>已休市</span>'
            )
        chips.append(session_html)
    except Exception as e:
        logger.warning(f"[page_utils] 处理异常: {e}")
    return chips


@cache_resource(show_spinner=False)
def get_fetcher():
    """模块级 StockFetcher 单例（替代各页面重复的 ``@st.cache_resource`` 包装）。"""
    return StockFetcher()


def fmt_rel(ts):
    """R-02: 绝对时间 → 相对时间字符串（下沉自 6 个页面的重复 _fmt_rel）。

    最健壮版本（pages/94 消息中心）：处理 ISO 毫秒/T 空格、fromisoformat fail 回退 strptime、
    pandas Timestamp 的 to_pydatetime、负时间戳兜底。
    """
    from datetime import datetime
    try:
        if isinstance(ts, str):
            s = ts.replace("Z", "")
            if "." in s:
                s = s[: s.index(".")]
            s = s.replace("T", " ")
            try:
                ts = datetime.fromisoformat(s)
            except Exception:
                ts = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
        elif hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        sec = (datetime.now() - ts).total_seconds()
        if sec < 0:
            return "刚刚"
        if sec < 60:
            return "刚刚"
        if sec < 3600:
            return f"{int(sec // 60)}分钟前"
        if sec < 86400:
            return f"{int(sec // 3600)}小时前"
        return f"{int(sec // 86400)}天前"
    except Exception:
        return str(ts) if ts else ""


def fmt_safe(v, nd: int = 2, na: str = "N/A") -> str:
    """R-02: 安全数值格式化（下沉自 pages/57 + pages/58 完全相同的 _safe）。

    处理 None / NaN / float('nan')；nd=小数位，na=兜底字符串。
    """
    if v is None or (isinstance(v, float) and v != v):
        return na
    return f"{v:.{nd}f}"


def section_title(text: str, accent: str = "var(--acc1)") -> None:
    """R-02: 带强调色的分区标题胶囊（下沉自 pages/31 + pages/32 相同实现）。

    统一走设计令牌 var(--acc1)（品牌色），随主题切换。accent 参数保留仅作兼容。
    """
    import streamlit as st
    st.markdown(
        f"<div style='display:inline-block;background:var(--acc1);color:#fff;"
        f"padding:4px 12px;border-radius:8px;font-weight:600;font-size:14px;"
        f"margin-bottom:2px;'>{text}</div>", unsafe_allow_html=True)


def styler_color_chg(val, up_color: str = "#ef4444", down_color: str = "#22c55e") -> str:
    """R-02: Styler 回调——按涨跌%正负上色（下沉自 pages/14 实现）。

    健壮版本：float(val) 抛异常也不会炸；返回空串让 Styler 保持默认色。
    """
    try:
        v = float(val)
    except Exception:
        return ""
    if v > 0:
        return f"color:{up_color};font-weight:600;"
    if v < 0:
        return f"color:{down_color};font-weight:600;"
    return ""


# ──────────────────────────────────────────────────────────
# R-02 批次3：跨页重复纯函数下沉（pages/50+54 / pages/70+76）
# ──────────────────────────────────────────────────────────

def last_data_date(df) -> str:
    """R-02: 取 DataFrame 最后一行交易日 'YYYY-MM-DD'；拿不到时退回今天。

    下沉自 pages/50 + pages/54 完全相同的 _last_data_date。
    落盘类操作（连板梯队快照 / 情绪笔记）一律用它而不是 now()：
    周末、节假日、盘后打开页面时 now() 是非交易日，会把「昨日」指到空档上。
    """
    import pandas as pd
    try:
        return str(pd.to_datetime(df["date"].iloc[-1]).date())
    except Exception:  # noqa: BLE001
        return pd.Timestamp.now().strftime("%Y-%m-%d")


def row_to_indicators(df, i=-1) -> dict:
    """R-02: 牧羊人 DataFrame 第 i 行 → 指标 dict（过滤 NaN / date 列）。

    下沉自 pages/50 + pages/54 逻辑相同的 _row_to_indicators。
    用 getattr(df, "empty", True) 兼容 duck-typed 对象。
    """
    if df is None or getattr(df, "empty", True):
        return {}
    try:
        row = df.iloc[i]
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for k in df.columns:
        if k == "date":
            continue
        try:
            v = float(row[k])
            if v == v:  # 过滤 NaN
                out[k] = v
        except Exception:  # noqa: BLE001
            continue
    return out


def temp_gauge(t, dark, title, level, color):
    """R-02: 市场温度 0-100 仪表盘（风险语义：冷=蓝、热=红；与涨跌红绿无关）。

    下沉自 pages/50 + pages/54 完全相同的 _temp_gauge。
    返回 plotly Figure，调用方 st.plotly_chart(fig) 即可。
    """
    import plotly.graph_objects as go
    _steps = [
        {"range": [0, 20], "color": "#1d4ed8"},
        {"range": [20, 40], "color": "#0891b2"},
        {"range": [40, 60], "color": "#ca8a04"},
        {"range": [60, 80], "color": "#ea580c"},
        {"range": [80, 100], "color": "#b91c1c"},
    ]
    _fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=round(float(t), 1),
        number={"font": {"size": 42, "color": color}, "suffix": "°"},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1,
                     "tickcolor": "#94a3b8", "tickfont": {"color": "#94a3b8"}},
            "bar": {"color": color, "thickness": 0.26},
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 1, "bordercolor": "#475569",
            "steps": _steps,
            "threshold": {"line": {"color": color, "width": 5},
                         "thickness": 0.85, "value": round(float(t), 1)},
        },
        title={"text": title, "font": {"size": 16, "color": color}},
    ))
    _fig.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        height=300, margin=dict(l=20, r=20, t=50, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e5e7eb" if dark else "#1f2937"),
    )
    return _fig


def score_bar(label, value, color) -> str:
    """R-02: HTML 评分进度条（0-100 clamp）。下沉自 pages/70 + pages/76 近似实现。"""
    from modules.colors import _hex_to_rgba
    pct = max(0.0, min(100.0, float(value or 0)))
    return (
        "<div style='margin:4px 0'>"
        "<div style='display:flex;justify-content:space-between;font-size:11px;margin-bottom:1px'>"
        f"<span style='opacity:.75'>{label}</span>"
        f"<span style='color:{color};font-weight:700'>{pct:.0f}</span></div>"
        f"<div style='height:6px;background:{_hex_to_rgba(color,0.16)};border-radius:4px'>"
        f"<span style='display:block;height:100%;width:{pct:.1f}%;background:{color};border-radius:4px'></span>"
        "</div></div>"
    )
