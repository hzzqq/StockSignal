"""modules/ui_kit.py
StockSignal 通用 UI 组件层 v1（金融级视觉 · 暗/亮双主题自适应）。

定位：补齐既有 widget 体系里「缺失但高频」的展示层组件，与已有
``page_widgets``（_data_card / _empty_info / _toast）、``ui_theme``（card /
loading_spinner / section_header）、``button_colors`` 互补，不重复实现。

设计铁律（与项目一致）：
  ✅ 仅注入「视觉」CSS（颜色 / 圆角 / 阴影 / 边框 / 动效）与 HTML 片段，
     绝不改动任何业务/DOM 结构或逻辑。
  ✅ 所有数据派生文本统一 html.escape，杜绝存储型 XSS（与 _widgets_base /
     page_widgets 既有 XSS 契约对齐）。
  ✅ 颜色全部走 CSS 变量（--acc1/--acc2/--txt/--txt2/--border/--card/--bg），
     并内置 fallback，保证未加载其它主题 CSS 的页面也能正常渲染。
  ✅ inject_kit_css 用 session_state 去重，全页面仅注入一次。

提供：
  - inject_kit_css()            一次性注入组件 CSS（自动去重）
  - page_hero(...)              签名页头（图标 + 标题 + 副标题 + 状态胶囊）
  - info_banner(...)            彩色提示横幅（info/success/warning/danger）
  - stat_tile(...)              指标瓦片（标签 + 大值 + 涨跌 delta）
  - chart_card(...)             图表容器卡片（标题栏 + 圆角卡片）
  - table_wrap(...)             响应式表格容器（移动端横向滚动）
  - 以及对应的 _xxx_html 纯函数（便于离线单测与复用）
"""
from __future__ import annotations

import html
import logging

logger = logging.getLogger(__name__)

import streamlit as st

_KIT_CSS = """
<style>
/* ===== ui_kit v1 组件层（沿用 ui_theme 主题变量 --acc1/--txt/--card/--border，随 theme_mode 自适应） ===== */

/* ---- 签名页头 hero ---- */
.ss-hero{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;
  margin:4px 0 18px;padding:16px 20px;border-radius:16px;
  background:linear-gradient(120deg,
    color-mix(in srgb, var(--acc1,#667eea) 16%, var(--card,#fff)) 0%,
    color-mix(in srgb, var(--acc2,#764ba2) 14%, var(--card,#fff)) 100%);
  border:1px solid var(--border,#e2e8f0);
  box-shadow:0 0 0 1px rgba(102,126,234,.10), 0 8px 24px rgba(15,15,35,.10);}
.ss-hero-main{display:flex;align-items:center;gap:14px;min-width:0}
.ss-hero-icon{font-size:26px;line-height:1;flex-shrink:0;
  width:46px;height:46px;display:flex;align-items:center;justify-content:center;
  border-radius:12px;background:linear-gradient(135deg,var(--acc1,#667eea),var(--acc2,#764ba2));
  box-shadow:0 4px 14px rgba(102,126,234,.35)}
.ss-hero-title{font-size:20px;font-weight:800;letter-spacing:.3px;color:var(--txt,#1e293b);line-height:1.2}
.ss-hero-sub{font-size:13px;color:var(--txt2,#64748b);margin-top:3px}
.ss-hero-chips{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.ss-pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;
  padding:5px 12px;border-radius:999px;border:1px solid var(--border,#e2e8f0);
  background:var(--card2,#f4f6fb);color:var(--txt2,#64748b)}
.ss-pill .dot{width:7px;height:7px;border-radius:50%;background:var(--txt2,#64748b)}
.ss-pill.open .dot{background:#ff4d4f;box-shadow:0 0 0 3px rgba(255,77,79,.25)}
.ss-pill.closed .dot{background:#00d486}
.ss-pill.theme-dark{color:#c7d2fe;border-color:#3b3b66;background:#1a1a2e}
.ss-pill.theme-light{color:#4338ca;border-color:#c7d2fe;background:#eef2ff}

/* ---- 信息横幅 ---- */
.ss-info{display:flex;align-items:flex-start;gap:10px;padding:12px 14px;border-radius:12px;
  margin:10px 0;font-size:13.5px;line-height:1.6;color:var(--txt,#1e293b);
  border:1px solid var(--border,#e2e8f0);background:var(--card2,#f4f6fb)}
.ss-info .ss-ic{font-size:16px;line-height:1.4;flex-shrink:0}
.ss-info.info{border-left:3px solid var(--acc1,#667eea);background:color-mix(in srgb,var(--acc1,#667eea) 8%,var(--card2,#f4f6fb))}
.ss-info.success{border-left:3px solid #16a34a;background:rgba(22,163,74,.08);color:var(--txt,#1e293b)}
.ss-info.warning{border-left:3px solid #ffa502;background:rgba(255,165,2,.10)}
.ss-info.danger{border-left:3px solid #ef4444;background:rgba(239,68,68,.08)}

/* ---- 指标瓦片 ---- */
.ss-stat{background:var(--card,#fff);border:1px solid var(--border,#e2e8f0);border-radius:14px;
  padding:14px 16px;box-shadow:0 1px 4px rgba(15,15,35,.06);min-width:0}
.ss-stat .label{font-size:12px;color:var(--txt2,#64748b);margin-bottom:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ss-stat .value{font-size:24px;font-weight:800;line-height:1.1;font-family:'Fira Code',ui-monospace,monospace;color:var(--txt,#1e293b)}
.ss-stat .delta{font-size:13px;font-weight:600;margin-top:4px}
.ss-stat .delta.up{color:#ff4d4f} .ss-stat .delta.down{color:#00d486} .ss-stat .delta.flat{color:var(--txt2,#64748b)}
.ss-stat-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:12px 0}

/* ---- 图表卡片 ---- */
.ss-chart{background:var(--card,#fff);border:1px solid var(--border,#e2e8f0);border-radius:16px;
  padding:16px 18px;margin:12px 0;box-shadow:0 1px 6px rgba(15,15,35,.06)}
.ss-chart h3{display:flex;align-items:center;gap:8px;margin:0 0 12px;font-size:15px;font-weight:700;color:var(--txt,#1e293b)}
.ss-chart h3::before{content:"";width:4px;height:16px;border-radius:3px;
  background:linear-gradient(180deg,var(--acc1,#667eea),var(--acc2,#764ba2))}

/* ---- 响应式表格容器 ---- */
.ss-table-wrap{width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch;
  border:1px solid var(--border,#e2e8f0);border-radius:12px;margin:10px 0}
.ss-table{width:100%;border-collapse:collapse;font-size:12.5px}
.ss-table th,.ss-table td{padding:9px 10px;text-align:center;border-bottom:1px solid var(--border,#e2e8f0);white-space:nowrap}
.ss-table thead th{position:sticky;top:0;background:var(--card2,#f4f6fb);color:var(--txt2,#64748b);
  font-weight:600;font-size:12px;z-index:1}
.ss-table tbody tr:nth-child(even){background:color-mix(in srgb,var(--card2,#f4f6fb) 55%,transparent)}
.ss-table tbody tr:hover{background:color-mix(in srgb,var(--acc1,#667eea) 10%,var(--card2,#f4f6fb))}

/* ---- 既有 .sf-table 增强：粘性表头 + 斑马纹 + 行 hover（沿用主题变量，随 theme_mode 自适应） ---- */
.sf-table thead th{position:sticky;top:0;background:var(--card2,#f4f6fb);color:var(--txt2,#64748b);
  font-weight:600;z-index:1}
.sf-table tbody tr:nth-child(even){background:color-mix(in srgb,var(--card2,#f4f6fb) 55%,transparent)}
.sf-table tbody tr:hover{background:color-mix(in srgb,var(--acc1,#667eea) 12%,var(--card2,#f4f6fb))}
</style>
"""

_INJECTED_KEY = "_ui_kit_css_v1"


def inject_kit_css() -> None:
    """注入 ui_kit 组件 CSS（全页面仅一次，session_state 去重）。"""
    if st.session_state.get(_INJECTED_KEY):
        return
    try:
        st.markdown(_KIT_CSS, unsafe_allow_html=True)
        st.session_state[_INJECTED_KEY] = True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[ui_kit] 处理异常: {e}")


# ──────────────────────────────────────────────────────────────
# 纯函数 HTML 构建器（便于离线单测 / XSS 校验）
# ──────────────────────────────────────────────────────────────
def _hero_html(title: str, icon: str = "📊", subtitle: str = "", chips: list = None) -> str:
    title = "" if title is None else str(title)
    icon = "📊" if icon is None else str(icon)
    subtitle_html = f'<div class="ss-hero-sub">{html.escape(str(subtitle))}</div>' if subtitle else ""
    chips = chips or []
    chips_html = "".join(str(c) for c in chips)
    return (
        f'<div class="ss-hero">'
        f'<div class="ss-hero-main">'
        f'<span class="ss-hero-icon">{html.escape(icon)}</span>'
        f'<div><div class="ss-hero-title">{html.escape(title)}</div>{subtitle_html}</div>'
        f'</div>'
        f'<div class="ss-hero-chips">{chips_html}</div>'
        f'</div>'
    )


_BANNER_KIND_CLASS = {
    "info": "info", "success": "success", "warning": "warning", "danger": "danger",
}


def _info_banner_html(text: str, kind: str = "info", icon: str = "💡") -> str:
    text = "" if text is None else str(text)
    kind = _BANNER_KIND_CLASS.get(kind, "info")
    icon = "💡" if icon is None else str(icon)
    return (
        f'<div class="ss-info {kind}">'
        f'<span class="ss-ic">{html.escape(icon)}</span>'
        f'<div>{html.escape(text)}</div>'
        f'</div>'
    )


def _stat_tile_html(label: str, value: str, delta: str = "", delta_dir: str = "flat",
                    accent: str = None) -> str:
    label = "" if label is None else str(label)
    value = "" if value is None else str(value)
    delta = delta or ""
    delta_dir = delta_dir if delta_dir in ("up", "down", "flat") else "flat"
    accent = html.escape(accent, quote=True) if accent else "var(--ss-acc1)"
    delta_html = f'<div class="delta {delta_dir}">{html.escape(delta)}</div>' if delta else ""
    return (
        f'<div class="ss-stat" style="border-top:3px solid {accent}">'
        f'<div class="label">{html.escape(label)}</div>'
        f'<div class="value">{html.escape(value)}</div>'
        f'{delta_html}</div>'
    )


def _chart_card_html(title: str, body_html: str) -> str:
    title = "" if title is None else str(title)
    body_html = body_html or ""
    return (
        f'<div class="ss-chart"><h3>{html.escape(title)}</h3>{body_html}</div>'
    )


def _table_wrap_html(table_html: str) -> str:
    table_html = table_html or ""
    return f'<div class="ss-table-wrap">{table_html}</div>'


# ──────────────────────────────────────────────────────────────
# 公开封装（注入 CSS + 渲染）
# ──────────────────────────────────────────────────────────────
def page_hero(title: str, icon: str = "📊", subtitle: str = "", chips: list = None) -> None:
    """签名页头：图标 + 标题 + 副标题 + 右侧状态胶囊。所有页面统一视觉记忆点。"""
    inject_kit_css()
    st.markdown(_hero_html(title, icon, subtitle, chips), unsafe_allow_html=True)


def info_banner(text: str, kind: str = "info", icon: str = "💡") -> None:
    """彩色提示横幅。kind: info/success/warning/danger。"""
    inject_kit_css()
    st.markdown(_info_banner_html(text, kind, icon), unsafe_allow_html=True)


def stat_tile(label: str, value: str, delta: str = "", delta_dir: str = "flat",
              accent: str = None) -> None:
    """单个指标瓦片。delta_dir: up/down/flat（A股红涨绿跌，up=红）。"""
    inject_kit_css()
    st.markdown(_stat_tile_html(label, value, delta, delta_dir, accent), unsafe_allow_html=True)


def stat_row(tiles: list) -> None:
    """一行多瓦片（自适应换行）。tiles: list of dict(label,value,delta,delta_dir,accent)。"""
    inject_kit_css()
    cells = "".join(
        _stat_tile_html(
            t.get("label", ""), t.get("value", ""), t.get("delta", ""),
            t.get("delta_dir", "flat"), t.get("accent"),
        )
        for t in tiles
    )
    st.markdown(f'<div class="ss-stat-row">{cells}</div>', unsafe_allow_html=True)


def chart_card(title: str, body_html: str) -> None:
    """图表容器卡片：标题栏 + 圆角卡片包裹 Plotly/HTML 图表。"""
    inject_kit_css()
    st.markdown(_chart_card_html(title, body_html), unsafe_allow_html=True)


def table_wrap(table_html: str) -> None:
    """响应式表格容器：移动端横向滚动 + 粘性表头。"""
    inject_kit_css()
    st.markdown(_table_wrap_html(table_html), unsafe_allow_html=True)
