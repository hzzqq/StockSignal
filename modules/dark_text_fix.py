"""
StockSignal 暗夜模式 · 全量文本可见性修复
==========================================
解决：暗夜模式下图表标签、轴文字、注解、数值、标题、芯片按钮等**所有文本元素看不清**的问题。

【设计原则】
  1. 文本按用途分 6 层：标题 / 正文 / 标签(轴) / 数值 / 注解 / 辅助(placeholder)
  2. 每层给 light / dark 两套色值，dark 模式统一提亮，确保 WCAG AA ≥4.5:1
  3. 背景色基准：暗夜 = #0f0f1a（深空蓝黑），白天 = #ffffff
  4. 强调色（数值高亮/信号词）用饱和色 + 纯白/纯黑字
  5. 图表类文本额外覆盖 Plotly/Matplotlib 的默认配色（含雷达图 polar 轴）
  6. ★ 芯片/标签/筛选按钮(chip)专项：暗夜下边框+文字提亮，背景加深

【与按钮配色的关系】
  button_colors.py 管 <button> 主操作元素（primary/success/warning 等）。
  本文件管其余所有文本 + 芯片类次要按钮。
  两者互补，不冲突。

移植：from modules.dark_text_fix import *
      inject_dark_text_css(mode)        # 每个页面顶部（mode 由 ui_theme._theme_is_dark 决定）
      fig.update_layout(**get_plotly_template(dark=...))   # 每个 Plotly 图表
"""

import streamlit as st

# ===========================================================================
# 暗夜模式背景基准色
# ===========================================================================
DARK_BG = "#0f0f1a"       # 深空蓝黑（星辰主题主背景）
LIGHT_BG = "#ffffff"      # 纯白

# ===========================================================================
# 文本分层配色表（6 层 × 双模）
# ===========================================================================
TEXT_PALETTE = {
    "title": {
        "light": {"color": "#111827", "weight": "700"},
        "dark":  {"color": "#f1f5f9", "weight": "700"},
    },
    "body": {
        "light": {"color": "#374151", "weight": "400"},
        "dark":  {"color": "#cbd5e1", "weight": "400"},
    },
    "label": {
        "light": {"color": "#4b5563", "weight": "500"},
        "dark":  {"color": "#94a3b8", "weight": "500"},   # ★ 核心：从 #3d4555 提亮到这
    },
    "value": {
        "light": {"color": "#111827", "weight": "600"},
        "dark":  {"color": "#e2e8f0", "weight": "600"},
    },
    "note": {
        "light": {"color": "#6b7280", "weight": "400"},
        "dark":  {"color": "#94a3b8", "weight": "400"},
    },
    "helper": {
        "light": {"color": "#9ca3af", "weight": "400"},
        "dark":  {"color": "#64748b", "weight": "400"},
    },
}

# ===========================================================================
# 强调色（用于数值高亮 / 信号词）— A股惯例：涨=红 跌=绿
# ===========================================================================
EMPHASIS_COLORS = {
    "up": {
        "light": {"bg": "#fef2f2", "text": "#dc2626", "border": "#fecaca"},
        "dark":  {"bg": "#450a0a", "text": "#fca5a5", "border": "#7f1d1d"},
    },
    "down": {
        "light": {"bg": "#f0fdf4", "text": "#16a34a", "border": "#bbf7d0"},
        "dark":  {"bg": "#052e16", "text": "#86efac", "border": "#166534"},
    },
    "neutral": {
        "light": {"bg": "#fffbeb", "text": "#d97706", "border": "#fde68a"},
        "dark":  {"bg": "#422006", "text": "#fbbf24", "border": "#b45309"},
    },
    "highlight": {
        "light": {"text": "#6366f1", "bg": "#eef2ff"},
        "dark":  {"text": "#a5b4fc", "bg": "#1e1b4b"},
    },
}

# ===========================================================================
# ★ 芯片/标签/筛选按钮配色（Chip/Tag/Filter Button）
# ===========================================================================
CHIP_PALETTE = {
    "default": {
        "light": {"bg": "#f3f4f6", "text": "#4b5563", "border": "#e5e7eb", "hover_bg": "#e5e7eb"},
        "dark":  {"bg": "#1a1a2e", "text": "#94a3b8", "border": "#334155", "hover_bg": "#252545"},
    },
    "active": {
        "light": {"bg": "#eef2ff", "text": "#4338ca", "border": "#c7d2fe", "hover_bg": "#e0e7ff"},
        "dark":  {"bg": "#312e81", "text": "#a5b4fc", "border": "#6366f1", "hover_bg": "#3730a3"},
    },
    "disabled": {
        "light": {"bg": "#f9fafb", "text": "#d1d5db", "border": "#f3f4f6", "hover_bg": "#f9fafb"},
        "dark":  {"bg": "#0f0f1a", "text": "#475569", "border": "#1e293b", "hover_bg": "#0f0f1a"},
    },
}

CHIP_RADIUS = "8px"
CHIP_FONT_SIZE = "13px"
CHIP_PADDING = "6px 16px"


# ===========================================================================
# CSS 注入 — 全量文本修复
# ===========================================================================
DARK_TEXT_CSS_LIGHT = """
<style>
/* ============================================================
   StockSignal 文本可见性修复 · 白天模式基础样式 + 工具类
   ============================================================ */
.sf-text-title, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stHeading, h1, h2, h3 {
  color: %(title_color)s !important; font-weight: %(title_weight)s !important;
}
.sf-text-body, .stMarkdown p, .stMarkdown li, .stText, .stCaption, p, li {
  color: %(body_color)s !important;
}
.sf-text-label, .stSelectbox label, .stTextInput label, .stNumberInput label, .stSlider label,
.stCheckbox label, .stRadio label, .stDataFrame label, .label, .axis-label, .legend-label,
[class*="label"], [class*="Label"] {
  color: %(label_color)s !important; font-weight: %(label_weight)s !important;
}
.sf-text-value, .stMetric value, .stMetric div[data-testid="stMetricValue"] {
  color: %(value_color)s !important; font-weight: %(value_weight)s !important;
}
.sf-text-note, .stCaption, .footer-note, .annotation, .caption, .footnote {
  color: %(note_color)s !important;
}
.sf-text-helper, ::placeholder, .stHelperText, [disabled], .disabled { color: %(helper_color)s !important; }
.stDataFrame table th { color: %(title_color)s !important; font-weight: 600 !important; }
.stDataFrame table td { color: %(body_color)s !important; }
.sf-chip {
  display:inline-flex;align-items:center;justify-content:center;
  border:%(chip_def_bd)s 1px solid; background:%(chip_def_bg)s;color:%(chip_def_txt)s;
  border-radius:%(chip_rad)s;padding:%(chip_pad)s; font-size:%(chip_fs)s;font-weight:500;cursor:pointer;
  transition:all .15s ease;user-select:none;white-space:nowrap;
}
.sf-chip:hover{background:%(chip_def_hv)s}
.sf-chip.active{background:%(chip_act_bg)s;color:%(chip_act_txt)s;border-color:%(chip_act_bd)s}
.sf-chip.active:hover{background:%(chip_act_hv)s}
.sf-chip.disabled{background:%(chip_dis_bg)s;color:%(chip_dis_txt)s;border-color:%(chip_dis_bd)s;cursor:not-allowed;opacity:.55}
.stMultiselect [data-baseweb="tag"] span, .stMultiValue span { color:%(body_color)s !important; }
.stCheckbox [role="group"] label, .stRadio [role="radiogroup"] label { color:%(label_color)s !important; }
</style>
""" % {
    "title_color": TEXT_PALETTE["title"]["light"]["color"],
    "title_weight": TEXT_PALETTE["title"]["light"]["weight"],
    "body_color":  TEXT_PALETTE["body"]["light"]["color"],
    "label_color": TEXT_PALETTE["label"]["light"]["color"],
    "label_weight": TEXT_PALETTE["label"]["light"]["weight"],
    "value_color": TEXT_PALETTE["value"]["light"]["color"],
    "value_weight": TEXT_PALETTE["value"]["light"]["weight"],
    "note_color":  TEXT_PALETTE["note"]["light"]["color"],
    "helper_color": TEXT_PALETTE["helper"]["light"]["color"],
    "chip_def_bg": CHIP_PALETTE["default"]["light"]["bg"],
    "chip_def_txt": CHIP_PALETTE["default"]["light"]["text"],
    "chip_def_bd": CHIP_PALETTE["default"]["light"]["border"],
    "chip_def_hv": CHIP_PALETTE["default"]["light"]["hover_bg"],
    "chip_act_bg": CHIP_PALETTE["active"]["light"]["bg"],
    "chip_act_txt": CHIP_PALETTE["active"]["light"]["text"],
    "chip_act_bd": CHIP_PALETTE["active"]["light"]["border"],
    "chip_act_hv": CHIP_PALETTE["active"]["light"]["hover_bg"],
    "chip_dis_bg": CHIP_PALETTE["disabled"]["light"]["bg"],
    "chip_dis_txt": CHIP_PALETTE["disabled"]["light"]["text"],
    "chip_dis_bd": CHIP_PALETTE["disabled"]["light"]["border"],
    "chip_rad":   CHIP_RADIUS, "chip_fs": CHIP_FONT_SIZE, "chip_pad": CHIP_PADDING,
}

DARK_TEXT_CSS_DARK = """
<style>
/* ============================================================
   StockSignal 文本可见性修复 · ★ 暗夜模式覆盖（核心！）
   ============================================================ */
.sf-text-title, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stHeading, h1, h2, h3 {
  color: %(title_color)s !important; font-weight: %(title_weight)s !important;
}
.sf-text-body, .stMarkdown p, .stMarkdown li, .stText, .stCaption, p, li { color: %(body_color)s !important; }
.sf-text-label, .stSelectbox label, .stTextInput label, .stNumberInput label, .stSlider label,
.stCheckbox label, .stRadio label, .stDataFrame label, .label, .axis-label, .legend-label,
[class*="label"], [class*="Label"] { color: %(label_color)s !important; font-weight: %(label_weight)s !important; }
.sf-text-value, .stMetric value, .stMetric div[data-testid="stMetricValue"] {
  color: %(value_color)s !important; font-weight: %(value_weight)s !important; }
.sf-text-note, .stCaption, .footer-note, .annotation, .caption, .footnote { color: %(note_color)s !important; }
.sf-text-helper, ::placeholder, .stHelperText, [disabled], .disabled { color: %(helper_color)s !important; }
.stDataFrame table th { color: %(title_color)s !important; font-weight: 600 !important; background-color:#1a1a2e !important; }
.stDataFrame table td { color: %(body_color)s !important; background-color:#0f0f1a !important; }

/* ★ Plotly 雷达图 / 极坐标图 轴标签（文档核心问题） */
.js-plotly-plot .radialaxis text, .js-plotly-plot .angularaxis text,
.js-plotly-plot .g-gtitle text, .js-plotly-plot .g-atitle text {
  fill: %(label_color)s !important; opacity: 1 !important;
}
.js-plotly-plot .xaxis text, .js-plotly-plot .yaxis text, .js-plotly-plot .zaxis text { fill: %(body_color)s !important; opacity:1 !important; }
.js-plotly-plot .xtick text, .js-plotly-plot .ytick text, .js-plotly-plot .ztick text { fill: %(label_color)s !important; opacity:1 !important; }
.js-plotly-plot .legend text, .js-plotly-plot .g-legtext text { fill: %(body_color)s !important; opacity:1 !important; }
.js-plotly-plot .annotatext text, .js-plotly-plot .annotation-text { fill: %(note_color)s !important; opacity:1 !important; }

svg text, canvas + div text, [class*="chart"] text { color: %(body_color)s !important; fill: %(body_color)s !important; }
svg .tick text, svg .axis text, svg label { fill: %(label_color)s !important; color: %(label_color)s !important; }

.sf-chip { background:%(chip_def_bg)s !important; color:%(chip_def_txt)s !important; border:%(chip_def_bd)s 1px solid !important; }
.sf-chip:hover{background:%(chip_def_hv)s !important}
.sf-chip.active{background:%(chip_act_bg)s !important;color:%(chip_act_txt)s !important;border-color:%(chip_act_bd)s !important}
.sf-chip.active:hover{background:%(chip_act_hv)s !important}
.sf-chip.disabled{background:%(chip_dis_bg)s !important;color:%(chip_dis_txt)s !important;border-color:%(chip_dis_bd)s !important;opacity:.55;cursor:not-allowed}

.stMultiselect [data-baseweb="tag"] span, .stMultiValue span { color:%(body_color)s !important; }
.stCheckbox [role="group"] label, .stRadio [role="radiogroup"] label { color:%(label_color)s !important; }
button:not(.sf-btn):not([data-testid="stFormSubmitButton"]) { color:%(body_color)s !important; border-color:%(chip_def_bd)s !important; }
</style>
""" % {
    "title_color": TEXT_PALETTE["title"]["dark"]["color"],
    "title_weight": TEXT_PALETTE["title"]["dark"]["weight"],
    "body_color":  TEXT_PALETTE["body"]["dark"]["color"],
    "label_color": TEXT_PALETTE["label"]["dark"]["color"],
    "label_weight": TEXT_PALETTE["label"]["dark"]["weight"],
    "value_color": TEXT_PALETTE["value"]["dark"]["color"],
    "value_weight": TEXT_PALETTE["value"]["dark"]["weight"],
    "note_color":  TEXT_PALETTE["note"]["dark"]["color"],
    "helper_color": TEXT_PALETTE["helper"]["dark"]["color"],
    "chip_def_bg": CHIP_PALETTE["default"]["dark"]["bg"],
    "chip_def_txt": CHIP_PALETTE["default"]["dark"]["text"],
    "chip_def_bd": CHIP_PALETTE["default"]["dark"]["border"],
    "chip_def_hv": CHIP_PALETTE["default"]["dark"]["hover_bg"],
    "chip_act_bg": CHIP_PALETTE["active"]["dark"]["bg"],
    "chip_act_txt": CHIP_PALETTE["active"]["dark"]["text"],
    "chip_act_bd": CHIP_PALETTE["active"]["dark"]["border"],
    "chip_act_hv": CHIP_PALETTE["active"]["dark"]["hover_bg"],
    "chip_dis_bg": CHIP_PALETTE["disabled"]["dark"]["bg"],
    "chip_dis_txt": CHIP_PALETTE["disabled"]["dark"]["text"],
    "chip_dis_bd": CHIP_PALETTE["disabled"]["dark"]["border"],
}


def inject_dark_text_css(mode="auto"):
    """注入全量文本可见性修复 CSS。

    参数:
      mode — "light"(强制白天) / "dark"(强制暗夜) / "auto"(默认：注入 light 基底，暗夜再叠加覆盖层)

    在 Streamlit 中建议 mode 由 modules.ui_theme._theme_is_dark() 决定，
    每个页面顶部随 apply_theme() 一起调用，无需手写 if。
    """
    st.markdown(DARK_TEXT_CSS_LIGHT, unsafe_allow_html=True)
    if mode == "dark" or mode == "auto":
        # auto 模式下仍注入 dark 覆盖层：
        # 当 mode=="auto" 时，调用方（apply_theme）仅在暗夜才调用本函数，
        # 因此这里直接注入 dark 覆盖即可。为兼容显式 "auto"，统一注入 dark 覆盖。
        st.markdown(DARK_TEXT_CSS_DARK, unsafe_allow_html=True)


def inject_dark_text_overrides():
    """单独调用暗夜覆盖层（当已确认处于暗夜模式时使用）。"""
    st.markdown(DARK_TEXT_CSS_DARK, unsafe_allow_html=True)


# ===========================================================================
# 快捷函数：生成带正确颜色的文本 HTML
# ===========================================================================
def colored_text(text, layer="body", emphasis=None, tag="span"):
    """生成带颜色 class 的文本 HTML（layer: title/body/label/value/note/helper）。"""
    cls = f"sf-text-{layer}"
    if emphasis:
        cls += f" sf-emph-{emphasis}"
    return f"<{tag} class=\"{cls}\">{text}</{tag}>"


def highlight_value(value, fmt=None, direction=None):
    """生成带方向色的数值（A股红涨绿跌）。"""
    if fmt:
        display = f"{value:{fmt}}"
    else:
        display = str(value)
    if direction is None:
        if isinstance(value, (int, float)):
            direction = "up" if value >= 0 else "down"
        else:
            direction = "neutral"
    emph = EMPHASIS_COLORS.get(direction, EMPHASIS_COLORS["neutral"])
    return (
        f'<span class="sf-text-value sf-emph-{direction}"'
        f' style="color:{emph["dark"]["text"]};font-weight:600">'
        f'{display}</span>'
    )


def chip_html(text, state="default", icon=None, extra_class=""):
    """生成芯片/标签按钮 HTML（state: default/active/disabled）。"""
    cls = ["sf-chip"]
    if state in ("active", "disabled"):
        cls.append(state)
    if extra_class:
        cls.append(extra_class)
    label = f"{icon or ''}{text}" if icon else text
    return f'<span class="{" ".join(cls)}">{label}</span>'


def chip_group(chips, active_index=None, inline=True):
    """生成一组芯片按钮 HTML（横排，可指定选中项）。"""
    parts = ['<div class="sf-chip-group" style="display:flex;gap:8px;flex-wrap:wrap;">']
    for i, label_text in enumerate(chips):
        state = "active" if i == active_index else "default"
        parts.append(chip_html(label_text, state=state))
    parts.append("</div>")
    return "\n".join(parts)


# ===========================================================================
# Plotly 图表模板（一键应用正确的文字颜色 + 雷达 polar 轴）
# ===========================================================================
PLOTLY_DARK_TEMPLATE = dict(
    paper_bgcolor="#0f0f1a",
    plot_bgcolor="#0f0f1a",
    font=dict(color="#cbd5e1", family="system-ui, -apple-system, 'PingFang SC', sans-serif", size=13),
    title_font=dict(color="#f1f5f9", size=18),
    xaxis=dict(tickfont=dict(color="#94a3b8", size=11), title_font=dict(color="#94a3b8", size=12),
               gridcolor="#1e293b", zerolinecolor="#334155", linecolor="#334155"),
    yaxis=dict(tickfont=dict(color="#94a3b8", size=11), title_font=dict(color="#94a3b8", size=12),
               gridcolor="#1e293b", zerolinecolor="#334155", linecolor="#334155"),
    # ★ 雷达图 polar 轴（文档核心问题区）
    polar=dict(
        bgcolor="rgba(0,0,0,0)",
        radialaxis=dict(gridcolor="#1e293b", tickfont=dict(color="#94a3b8", size=11), linecolor="#334155", angle=90, range=[0, 100]),
        angularaxis=dict(gridcolor="#1e293b", tickfont=dict(color="#94a3b8", size=12), linecolor="#334155"),
    ),
    legend=dict(font=dict(color="#cbd5e1", size=11), bgcolor="rgba(15,15,26,0.8)", bordercolor="#1e293b"),
    margin=dict(l=60, r=40, t=50, b=60),
)

PLOTLY_LIGHT_TEMPLATE = dict(
    paper_bgcolor="#ffffff",
    plot_bgcolor="#fafafa",
    font=dict(color="#374151", family="system-ui, -apple-system, 'PingFang SC', sans-serif", size=13),
    title_font=dict(color="#111827", size=18),
    xaxis=dict(tickfont=dict(color="#4b5563", size=11), title_font=dict(color="#4b5563", size=12),
               gridcolor="#e5e7eb", zerolinecolor="#9ca3af", linecolor="#d1d5db"),
    yaxis=dict(tickfont=dict(color="#4b5563", size=11), title_font=dict(color="#4b5563", size=12),
               gridcolor="#e5e7eb", zerolinecolor="#9ca3af", linecolor="#d1d5db"),
    polar=dict(
        bgcolor="rgba(255,255,255,0)",
        radialaxis=dict(gridcolor="#e5e7eb", tickfont=dict(color="#4b5563", size=11), linecolor="#d1d5db", angle=90, range=[0, 100]),
        angularaxis=dict(gridcolor="#e5e7eb", tickfont=dict(color="#4b5563", size=12), linecolor="#d1d5db"),
    ),
    legend=dict(font=dict(color="#374151", size=11), bgcolor="rgba(255,255,255,0.9)", bordercolor="#e5e7eb"),
    margin=dict(l=60, r=40, t=50, b=60),
)


def get_plotly_template(dark=False):
    """获取 Plotly 布局模板（含正确的文字颜色 + 雷达 polar 轴配色）。"""
    return PLOTLY_DARK_TEMPLATE if dark else PLOTLY_LIGHT_TEMPLATE


def apply_plotly_theme(fig, dark=False):
    """把正确文字/网格/雷达轴配色应用到 fig（一行调用）。返回 fig 本身。"""
    fig.update_layout(**get_plotly_template(dark=dark))
    return fig


if __name__ == "__main__":
    print("dark_text_fix OK")
    print(f"Text layers: {list(TEXT_PALETTE.keys())}")
    print(f"Emphasis types: {list(EMPHASIS_COLORS.keys())}")
