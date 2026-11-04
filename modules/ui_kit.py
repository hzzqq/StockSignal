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
  ✅ 颜色全部走 CSS 变量（--brand-1/--brand-2/--txt/--txt2/--border/--card/--bg），
     并内置 fallback，保证未加载其它主题 CSS 的页面也能正常渲染。
  ✅ inject_kit_css 每次调用都注入（T-180 教训：session_state 去重会导致
     st.switch_page 导航重建 DOM 后跳过注入 → 新页面样式全丢）。

提供：
  - inject_kit_css()            每次注入组件 CSS（幂等，不做去重）
  - page_hero(...)              签名页头（图标 + 标题 + 副标题 + 状态胶囊）
  - xc_info_banner(...)         彩色提示横幅（info/success/warning/danger；旧名 info_banner 已 deprecated）
  - stat_tile(...)              指标瓦片（标签 + 大值 + 涨跌 delta）
  - chart_card(...)             图表容器卡片 ⚠️deprecated（零生产调用，新代码用 xc_chart_cell）
  - table_wrap(...)             响应式表格容器（移动端横向滚动）
  - 以及对应的 _xxx_html 纯函数（便于离线单测与复用）
"""
from __future__ import annotations

import contextlib
import html
import logging
import re

logger = logging.getLogger(__name__)

import streamlit as st

_TOKEN_CSS = r"""
<style>
/* ===== 设计令牌层（T-145 A1，spec: .workbuddy/specs/t145_ui_upgrade_contract.md）=====
   语义色 --ss-up/--ss-down = modules/colors.UP_COLOR/DOWN_COLOR（A股红涨绿跌，语义不可反转）；
   主题色 token 是 ui_theme :root 七变量的语义化别名（权威色值仍在 ui_theme.dashboard_sf_css）；
   空间/圆角/阴影/字体 token 先接入共享值，非标值（10/14/18px 等）渐进收敛不强改。 */
:root{
  --ss-ok:#16a34a; --ss-warn:#ffa502; --ss-warn-strong:#f59e0b; --ss-danger:#ef4444;
  --ss-accent:var(--brand-1,#667eea); --ss-accent2:var(--brand-2,#764ba2);
  --ss-surface:var(--card,#fff); --ss-surface-2:var(--card2,#f4f6fb);
  --ss-text:var(--txt,#1e293b); --ss-text-muted:var(--txt2,#64748b);
  --ss-line:var(--border,#e2e8f0);
  --ss-radius:12px; --ss-radius-card:16px; --ss-radius-pill:999px;
  --ss-radius-xs:3px; --ss-radius-sm:8px; --ss-radius-lg:14px;
  --ss-space-1:4px; --ss-space-2:8px; --ss-space-3:12px; --ss-space-4:16px; --ss-space-5:20px; --ss-space-6:24px;
  --ss-shadow-card:0 1px 4px rgba(15,15,35,.06);
  --ss-shadow-lift:0 10px 30px var(--ss-glow-soft);
  --ss-shadow-hero:0 0 0 1px var(--ss-glow-soft),0 12px 32px var(--ss-glow-soft);
  --ss-font-num:'Fira Code',ui-monospace,monospace;
  /* T-261：全局中文排版字体栈（Windows 本机优先微软雅黑 UI，macOS 回退苹方） */
  --ss-font-cjk:'Microsoft YaHei UI','PingFang SC','Microsoft YaHei','Source Han Sans SC',system-ui,sans-serif;
  /* v10 微动效令牌（T-176） */
  --ss-fade:.25s;
  /* ===== L3 组件语义层（ui-ds 设计系统 Phase1，P0 批次）=====
     目标：消除组件层硬编码紫 rgba（经典紫 #667eea / 深紫 #7c5cff）——
     terminal（琥珀）/cyber（黄青）风格下紫光穿帮的根因。
     全部由 L2 语义别名 color-mix 派生（无新硬编码色相），七风格自动随
     --ss-accent/--ss-accent2 换色相。P0 纯 additive：组件引用暂不切换，
     P0.5 起 _KIT_CSS/dashboard_sf_css 逐处替换为 var() 引用（G1 守卫跟进）。 */
  --ss-glow:color-mix(in srgb,var(--ss-accent) 35%,transparent);
  --ss-glow-soft:color-mix(in srgb,var(--ss-accent) 18%,transparent);
  --ss-hero-overlay:color-mix(in srgb,var(--ss-accent2) 22%,transparent);
  --ss-card-border:color-mix(in srgb,var(--ss-accent) 22%,var(--ss-line));
  --ss-card-border-strong:color-mix(in srgb,var(--ss-accent) 28%,var(--ss-line));
  --ss-pill-dark-fg:color-mix(in srgb,var(--ss-accent) 78%,#ffffff);
  --ss-pill-dark-bg:color-mix(in srgb,var(--ss-accent) 24%,#1a1a2e);
  --ss-focus-ring:var(--ss-accent);
  /* P1-2d 信息盒族独立语义四色（ui-ds Phase1 §2.2④）：success 从 --ss-down（跌价绿）
     解耦到 --ss-ok（恒绿系功能色），消除「信息盒绿色 ≠ 跌价」认知风险；
     info/warn/danger 为同值别名，为浅色风格对比度预留独立调节点。 */
  --ss-box-info:var(--ss-accent);
  --ss-box-success:var(--ss-ok);
  --ss-box-warn:var(--ss-warn-strong);
  --ss-box-danger:var(--ss-danger);
  /* L3 字号阶梯（Phase1 §1.3：13/13.5/14/14.5/15/16/17/20/22 散布收敛 6 级） */
  --ss-fs-display:22px; --ss-fs-hero:22px; --ss-fs-title:16px;
  --ss-fs-body:13.5px; --ss-fs-label:12px; --ss-fs-caption:11px;
  /* design_system.md §2 新增语义别名（绑定 --ss-* / --acc* 等价变量或 colors.* 既有值，
     绝不臆造独立色相；供未来 page 迁移复用，对现有 --brand-1/--ss-* 消费者零影响） */
  --c-up:var(--ss-up,#ff4d4f); --c-down:var(--ss-down,#00d486); --c-hold:#ffa502;
  --c-warn:#f59e0b; --c-danger:#ef4444; --c-info:#3b82f6; --c-ok:var(--ss-ok,#16a34a);
  --radius-card:var(--ss-radius-card,16px); --radius-btn:6px; --radius-input:4px; --radius-pill:var(--ss-radius-pill,999px);
  --font-num:var(--ss-font-num); --font-cjk:var(--ss-font-cjk);
}
/* ===== T-261 全局排版：中文优化字体栈 + 阅读行高 =====
   Streamlit 默认 Source Sans Pro 对中文回退随机（宋体/雅黑混杂），统一为
   CJK 优先栈；等宽场景（code/pre/数字）由各组件显式字体保留，不受影响。 */
body, .stApp, [data-testid="stMarkdownContainer"], .stMarkdown,
[data-testid="stSidebar"], [data-testid="stSidebar"] * {
  font-family: var(--ss-font-cjk);
}
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li {
  line-height: 1.65;
  letter-spacing: .1px;
}
code, pre, [data-testid="stCodeBlock"], [data-testid="stCodeBlock"] code,
.ss-stat .value, .xc-card .value {
  font-family: var(--ss-font-num) !important;
}
@keyframes ss-fade-in{from{opacity:0;transform:translateY(3px)}to{opacity:1;transform:none}}
/* hero 与统计卡：单次淡入 + stat 悬浮轻抬（克制微动效） */
.ss-hero{animation:ss-fade-in var(--ss-fade) ease both}
.ss-stat{transition:transform .18s ease,box-shadow .18s ease;border-radius:var(--ss-radius-card);box-shadow:var(--ss-shadow-card)}
.ss-stat:hover{transform:translateY(-2px);box-shadow:var(--ss-shadow-lift)}
::selection{background:color-mix(in srgb,var(--ss-accent) 30%,transparent)}
@media (prefers-reduced-motion: reduce){*{animation:none!important;transition:none!important}}
</style>
"""


def _build_token_css() -> str:
    """design_system.md 第5章C阶段：令牌单一来源生成器——语义别名由 ``modules.colors`` 派生。

    返回的别名串等同于 ``_TOKEN_CSS`` 内「design_system.md 新增语义别名」段，
    是 CSS 侧别名与 Python 侧单一来源 ``colors.*`` 之间的一致性交接点。
    守卫 ``test_ui_kit_tokens`` 用本函数断言「CSS 别名 == colors.* 值」。
    """
    from modules import colors
    return (
        "--brand-1:#4f46e5; --brand-2:#7c3aed;"
        f"--c-up:{colors.UP_COLOR}; --c-down:{colors.DOWN_COLOR}; --c-hold:{colors.HOLD_COLOR};"
        f"--c-warn:{colors.SIG_WARNING}; --c-danger:{colors.SIG_DANGER};"
        f"--c-info:{colors.SIG_INFO}; --c-ok:var(--ss-ok,#16a34a);"
    )


_KIT_CSS = _TOKEN_CSS + r"""
<style>
/* ===== ui_kit v1 组件层（沿用 ui_theme 主题变量 --brand-1/--txt/--card/--border，随 theme_mode 自适应） ===== */

/* ---- 签名页头 hero ----
   ⚠️ deprecated（ui-ds Phase1 §2.3）：.ss-hero 旧星辰词汇，HTML 构建器默认路由 .xc-hero；
   本块仍被 _hero_html(style='sf') 兜底分支引用，【必须保留】，禁删。 */
.ss-hero{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:var(--ss-space-3);
  margin:var(--ss-space-1) 0 var(--ss-space-5);padding:var(--ss-space-4) var(--ss-space-5);border-radius:var(--ss-radius-card);
  background:linear-gradient(120deg,
    color-mix(in srgb, var(--ss-accent) 16%, var(--ss-surface)) 0%,
    color-mix(in srgb, var(--ss-accent2) 14%, var(--ss-surface)) 100%);
  border:1px solid var(--ss-line);
  box-shadow:0 0 0 1px var(--ss-glow-soft), 0 8px 24px rgba(15,15,35,.10);}
.ss-hero-main{display:flex;align-items:center;gap:14px;min-width:0}
.ss-hero-icon{font-size:26px;line-height:1;flex-shrink:0;
  width:46px;height:46px;display:flex;align-items:center;justify-content:center;
  border-radius:var(--ss-radius);background:linear-gradient(135deg,var(--ss-accent),var(--ss-accent2));
  box-shadow:0 4px 14px var(--ss-glow)}
.ss-hero-title{font-size:20px;font-weight:800;letter-spacing:.3px;color:var(--ss-text);line-height:1.2}
.ss-hero-sub{font-size:13px;color:var(--ss-text-muted);margin-top:3px}
.ss-hero-chips{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.ss-pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;
  padding:5px 12px;border-radius:var(--ss-radius-pill);border:1px solid var(--ss-line);
  background:var(--ss-surface-2);color:var(--ss-text-muted)}
.ss-pill .dot{width:7px;height:7px;border-radius:50%;background:var(--ss-text-muted)}
.ss-pill.open .dot{background:var(--ss-up);box-shadow:0 0 0 3px rgba(255,77,79,.25)}
.ss-pill.closed .dot{background:var(--ss-down)}
/* P1-2 pill 令牌化（ui-ds Phase1 §2.2①痛3）：indigo 硬编码改读 L3 --ss-pill-dark-*，
   七风格下自动随 --ss-accent 换色相（terminal 琥珀/cyber 黄青不再残留经典星辰紫）；
   border 由 bg/fg 派生（color-mix，无新硬编码色相）。theme-light 无对应令牌，暂保留（零引用死规则，见回报）。 */
.ss-pill.theme-dark{color:var(--ss-pill-dark-fg);
  border-color:color-mix(in srgb,var(--ss-pill-dark-bg) 85%,var(--ss-pill-dark-fg));
  background:var(--ss-pill-dark-bg)}
/* [deprecated 2026-11-01] .ss-pill.theme-light 零引用死规则（全仓 grep 0 处），
   且 phase1 未批 --ss-pill-light-* 令牌——保留规则本体待浅色风格需要时再激活，
   禁止新增调用（G5 精神：先登记令牌再使用）。 */
.ss-pill.theme-light{color:#4338ca;border-color:#c7d2fe;background:#eef2ff}

/* ---- 信息横幅 ----
   ⚠️ deprecated（ui-ds Phase1 §2.3）：.ss-info 旧词汇，信息横幅已收敛到 .xc-info
   （xc_info_banner / info_banner 双入口同构）。规则仅剩兜底价值，保留不删
   （test_ui_kit_tokens 锁 .ss-stat 存在性同族约束）；pages 禁新增 class="ss-info" 字面量。 */
.ss-info{display:flex;align-items:flex-start;gap:10px;padding:12px 14px;border-radius:var(--ss-radius);
  margin:10px 0;font-size:13.5px;line-height:1.6;color:var(--ss-text);
  border:1px solid var(--ss-line);background:var(--ss-surface-2)}
.ss-info .ss-ic{font-size:16px;line-height:1.4;flex-shrink:0}
.ss-info.info{border-left:3px solid var(--ss-accent);background:color-mix(in srgb,var(--ss-accent) 8%,var(--ss-surface-2))}
.ss-info.success{border-left:3px solid var(--ss-ok);background:color-mix(in srgb,var(--ss-ok) 8%,transparent);color:var(--ss-text)}
.ss-info.warning{border-left:3px solid var(--ss-warn);background:color-mix(in srgb,var(--ss-warn) 10%,transparent)}
.ss-info.danger{border-left:3px solid var(--ss-danger);background:color-mix(in srgb,var(--ss-danger) 8%,transparent)}

/* ---- 指标瓦片 ----
   ⚠️ deprecated（ui-ds Phase1 §2.3）：.ss-stat 旧词汇，指标瓦片已收敛到 .xc-card
   （stat_tile/_stat_tile_html → _xc_card_html 单一 canonical）。规则本体保留不删
   ——test_ui_kit_tokens::test_primitives_read_tokens_no_stray_hex L72-74 锁 .ss-stat{
   存在性；pages 禁新增 class="ss-stat" 字面量。 */
.ss-stat{background:var(--ss-surface);border:1px solid var(--ss-line);border-radius:var(--ss-radius-card);
  padding:14px 16px;box-shadow:var(--ss-shadow-card);min-width:0}
.ss-stat .label{font-size:12px;color:var(--ss-text-muted);margin-bottom:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ss-stat .value{font-size:24px;font-weight:800;line-height:1.1;font-family:var(--ss-font-num);color:var(--ss-text)}
.ss-stat .delta{font-size:13px;font-weight:600;margin-top:4px}
.ss-stat .delta.up{color:var(--ss-up)} .ss-stat .delta.down{color:var(--ss-down)} .ss-stat .delta.flat{color:var(--ss-text-muted)}
.ss-stat-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:12px 0}

/* ---- 图表卡片 ----
   ⚠️ deprecated（ui-ds Phase1 §2.3 + phase3 §1.4 裁定）：.ss-chart HTML 包图路线已被
   实践淘汰（chart_card 生产调用为零——Streamlit 元素独立容器，无法跨容器包裹
   st.plotly_chart）。规则保留不删（test_ui_kit 锁 _chart_card_html 契约）；
   图表卡新入口是 xc_chart_cell（标题条）+ 页面紧随 st.plotly_chart。 */
.ss-chart{background:var(--ss-surface);border:1px solid var(--ss-line);border-radius:var(--ss-radius-card);
  padding:16px 18px;margin:12px 0;box-shadow:0 1px 6px rgba(15,15,35,.06)}
.ss-chart h3{display:flex;align-items:center;gap:8px;margin:0 0 12px;font-size:15px;font-weight:700;color:var(--ss-text)}
.ss-chart h3::before{content:"";width:4px;height:16px;border-radius:var(--ss-radius-xs);
  background:linear-gradient(180deg,var(--ss-accent),var(--ss-accent2))}

/* ---- 响应式表格容器 ---- */
.ss-table-wrap{width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch;
  border:1px solid var(--ss-line);border-radius:var(--ss-radius);margin:10px 0}
.ss-table{width:100%;border-collapse:collapse;font-size:12.5px}
.ss-table th,.ss-table td{padding:9px 10px;text-align:center;border-bottom:1px solid var(--ss-line);white-space:nowrap}
.ss-table thead th{position:sticky;top:0;background:var(--ss-surface-2);color:var(--ss-text-muted);
  font-weight:600;font-size:12px;z-index:1}
.ss-table tbody tr:nth-child(even){background:color-mix(in srgb,var(--ss-surface-2) 55%,transparent)}
.ss-table tbody tr:hover{background:color-mix(in srgb,var(--ss-accent) 10%,var(--ss-surface-2))}

/* ---- 既有 .sf-table 增强：粘性表头 + 斑马纹 + 行 hover（沿用主题变量，随 theme_mode 自适应） ---- */
.sf-table thead th{position:sticky;top:0;background:var(--ss-surface-2);color:var(--ss-text-muted);
  font-weight:600;z-index:1}
.sf-table tbody tr:nth-child(even){background:color-mix(in srgb,var(--ss-surface-2) 55%,transparent)}
.sf-table tbody tr:hover{background:color-mix(in srgb,var(--ss-accent) 12%,var(--ss-surface-2))}

/* ===== 新城风格视觉层（参照 app_dist/微应用大厅/index.html 2026-08-28 接入） =====
   命名空间 .xc-* 以避免污染既有 .sf-* / .ss-* 主题。深紫渐变 + 大圆角 + 抬升光晕。
   颜色走 var(--brand-1)/(--brand-2) 主题变量，自动跟 theme_mode 切亮/暗。
*/
.xc-hero{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:14px;
  margin:6px 0 22px;padding:18px 24px;border-radius:var(--ss-radius-card);
  background:linear-gradient(120deg,
    color-mix(in srgb, var(--ss-accent) 22%, var(--ss-surface)) 0%,
    color-mix(in srgb, var(--ss-accent2) 18%, var(--ss-surface)) 100%);
  border:1px solid color-mix(in srgb, var(--ss-accent) 30%, var(--ss-line));
  box-shadow:var(--ss-shadow-hero);
  position:relative;overflow:hidden}
.xc-hero::before{content:"";position:absolute;inset:0;
  background:radial-gradient(circle at 12% -10%, var(--ss-hero-overlay), transparent 55%);
  pointer-events:none}
.xc-hero-main{display:flex;align-items:center;gap:14px;min-width:0;position:relative;z-index:1}
.xc-hero-icon{font-size:26px;line-height:1;flex-shrink:0;
  width:48px;height:48px;display:flex;align-items:center;justify-content:center;
  border-radius:var(--ss-radius-lg);background:linear-gradient(135deg,var(--ss-accent),var(--ss-accent2));
  box-shadow:0 6px 18px var(--ss-glow)}
.xc-hero-title{font-size:22px;font-weight:800;letter-spacing:.3px;color:var(--ss-text);line-height:1.2}
.xc-hero-sub{font-size:13px;color:var(--ss-text-muted);margin-top:4px;font-weight:500}
.xc-hero-chips{display:flex;gap:8px;flex-wrap:wrap;align-items:center;position:relative;z-index:1}

/* 新城卡片网格容器（auto-fill 自适应） */
.xc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(168px,1fr));gap:14px;margin:14px 0 22px}
.xc-card{background:var(--ss-surface);border:1px solid color-mix(in srgb,var(--ss-accent) 22%,var(--ss-line));
  border-radius:var(--ss-radius-card);padding:14px 16px;display:flex;flex-direction:column;gap:6px;position:relative;
  transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease;
  box-shadow:var(--ss-shadow-card)}
.xc-card:hover{transform:translateY(-4px);border-color:var(--ss-accent);
  box-shadow:var(--ss-shadow-lift)}
.xc-card .ctop{display:flex;align-items:center;gap:9px}
.xc-card .ico{width:36px;height:36px;border-radius:var(--ss-radius);display:flex;align-items:center;justify-content:center;
  font-size:18px;background:linear-gradient(135deg,var(--ss-accent),var(--ss-accent2));flex-shrink:0}
.xc-card .cname{font-size:14px;font-weight:600;color:var(--ss-text);line-height:1.2}
.xc-card .csub{font-size:11.5px;color:var(--ss-text-muted);margin-top:1px}
.xc-card .value{font-size:22px;font-weight:800;font-family:var(--ss-font-num);line-height:1.15;letter-spacing:.2px}
.xc-card .delta{font-size:13px;font-weight:700;margin-top:2px}
.xc-card .delta.up{color:var(--ss-up)}
.xc-card .delta.down{color:var(--ss-down)}
.xc-card .delta.flat{color:var(--ss-text-muted)}
/* KPI 主数值语义色（A 股红涨绿跌；flat 用主文本色） */
.xc-card .value.up{color:var(--ss-up)}
.xc-card .value.down{color:var(--ss-down)}
.xc-card .value.flat{color:var(--ss-text)}
.xc-card .meta{font-size:11px;color:var(--ss-text-muted);line-height:1.55;margin-top:4px}
.xc-card .meta .up{color:var(--ss-up)}
.xc-card .meta .down{color:var(--ss-down)}
.xc-section-h{display:flex;align-items:flex-start;gap:10px;margin:18px 0 12px;font-size:16px;font-weight:700;color:var(--ss-text)}
.xc-section-h::before{content:"";width:4px;height:18px;border-radius:var(--ss-radius-xs);flex-shrink:0;margin-top:3px;
  background:linear-gradient(180deg,var(--ss-accent),var(--ss-accent2))}
.xc-sh-main{display:flex;flex-direction:column;min-width:0}
.xc-sh-title{line-height:1.3}
.xc-sh-sub{font-size:12px;font-weight:400;color:var(--ss-text-muted);margin-top:3px;line-height:1.5}
.xc-sh-ic{font-size:16px;line-height:1.4;flex-shrink:0}
.xc-sh-xtra{margin-left:auto;font-size:12px;font-weight:500;color:var(--ss-text-muted);flex-shrink:0}

/* Bento 非对称网格容器（2026 市面范式：错落大卡 + 小卡，轻量、零重渲染） */
.xc-bento{display:grid;gap:16px;margin:14px 0 22px;grid-auto-rows:1fr;
  grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}
.xc-bento-cell{background:var(--ss-surface);border:1px solid color-mix(in srgb,var(--ss-accent) 20%,var(--ss-line));
  border-radius:var(--ss-radius-card);padding:14px 16px;position:relative;min-width:0;
  transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease;box-shadow:var(--ss-shadow-card)}
.xc-bento-cell:hover{transform:translateY(-4px);border-color:var(--ss-accent);box-shadow:var(--ss-shadow-lift)}

/* 新城信息横幅（info/success/warning/danger，沿用 xc 紫强调） */
.xc-info{display:flex;align-items:flex-start;gap:10px;padding:12px 14px;border-radius:var(--ss-radius);
  margin:10px 0;font-size:13.5px;line-height:1.6;color:var(--ss-text);
  border:1px solid color-mix(in srgb,var(--ss-accent) 30%,var(--ss-line));
  background:color-mix(in srgb,var(--ss-accent) 8%,var(--ss-surface-2))}
.xc-info .xc-ic{font-size:16px;line-height:1.4;flex-shrink:0}
.xc-info.success{border-left:3px solid var(--ss-box-success);background:color-mix(in srgb,var(--ss-box-success) 8%,transparent)}
.xc-info.warning{border-left:3px solid var(--ss-warn);background:color-mix(in srgb,var(--ss-warn) 10%,transparent)}
.xc-info.danger{border-left:3px solid var(--ss-danger);background:color-mix(in srgb,var(--ss-danger) 8%,transparent)}

/* 新城内容卡（1:1 替代 ui_theme.sf_card，统一组件词汇到 xc_*；令牌化、主题自适应） */
.xc-content-card{background:var(--ss-surface);border:1px solid color-mix(in srgb,var(--ss-accent) 20%,var(--ss-line));
  border-radius:var(--ss-radius-card);padding:14px 16px;margin:12px 0;box-shadow:var(--ss-shadow-card)}
.xc-content-card .xc-cc-title{font-size:var(--ss-fs-title);font-weight:700;color:var(--ss-text);margin-bottom:6px;line-height:1.3}
.xc-content-card .xc-cc-body{font-size:13.5px;color:var(--ss-text-muted);line-height:1.7}

/* 新城友好错误卡 / 空态卡（不泄露内部异常，提供重试/降级引导） */
.xc-error-box,.xc-empty-box{display:flex;align-items:flex-start;gap:12px;padding:16px 18px;border-radius:var(--ss-radius-card);
  margin:14px 0;font-size:14px;line-height:1.6;color:var(--ss-text);
  border:1px solid var(--ss-line);background:var(--ss-surface-2)}
.xc-error-box{border-left:4px solid var(--ss-danger);background:color-mix(in srgb,var(--ss-danger) 7%,var(--ss-surface-2))}
.xc-empty-box{border-left:4px solid var(--ss-accent);background:color-mix(in srgb,var(--ss-accent) 6%,var(--ss-surface-2))}
/* P1-2d：success 左条/底色从 --ss-down 解耦到 --ss-box-success（=var(--ss-ok)，同为绿系；
   原 --ss-down 兼任 A 股跌价绿有认知风险）。info/warn/danger 同理走 --ss-box-* 单源。 */
.xc-success-box{border-left:4px solid var(--ss-box-success);background:color-mix(in srgb,var(--ss-box-success) 9%,var(--ss-surface-2))}
.xc-warn-box{border-left:4px solid var(--ss-warn-strong);background:color-mix(in srgb,var(--ss-warn-strong) 10%,var(--ss-surface-2))}
.xc-err-ic{font-size:22px;line-height:1.3;flex-shrink:0}
.xc-err-body{min-width:0}
.xc-err-title{font-weight:700;font-size:14.5px}
.xc-err-hint{margin-top:6px;font-size:12.5px;color:var(--ss-text-muted)}

/* ---- T-277 提示长文折叠（基元收敛）：长 hint 默认收起，摘要 + 展开 ---- */
.xc-hint-fold{margin-top:4px}
.xc-hint-fold>summary{cursor:pointer;list-style:none;font-size:12.5px;color:var(--ss-text-muted);
  display:inline-flex;align-items:center;gap:6px;padding:2px 0;line-height:1.6}
.xc-hint-fold>summary::-webkit-details-marker{display:none}
.xc-hint-fold>summary:hover{color:var(--ss-accent)}
.xc-hint-more{font-size:11px;padding:1px 7px;border:1px solid var(--ss-line);border-radius:var(--ss-radius-pill);
  color:var(--ss-text-muted);background:var(--ss-surface-2);flex-shrink:0}
.xc-hint-fold[open]>summary .xc-hint-more::before{content:"收起"}
.xc-hint-fold[open]>summary .xc-hint-more{font-size:0}
.xc-hint-fold[open]>summary .xc-hint-more::before{font-size:11px}
.xc-hint-fold[open] .xc-err-hint{margin-top:6px}

/* ---- H1+ 数据来源底账徽标（additive，T-212；纯前端 <details>，零 rerun） ---- */
.ss-prov{margin:8px 0;font-size:12.5px;color:var(--ss-text-muted)}
.ss-prov>summary{cursor:pointer;list-style:none;display:inline-flex;align-items:center;gap:6px;
  padding:4px 10px;border:1px solid var(--ss-line);border-radius:var(--ss-radius-pill);
  background:var(--ss-surface-2);color:var(--ss-text-muted);font-weight:600}
.ss-prov>summary::-webkit-details-marker{display:none}
.ss-prov[open]>summary{color:var(--ss-accent);border-color:var(--ss-accent)}
.ss-prov-table{margin-top:8px;border:1px solid var(--ss-line);border-radius:var(--ss-radius);overflow:hidden}
.ss-prov-row{display:flex;gap:10px;align-items:center;padding:6px 10px;border-top:1px solid var(--ss-line)}
.ss-prov-row:first-child{border-top:none}
.ss-prov-name{flex:0 0 auto;font-weight:600;color:var(--ss-text)}
.ss-prov-meta{flex:1 1 auto;color:var(--ss-text-muted)}
.ss-prov-st{border-radius:var(--ss-radius-pill);padding:1px 8px;font-size:11px;font-weight:700;flex:0 0 auto;
  background:color-mix(in srgb,var(--ss-text-muted) 16%,transparent);color:var(--ss-text-muted)}
.ss-prov-st.ok{background:color-mix(in srgb,var(--ss-ok) 16%,transparent);color:var(--ss-ok)}
.ss-prov-st.warn{background:color-mix(in srgb,var(--ss-warn) 18%,transparent);color:var(--ss-warn)}
.ss-prov-st.stale,.ss-prov-st.unknown{background:color-mix(in srgb,var(--ss-danger) 16%,transparent);color:var(--ss-danger)}
.ss-prov-fb{background:color-mix(in srgb,var(--ss-accent) 16%,transparent);color:var(--ss-accent);
  border-radius:var(--ss-radius-pill);padding:1px 8px;font-size:11px;font-weight:700;flex:0 0 auto}

</style>
<style>
/* ===== T-263 顶部空白收敛：纯注入容器不占 flex gap =====
   stVerticalBlock 是 flex + gap:1rem；CSS 注入用 st.markdown(<style>) 产生的零高
   stElementContainer 每个都吃 ~16.5px gap（页43实测 hero 前堆积 22 个 ≈ 363px 空白）。
   收敛：仅当 markdown 容器子节点【全部】为 style/link（纯注入、零可见内容）时隐藏
   其元素容器——<style> 在 display:none 容器内仍全局生效；混合可见内容的容器
   （如顶栏 mega markdown = style,style,style,div）不受影响。
   语法限定顶层 :has / :not 链（Edge155 实证不支持 :has 内嵌 :has）。 */
[data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"] > style:first-child):has([data-testid="stMarkdownContainer"] > style:last-child):not(:has([data-testid="stMarkdownContainer"] > :not(style):not(link))){display:none}
[data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"] > link:first-child):has([data-testid="stMarkdownContainer"] > style:last-child):not(:has([data-testid="stMarkdownContainer"] > :not(style):not(link))){display:none}
</style>
<style>
/* ===== 前端打磨层（additive：不改动任何已锁定的 .xc-card/.xc-hero 声明） ===== */
/* 表格容器：主题化细滚动条（数据密集页高频出现，原生滚动条在暗色下刺眼） */
.ss-table-wrap{scrollbar-width:thin;scrollbar-color:var(--ss-accent) var(--ss-line)}
.ss-table-wrap::-webkit-scrollbar{height:8px;width:8px}
.ss-table-wrap::-webkit-scrollbar-thumb{background:color-mix(in srgb,var(--ss-accent) 55%,var(--ss-line));border-radius:var(--ss-radius-pill)}
.ss-table-wrap::-webkit-scrollbar-track{background:var(--ss-surface-2)}
/* 表单控件主题色（复选/单选/滑块跟随强调色，去除浏览器默认蓝，统一视觉记忆） */
.stApp input[type="checkbox"],.stApp input[type="radio"],.stApp input[type="range"]{accent-color:var(--ss-accent)}
/* 键盘可达性：聚焦环（不依赖外部 class，随主题切色） */
.xc-card:focus-visible,.xc-card[tabindex]:focus{outline:2px solid var(--ss-accent);outline-offset:2px}
/* KPI 卡片最小高度，避免单行/少字段时过矮、网格参差不齐 */
.xc-card{min-height:96px}
</style>
"""

# ★ 首帧兜底 CSS：page_hero 每次都注入，不走 session_state 去重。
# 解决 streamlit 冷启动时序竞态下 ui_kit 的 _KIT_CSS 未生效、导致 chip/hero 容器「首屏朴素、
# 刷新后才好」的问题。CSS 重声明无害，浏览器后到的覆盖先到的。
_HERO_FALLBACK_CSS = _TOKEN_CSS + r"""
<style>
/* page_hero 首帧兜底（与 _KIT_CSS 内的 .xc-hero* 等价，独立注入保证不丢） */
.xc-hero{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:14px;
  margin:6px 0 22px;padding:18px 24px;border-radius:var(--ss-radius-card);
  background:linear-gradient(120deg,
    color-mix(in srgb, var(--ss-accent) 22%, var(--ss-surface)) 0%,
    color-mix(in srgb, var(--ss-accent2) 18%, var(--ss-surface)) 100%);
  border:1px solid color-mix(in srgb, var(--ss-accent) 30%, var(--ss-line));
  box-shadow:var(--ss-shadow-hero);
  position:relative;overflow:hidden}
.xc-hero::before{content:"";position:absolute;inset:0;
  background:radial-gradient(circle at 12% -10%, var(--ss-hero-overlay), transparent 55%);
  pointer-events:none}
.xc-hero-main{display:flex;align-items:center;gap:14px;min-width:0;position:relative;z-index:1}
.xc-hero-icon{font-size:26px;line-height:1;flex-shrink:0;
  width:48px;height:48px;display:flex;align-items:center;justify-content:center;
  border-radius:var(--ss-radius-lg);background:linear-gradient(135deg,var(--ss-accent),var(--ss-accent2));
  box-shadow:0 6px 18px var(--ss-glow)}
.xc-hero-title{font-size:22px;font-weight:800;letter-spacing:.3px;color:var(--ss-text);line-height:1.2}
.xc-hero-sub{font-size:13px;color:var(--ss-text-muted);margin-top:4px;font-weight:500}
.xc-hero-chips{display:flex;gap:8px;flex-wrap:wrap;align-items:center;position:relative;z-index:1}</style>
<style>
/* ===== T-263 顶部空白收敛：纯注入容器不占 flex gap =====
   stVerticalBlock 是 flex + gap:1rem；CSS 注入用 st.markdown(<style>) 产生的零高
   stElementContainer 每个都吃 ~16.5px gap（页43实测 hero 前堆积 22 个 ≈ 363px 空白）。
   收敛：仅当 markdown 容器子节点【全部】为 style/link（纯注入、零可见内容）时隐藏
   其元素容器——<style> 在 display:none 容器内仍全局生效；混合可见内容的容器
   （如顶栏 mega markdown = style,style,style,div）不受影响。
   语法限定顶层 :has / :not 链（Edge155 实证不支持 :has 内嵌 :has）。 */
[data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"] > style:first-child):has([data-testid="stMarkdownContainer"] > style:last-child):not(:has([data-testid="stMarkdownContainer"] > :not(style):not(link))){display:none}
[data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"] > link:first-child):has([data-testid="stMarkdownContainer"] > style:last-child):not(:has([data-testid="stMarkdownContainer"] > :not(style):not(link))){display:none}
</style>
"""


def inject_kit_css() -> None:
    """注入 ui_kit 组件 CSS——每次调用都注入，绝不 session_state 去重。

    ⚠️ T-180 事故教训：曾用 session_state 标记「全页面仅一次」，但
    st.switch_page 导航会重建 DOM（旧页面的 <style> 元素随旧 DOM 消失），
    而 session_state 跨页面保留 → 新页面跳过注入 → 导航后组件样式全丢
    （卡片裸文本），F5 重置 session_state 才恢复。CSS 注入幂等且开销
    极小，必须每次注入（与主题层 apply_theme 同策略）。
    """
    try:
        st.markdown(_KIT_CSS, unsafe_allow_html=True)  # ui_audit_exempt: unsafe-allow_html 内部组件渲染层
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
    # T-277：长文案折叠为摘要（同 _hint_html 语义，内容零删减）
    body = html.escape(text)
    if len(text) > 140:
        body = ('<details class="xc-hint-fold"><summary>'
                + html.escape(text[:64]) + '…<span class="xc-hint-more">展开</span>'
                + '</summary><div class="xc-err-hint">' + html.escape(text) + '</div></details>')
    return (
        f'<div class="xc-info {kind}">'
        f'<span class="xc-ic">{html.escape(icon)}</span>'
        f'<div>{body}</div>'
        f'</div>'
    )


_PROV_ST_LABEL = {"ok": "正常", "warn": "偏旧", "stale": "陈旧", "unknown": "未知"}


def _prov_badge_html(rows, title: str = "数据来源") -> str:
    """H1+ 数据来源底账徽标 HTML（纯函数，便于离线单测 / XSS 校验）。

    诚实语义（守 §五）：``unknown`` 显示「未取到」且状态标「未知」，**绝不显示为正常**；
    ``is_fallback=True`` 显式标「回退源」。纯前端 ``<details>``，**不触发任何 rerun**。
    空行 → 返回 ``""``（调用方据此零破坏）。
    """
    rows = list(rows or [])
    if not rows:
        return ""
    n_old = sum(1 for r in rows if r.get("status") in ("warn", "stale"))
    items = []
    for r in rows:
        st = r.get("status", "unknown")
        st = st if st in _PROV_ST_LABEL else "unknown"
        name = html.escape(str(r.get("name") or r.get("key") or "?"))
        as_of = r.get("as_of")
        if not as_of:
            meta = "未取到（未知）"
        else:
            meta = html.escape(str(as_of))
            if r.get("lag_days") is not None:
                meta += f"（滞后 {r['lag_days']} 天）"
        fb = '<span class="ss-prov-fb">回退源</span>' if r.get("is_fallback") is True else ""
        items.append(
            f'<div class="ss-prov-row"><span class="ss-prov-name">{name}</span>'
            f'<span class="ss-prov-meta">{meta}</span>{fb}'
            f'<span class="ss-prov-st {st}">{_PROV_ST_LABEL[st]}</span></div>')
    head = f"ⓘ {html.escape(str(title or '数据来源'))}"
    if n_old:
        head += f" · ⚠️ {n_old} 源偏旧/陈旧"
    return (f'<details class="ss-prov"><summary>{head}</summary>'
            f'<div class="ss-prov-table">{"".join(items)}</div></details>')


def prov_badge(rows=None, *, slug: str = None, title: str = "数据来源",
               includes: dict = None) -> None:
    """渲染「ⓘ 数据来源」底账徽标（H1+ 方向 A，additive-only）。

    :param rows: 直接给底账行（``data_provenance.build_provenance`` 输出）
    :param slug: 或给页面 slug，经 ``data_provenance.sources_for`` 取依赖源；
        **未登记页面 → no-op**（AC-A5 零破坏）
    :param includes: 可选，调用方确知的 `{key: {is_fallback, source_chain}}`

    只读展示：不取数、不写盘、不触发 rerun。
    """
    try:
        from modules import data_provenance as _dp
        if rows is None and slug:
            _keys = _dp.sources_for(slug)
            if not _keys:
                return
            rows = _dp.build_provenance(_keys, includes=includes)
        _h = _prov_badge_html(rows, title=title)
        if _h:
            st.markdown(_h, unsafe_allow_html=True)  # ui_audit_exempt: unsafe-allow_html 内部组件渲染层
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[ui_kit] prov_badge 处理异常: {e}")


# P1-2b（ui-ds Phase1 §2.2②a）：accent 语义档 → 令牌映射（防彩虹卡收敛入口）。
#   传档位名走 var() 令牌（七风格自动换色相）；传 hex 走兼容直传（test_ui_kit 锁定）。
#   存量调用全量核查：现网 accent= 实参全部是 hex 字面量，与档位名零撞车。
_XC_ACCENT_TIERS = {
    "up": "var(--ss-up)",        # A股红（涨语义强调）
    "down": "var(--ss-down)",    # A股绿（跌语义强调）
    "neutral": "var(--ss-line)", # 中性分隔线色
    "accent": "var(--ss-accent)",# 主题强调色
}


def _xc_card_html(label: str = "", value: str = "", delta: str = "", delta_dir: str = "flat",
                  accent: str = None, icon: str = "", sub: str = "", meta: str = "",
                  tone: str = None) -> str:
    """新城(xc)风格 KPI 卡片 HTML（全站 canonical Bento 卡；纯函数，便于离线单测 / XSS 校验）。

    - ``delta_dir``：up/down/flat —— A 股红涨绿跌（up=红）。非法值回落 flat。
    - ``tone``：可选，给主数值着 A 股语义色（up=红 / down=绿 / flat=主文本色）。
    - ``accent``：可选，卡片顶部强调边颜色。P1-2b 起支持语义档位 ``"up"|``"down"|
      ``"neutral"|"accent"``（映射 --ss-up/--ss-down/--ss-line/--ss-accent，随七风格
      换色相）；传 hex 直传保持兼容（旧调用零改动）。
    - 文本一律 html.escape，None/空安全，绝不抛异常。
    """
    label = "" if label is None else str(label)
    value = "" if value is None else str(value)
    delta = "" if delta is None else str(delta)
    delta_dir = delta_dir if delta_dir in ("up", "down", "flat") else "flat"
    icon = "" if icon is None else str(icon)
    sub = "" if sub is None else str(sub)
    meta = "" if meta is None else str(meta)
    tone_cls = f" {tone}" if tone in ("up", "down", "flat") else ""
    if accent:
        _tier = _XC_ACCENT_TIERS.get(str(accent))
        _color = _tier if _tier else html.escape(str(accent), quote=True)
        style = f' style="border-top:3px solid {_color}"'
    else:
        style = ""
    top = ""
    if icon or sub or label:
        ico = f'<div class="ico">{html.escape(icon)}</div>' if icon else ""
        sub_html = f'<div class="csub">{html.escape(sub)}</div>' if sub else ""
        top = f'<div class="ctop">{ico}<div><div class="cname">{html.escape(label)}</div>{sub_html}</div></div>'
    value_html = f'<div class="value{tone_cls}">{html.escape(value)}</div>'
    delta_html = f'<div class="delta {delta_dir}">{html.escape(delta)}</div>' if delta else ""
    meta_html = f'<div class="meta">{html.escape(meta)}</div>' if meta else ""
    return f'<div class="xc-card"{style}>{top}{value_html}{delta_html}{meta_html}</div>'


def _stat_tile_html(label: str, value: str, delta: str = "", delta_dir: str = "flat",
                    accent: str = None) -> str:
    """兼容层：旧指标瓦片 → 统一渲染为 .xc-card（全站单一 KPI 卡视觉，消除 .ss-stat 重复）。"""
    return _xc_card_html(label=label, value=value, delta=delta, delta_dir=delta_dir, accent=accent)


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

    ★ 首帧兜底：再注入一次 .xc-hero* 关键样式（不走 session_state 去重），
    保证 streamlit 冷启动竞态下 ui_kit._KIT_CSS 未生效时，hero 容器仍完整可见。
    """
    inject_kit_css()
    st.markdown(_HERO_FALLBACK_CSS, unsafe_allow_html=True)  # ui_audit_exempt: unsafe-allow_html 内部组件渲染层
    st.markdown(_hero_html(title, icon, subtitle, chips, style=style), unsafe_allow_html=True)  # ui_audit_exempt: unsafe-allow_html 内部组件渲染层


def xc_section_header(title: str, subtitle: str = "", icon: str = "📊",
                      xtra: str = "", render: bool = True):
    """新城风格分区小标题（带渐变紫竖条 + 可选图标/副标题/右侧标注）。

    design_system.md 第3章组件规范：优先 xc_section_header（替代旧 section_header）。
    render=True（默认）：直接 st.markdown 渲染并返回 None（兼容旧 section_header
    即渲染契约）；render=False：返回 HTML 片段（供调用方自行嵌入，如 _hero 内部）。
    subtitle 渲染为标题下方弱色副行，xtra 渲染为右侧弱色标注，icon 为前缀图标。
    """
    inject_kit_css()
    title = "" if title is None else str(title)
    icon_html = f'<span class="xc-sh-ic">{html.escape(str(icon))}</span>' if icon else ""
    sub_html = f'<div class="xc-sh-sub">{html.escape(str(subtitle))}</div>' if subtitle else ""
    xtra_html = f'<span class="xc-sh-xtra">{html.escape(str(xtra))}</span>' if xtra else ""
    html_out = (
        f'<div class="xc-section-h">{icon_html}'
        f'<div class="xc-sh-main"><span class="xc-sh-title">{html.escape(title)}</span>{sub_html}</div>'
        f'{xtra_html}</div>'
    )
    if render:
        st.markdown(html_out, unsafe_allow_html=True)  # ui_audit_exempt: unsafe-allow_html 内部组件渲染层
        return None
    return html_out


def xc_subheader(title: str, icon: str = "", xtra: str = "") -> None:
    """新城风格分区标题（渲染版）。等同 xc_section_header 但直接渲染，替代裸 st.subheader。"""
    inject_kit_css()
    prefix = f"{html.escape(icon)} " if icon else ""
    xc_section_header(f"{prefix}{title}", xtra=xtra)


def xc_chart_cell(title: str, xtra: str = "") -> None:
    """图表卡标题条（两段式图表卡·第一段）：渲染标题条后，页面**紧随其后**调用
    ``st.plotly_chart(...)``，视觉上构成一张图表卡。

    ⚠️ **不承诺包裹**（phase3 §1.4 裁定）：Streamlit 每个元素是独立的
    stElementContainer，st.markdown 的 HTML 无法跨容器包裹原生 st.plotly_chart
    ——chart_card() 的 HTML 包图路线因此被实践淘汰（零生产调用）。本工厂只渲染
    标题条 HTML（复用全站统一的 .xc-section-h 结构：渐变竖条 + 右侧 xtra 标注），
    并附加 ``.xc-chart-cell`` 类供 G5 白名单登记与图表皮肤定位。
    """
    inject_kit_css()
    title = "" if title is None else str(title)
    xtra_html = f'<span class="xc-sh-xtra">{html.escape(str(xtra))}</span>' if xtra else ""
    st.markdown(
        f'<div class="xc-section-h xc-chart-cell">{html.escape(title)}{xtra_html}</div>',
        unsafe_allow_html=True,  # ui_audit_exempt: unsafe-allow_html 内部组件渲染层
    )


def xc_info_banner(text: str, kind: str = "info", icon: str = "💡") -> None:
    """新城风格彩色提示横幅（info/success/warning/danger）。

    B 阶段词汇统一后的 canonical 横幅：与 legacy info_banner 共用
    _info_banner_html 渲染（含 T-277 长文案折叠），仅保留旧名做兼容委托。
    """
    inject_kit_css()
    st.markdown(_info_banner_html(text, kind, icon), unsafe_allow_html=True)  # ui_audit_exempt: unsafe-allow_html 内部组件渲染层


def xc_content_card(title: str, body: str = "", icon: str = "", *, compact_when_empty: bool = True) -> None:
    """新城(xc)风格内容卡：标题 + 正文（1:1 替代 ui_theme.sf_card，统一组件词汇到 xc_*）。

    文本一律 html.escape，防注入；纯视觉，不改动业务逻辑。

    - ``body`` 为空且 ``compact_when_empty=True``：复用 .xc-section-h 紧凑节标题（对齐
      sf_card 的 T-266 空间治理，不占大卡片纵向空间），不渲染大卡片。
    - ``body`` 非空：渲染 .xc-content-card（标题 + 正文，令牌化、主题自适应）。

    Args:
        title: 卡片标题。
        body: 卡片正文（纯文本，会被转义；传 HTML 不会被执行）。
        icon: 可选前置图标（emoji 或字符）。
        compact_when_empty: 空正文是否降级为紧凑节标题（默认 True，保持与 sf_card 一致）。
    """
    title = html.escape(str(title))
    body = html.escape(str(body))
    icon = html.escape(str(icon)) if icon else ""
    icon_html = f"{icon} " if icon else ""
    if compact_when_empty and not str(body).strip():
        # 紧凑节标题：复用全站统一的 .xc-section-h（左 accent 条）
        st.markdown(
            f'<div class="xc-section-h" style="margin:10px 0 8px">{icon_html}{title}</div>',
            unsafe_allow_html=True,  # ui_audit_exempt: unsafe-allow_html 内部组件渲染层
        )
        return
    inject_kit_css()
    st.markdown(
        f'<div class="xc-content-card">'
        f'<div class="xc-cc-title">{icon_html}{title}</div>'
        f'<div class="xc-cc-body">{body}</div>'
        f'</div>',
        unsafe_allow_html=True,  # ui_audit_exempt: unsafe-allow_html 内部组件渲染层
    )



_HINT_COLLAPSE_THRESHOLD = 140  # T-277：提示文案折叠阈值（字符数）


def _hint_html(hint, icon: str = "💡") -> str:
    """提示文案渲染基元（T-277 全站收敛）：短文案内联，长文案折叠为可展开摘要。

    痛点：全站 260+ 处提示卡的长 hint 撑开半屏（占位大、不美观）。
    收敛：超阈值内容默认收起，仅显示「图标 + 首句摘要…」，点击展开全文——
    内容零删减（诚实语义完整保留），只是默认不铺满屏幕。
    """
    if hint is None:
        return ""
    text = str(hint)
    if not text:
        return ""
    if len(text) <= _HINT_COLLAPSE_THRESHOLD:
        return f'<div class="xc-err-hint">{html.escape(icon)} {html.escape(text)}</div>'
    summary = html.escape(text[:56]) + "…"
    return (f'<details class="xc-hint-fold"><summary>{html.escape(icon)} {summary}'
            f'<span class="xc-hint-more">展开</span></summary>'
            f'<div class="xc-err-hint">{html.escape(text)}</div></details>')


def xc_error_box(title: str, hint: str = "", icon: str = "⚠️") -> None:
    """新城风格友好错误卡：不泄露内部异常细节，提供重试/降级引导。

    内部异常请由调用方用 logger.warning 记录，不要把原始异常拼进 title。
    """
    inject_kit_css()
    title = "" if title is None else str(title)
    icon = "⚠️" if icon is None else str(icon)
    hint_html = _hint_html(hint, "💡")
    st.markdown(
        f'<div class="xc-error-box"><span class="xc-err-ic">{html.escape(icon)}</span>'
        f'<div class="xc-err-body"><div class="xc-err-title">{html.escape(title)}</div>{hint_html}</div></div>',
        unsafe_allow_html=True,  # ui_audit_exempt: unsafe-allow_html 内部组件渲染层
    )


def xc_empty_box(title: str, hint: str = "", icon: str = "📭") -> None:
    """新城风格空态卡：数据为空/暂无时的友好占位。"""
    inject_kit_css()
    title = "" if title is None else str(title)
    icon = "📭" if icon is None else str(icon)
    hint_html = _hint_html(hint)
    st.markdown(
        f'<div class="xc-empty-box"><span class="xc-err-ic">{html.escape(icon)}</span>'
        f'<div class="xc-err-body"><div class="xc-err-title">{html.escape(title)}</div>{hint_html}</div></div>',
        unsafe_allow_html=True,  # ui_audit_exempt: unsafe-allow_html 内部组件渲染层
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


@contextlib.contextmanager
def xc_error_boundary(title: str, hint: str = "", log=None):
    """三态闭环（design_system.md §4）：把散落的 ``try/except`` 收敛为一处。

    用法::

        with xc_error_boundary("持仓快照加载失败", hint="检查交易接口连接。"):
            rows = api_get(...)

    异常只进 logger（绝不拼进可见文案），并渲染友好错误卡；正常路径零副作用。
    与 ``xc_handle_error`` 同契约：失败给错误卡不谎报、异常不泄露。
    """
    try:
        yield
    except Exception as exc:  # noqa: BLE001
        (log or logger).warning("%s: %s", title, exc)
        xc_handle_error(title, exc=exc, hint=hint)


def _inline_md(text: str) -> str:
    """极简行内 markdown：先整体 HTML 转义（防 XSS），再把 ``**粗体**`` / ``*斜体*``
    还原为 ``<b>`` / ``<i>``。转义先行，故即使原文含标签也会被中和，安全。"""
    s = html.escape("" if text is None else str(text))
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*(.+?)\*", r"<i>\1</i>", s)
    return s


def xc_success_box(title: str, hint: str = "", icon: str = "✅") -> None:
    """新城风格成功卡（绿，P1-2d 起走 --ss-box-success=var(--ss-ok) 功能绿，
    与 A 股跌价绿 --ss-down 解耦）。title 支持 ``**粗体**`` 行内强调。"""
    inject_kit_css()
    title = "" if title is None else str(title)
    title = title.replace("✅", "").replace("⚠️", "").strip()
    icon = "✅" if icon is None else str(icon)
    hint_html = _hint_html(hint, "💡")
    st.markdown(
        f'<div class="xc-success-box"><span class="xc-err-ic">{html.escape(icon)}</span>'
        f'<div class="xc-err-body"><div class="xc-err-title">{_inline_md(title)}</div>{hint_html}</div></div>',
        unsafe_allow_html=True,  # ui_audit_exempt: unsafe-allow_html 内部组件渲染层
    )


def xc_warn_box(title: str, hint: str = "", icon: str = "⚠️") -> None:
    """新城风格警告卡（琥珀色）。title 支持 ``**粗体**`` 行内强调。"""
    inject_kit_css()
    title = "" if title is None else str(title)
    title = title.replace("✅", "").replace("⚠️", "").strip()
    icon = "⚠️" if icon is None else str(icon)
    hint_html = _hint_html(hint, "💡")
    st.markdown(
        f'<div class="xc-warn-box"><span class="xc-err-ic">{html.escape(icon)}</span>'
        f'<div class="xc-err-body"><div class="xc-err-title">{_inline_md(title)}</div>{hint_html}</div></div>',
        unsafe_allow_html=True,  # ui_audit_exempt: unsafe-allow_html 内部组件渲染层
    )


def info_banner(text: str, kind: str = "info", icon: str = "💡") -> None:
    """Deprecated：请改用 xc_info_banner（B 阶段组件词汇统一）。

    仅作兼容薄委托保留，勿新增调用；守卫 test_component_vocabulary 禁止新调用点。
    """
    xc_info_banner(text, kind, icon)


def stat_tile(label: str, value: str, delta: str = "", delta_dir: str = "flat",
              accent: str = None) -> None:
    """单个指标瓦片（.xc-card 视觉）。delta_dir: up/down/flat（A股红涨绿跌，up=红）。"""
    inject_kit_css()
    st.markdown(_stat_tile_html(label, value, delta, delta_dir, accent), unsafe_allow_html=True)  # ui_audit_exempt: unsafe-allow_html 内部组件渲染层


def xc_kpi_grid(cards, min_col: int = 168) -> None:
    """把一组 KPI 指标渲染成新城(xc)风格自适应卡片网格 —— 全站 canonical「Bento 样板」。

    统一入口：替代各页 ``st.columns(N) + st.metric(...)`` 的散装指标条，好处有三：
    ① 自适应列数（响应式，窄屏自动折行）；② 主数值 / delta 走 A 股红涨绿跌语义色
    （``st.metric`` 默认是「涨绿跌红」，与 A 股相反）；③ 与全站 ``.xc-card`` 视觉一致。

    Args:
        cards: list[dict]（或单个 dict），每项键（除 label/value 外均可选）：
            - label     : 主标签
            - value     : 主数值（字符串，调用方自行格式化）
            - icon      : 图标 emoji
            - sub       : 图标旁小字副标题
            - delta     : 变化文本（如 "+1.23%"）
            - delta_dir : 'up'|'down'|'flat' —— delta 的 A 股语义色
            - tone      : 'up'|'down'|'flat' —— 主数值的语义色（可选）
            - accent    : 卡片顶部强调边颜色（可选）
            - meta      : 底部小字补充说明（可选）
        min_col: 单卡最小宽度（px），决定一行放几张；默认 168。

    纯 HTML 渲染（不走 st.columns），故任意数量卡片均可自适应排列。
    """
    inject_kit_css()
    if not cards:
        return
    if isinstance(cards, dict):
        cards = [cards]
    cells = []
    for c in cards:
        if not isinstance(c, dict):
            continue
        cells.append(_xc_card_html(
            label=c.get("label"), value=c.get("value"),
            delta=c.get("delta", ""), delta_dir=c.get("delta_dir", "flat"),
            accent=c.get("accent"), icon=c.get("icon", ""),
            sub=c.get("sub", ""), meta=c.get("meta", ""), tone=c.get("tone"),
        ))
    if not cells:
        return
    st.markdown(
        f'<div class="xc-grid" style="grid-template-columns:repeat(auto-fit,minmax({int(min_col)}px,1fr))">'
        f'{"".join(cells)}</div>',
        unsafe_allow_html=True,  # ui_audit_exempt: unsafe-allow_html 内部组件渲染层
    )


def stat_row(tiles: list) -> None:
    """一行多瓦片（自适应换行）。tiles: list of dict(label,value,delta,delta_dir,accent)。
    与 xc_kpi_grid 共用同一 .xc-card 视觉（全站统一 KPI 卡，消除 .ss-stat 重复视觉）。"""
    xc_kpi_grid(tiles)


def _bento_html(cells, template: str, gap: int) -> str:
    """纯函数：把若干 HTML 片段包进 .xc-bento 非对称网格。便于离线单测 / XSS 校验。"""
    inner = "".join(f'<div class="xc-bento-cell">{c}</div>' for c in cells if c)
    return (
        f'<div class="xc-bento" '
        f'style="grid-template-columns:{template};gap:{int(gap)}px">'
        f'{inner}</div>'
    )


def xc_bento_grid(cells, template: str = "repeat(auto-fit,minmax(220px,1fr))", gap: int = 16) -> None:
    """把一组 HTML 片段渲染成 Bento 非对称网格（错落大卡 + 小卡，2026 市面范式）。

    适合承载任意内容块（KPI 卡、导航卡、信息块）的轻量错落布局；纯 HTML 渲染，
    不引入额外 Streamlit 组件，零重渲染开销。所有视觉走设计令牌，主题自适应。

    Args:
        cells: list[str]，每个是已构建好的 HTML 片段（如 xc_bento_cell / _xc_card_html 输出）。
               空片段会被跳过。
        template: CSS ``grid-template-columns``，支持非对称，如 ``"1.6fr 1fr 1fr"``、
                  ``"1fr 1fr 1fr 1fr"``。默认自适应等宽。
        gap: 单元格间距（px），默认 16。
    """
    inject_kit_css()
    if not cells:
        return
    st.markdown(_bento_html(cells, template, gap), unsafe_allow_html=True)  # ui_audit_exempt: unsafe-allow_html 内部组件渲染层


def xc_bento_kpi(cards, template: str = "repeat(auto-fit,minmax(220px,1fr))", gap: int = 16) -> None:
    """Bento 版 KPI 网格：把 xc_kpi_grid 的卡片放进非对称 Bento 网格（错落大卡 + 小卡）。

    cards / template / gap 语义同 :func:`xc_kpi_grid` 与 :func:`xc_bento_grid`。
    """
    inject_kit_css()
    if not cards:
        return
    if isinstance(cards, dict):
        cards = [cards]
    cells = []
    for c in cards:
        if not isinstance(c, dict):
            continue
        cells.append(_xc_card_html(
            label=c.get("label"), value=c.get("value"),
            delta=c.get("delta", ""), delta_dir=c.get("delta_dir", "flat"),
            accent=c.get("accent"), icon=c.get("icon", ""),
            sub=c.get("sub", ""), meta=c.get("meta", ""), tone=c.get("tone"),
        ))
    if not cells:
        return
    st.markdown(_bento_html(cells, template, gap), unsafe_allow_html=True)  # ui_audit_exempt: unsafe-allow_html 内部组件渲染层



def chart_card(title: str, body_html: str) -> None:
    """图表容器卡片：标题栏 + 圆角卡片包裹 Plotly/HTML 图表。

    ⚠️ deprecated（ui-ds P1-4b）：生产调用为零（pages 全量 grep 证实），HTML 包图
    路线已被 phase3 §1.4 裁定淘汰——Streamlit 元素独立容器，无法跨容器包裹原生
    st.plotly_chart。保留仅为 test_module_imports_and_has_public_api 兼容锁；
    新代码请用 ``xc_chart_cell(title)`` + 紧随其后的 ``st.plotly_chart(...)``。
    """
    inject_kit_css()
    st.markdown(_chart_card_html(title, body_html), unsafe_allow_html=True)  # ui_audit_exempt: unsafe-allow_html 内部组件渲染层


def table_wrap(table_html: str) -> None:
    """响应式表格容器：移动端横向滚动 + 粘性表头。"""
    inject_kit_css()
    st.markdown(_table_wrap_html(table_html), unsafe_allow_html=True)  # ui_audit_exempt: unsafe-allow_html 内部组件渲染层


# ───────────────────── T-262 折叠方式多元化（三原语） ─────────────────────
# 设计回应（用户 2026-10-12）：折叠方式太单一——
#   A 有用型   ss_fold_useful    ：expander 标签自带一行摘要，展开看全量（内容多但有用）
#   B 悬停预览 ss_hover_preview  ：细触发字 + 悬停浮出内容面板（学「搜索 Ctrl K」浮层范式）
#   C 细小化   ss_mini           ：低价值内容的最小 footprint（弱色小字触发 + 悬停显示）
# B/C 为纯 CSS 实现（无 JS，Streamlit 剥 <script> 也不受影响）。

_FOLD_CSS = r"""<style>
/* T-262 悬停预览（纯 CSS 浮层） */
.ss-hint{position:relative;display:inline-block;cursor:help;vertical-align:middle}
.ss-hint-t{color:var(--ss-text-muted,var(--txt2,#64748b));font-size:12px;
  border-bottom:1px dashed var(--ss-line,var(--border,#e2e8f0))}
.ss-hint-p{position:absolute;top:135%;left:0;z-index:99999;opacity:0;visibility:hidden;
  transform:translateY(-4px);transition:opacity .15s ease,transform .15s ease;
  background:var(--ss-surface,var(--card,#fff));color:var(--ss-text,var(--txt,#1e293b));
  border:1px solid var(--ss-line,var(--border,#e2e8f0));border-radius:var(--ss-radius);
  padding:10px 12px;box-shadow:0 10px 30px rgba(15,15,35,.18);
  min-width:220px;max-width:360px;font-size:13px;line-height:1.65}
.ss-hint:hover .ss-hint-p,.ss-hint:focus-within .ss-hint-p{opacity:1;visibility:visible;transform:translateY(0)}
/* P2-1 键盘可达：Tab 聚焦触发器时与 hover 同参展开浮层（:focus-within 与 hover 同参）；
   DOMPurify 默认 allowlist 放行 tabindex（Phase3 实测），外层 .ss-hint 带 tabindex="0" 可聚焦 */
.ss-hint:focus-visible{outline:2px solid var(--ss-focus-ring,var(--ss-accent,var(--brand-1,#667eea)));outline-offset:2px;border-radius:var(--ss-radius-xs)}
.ss-hint-p b{color:var(--ss-accent,var(--brand-1,#667eea))}
/* C 细小化触发（更弱的存在感） */
.ss-hint.mini .ss-hint-t{font-size:11px;opacity:.72}
</style>"""


def _fold_hover_html(trigger: str, panel_html: str, mini: bool = False) -> str:
    """悬停预览纯函数（可离线单测）：触发字 + 浮层面板。

    P2-1 键盘可达：外层 .ss-hint 带 tabindex="0"，键盘 Tab 聚焦后经
    .ss-hint:focus-within 与 hover 同参展开浮层（DOMPurify 默认放行 tabindex，
    Phase3 已实测；静态属性不经过转义路径，不会被剥离）。
    """
    cls = "ss-hint mini" if mini else "ss-hint"
    return (f'<span class="{cls}" tabindex="0"><span class="ss-hint-t">{trigger}</span>'
            f'<span class="ss-hint-p">{panel_html}</span></span>')


def ss_hover_preview(trigger: str, panel_html: str, mini: bool = False) -> None:
    """B/C：悬停预览——鼠标放上才显示内容，页面默认只有一行细字。

    Args:
        trigger: 触发字（短，如「ⓘ 口径说明」）；
        panel_html: 浮层内容（受信 HTML，调用方自行转义用户数据）；
        mini: True 时用 C 细小化触发样式（更低存在感）。
    """
    inject_kit_css()
    st.markdown(_FOLD_CSS + _fold_hover_html(trigger, panel_html, mini=mini),
                unsafe_allow_html=True)  # ui_audit_exempt: unsafe-allow_html 内部组件渲染层


@contextlib.contextmanager
def ss_fold_useful(label: str, summary: str = "", expanded: bool = False,
                   icon: str | None = None):
    """A：有用型折叠——expander 标签自带一行摘要，展开看全量。

    折叠后样式仍然「有用」：标签即预览（最近一条/总量等），不必展开也有信息量。
    用法：``with ss_fold_useful("🕘 登录历史", "最近：8小时前 admin 登录 · 共16条"): ...``
    """
    lab = f"{label}　·　{summary}" if summary else label
    with st.expander(lab, expanded=expanded, icon=icon):
        if summary:
            st.caption(summary)
        yield