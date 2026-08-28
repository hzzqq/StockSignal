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

_KIT_CSS = r"""
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

/* ===== 新城风格视觉层（参照 E:\project\app_dist\微应用大厅\index.html 2026-08-28 接入） =====
   命名空间 .xc-* 以避免污染既有 .sf-* / .ss-* 主题。深紫渐变 + 大圆角 + 抬升光晕。
   颜色走 var(--acc1)/(--acc2) 主题变量，自动跟 theme_mode 切亮/暗。
*/
.xc-hero{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:14px;
  margin:6px 0 22px;padding:18px 24px;border-radius:18px;
  background:linear-gradient(120deg,
    color-mix(in srgb, var(--acc1,#667eea) 22%, var(--card,#fff)) 0%,
    color-mix(in srgb, var(--acc2,#764ba2) 18%, var(--card,#fff)) 100%);
  border:1px solid color-mix(in srgb, var(--acc1,#667eea) 30%, var(--border,#e2e8f0));
  box-shadow:0 0 0 1px rgba(102,126,234,.14), 0 12px 32px rgba(102,126,234,.12);
  position:relative;overflow:hidden}
.xc-hero::before{content:"";position:absolute;inset:0;
  background:radial-gradient(circle at 12% -10%, rgba(124,92,255,.22), transparent 55%);
  pointer-events:none}
.xc-hero-main{display:flex;align-items:center;gap:14px;min-width:0;position:relative;z-index:1}
.xc-hero-icon{font-size:26px;line-height:1;flex-shrink:0;
  width:48px;height:48px;display:flex;align-items:center;justify-content:center;
  border-radius:14px;background:linear-gradient(135deg,var(--acc1,#667eea),var(--acc2,#764ba2));
  box-shadow:0 6px 18px rgba(102,126,234,.42)}
.xc-hero-title{font-size:22px;font-weight:800;letter-spacing:.3px;color:var(--txt,#1e293b);line-height:1.2}
.xc-hero-sub{font-size:13px;color:var(--txt2,#64748b);margin-top:4px;font-weight:500}
.xc-hero-chips{display:flex;gap:8px;flex-wrap:wrap;align-items:center;position:relative;z-index:1}

/* 新城卡片网格容器（auto-fill 自适应） */
.xc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(168px,1fr));gap:14px;margin:14px 0 22px}
.xc-card{background:var(--card,#fff);border:1px solid color-mix(in srgb,var(--acc1,#667eea) 22%,var(--border,#e2e8f0));
  border-radius:16px;padding:14px 16px;display:flex;flex-direction:column;gap:6px;position:relative;
  transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease;
  box-shadow:0 1px 4px rgba(15,15,35,.06)}
.xc-card:hover{transform:translateY(-4px);border-color:var(--acc1,#667eea);
  box-shadow:0 10px 30px rgba(102,126,234,.18)}
.xc-card .ctop{display:flex;align-items:center;gap:9px}
.xc-card .ico{width:36px;height:36px;border-radius:11px;display:flex;align-items:center;justify-content:center;
  font-size:18px;background:linear-gradient(135deg,var(--acc1,#667eea),var(--acc2,#764ba2));flex-shrink:0}
.xc-card .cname{font-size:14px;font-weight:600;color:var(--txt,#1e293b);line-height:1.2}
.xc-card .csub{font-size:11.5px;color:var(--txt2,#64748b);margin-top:1px}
.xc-card .value{font-size:22px;font-weight:800;font-family:'Fira Code',ui-monospace,monospace;line-height:1.15;letter-spacing:.2px}
.xc-card .delta{font-size:13px;font-weight:700;margin-top:2px}
.xc-card .delta.up{color:#ff4d4f}
.xc-card .delta.down{color:#00d486}
.xc-card .delta.flat{color:var(--txt2,#64748b)}
.xc-card .meta{font-size:11px;color:var(--txt2,#64748b);line-height:1.55;margin-top:4px}
.xc-card .meta .up{color:#ff4d4f}
.xc-card .meta .down{color:#00d486}
.xc-section-h{display:flex;align-items:center;gap:10px;margin:18px 0 12px;font-size:16px;font-weight:700;color:var(--txt,#1e293b)}
.xc-section-h::before{content:"";width:4px;height:18px;border-radius:3px;
  background:linear-gradient(180deg,var(--acc1,#667eea),var(--acc2,#764ba2))}
.xc-section-h .xtra{margin-left:auto;font-size:12px;font-weight:500;color:var(--txt2,#64748b)}

/* 新城信息横幅（info/success/warning/danger，沿用 xc 紫强调） */
.xc-info{display:flex;align-items:flex-start;gap:10px;padding:12px 14px;border-radius:12px;
  margin:10px 0;font-size:13.5px;line-height:1.6;color:var(--txt,#1e293b);
  border:1px solid color-mix(in srgb,var(--acc1,#667eea) 30%,var(--border,#e2e8f0));
  background:color-mix(in srgb,var(--acc1,#667eea) 8%,var(--card2,#f4f6fb))}
.xc-info .xc-ic{font-size:16px;line-height:1.4;flex-shrink:0}
.xc-info.success{border-left:3px solid #16a34a;background:rgba(22,163,74,.08)}
.xc-info.warning{border-left:3px solid #ffa502;background:rgba(255,165,2,.10)}
.xc-info.danger{border-left:3px solid #ef4444;background:rgba(239,68,68,.08)}

/* 新城友好错误卡 / 空态卡（不泄露内部异常，提供重试/降级引导） */
.xc-error-box,.xc-empty-box{display:flex;align-items:flex-start;gap:12px;padding:16px 18px;border-radius:14px;
  margin:14px 0;font-size:14px;line-height:1.6;color:var(--txt,#1e293b);
  border:1px solid var(--border,#e2e8f0);background:var(--card2,#f4f6fb)}
.xc-error-box{border-left:4px solid #ef4444;background:color-mix(in srgb,#ef4444 7%,var(--card2,#f4f6fb))}
.xc-empty-box{border-left:4px solid var(--acc1,#667eea);background:color-mix(in srgb,var(--acc1,#667eea) 6%,var(--card2,#f4f6fb))}
.xc-err-ic{font-size:22px;line-height:1.3;flex-shrink:0}
.xc-err-body{min-width:0}
.xc-err-title{font-weight:700;font-size:14.5px}
.xc-err-hint{margin-top:6px;font-size:12.5px;color:var(--txt2,#64748b)}
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
def _hero_html(title: str, icon: str = "📊", subtitle: str = "", chips: list = None,
               style: str = "xc") -> str:
    """签名页头 HTML。``style='xc'``（新城·默认）走 .xc-hero；``style='sf'`` 走原 .ss-hero 兜底。"""
    title = "" if title is None else str(title)
    icon = "📊" if icon is None else str(icon)
    chips = chips or []
    cls = "xc-hero" if style == "xc" else "ss-hero"
    icon_cls = "xc-hero-icon" if style == "xc" else "ss-hero-icon"
    title_cls = "xc-hero-title" if style == "xc" else "ss-hero-title"
    sub_cls = "xc-hero-sub" if style == "xc" else "ss-hero-sub"
    chips_cls = "xc-hero-chips" if style == "xc" else "ss-hero-chips"
    subtitle_html = (
        f'<div class="{sub_cls}">{html.escape(str(subtitle))}</div>' if subtitle else ""
    )
    chips_html = "".join(str(c) for c in chips)
    return (
        f'<div class="{cls}">'
        f'<div class="{cls}-main">'
        f'<span class="{icon_cls}">{html.escape(icon)}</span>'
        f'<div><div class="{title_cls}">{html.escape(title)}</div>{subtitle_html}</div>'
        f'</div>'
        f'<div class="{chips_cls}">{chips_html}</div>'
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
def page_hero(title: str, icon: str = "📊", subtitle: str = "", chips: list = None,
              style: str = "xc") -> None:
    """签名页头：图标 + 标题 + 副标题 + 右侧状态胶囊。所有页面统一视觉记忆点。

    ``style`` 默认 ``'xc'``（新城·`微应用大厅` 视觉），传入 ``'sf'`` 回退到旧星辰 .ss-hero。
    """
    inject_kit_css()
    st.markdown(_hero_html(title, icon, subtitle, chips, style=style), unsafe_allow_html=True)


def xc_section_header(title: str, xtra: str = "") -> str:
    """新城风格分区小标题（带渐变紫竖条 + 可选右侧标注）。返回 HTML 片段。"""
    title = "" if title is None else str(title)
    xtra_html = f'<span class="xtra">{html.escape(str(xtra))}</span>' if xtra else ""
    return f'<div class="xc-section-h">{html.escape(title)}{xtra_html}</div>'


def xc_subheader(title: str, icon: str = "", xtra: str = "") -> None:
    """新城风格分区标题（渲染版）。等同 xc_section_header 但直接渲染，替代裸 st.subheader。"""
    inject_kit_css()
    prefix = f"{html.escape(icon)} " if icon else ""
    st.markdown(xc_section_header(f"{prefix}{title}", xtra=xtra), unsafe_allow_html=True)


_BANNER_KIND_XC = {"info": "info", "success": "success", "warning": "warning", "danger": "danger"}


def xc_info_banner(text: str, kind: str = "info", icon: str = "💡") -> None:
    """新城风格彩色提示横幅（info/success/warning/danger）。"""
    inject_kit_css()
    text = "" if text is None else str(text)
    kind = _BANNER_KIND_XC.get(kind, "info")
    icon = "💡" if icon is None else str(icon)
    st.markdown(
        f'<div class="xc-info {kind}"><span class="xc-ic">{html.escape(icon)}</span>'
        f'<div>{html.escape(text)}</div></div>',
        unsafe_allow_html=True,
    )


def xc_error_box(title: str, hint: str = "", icon: str = "⚠️") -> None:
    """新城风格友好错误卡：不泄露内部异常细节，提供重试/降级引导。

    内部异常请由调用方用 logger.warning 记录，不要把原始异常拼进 title。
    """
    inject_kit_css()
    title = "" if title is None else str(title)
    icon = "⚠️" if icon is None else str(icon)
    hint_html = f'<div class="xc-err-hint">💡 {html.escape(str(hint))}</div>' if hint else ""
    st.markdown(
        f'<div class="xc-error-box"><span class="xc-err-ic">{html.escape(icon)}</span>'
        f'<div class="xc-err-body"><div class="xc-err-title">{html.escape(title)}</div>{hint_html}</div></div>',
        unsafe_allow_html=True,
    )


def xc_empty_box(title: str, hint: str = "", icon: str = "📭") -> None:
    """新城风格空态卡：数据为空/暂无时的友好占位。"""
    inject_kit_css()
    title = "" if title is None else str(title)
    icon = "📭" if icon is None else str(icon)
    hint_html = f'<div class="xc-err-hint">{html.escape(str(hint))}</div>' if hint else ""
    st.markdown(
        f'<div class="xc-empty-box"><span class="xc-err-ic">{html.escape(icon)}</span>'
        f'<div class="xc-err-body"><div class="xc-err-title">{html.escape(title)}</div>{hint_html}</div></div>',
        unsafe_allow_html=True,
    )


def xc_handle_error(title: str, exc: Exception | str | None = None, hint: str = "",
                    icon: str = "⚠️") -> None:
    """一站式「捕获异常 → 记录日志 → 友好展示」。

    取代 ``except Exception as e: st.error(f"...{e}")`` 这类直接把内部异常
    细节泄露给终端用户的反模式。异常文本只进日志（logger.warning），
    绝不拼进用户可见的 title。

    Args:
        title: 给用户看的中文友好文案（不含异常细节）。
        exc:   捕获到的异常对象（或其字符串），仅用于日志记录。
        hint:  可选的引导文案（重试 / 检查网络等）。
        icon:  展示图标，默认 ⚠️。
    """
    if exc is not None:
        logger.warning("%s: %s", title, exc)
    xc_error_box(title, hint=hint, icon=icon)


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
