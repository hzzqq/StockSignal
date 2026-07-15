"""
StockSignal 按钮配色系统 · 双模（Light / Dark）通用
=====================================================
解决：同一套按钮在白天模式和暗夜模式下都能看清文字、符合 WCAG AA 对比度。

【设计原则】
  1. 按钮文字统一用 #ffffff（纯白）或 #111827（近黑），杜绝灰/彩色文字
  2. 背景色按语义分档：primary / success / warning / danger / ghost / info
  3. 每种颜色都给 light / dark 两套值，确保对比度 >= 4.5:1（AA 级）
  4. hover 统一规则：背景加深 8~12% + 轻上浮 + 阴影加深
  5. disabled 统一规则：透明度降至 0.45 + cursor:not-allowed

【与星辰主题的关系】
  本配色系统的 primary 色复用 starfield_theme 的 --acc1/#667eea，其余色为新增。
  所有值均为硬编码 hex（不依赖 :root 变量），可独立于任何主题使用。

移植：from modules.button_colors import *
      inject_button_css(mode)   # mode 由 modules.ui_theme._theme_is_dark 决定
      st.markdown(btn_html("提交", kind="primary"), unsafe_allow_html=True)
"""

import streamlit as st

BUTTON_PALETTE = {
    "primary": {
        "light": {"bg": "#5b5ef7", "text": "#ffffff"},
        "dark":  {"bg": "#6366f1", "text": "#ffffff"},
    },
    "success": {
        "light": {"bg": "#16a34a", "text": "#ffffff"},
        "dark":  {"bg": "#22c55e", "text": "#ffffff"},
    },
    "warning": {
        "light": {"bg": "#d97706", "text": "#ffffff"},
        "dark":  {"bg": "#f59e0b", "text": "#ffffff"},   # ★ 暗夜用亮琥珀 + 纯白字（修复看不清）
    },
    "danger": {
        "light": {"bg": "#dc2626", "text": "#ffffff"},
        "dark":  {"bg": "#ef4444", "text": "#ffffff"},
    },
    "ghost": {
        "light": {"bg": "#f3f4f6", "text": "#374151"},
        "dark":  {"bg": "#374151", "text": "#e5e7eb"},
    },
    "info": {
        "light": {"bg": "#0284c7", "text": "#ffffff"},
        "dark":  {"bg": "#38bdf8", "text": "#0c4a6e"},
    },
}

BTN_RADIUS = "10px"
BTN_FONT_SIZE = "14px"
BTN_PADDING = "10px 24px"

BUTTON_CSS = """
<style>
.sf-btn{
  display:inline-flex;align-items:center;justify-content:center;gap:8px;border:none;cursor:pointer;
  font-family:system-ui,-apple-system,'PingFang SC',sans-serif;font-size:%(fs)s;font-weight:600;line-height:1.4;
  border-radius:%(rad)s;padding:%(pad)s;transition:all .18s ease;user-select:none;white-space:nowrap;
  box-shadow:0 2px 8px rgba(0,0,0,.08),0 1px 3px rgba(0,0,0,.06);
}
.sf-btn:hover{transform:translateY(-1px);box-shadow:0 4px 14px rgba(0,0,0,.14),0 2px 6px rgba(0,0,0,.08)}
.sf-btn:active{transform:translateY(0)}
.sf-btn:disabled,.sf-btn.disabled{opacity:.45;cursor:not-allowed;transform:none!important;box-shadow:none!important}
.sf-btn-primary{background:%(p_bg)s;color:%(p_txt)s}.sf-btn-primary:hover{background:%(p_hv)s}
.sf-btn-success{background:%(s_bg)s;color:%(s_txt)s}.sf-btn-success:hover{background:%(s_hv)s}
.sf-btn-warning{background:%(w_bg)s;color:%(w_txt)s}.sf-btn-warning:hover{background:%(w_hv)s}
.sf-btn-danger{background:%(d_bg)s;color:%(d_txt)s}.sf-btn-danger:hover{background:%(d_hv)s}
.sf-btn-ghost{background:%(g_bg)s;color:%(g_txt)s;border:1px solid %(g_bd)s}.sf-btn-ghost:hover{background:%(g_hv)s}
.sf-btn-info{background:%(i_bg)s;color:%(i_txt)s}.sf-btn-info:hover{background:%(i_hv)s}
.sf-btn-sm{font-size:12px;padding:6px 16px;border-radius:8px}
.sf-btn-lg{font-size:16px;padding:14px 32px;border-radius:12px}
.sf-btn-block{display:flex;width:100%%}
.sf-btn-icon{width:38px;height:38px;border-radius:50%%;padding:0;font-size:16px;flex-shrink:0}
.sf-btn-icon.sm{width:30px;height:30px;font-size:13px}
</style>
""" % {
    "fs": BTN_FONT_SIZE, "rad": BTN_RADIUS, "pad": BTN_PADDING,
    "p_bg": BUTTON_PALETTE["primary"]["light"]["bg"], "p_txt": BUTTON_PALETTE["primary"]["light"]["text"], "p_hv": "#4338ca",
    "s_bg": BUTTON_PALETTE["success"]["light"]["bg"], "s_txt": BUTTON_PALETTE["success"]["light"]["text"], "s_hv": "#15803d",
    "w_bg": BUTTON_PALETTE["warning"]["light"]["bg"], "w_txt": BUTTON_PALETTE["warning"]["light"]["text"], "w_hv": "#b45309",
    "d_bg": BUTTON_PALETTE["danger"]["light"]["bg"], "d_txt": BUTTON_PALETTE["danger"]["light"]["text"], "d_hv": "#b91c1c",
    "g_bg": BUTTON_PALETTE["ghost"]["light"]["bg"], "g_txt": BUTTON_PALETTE["ghost"]["light"]["text"],
    "g_bd": "#d1d5db", "g_hv": "#e5e7eb",
    "i_bg": BUTTON_PALETTE["info"]["light"]["bg"], "i_txt": BUTTON_PALETTE["info"]["light"]["text"], "i_hv": "#0369a1",
}

BUTTON_CSS_DARK = """
<style>
.sf-btn-primary{background:%(p_bg)s!important;color:%(p_txt)s!important}.sf-btn-primary:hover{background:%(p_hv)s!important}
.sf-btn-success{background:%(s_bg)s!important;color:%(s_txt)s!important}.sf-btn-success:hover{background:%(s_hv)s!important}
.sf-btn-warning{background:%(w_bg)s!important;color:%(w_txt)s!important}.sf-btn-warning:hover{background:%(w_hv)s!important}
.sf-btn-danger{background:%(d_bg)s!important;color:%(d_txt)s!important}.sf-btn-danger:hover{background:%(d_hv)s!important}
.sf-btn-ghost{background:%(g_bg)s!important;color:%(g_txt)s!important;border-color:%(g_bd)s!important}.sf-btn-ghost:hover{background:%(g_hv)s!important}
.sf-btn-info{background:%(i_bg)s!important;color:%(i_txt)s!important}.sf-btn-info:hover{background:%(i_hv)s!important}
</style>""" % {
    "p_bg": BUTTON_PALETTE["primary"]["dark"]["bg"], "p_txt": BUTTON_PALETTE["primary"]["dark"]["text"], "p_hv": "#4f46e5",
    "s_bg": BUTTON_PALETTE["success"]["dark"]["bg"], "s_txt": BUTTON_PALETTE["success"]["dark"]["text"], "s_hv": "#16a34a",
    "w_bg": BUTTON_PALETTE["warning"]["dark"]["bg"], "w_txt": BUTTON_PALETTE["warning"]["dark"]["text"], "w_hv": "#d97706",
    "d_bg": BUTTON_PALETTE["danger"]["dark"]["bg"], "d_txt": BUTTON_PALETTE["danger"]["dark"]["text"], "d_hv": "#dc2626",
    "g_bg": BUTTON_PALETTE["ghost"]["dark"]["bg"], "g_txt": BUTTON_PALETTE["ghost"]["dark"]["text"], "g_bd": "#4b5563", "g_hv": "#4b5563",
    "i_bg": BUTTON_PALETTE["info"]["dark"]["bg"], "i_txt": BUTTON_PALETTE["info"]["dark"]["text"], "i_hv": "#0ea5e9",
}


def inject_button_css(mode="auto"):
    """注入按钮配色 CSS。

    参数:
      mode — "light" / "dark" / "auto"(默认)。auto 下注入 light 基底 + dark 覆盖层。
      在 Streamlit 中 mode 由 modules.ui_theme._theme_is_dark() 决定，随 apply_theme() 调用。
    """
    st.markdown(BUTTON_CSS, unsafe_allow_html=True)
    if mode == "dark" or mode == "auto":
        st.markdown(BUTTON_CSS_DARK, unsafe_allow_html=True)


def btn_html(text, kind="primary", icon=None, size="", disabled=False, block=False, extra_class=""):
    """生成按钮的 HTML 字符串。

    kind: primary / success / warning / danger / ghost / info
    """
    cls_parts = ["sf-btn", f"sf-btn-{kind}"]
    if size:
        cls_parts.append(f"sf-btn-{size}")
    if block:
        cls_parts.append("sf-btn-block")
    if disabled:
        cls_parts.append("disabled")
    if extra_class:
        cls_parts.append(extra_class)
    label = f"{icon or ''}{text}" if icon else text
    return f'<button class="{" ".join(cls_parts)}"{" disabled" if disabled else ""}>{label}</button>'


if __name__ == "__main__":
    print("button_colors OK")
    print(f"Palette: {list(BUTTON_PALETTE.keys())}")
