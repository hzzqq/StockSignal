"""
modules/ui_theme.py
-------------------
StockSignal 金融级 UI 润色层 v9（支持暗夜/亮色双模式）。

设计原则（非常重要）：
  ✅ 只注入「视觉」CSS（颜色 / 圆角 / 阴影 / 边框 / 字体 / 动效），
     绝不 display:none 任何功能组件、绝不改动 DOM 结构或业务逻辑。
  ✅ 通过 modules/session.init_session_state() 统一注入，
     所有页面（含登录页）零改动即获得统一主题。
  ✅ 暗夜模式 v9：星辰决策仪表盘风格（深空黑底 #0f0f23 + 紫蓝极光 #667eea/#764ba2 + 红涨绿跌）
  ✅ 亮色模式 v6：专业金融仪表盘（微冷灰底 + 金蓝点缀 + 高对比度文字）

v9 核心变更：
  ✅ 暗色主题切换到「星辰决策仪表盘」风格：深蓝紫黑底 + 紫蓝渐变强调 + 红涨绿跌（A股）
  ✅ 重点修复 Plotly 图表在暗色模式下发白、白网格、白K线的问题
  ✅ 卡片统一 16px 圆角 + 紫蓝微光描边
  ✅ 坐标轴/网格线/图例文字统一为暗色系
"""
from __future__ import annotations
import streamlit as st
import streamlit.components.v1 as components

# ── 金融配色常量（A股：红涨绿跌）──
UP = "#ff4d4f"        # 涨（中国习惯：红）
DOWN = "#00d486"      # 跌（中国习惯：绿）
HOLD = "#ffa502"

# ── 星辰设计令牌 ──
SF_BG = "#0f0f23"
SF_CARD = "#1a1a2e"
SF_CARD_DARK = "#15152a"
SF_ACC1 = "#667eea"
SF_ACC2 = "#764ba2"
SF_TXT = "#e2e8f0"
SF_TXT2 = "#94a3b8"
SF_BORDER = "#2d2d44"
SF_GRID = "#23233c"

# ── 全局字号档位（rem 相对根字号 16px；无单位的数值无效，浏览器会忽略）──
# 小/中(medium=标准)/大/特大/巨大，至少 5 档。默认 medium=1.03rem（比旧版 1.00 略大）。
# 作为唯一数据源，页面设置项（6_我的.py）与此处共用，保证一致。
FONT_SCALE = {
    "small":   "0.95rem",   # 小
    "medium":  "1.03rem",   # 标准（旧“中”，默认档，已放大）
    "large":   "1.12rem",   # 大
    "xlarge":  "1.22rem",   # 特大
    "xxlarge": "1.32rem",   # 巨大
}
FONT_DEFAULT = "medium"


def inject_font_size() -> None:
    """按 session_state 的 font_size 注入全局字号（覆盖 html/body/.stApp）。

    同时作用于 html，使所有 rem 子元素（表格/指标卡等）随档位整体缩放，
    真正实现「整个项目字体可调」。仅注入 CSS，不改任何功能逻辑。
    用户未单独设置时回落到 FONT_DEFAULT（1.03rem，已比旧默认更大）。
    """
    _key = st.session_state.get("font_size", FONT_DEFAULT)
    _rem = FONT_SCALE.get(_key, FONT_SCALE[FONT_DEFAULT])
    st.markdown(
        f"""<style>
        html, body, .stApp {{ font-size: {_rem} !important; }}
        </style>""",
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════
#  暗色主题 CSS v9 — 星辰决策仪表盘风格
#  配色：深空黑底 #0f0f23 / 卡片 #1a1a2e / 强调紫蓝渐变
#  涨跌：红涨 #ff4d4f / 绿跌 #00d486（A股惯例）
# ════════════════════════════════════════════════════════════
_DARK_CSS = """
<!-- Google Fonts: Fira Code (数据) + Inter (UI) -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">

<style>
/* ===== 星辰决策仪表盘 · 组件类（供页面按需使用） ===== */
:root{
  --bg:#0f0f23; --card:#1a1a2e; --buy:#ff4d4f; --sell:#00d486;
  --hold:#ffa502; --acc1:#667eea; --acc2:#764ba2;
  --txt:#e2e8f0; --txt2:#94a3b8; --border:#2d2d44; --grid:#23233c;
}

.sf-header{display:flex;align-items:center;justify-content:space-between;
  flex-wrap:wrap;gap:10px;margin-bottom:20px;padding:16px 20px;
  background:linear-gradient(90deg,#1a1a2e,#241b3a);
  border:1px solid var(--border);border-radius:16px;
  box-shadow:0 0 0 1px rgba(102,126,234,.08),0 8px 24px rgba(0,0,0,.35)}
.sf-brand{font-size:15px;color:var(--txt2);letter-spacing:1px}
.sf-brand b{color:var(--acc1)}

.sf-card{background:var(--card);border:1px solid var(--border);
  border-radius:16px;padding:20px;margin-top:18px;
  box-shadow:0 0 0 1px rgba(102,126,234,.06),0 6px 20px rgba(0,0,0,.28)}
.sf-card h2{font-size:16px;margin:0 0 14px;display:flex;align-items:center;gap:8px;
  padding-bottom:10px;border-bottom:1px solid var(--border);color:var(--txt)}
.sf-card h2::before{content:"";width:4px;height:16px;
  background:linear-gradient(180deg,var(--acc1),var(--acc2));border-radius:3px}

.sf-one-line{font-size:14.5px;font-weight:700;color:var(--buy);
  background:rgba(255,77,79,.08);border-left:3px solid var(--buy);
  padding:10px 14px;border-radius:8px;margin-bottom:14px;line-height:1.7}
.sf-one-line.hold{color:var(--hold);border-left-color:var(--hold);
  background:rgba(255,165,2,.08)}

.sf-table{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:4px}
.sf-table th,.sf-table td{padding:9px 8px;text-align:center;border-bottom:1px solid var(--border)}
.sf-table th{color:var(--txt2);font-weight:600;font-size:12px;background:#15152a}
.sf-table tr:hover td{background:rgba(102,126,234,.05)}
.sf-table td.l{text-align:left}
.sf-up{color:var(--buy);font-weight:700}
.sf-down{color:var(--sell);font-weight:700}

.sf-tag{display:inline-block;font-size:11px;padding:2px 9px;border-radius:14px;
  font-weight:600;margin:2px}
.sf-tag.win{background:rgba(0,212,134,.16);color:#00d4aa;border:1px solid rgba(0,212,134,.4)}
.sf-tag.mid{background:rgba(255,165,2,.16);color:var(--hold);border:1px solid rgba(255,165,2,.4)}
.sf-tag.weak{background:rgba(255,77,79,.14);color:var(--buy);border:1px solid rgba(255,77,79,.4)}
.sf-tag.neu{background:rgba(148,163,184,.12);color:var(--txt2);border:1px solid var(--border)}

.sf-vs{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:8px}
@media(max-width:780px){.sf-vs{grid-template-columns:1fr}}
.sf-vsbox{background:#15152a;border:1px solid var(--border);border-radius:12px;padding:14px}
.sf-vsbox h3{font-size:14px;margin-bottom:8px;color:var(--txt)}
.sf-verdict{font-size:13px;font-weight:700;margin:8px 0;padding:6px 10px;border-radius:8px}
.sf-verdict.b{background:rgba(0,212,134,.12);color:#00d4aa}
.sf-verdict.o{background:rgba(255,165,2,.12);color:var(--hold)}
.sf-vsbox ul{margin:6px 0 0 16px;font-size:12.5px;color:var(--txt2)}
.sf-vsbox ul li{margin:3px 0}

.sf-alert{border-radius:12px;padding:12px 14px;margin-top:14px;font-size:13px;line-height:1.7}
.sf-alert.risk{background:rgba(255,77,79,.10);border:1px solid rgba(255,77,79,.45);color:#ffb3bb}
.sf-alert.cat{background:rgba(0,212,134,.10);border:1px solid rgba(0,212,134,.45);color:#9af0dd}
.sf-alert b{display:block;margin-bottom:4px;font-size:13.5px}

.sf-note{font-size:12.5px;color:var(--txt2);margin-top:10px;line-height:1.7}
.sf-disclaimer{margin-top:14px;font-size:11.5px;color:#6b7280;
  border-top:1px dashed var(--border);padding-top:10px}

/* ===== 全局基调：深空黑 + 紫蓝极光 ===== */
html, body, .stApp {
    color: #e2e8f0;
    font-family: 'Inter', -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
}
.stApp {
    background-color: #0f0f23;
    background-image:
        radial-gradient(ellipse 80% 50% at 12% -8%, rgba(102, 126, 234, 0.10) 0%, transparent 55%),
        radial-gradient(ellipse 60% 45% at 88% 5%, rgba(118, 75, 162, 0.08) 0%, transparent 50%),
        radial-gradient(ellipse 90% 60% at 50% 108%, rgba(102, 126, 234, 0.10) 0%, transparent 55%),
        url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.03'/%3E%3C/svg%3E");
}

/* ===== 隐藏 Streamlit 默认菜单/工具栏，但保留顶部 header 容器
        以便侧边栏展开/折叠按钮始终可见；header 本身设为透明不占视觉空间 ===== */
#MainMenu { display: none !important; }
footer { display: none !important; }
[data-testid="stToolbar"] { padding: 0 !important; margin: 0 !important; min-height: 0 !important; background: transparent !important; border: none !important; box-shadow: none !important; }
[data-testid="stDecoration"] { display: none !important; }
header[data-testid="stHeader"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
    margin: 0 !important;
    height: auto !important;
    min-height: 0 !important;
}

/* 折叠态的展开按钮：固定到左上角，避免被透明 header 压成 0×0 看不见/点不到 */
button[data-testid="stExpandSidebarButton"] {
    position: fixed !important;
    top: 10px !important;
    left: 10px !important;
    z-index: 99999 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    width: 38px !important;
    height: 38px !important;
    padding: 0 !important;
    background: rgba(30, 30, 60, 0.92) !important;
    border: 1px solid rgba(255, 255, 255, 0.25) !important;
    border-radius: 8px !important;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.45) !important;
    cursor: pointer !important;
    visibility: visible !important;
    opacity: 1 !important;
}
button[data-testid="stExpandSidebarButton"]:hover {
    background: rgba(102, 126, 234, 0.95) !important;
    border-color: rgba(255, 255, 255, 0.55) !important;
}

/* ===== 侧边栏：深空黑玻璃拟态 ===== */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, rgba(21, 21, 46, 0.98) 0%, rgba(15, 15, 35, 0.99) 100%);
    border-right: 1px solid rgba(255, 255, 255, 0.06);
    backdrop-filter: blur(12px);
}
section[data-testid="stSidebar"] .stMarkdown h1,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3 {
    color: #667eea;
    border-bottom: 1px solid rgba(102, 126, 234, 0.20);
    padding-bottom: 6px;
    font-family: 'Inter', sans-serif;
}
section[data-testid="stSidebar"] a,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] div:not([class*="plotly"]):not([class*="canvas"]) {
    color: #94a3b8 !important;
}
section[data-testid="stSidebar"] a[aria-current="page"],
section[data-testid="stSidebar"] [aria-selected="true"] {
    color: #667eea !important;
    font-weight: 700 !important;
}
section[data-testid="stSidebar"] a:hover {
    color: #a5b4fc !important;
    background-color: rgba(102, 126, 234, 0.08) !important;
    border-radius: 6px !important;
}

/* ===== 标题：紫蓝渐变 ===== */
h1, h2, h3 { font-weight: 700; letter-spacing: 0.3px; font-family: 'Inter', sans-serif; }
.stTitle h1 {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
}
h2 { border-left: 4px solid #667eea; padding-left: 10px; margin-top: 18px; position: relative; }
h2::after { content:''; position:absolute; left:-4px; top:0; bottom:0; width:4px; background:linear-gradient(180deg,#667eea,#764ba2); border-radius:2px; }
h3 { border-left: 3px solid rgba(102, 126, 234, 0.55); padding-left: 8px; }

/* ===== 指标卡：深空黑玻璃 + 紫蓝边光 ===== */
.stMetric {
    background: linear-gradient(145deg, rgba(26, 26, 46, 0.85), rgba(21, 21, 42, 0.92));
    border: 1px solid rgba(102, 126, 234, 0.12);
    border-left: 3px solid #667eea;
    border-radius: 16px; padding: 16px 20px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.05), 0 0 20px rgba(102, 126, 234, 0.05);
    backdrop-filter: blur(8px); transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.stMetric:hover { transform: translateY(-1px); box-shadow: 0 12px 28px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.07), 0 0 28px rgba(102, 126, 234, 0.10); }
.stMetric label, .stMetric .metric-label { color: #94a3b8 !important; font-size: 0.8rem; font-family:'Inter',sans-serif; font-weight: 500; }
.stMetric [data-testid="stMetricValue"] {
    color: #e2e8f0 !important;
    font-family:'Fira Code',monospace !important;
    font-weight: 600 !important;
    font-size: 1.35rem !important;
    text-shadow: 0 0 12px rgba(102, 126, 234, 0.15);
}
.stMetric [data-testid="stMetricDelta"] { color: #94a3b8 !important; }

/* ===== 按钮 ===== */
.stButton button {
    border-radius: 10px;
    border: 1px solid rgba(102, 126, 234, 0.35) !important;
    background: linear-gradient(180deg, rgba(26, 26, 46, 0.9), rgba(15, 15, 35, 0.95)) !important;
    color: #e2e8f0 !important;
    font-weight: 600;
    font-family: 'Inter', sans-serif;
    transition: all 0.2s cubic-bezier(0.4,0,0.2,1);
    box-shadow: 0 2px 8px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.05);
    position: relative;
    overflow: hidden;
}
.stButton button::before { content:''; position:absolute; top:0; left:-100%; width:100%; height:100%; background:linear-gradient(90deg,transparent,rgba(102,126,234,0.08),transparent); transition:left 0.5s ease; }
.stButton button:hover::before { left:100%; }
.stButton button:hover { transform: translateY(-1.5px); box-shadow: 0 6px 20px rgba(102,126,234,0.18), 0 0 20px rgba(102,126,234,0.08); border-color: rgba(102,126,234,0.6) !important; color: #FFFFFF !important; }
.stApp .stButton button[kind="primary"] {
    background: linear-gradient(180deg, #D4A02A, #B8860B) !important;
    border: none !important;
    color: #111827 !important;
    font-weight: 700;
    box-shadow: 0 3px 12px rgba(184, 134, 11, 0.4);
}
.stApp .stButton button[kind="primary"]:hover { box-shadow: 0 6px 24px rgba(184, 134, 11, 0.55) !important; }
/* form submit primary button */
.stApp [data-testid="stFormSubmitButton"] button,
.stApp button[data-testid="stFormSubmitButton"] {
    background: linear-gradient(180deg, #D4A02A, #B8860B) !important;
    border: none !important;
    color: #111827 !important;
    font-weight: 700 !important;
    box-shadow: 0 3px 12px rgba(184, 134, 11, 0.4) !important;
}
.stApp [data-testid="stFormSubmitButton"] button:hover,
.stApp button[data-testid="stFormSubmitButton"]:hover {
    box-shadow: 0 6px 24px rgba(184, 134, 11, 0.55) !important;
}

/* ===== Tabs ===== */
.stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid rgba(255,255,255,0.08); }
.stTabs [data-baseweb="tab"] {
    border-radius: 8px 8px 0 0;
    background: rgba(255,255,255,0.03);
    border: 1px solid transparent;
    border-bottom: none;
    color: #94a3b8;
    font-family: 'Inter', sans-serif;
    font-weight: 500;
    transition: all 0.2s ease;
    padding: 8px 16px;
}
.stTabs [data-baseweb="tab"]:hover { background: rgba(102, 126, 234, 0.08); color: #a5b4fc; }
.stTabs [data-baseweb="tab"][aria-selected="true"] { background: rgba(102, 126, 234, 0.12) !important; color: #667eea !important; border-bottom: 2.5px solid #667eea !important; font-weight: 600; }

/* ===== 表格 ===== */
.stDataFrame, [data-testid="stTable"] { background: rgba(21, 21, 42, 0.75) !important; border: 1px solid rgba(102, 126, 234, 0.08) !important; border-radius: 10px !important; overflow: hidden !important; }
.stDataFrame thead th, [data-testid="stTable"] thead th {
    background: linear-gradient(180deg, #16162c, #101020) !important;
    color: #667eea !important;
    font-weight: 600 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.85rem !important;
    border-bottom: 1px solid rgba(102, 126, 234, 0.25) !important;
}
.stDataFrame tbody td, [data-testid="stTable"] tbody td {
    color: #e2e8f0 !important;
    background: transparent !important;
    font-family: 'Fira Code', monospace;
    font-size: 0.82rem;
    border-bottom: 1px solid rgba(255,255,255,0.05);
}
.stDataFrame tr:hover td, [data-testid="stTable"] tr:hover td { background: rgba(102, 126, 234, 0.06) !important; }

/* ===== 输入框 / 下拉框 / 日期 / 数字 / 文本域：深空黑 + 高对比文字 ===== */
/* 兼容 Streamlit 1.58 多种 DOM 层级：外层组件、data-baseweb 容器、内层 input/select */
.stTextInput,
.stTextArea,
.stSelectbox,
.stDateInput,
.stNumberInput,
.stMultiSelect,
[data-testid="stTextInput"],
[data-testid="stTextArea"],
[data-testid="stSelectbox"],
[data-testid="stDateInput"],
[data-testid="stNumberInput"],
[data-testid="stMultiSelect"] {
    color: #e2e8f0 !important;
}

.stTextInput div[data-baseweb="input"],
.stTextInput div[data-baseweb="base-input"],
.stTextArea div[data-baseweb="textarea"],
.stTextArea div[data-baseweb="base-input"],
.stSelectbox div[data-baseweb="select"],
.stSelectbox div[data-baseweb="base-input"],
.stDateInput div[data-baseweb="date-input"],
.stDateInput div[data-baseweb="base-input"],
.stNumberInput div[data-baseweb="input"],
.stNumberInput div[data-baseweb="base-input"],
.stMultiSelect div[data-baseweb="select"],
.stMultiSelect div[data-baseweb="base-input"],
[data-testid="stTextInput"] div[data-baseweb="input"],
[data-testid="stTextInput"] div[data-baseweb="base-input"],
[data-testid="stTextInputRootElement"] div[data-baseweb="base-input"],
[data-testid="stTextArea"] div[data-baseweb="textarea"],
[data-testid="stTextArea"] div[data-baseweb="base-input"],
[data-testid="stSelectbox"] div[data-baseweb="select"],
[data-testid="stSelectbox"] div[data-baseweb="base-input"],
[data-testid="stDateInput"] div[data-baseweb="date-input"],
[data-testid="stDateInput"] div[data-baseweb="base-input"],
[data-testid="stNumberInput"] div[data-baseweb="input"],
[data-testid="stNumberInput"] div[data-baseweb="base-input"],
[data-testid="stMultiSelect"] div[data-baseweb="select"],
[data-testid="stMultiSelect"] div[data-baseweb="base-input"] {
    background: rgba(21, 21, 42, 0.85) !important;
    border: 1px solid rgba(255, 255, 255, 0.12) !important;
    border-radius: 8px !important;
}

/* Streamlit 1.58 selectbox 真实可视框在 data-baseweb="select" 的直接 div 子元素中，
   外层 select 容器已被染黑，但内层 div 仍被 baseweb 类设为白色背景 */
.stSelectbox div[data-baseweb="select"] > div,
[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
.stMultiSelect div[data-baseweb="select"] > div,
[data-testid="stMultiSelect"] div[data-baseweb="select"] > div {
    background: rgba(21, 21, 42, 0.85) !important;
}


.stTextInput input,
.stTextArea textarea,
.stSelectbox [role="combobox"],
.stDateInput input,
.stNumberInput input,
.stMultiSelect input,
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stSelectbox"] [role="combobox"],
[data-testid="stDateInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stMultiSelect"] input,
[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea,
[data-baseweb="select"] [role="combobox"],
[data-baseweb="date-input"] input {
    color: #e2e8f0 !important;
    -webkit-text-fill-color: #e2e8f0 !important;
    background: transparent !important;
    caret-color: #667eea !important;
}

/* placeholder 暗色提示 */
.stTextInput input::placeholder,
.stTextArea textarea::placeholder,
.stDateInput input::placeholder,
.stNumberInput input::placeholder,
.stSelectbox [role="combobox"] [aria-placeholder] {
    color: #64748b !important;
    opacity: 1 !important;
}

/* focus 状态：紫蓝光环 */
.stTextInput div[data-baseweb="input"]:focus-within,
.stTextInput div[data-baseweb="base-input"]:focus-within,
.stTextArea div[data-baseweb="textarea"]:focus-within,
.stTextArea div[data-baseweb="base-input"]:focus-within,
.stSelectbox div[data-baseweb="select"]:focus-within,
.stSelectbox div[data-baseweb="base-input"]:focus-within,
.stDateInput div[data-baseweb="date-input"]:focus-within,
.stDateInput div[data-baseweb="base-input"]:focus-within,
.stNumberInput div[data-baseweb="input"]:focus-within,
.stNumberInput div[data-baseweb="base-input"]:focus-within,
.stMultiSelect div[data-baseweb="select"]:focus-within,
.stMultiSelect div[data-baseweb="base-input"]:focus-within,
[data-testid="stTextInput"] div[data-baseweb="input"]:focus-within,
[data-testid="stTextInput"] div[data-baseweb="base-input"]:focus-within,
[data-testid="stTextInputRootElement"] div[data-baseweb="base-input"]:focus-within,
[data-testid="stTextArea"] div[data-baseweb="textarea"]:focus-within,
[data-testid="stTextArea"] div[data-baseweb="base-input"]:focus-within,
[data-testid="stSelectbox"] div[data-baseweb="select"]:focus-within,
[data-testid="stSelectbox"] div[data-baseweb="base-input"]:focus-within,
[data-testid="stDateInput"] div[data-baseweb="date-input"]:focus-within,
[data-testid="stDateInput"] div[data-baseweb="base-input"]:focus-within,
[data-testid="stNumberInput"] div[data-baseweb="input"]:focus-within,
[data-testid="stNumberInput"] div[data-baseweb="base-input"]:focus-within,
[data-testid="stMultiSelect"] div[data-baseweb="select"]:focus-within,
[data-testid="stMultiSelect"] div[data-baseweb="base-input"]:focus-within {
    border-color: #667eea !important;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.20), 0 0 20px rgba(102, 126, 234, 0.08) !important;
}

/* 下拉菜单面板 */
div[data-baseweb="select"] ul,
ul[data-baseweb="menu"] {
    background: #1a1a2e !important;
    border: 1px solid rgba(255, 255, 255, 0.12) !important;
    border-radius: 8px !important;
}
ul[data-baseweb="menu"] li,
li[data-baseweb="menu-item"] {
    color: #e2e8f0 !important;
    background: #1a1a2e !important;
}
ul[data-baseweb="menu"] li:hover,
li[data-baseweb="menu-item"]:hover,
li[data-baseweb="menu-item"][aria-selected="true"] {
    background: rgba(102, 126, 234, 0.18) !important;
    color: #FFFFFF !important;
}

/* Radio / Checkbox */
.stRadio [role="radiogroup"],
.stCheckbox [role="group"],
.stRadio [data-baseweb="radio-group"],
.stCheckbox [data-baseweb="checkbox-group"] {
    color: #e2e8f0 !important;
}
.stRadio [role="radio"],
.stCheckbox [role="checkbox"],
[data-baseweb="radio"] [role="radio"],
[data-baseweb="checkbox"] [role="checkbox"] {
    background: rgba(21, 21, 42, 0.85) !important;
    border: 2px solid rgba(255, 255, 255, 0.15) !important;
}
.stRadio [role="radio"]:checked,
.stRadio [role="radio"][aria-checked="true"],
.stCheckbox [role="checkbox"]:checked,
.stCheckbox [role="checkbox"][aria-checked="true"] {
    background: #667eea !important;
    border-color: #667eea !important;
}
.stRadio [role="radio"]:checked + span,
.stCheckbox [role="checkbox"]:checked + span,
.stRadio label span,
.stCheckbox label span {
    color: #e2e8f0 !important;
}

/* disabled 状态 */
.stTextInput div[data-baseweb="input"][disabled],
.stSelectbox div[data-baseweb="select"][disabled],
.stDateInput div[data-baseweb="date-input"][disabled] {
    background: rgba(21, 21, 42, 0.45) !important;
    border-color: rgba(255, 255, 255, 0.06) !important;
    opacity: 0.6 !important;
}

/* ===== 标签文字 ===== */
label, [data-baseweb="label"], .stTextInput label, .stTextArea label, .stSelectbox label,
.stDateInput label, .stNumberInput label, .stCheckbox label, .stRadio label, .stFileUploader label {
    color: #94a3b8 !important;
    font-weight: 500 !important;
}
.stCaption, .caption, small, [data-testid="stCaption"] { color: #64748b !important; }

/* ===== Checkbox / Radio（Streamlit 1.58 DOM 实测）=====
   radio 圆框  : label[data-baseweb="radio"]    > div:first-child  （baseweb class st-g4 浅色底 / st-c1 选中金）
   checkbox 方格: label[data-baseweb="checkbox"] > span:first-child （baseweb class st-dp 浅色底 / 选中金）
   选中态由内部隐藏 <input>:checked 决定，用 :has() 覆盖 baseweb 默认浅色背景。
   注意：不要使用 :not(#fake_id) 提权技巧——部分浏览器下该写法整条选择器不生效。 */
label[data-baseweb="radio"],
label[data-baseweb="checkbox"] { color: #e2e8f0 !important; }
label[data-baseweb="radio"] > div:first-child,
label[data-baseweb="checkbox"] > span:first-child {
    background: rgba(21, 21, 42, 0.85) !important;
    border: 1px solid rgba(255, 255, 255, 0.25) !important;
    border-radius: 50% !important;
}
label[data-baseweb="checkbox"] > span:first-child { border-radius: 4px !important; }
label[data-baseweb="radio"]:has(input:checked) > div:first-child,
label[data-baseweb="checkbox"]:has(input:checked) > span:first-child {
    background: #667eea !important;
    border-color: #667eea !important;
}
label[data-baseweb="checkbox"]:has(input:checked) > span:first-child svg,
label[data-baseweb="checkbox"]:has(input:checked) > span:first-child path {
    fill: #e2e8f0 !important;
    stroke: #e2e8f0 !important;
}
label[data-baseweb="radio"] > div:last-child,
label[data-baseweb="checkbox"] > div:last-child { color: #e2e8f0 !important; }

/* ===== 表单容器 ===== */
[data-testid="stForm"], .stForm, form {
    background: rgba(26, 26, 46, 0.7) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 12px !important;
    padding: 18px 22px !important;
    box-shadow: 0 8px 24px rgba(0,0,0,0.35) !important;
}

/* ===== 滚动条 ===== */
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: rgba(15, 15, 35, 0.9); border-radius: 10px; }
::-webkit-scrollbar-thumb { background: linear-gradient(180deg, #1a1a2e, #2d2d44); border-radius: 10px; border: 1px solid rgba(255,255,255,0.05); }
::-webkit-scrollbar-thumb:hover { background: linear-gradient(180deg, #2d2d44, #3a3a5c); }

/* ===== 提示框 ===== */
.stAlert { border-radius: 12px; border-left: 4px solid; font-family: 'Inter', sans-serif; }
.stAlert[data-baseweb="notification"][kind="success"] { border-left-color: #00d486; background: rgba(0, 212, 134, 0.10); color: #e2e8f0 !important; }
.stAlert[data-baseweb="notification"][kind="error"] { border-left-color: #ff4d4f; background: rgba(255, 77, 79, 0.10); color: #e2e8f0 !important; }
.stAlert[data-baseweb="notification"][kind="warning"] { border-left-color: #ffa502; background: rgba(255, 165, 2, 0.10); color: #e2e8f0 !important; }
.stAlert[data-baseweb="notification"][kind="info"] { border-left-color: #667eea; background: rgba(102, 126, 234, 0.10); color: #e2e8f0 !important; }

hr { border: none; border-top: 1px solid rgba(255,255,255,0.08); margin: 20px 0; }

/* ===== Slider ===== */
[data-testid="stSlider"] [role="slider"] { background: linear-gradient(90deg, #667eea, #764ba2) !important; }
[data-testid="stSlider"] [role="slider"]:hover { box-shadow: 0 0 12px rgba(102, 126, 234, 0.35); }
[data-testid="stSlider"] [role="slider"]::-webkit-slider-runnable-track { background: rgba(255,255,255,0.1) !important; border-radius: 4px !important; }

/* ===== Plotly 图表容器 ===== */
.js-plotly-plot .plotly .modebar { background: rgba(21, 21, 42, 0.92) !important; border-radius: 8px; backdrop-filter: blur(8px); border: 1px solid rgba(255,255,255,0.08); }
.js-plotly-plot .xtick text, .js-plotly-plot .ytick text, .js-plotly-plot .axislabel,
.js-plotly-plot .xaxislayer-above text, .js-plotly-plot .yaxislayer-above text { fill: #94a3b8 !important; color: #94a3b8 !important; }
.js-plotly-plot .legend text { fill: #94a3b8 !important; font-size: 0.8rem !important; }
.js-plotly-plot .gtitle, .js-plotly-plot .g-title { fill: #e2e8f0 !important; color: #e2e8f0 !important; font-weight: 600 !important; }

/* ===== Expander ===== */
.streamlit-expanderHeader { background: rgba(26, 26, 46, 0.6); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; font-family: 'Inter', sans-serif; color: #e2e8f0 !important; }
.streamlit-expanderHeader:hover { border-color: rgba(102, 126, 234, 0.4); background: rgba(102, 126, 234, 0.06); }

/* ===== Spinner / 链接 / 代码 ===== */
.stSpinner > div { color: #667eea !important; border-top-color: #667eea !important; }
a { color: #a5b4fc !important; }
a:hover { color: #667eea !important; }
.stCode, code, pre { background: rgba(21, 21, 42, 0.9) !important; color: #e2e8f0 !important; border: 1px solid rgba(255,255,255,0.08) !important; border-radius: 8px !important; font-family: 'Fira Code', monospace !important; }
.stMarkdown, .stMarkdown p, .stMarkdown li, .stMarkdown span { color: #e2e8f0 !important; }
.stText, [data-testid="stText"] { color: #e2e8f0 !important; }

/* ===== 暗夜模式下原生控件配色（修复输入框白底 / 选择框白底 / 文字看不清） ===== */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input {
  background-color: #15152a !important;
  color: #e2e8f0 !important;
  border: 1px solid #2d2d44 !important;
}
[data-testid="stTextInput"] input::placeholder,
[data-testid="stTextArea"] textarea::placeholder {
  color: #94a3b8 !important;
}
/* selectbox 控件本体（非下拉） */
[data-testid="stSelectbox"] [data-baseweb="select"] { background: transparent !important; }
[data-testid="stSelectbox"] [data-baseweb="select"] > div {
  background-color: #1a1a2e !important;
  color: #e2e8f0 !important;
  border: 1px solid #2d2d44 !important;
}
[data-testid="stSelectbox"] input { color: #e2e8f0 !important; caret-color: #e2e8f0 !important; }
[data-testid="stSelectbox"] svg { fill: #94a3b8 !important; stroke: #94a3b8 !important; }
/* selectbox 下拉列表 */
ul[data-baseweb="listbox"],
ul[role="listbox"] {
  background-color: #15152a !important;
  border: 1px solid #2d2d44 !important;
}
li[data-baseweb="option"],
li[role="option"] {
  color: #e2e8f0 !important;
  background-color: transparent !important;
}
li[data-baseweb="option"]:hover,
li[role="option"]:hover,
li[data-baseweb="option"][aria-selected="true"],
li[role="option"][aria-selected="true"] {
  background-color: #241b3a !important;
  color: #ffffff !important;
}
/* ===== Popover 弹层（星辰 AI）暗色适配 =====
   目标：覆盖 baseweb 默认白色浮层，强制深空黑底 + 高对比文字 */
[data-testid="stPopoverBody"],
[data-testid="stPopoverBody"] > div,
[data-testid="stPopover"] [role="dialog"],
[data-testid="stPopover"] [role="dialog"] > div,
[data-testid="stPopover"] > div,
[data-testid="stPopover"] [data-testid="stVerticalBlock"],
[data-testid="stPopover"] [data-testid="stVerticalBlockBorderWrapper"] {
  background: #1a1a2e !important;
  color: #e2e8f0 !important;
  border-color: #2d2d44 !important;
}
[data-testid="stPopoverBody"] p,
[data-testid="stPopoverBody"] span,
[data-testid="stPopoverBody"] div,
[data-testid="stPopoverBody"] h4,
[data-testid="stPopoverBody"] h5,
[data-testid="stPopover"] p,
[data-testid="stPopover"] span,
[data-testid="stPopover"] h4,
[data-testid="stPopover"] h5,
[data-testid="stPopover"] .stMarkdown,
[data-testid="stPopover"] .stMarkdown p,
[data-testid="stPopover"] .stMarkdown span,
[data-testid="stPopover"] .stMarkdown div {
  color: #e2e8f0 !important;
}
[data-testid="stPopover"] .stMarkdown,
[data-testid="stPopoverBody"] .stMarkdown {
  background: transparent !important;
}
/* Popover 内文本域 */
[data-testid="stPopoverBody"] textarea,
[data-testid="stPopover"] textarea {
  background: #15152a !important;
  color: #e2e8f0 !important;
  border: 1px solid #2d2d44 !important;
}
[data-testid="stPopoverBody"] textarea::placeholder,
[data-testid="stPopover"] textarea::placeholder {
  color: #64748b !important;
}
/* Popover 内按钮 */
[data-testid="stPopoverBody"] button,
[data-testid="stPopover"] button {
  color: #111827 !important;
  font-weight: 600 !important;
}
/* Popover 触发按钮（暗夜下默认白底，需强制深色渐变底+白字）
   放在 popover 通用按钮规则之后，保证触发按钮自身文字为白色 */
[data-testid="stPopover"] > button,
button[data-testid="stPopoverButton"] {
  background: linear-gradient(135deg, #667eea, #764ba2) !important;
  color: #ffffff !important;
  border: none !important;
  font-weight: 600 !important;
}
[data-testid="stPopover"] > button:hover,
button[data-testid="stPopoverButton"]:hover {
  background: linear-gradient(135deg, #764ba2, #667eea) !important;
  box-shadow: 0 4px 14px rgba(102, 126, 234, .35) !important;
}
/* radio / checkbox 文字与选中态 */
[data-testid="stRadio"] label,
[data-testid="stCheckbox"] label { color: #e2e8f0 !important; }
[data-testid="stRadio"] > div,
[data-testid="stRadio"] { background: transparent !important; }
[data-baseweb="radio"] { background: #1a1a2e !important; border-color: #2d2d44 !important; }
[data-baseweb="radio"][aria-checked="true"] { background: #667eea !important; border-color: #667eea !important; }
/* slider 轨道与滑块 */
[data-testid="stSlider"] { color: #e2e8f0 !important; }
[data-baseweb="slider"] { background: transparent !important; }
[data-baseweb="slider"] [data-testid="track"] { background: #2d2d44 !important; }
[data-baseweb="slider"] [data-testid="thumb"] { background: #667eea !important; border-color: #667eea !important; }
</style>
"""


# ════════════════════════════════════════════════════════════
#  亮色主题 CSS v6 — 专业金融仪表盘
# ════════════════════════════════════════════════════════════
_LIGHT_CSS = """
<!-- Google Fonts: Fira Code (数据) + Inter (UI) -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">

<style>
html, body, .stApp {
    color: #374151 !important;
    font-family: 'Inter', -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif !important;
}
.stApp {
    background-color: #F5F7FA !important;
    background-image:
        radial-gradient(ellipse 70% 40% at 10% -5%, rgba(184,134,11,0.035) 0%, transparent 55%),
        radial-gradient(ellipse 80% 50% at 90% 105%, rgba(59,130,246,0.02) 0%, transparent 50%);
}
/* ===== 隐藏 Streamlit 默认菜单/工具栏，但保留顶部 header 容器
        以便侧边栏展开/折叠按钮始终可见；header 本身设为透明不占视觉空间 ===== */
#MainMenu { display: none !important; }
footer { display: none !important; }
[data-testid="stToolbar"] { padding: 0 !important; margin: 0 !important; min-height: 0 !important; background: transparent !important; border: none !important; box-shadow: none !important; }
[data-testid="stDecoration"] { display: none !important; }
header[data-testid="stHeader"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
    margin: 0 !important;
    height: auto !important;
    min-height: 0 !important;
}

/* 折叠态的展开按钮：固定到左上角，避免被透明 header 压成 0×0 看不见/点不到 */
button[data-testid="stExpandSidebarButton"] {
    position: fixed !important;
    top: 10px !important;
    left: 10px !important;
    z-index: 99999 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    width: 38px !important;
    height: 38px !important;
    padding: 0 !important;
    background: #FFFFFF !important;
    border: 1px solid #C9CCD1 !important;
    border-radius: 8px !important;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.18) !important;
    cursor: pointer !important;
    visibility: visible !important;
    opacity: 1 !important;
}
button[data-testid="stExpandSidebarButton"]:hover {
    background: #EAECEF !important;
    border-color: #3B82F6 !important;
}

section[data-testid="stSidebar"] {
    background: #EEF0F2 !important;
    border-right: 1px solid #D5D7DB !important;
    color: #374151 !important;
}
section[data-testid="stSidebar"] .stMarkdown h1,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3 {
    color: #92400E !important;
    border-bottom: 1px solid rgba(184,134,11,0.18) !important;
    padding-bottom: 6px;
    font-family: 'Inter', sans-serif !important;
}
section[data-testid="stSidebar"] a,
section[data-testid="stSidebar"] [class*="link"],
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] div:not([class*="plotly"]):not([class*="canvas"]) {
    color: #374151 !important;
}
section[data-testid="stSidebar"] a[aria-current="page"],
section[data-testid="stSidebar"] [aria-selected="true"] {
    color: #92400E !important;
    font-weight: 700 !important;
}
section[data-testid="stSidebar"] a:hover {
    color: #78350F !important;
    background-color: rgba(184,134,11,0.08) !important;
    border-radius: 6px !important;
}

h1, h2, h3, h4, h5, h6 {
    color: #111827 !important;
    font-weight: 700 !important;
    letter-spacing: 0.3px !important;
    font-family: 'Inter', sans-serif !important;
}
h2 {
    border-left: 4px solid #B8860B !important;
    padding-left: 10px !important;
    margin-top: 18px !important;
}
h3 {
    border-left: 3px solid rgba(184,134,11,0.5) !important;
    padding-left: 8px !important;
}

.stMetric {
    background: #FFFFFF !important;
    border: 1px solid #E5E7EB !important;
    border-left: 3px solid #B8860B !important;
    border-radius: 12px !important;
    padding: 16px 20px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.02) !important;
    transition: transform 0.2s ease, box-shadow 0.2s ease !important;
}
.stMetric:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 12px rgba(0,0,0,0.08) !important;
    border-color: #D1D5DB !important;
}
.stMetric label,
.stMetric .metric-label {
    color: #6B7280 !important;
    font-size: 0.8rem !important;
    font-family: 'Inter', sans-serif !important;
}
.stMetric [data-testid="stMetricValue"] {
    color: #111827 !important;
    font-weight: 650 !important;
    font-family: 'Fira Code', monospace !important;
}

.stButton button {
    border-radius: 8px !important;
    border: 1px solid #D1D5DB !important;
    font-weight: 600 !important;
    font-family: 'Inter', sans-serif !important;
    color: #374151 !important;
    background: linear-gradient(180deg, #FFFFFF, #F9FAFB) !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
    transition: all 0.15s ease !important;
}
.stButton button:hover {
    border-color: #B8860B !important;
    background: linear-gradient(180deg, #FFFBF0, #FEF3C7) !important;
    box-shadow: 0 3px 10px rgba(184,134,11,0.12) !important;
    transform: translateY(-1px) !important;
    color: #111827 !important;
}
.stButton button[kind="primary"] {
    background: linear-gradient(180deg, #D4A02A, #B8860B) !important;
    border: none !important;
    color: #FFFFFF !important;
    font-weight: 700 !important;
    box-shadow: 0 3px 10px rgba(184,134,11,0.25) !important;
}
.stButton button[kind="primary"]:hover {
    background: linear-gradient(180deg, #E0AA2E, #C9941F) !important;
    box-shadow: 0 5px 16px rgba(184,134,11,0.35) !important;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 6px !important;
    border-bottom: 2px solid #E5E7EB !important;
    background: transparent !important;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px 8px 0 0 !important;
    background: #F8FAFC !important;
    border: 1px solid #E5E7EB !important;
    border-bottom: none !important;
    color: #4B5563 !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 500 !important;
    transition: all 0.15s ease !important;
    padding: 8px 18px !important;
}
.stTabs [data-baseweb="tab"]:hover {
    background: #FFFBF0 !important;
    color: #92400E !important;
}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    background: #FFFFFF !important;
    color: #B8860B !important;
    font-weight: 700 !important;
    border-bottom: 2.5px solid #B8860B !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
}

.stDataFrame,
[data-testid="stTable"] {
    background: #FFFFFF !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 10px !important;
    overflow: hidden !important;
}
.stDataFrame thead th,
[data-testid="stTable"] thead th {
    background: linear-gradient(180deg, #F8FAFC, #F1F3F5) !important;
    color: #111827 !important;
    font-weight: 600 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.83rem !important;
    border-bottom: 2px solid #E5E7EB !important;
}
.stDataFrame tbody td,
[data-testid="stTable"] tbody td {
    color: #374151 !important;
    background: #FFFFFF !important;
    border-bottom: 1px solid #F3F4F6 !important;
    font-family: 'Fira Code', monospace !important;
    font-size: 0.82rem !important;
}
.stDataFrame tr:hover td,
[data-testid="stTable"] tr:hover td {
    background: #FFFBF0 !important;
}

.stTextInput div[data-baseweb="input"],
.stTextInput div[data-baseweb="base-input"],
.stTextArea div[data-baseweb="textarea"],
.stTextArea div[data-baseweb="base-input"],
.stSelectbox div[data-baseweb="select"],
.stSelectbox div[data-baseweb="base-input"],
.stDateInput div[data-baseweb="date-input"],
.stDateInput div[data-baseweb="base-input"],
.stNumberInput div[data-baseweb="input"],
.stNumberInput div[data-baseweb="base-input"],
.stMultiSelect div[data-baseweb="select"],
.stMultiSelect div[data-baseweb="base-input"],
[data-testid="stTextInput"] div[data-baseweb="input"],
[data-testid="stTextInput"] div[data-baseweb="base-input"],
[data-testid="stTextInputRootElement"] div[data-baseweb="base-input"],
[data-testid="stTextArea"] div[data-baseweb="textarea"],
[data-testid="stTextArea"] div[data-baseweb="base-input"],
[data-testid="stSelectbox"] div[data-baseweb="select"],
[data-testid="stSelectbox"] div[data-baseweb="base-input"],
[data-testid="stDateInput"] div[data-baseweb="date-input"],
[data-testid="stDateInput"] div[data-baseweb="base-input"],
[data-testid="stNumberInput"] div[data-baseweb="input"],
[data-testid="stNumberInput"] div[data-baseweb="base-input"],
[data-testid="stMultiSelect"] div[data-baseweb="select"],
[data-testid="stMultiSelect"] div[data-baseweb="base-input"] {
    background: #FFFFFF !important;
    border: 1px solid #D1D5DB !important;
    border-radius: 8px !important;
}
.stTextInput input,
.stTextArea textarea,
.stSelectbox [role="combobox"],
.stDateInput input,
.stNumberInput input {
    color: #111827 !important;
    -webkit-text-fill-color: #111827 !important;
    background: transparent !important;
}
.stTextInput > div[data-baseweb="input"]:focus-within,
.stTextArea > div[data-baseweb="textarea"]:focus-within,
.stSelectbox > div[data-baseweb="select"]:focus-within,
.stDateInput > div[data-baseweb="date-input"]:focus-within,
.stNumberInput > div[data-baseweb="input"]:focus-within {
    border-color: #B8860B !important;
    box-shadow: 0 0 0 3px rgba(184,134,11,0.15) !important;
}

label,
[data-baseweb="label"],
[data-baseweb="form-label"],
.stTextInput label,
.stTextArea label,
.stSelectbox label,
.stDateInput label,
.stNumberInput label,
.stCheckbox label,
.stRadio label,
.stFileUploader label {
    color: #4B5563 !important;
    font-weight: 500 !important;
    font-size: 0.875rem !important;
    font-family: 'Inter', sans-serif !important;
}
.stCaption,
.caption,
small,
[data-testid="stCaption"] {
    color: #6B7280 !important;
    font-size: 0.82rem !important;
}

/* Radio / Checkbox（Streamlit 1.58 DOM 实测）*/
label[data-baseweb="radio"] > div:first-child,
label[data-baseweb="checkbox"] > span:first-child {
    background: #FFFFFF !important;
    border: 1px solid #D1D5DB !important;
    border-radius: 50% !important;
}
label[data-baseweb="checkbox"] > span:first-child { border-radius: 4px !important; }
label[data-baseweb="radio"]:has(input:checked) > div:first-child,
label[data-baseweb="checkbox"]:has(input:checked) > span:first-child {
    background: #B8860B !important;
    border-color: #996515 !important;
}
label[data-baseweb="checkbox"]:has(input:checked) > span:first-child svg,
label[data-baseweb="checkbox"]:has(input:checked) > span:first-child path {
    fill: #FFFFFF !important;
    stroke: #FFFFFF !important;
}

[data-testid="stForm"],
.stForm,
form {
    background: #FFFFFF !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 12px !important;
    padding: 18px 22px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.02) !important;
}

.streamlit-expanderHeader {
    background: #FFFFFF !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 10px !important;
    color: #374151 !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 500 !important;
}
.streamlit-expanderHeader:hover {
    border-color: #B8860B !important;
    background: #FFFBF0 !important;
}

.stAlert {
    background: #FFFFFF !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 10px !important;
    color: #111827 !important;
    font-family: 'Inter', sans-serif !important;
}
.stAlert[data-baseweb="notification"][kind="success"] {
    border-left-color: #0ECB81 !important;
    background: rgba(14,203,129,0.06) !important;
}
.stAlert[data-baseweb="notification"][kind="error"] {
    border-left-color: #EF4444 !important;
    background: rgba(239,68,68,0.04) !important;
}
.stAlert[data-baseweb="notification"][kind="warning"] {
    border-left-color: #F59E0B !important;
    background: rgba(245,158,11,0.05) !important;
}
.stAlert[data-baseweb="notification"][kind="info"] {
    border-left-color: #3B82F6 !important;
    background: rgba(59,130,246,0.04) !important;
}
.stInfo {
    background: rgba(255,255,255,0.95) !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 10px !important;
    color: #374151 !important;
}

.js-plotly-plot,
.js-plotly-plot .js-plotly-plot,
div[data-testid="stPlotlyChart"] {
    background: #FFFFFF !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 10px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
    padding: 4px !important;
}
.js-plotly-plot .plotly .modebar {
    background: rgba(255,255,255,0.92) !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 6px !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06) !important;
}
.js-plotly-plot .xtick text,
.js-plotly-plot .ytick text,
.js-plotly-plot .axislabel,
.js-plotly-plot .xaxislayer-above text,
.js-plotly-plot .yaxislayer-above text {
    fill: #6B7280 !important;
    color: #6B7280 !important;
    font-size: 0.78rem !important;
}
.js-plotly-plot .legend text {
    fill: #4B5563 !important;
    font-size: 0.8rem !important;
}
.js-plotly-plot .gtitle,
.js-plotly-plot .g-title {
    fill: #111827 !important;
    color: #111827 !important;
    font-weight: 600 !important;
}
.js-plotly-plot .gtitle text {
    fill: #4B5563 !important;
}

::-webkit-scrollbar { width: 8px !important; height: 8px !important; }
::-webkit-scrollbar-track {
    background: #EEF0F2 !important;
    border-radius: 6px !important;
}
::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, #C4C8CE, #A8ADB6) !important;
    border-radius: 6px !important;
    border: 1px solid #D5D7DB !important;
}
::-webkit-scrollbar-thumb:hover {
    background: linear-gradient(180deg, #A8ADB6, #9094A0) !important;
}

[data-testid="stSlider"] [role="slider"] {
    background: linear-gradient(90deg, #B8860B, #996515) !important;
    border: 2px solid #996515 !important;
}
[data-testid="stSlider"] [role="slider"]:hover {
    box-shadow: 0 0 8px rgba(184,134,11,0.25) !important;
}
[data-testid="stSlider"] [role="slider"]::-webkit-slider-runnable-track {
    background: #E5E7EB !important;
    border-radius: 4px !important;
}

hr {
    border: none !important;
    border-top: 1px solid #E5E7EB !important;
    margin: 20px 0 !important;
}
.stSpinner > div {
    color: #B8860B !important;
    border-top-color: #B8860B !important;
}
a { color: #2563EB !important; }
a:hover { color: #1D4ED8 !important; }
.stCode,
code,
pre {
    background: #F8FAFC !important;
    color: #111827 !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 8px !important;
    font-family: 'Fira Code', monospace !important;
}
.stMarkdown { color: #374151 !important; }
.stMarkdown p,
.stMarkdown li,
.stMarkdown span {
    color: #374151 !important;
}
.stText,
[data-testid="stText"] {
    color: #374151 !important;
}
/* ===== Popover 弹层（星辰 AI）亮色适配 ===== */
[data-testid="stPopover"],
[data-testid="stPopover"] > div,
[data-testid="stPopover"] [data-testid="stVerticalBlock"],
[data-testid="stPopover"] [data-testid="stVerticalBlockBorderWrapper"] {
  background: #ffffff !important;
  color: #111827 !important;
  border-color: #e5e7eb !important;
}
[data-testid="stPopover"] p,
[data-testid="stPopover"] span,
[data-testid="stPopover"] div,
[data-testid="stPopover"] h4,
[data-testid="stPopover"] h5,
[data-testid="stPopover"] .stMarkdown,
[data-testid="stPopover"] .stMarkdown p,
[data-testid="stPopover"] .stMarkdown span,
[data-testid="stPopover"] .stMarkdown div {
  color: #111827 !important;
}
[data-testid="stPopover"] .stMarkdown {
  background: transparent !important;
}
[data-testid="stPopover"] textarea {
  background: #ffffff !important;
  color: #111827 !important;
  border: 1px solid #d1d5db !important;
}
[data-testid="stPopover"] textarea::placeholder {
  color: #9ca3af !important;
}
[data-testid="stPopover"] button {
  color: #ffffff !important;
  font-weight: 600 !important;
}
</style>
"""


# Plotly 暗色模板：修复白底/白网格/白K线（方框发白的根因）
PLOTLY_DARK = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"color": "#94a3b8", "family": "system-ui, -apple-system, 'PingFang SC', sans-serif"},
    "xaxis": {"gridcolor": "#23233c", "zerolinecolor": "#2d2d44",
              "linecolor": "#2d2d44", "tickcolor": "#2d2d44",
              "title": {"font": {"color": "#94a3b8"}}},
    "yaxis": {"gridcolor": "#23233c", "zerolinecolor": "#2d2d44",
              "linecolor": "#2d2d44", "tickcolor": "#2d2d44",
              "title": {"font": {"color": "#94a3b8"}}},
    "legend": {"bgcolor": "rgba(0,0,0,0)", "font": {"color": "#94a3b8"}},
}


def inject_plotly_dark() -> None:
    """若页面用到 Plotly（st.plotly_chart / K线），调用一次本函数
    让 Plotly 默认走暗色，根除白底白框。"""
    try:
        import plotly.io as pio
        import plotly.graph_objects as go
        if "starfield_dark" not in pio.templates:
            pio.templates["starfield_dark"] = go.layout.Template(layout=PLOTLY_DARK)
        pio.templates.default = "starfield_dark"
    except Exception:
        pass


def _theme_is_dark() -> bool:
    """当前是否应呈现暗色：仅由用户全局主题 theme_mode 控制（默认亮色）。

    不再按页面强制暗色——之前「个股分析 / 多股对比」访问后所有页面被污染成暗色，
    用户投诉「切功能模块黑白切换」。现在所有页面统一跟随右上角主题开关，
    白天 / 暗夜两种模式都可手动切换，离开页面不残留。
    """
    return st.session_state.get("theme_mode", "light") == "dark"


def apply_theme() -> None:
    """注入全局润色 CSS（暗色/亮色）并设置 Plotly 模板。"""
    if _theme_is_dark():
        st.markdown(_DARK_CSS, unsafe_allow_html=True)
        inject_plotly_dark()
    else:
        st.markdown(_LIGHT_CSS, unsafe_allow_html=True)
    # 全局字号：覆盖 html/body/.stApp，使所有页面（含 Streamlit 默认文本）整体缩放
    inject_font_size()
    # 全局 ▲ 回到顶部 + C 键清缓存拦截 + 星辰 AI 页 ▼ 回到底部，
    # 三者合并进 inject_scroll_nav 的【单一、且每页唯一可靠执行的】components.html 注入。
    # ▼ 由星辰 AI 对话页的 st.chat_input（testid=stChatInput，全站唯一）驱动出现/消失，
    # 避免页面内再发起第二次 components.html 调用（实测同页多次 components.html 仅首次脚本可靠执行）。
    from modules.scroll_nav import inject_scroll_nav
    inject_scroll_nav(show_bottom=False, bottom_marker="stChatInput", dark=_theme_is_dark())


def get_current_mode() -> str:
    return st.session_state.get("theme_mode", "light")


def dashboard_sf_css() -> str:
    """个股分析「决策仪表盘」的 .sf-* 组件样式（白天 / 暗夜双主题自适应）。

    通过 CSS 变量切换：暗夜用深空黑底 + 紫蓝渐变，白天用白卡 + 浅边框高对比。
    页面只需注入一次，:root 变量会覆盖全局主题里的同名变量，保证配色一致。
    """
    dark = _theme_is_dark()
    if dark:
        root = """
  --bg:#0f0f23; --card:#1a1a2e; --card2:#15152a; --buy:#009e60; --sell:#dc2626; --hold:#d97706;
  --acc1:#4f46e5; --acc2:#7c3aed; --txt:#e2e8f0; --txt2:#94a3b8; --border:#2d2d44;
  --hover:#15152a; --alert-risk:#ffb3bb; --alert-cat:#9af0dd; --disclaimer:#6b7280;
  --header-g1:#1a1a2e; --header-g2:#241b3a; --icon-g1:#1a1a2e; --icon-g2:#241b3a;
"""
    else:
        root = """
  --bg:#ffffff; --card:#ffffff; --card2:#f4f6fb; --buy:#009e60; --sell:#dc2626; --hold:#d97706;
  --acc1:#4f46e5; --acc2:#7c3aed; --txt:#1e293b; --txt2:#64748b; --border:#e2e8f0;
  --hover:#f1f5f9; --alert-risk:#991b1b; --alert-cat:#166534; --disclaimer:#94a3b8;
  --header-g1:#eef2ff; --header-g2:#ede9fe; --icon-g1:#eef2ff; --icon-g2:#ede9fe;
"""
    return f"""
<style>
:root{{{root}}}
/* 文档风格：绿涨红跌（参考 002947，本页统一采用） */
.sf-doc-up{{color:var(--buy)!important}}
.sf-doc-down{{color:var(--sell)!important}}
.sf-doc-neu{{color:var(--hold)!important}}
.sf-buy-badge{{display:inline-block;font-size:22px;font-weight:800;letter-spacing:2px;
  padding:10px 28px;border-radius:14px;color:#fff;background:linear-gradient(135deg,#009e60,#047857);
  box-shadow:0 0 20px rgba(0,158,96,.22)}}
.sf-sell-badge{{background:linear-gradient(135deg,#dc2626,#b91c1c);color:#fff;box-shadow:0 0 20px rgba(220,38,38,.22)}}
.sf-hold-badge{{background:linear-gradient(135deg,#d97706,#b45309);color:#fff;box-shadow:0 0 20px rgba(217,119,6,.22)}}
.sf-price-big{{font-size:42px;font-weight:800;letter-spacing:-1px;font-family:'Fira Code',monospace;color:var(--buy)}}
.sf-triangle{{font-size:22px;margin-right:4px}}
.sf-metric-card{{background:var(--card2);border:1px solid var(--border);border-radius:12px;padding:14px;text-align:center}}
.sf-metric-card .label{{font-size:12px;color:var(--txt2);margin-bottom:6px}}
.sf-metric-card .value{{font-size:22px;font-weight:700;font-family:'Fira Code',monospace;color:var(--txt)}}
.sf-insight-box{{background:rgba(0,158,96,.10);border:1px solid rgba(0,158,96,.35);
  border-radius:12px;padding:14px 16px;line-height:1.8;font-size:14px;color:var(--txt)}}
.sf-insight-box.hold{{background:rgba(217,119,6,.10);border-color:rgba(217,119,6,.35);color:var(--txt)}}
.sf-grid-4{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0}}
@media(max-width:900px){{.sf-grid-4{{grid-template-columns:repeat(2,1fr)}}}}
@media(max-width:540px){{.sf-grid-4{{grid-template-columns:1fr}}}}
.sf-perspective-card{{background:var(--card2);border:1px solid var(--border);border-radius:14px;padding:16px;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
.sf-perspective-card .title{{font-size:12px;color:var(--txt2);margin-bottom:10px}}
.sf-perspective-card .body{{font-size:14px;color:var(--txt);line-height:1.6}}
.sf-pill{{display:inline-block;font-size:11px;font-weight:600;padding:3px 10px;border-radius:12px;margin:2px 2px 2px 0}}
.sf-pill.up{{background:rgba(0,158,96,.12);color:var(--buy);border:1px solid rgba(0,158,96,.35)}}
.sf-pill.down{{background:rgba(220,38,38,.12);color:var(--sell);border:1px solid rgba(220,38,38,.35)}}
.sf-pill.mid{{background:rgba(217,119,6,.12);color:var(--hold);border:1px solid rgba(217,119,6,.35)}}
.sf-intel-header{{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:12px}}
.sf-intel-header h2{{margin:0;padding:0;border:0}}
.sf-intel-bar{{height:6px;border-radius:3px;overflow:hidden;display:flex;margin:10px 0 18px;background:var(--border)}}
.sf-intel-bar .bar-pos{{height:100%;background:var(--buy)}}
.sf-intel-bar .bar-neu{{height:100%;background:var(--hold)}}
.sf-intel-bar .bar-neg{{height:100%;background:var(--sell)}}
.sf-section-header{{display:flex;align-items:center;gap:12px;margin:0 0 14px;padding:0 0 12px;border-bottom:1px solid var(--border);position:relative}}
.sf-section-header .icon{{font-size:20px;width:34px;height:34px;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,var(--icon-g1),var(--icon-g2));border:1px solid var(--border);border-radius:10px}}
.sf-section-header .titles{{flex:1}}
.sf-section-header h2{{margin:0;font-size:17px;font-weight:700;color:var(--txt);border:none!important;padding:0!important}}
.sf-section-header .sub{{font-size:12px;color:var(--txt2);margin-top:2px}}
.sf-section-header .deco{{width:40px;height:3px;border-radius:2px;background:linear-gradient(90deg,#4f46e5,#7c3aed);position:absolute;bottom:-1.5px;left:0}}
.sf-header{{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;margin-bottom:18px;padding:14px 18px;background:linear-gradient(90deg,var(--header-g1),var(--header-g2));border:1px solid var(--border);border-radius:14px}}
.sf-brand{{font-size:15px;color:var(--txt2);letter-spacing:1px}}
.sf-brand b{{color:var(--acc1)}}
.sf-tag{{display:inline-block;font-size:11px;font-weight:600;padding:3px 10px;border-radius:12px;margin:2px 2px 2px 0}}
.sf-tag.up{{background:rgba(0,158,96,.14);color:var(--buy);border:1px solid rgba(0,158,96,.38)}}
.sf-tag.down{{background:rgba(220,38,38,.14);color:var(--sell);border:1px solid rgba(220,38,38,.38)}}
.sf-tag.mid{{background:rgba(217,119,6,.14);color:var(--hold);border:1px solid rgba(217,119,6,.38)}}
.sf-tag.neu{{background:rgba(148,163,184,.12);color:var(--txt2);border:1px solid var(--border)}}
.sf-alert{{border-radius:12px;padding:13px 15px;margin-top:14px;font-size:13.5px;color:var(--txt);line-height:1.7}}
.sf-alert.risk{{background:rgba(220,38,38,.10);border:1px solid rgba(220,38,38,.30);color:var(--alert-risk)}}
.sf-alert.cat{{background:rgba(0,158,96,.10);border:1px solid rgba(0,158,96,.30);color:var(--alert-cat)}}
.sf-alert b{{display:block;margin-bottom:5px;font-size:14px}}
.sf-table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}}
.sf-table th,.sf-table td{{padding:9px 10px;text-align:left;border-bottom:1px solid var(--border)}}
.sf-table th{{color:var(--txt2);font-weight:600;font-size:12px}}
.sf-table tr:hover td{{background:var(--hover)}}
.sf-disclaimer{{margin-top:14px;font-size:11.5px;color:var(--disclaimer);border-top:1px dashed var(--border);padding-top:10px}}
.sf-vs{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:8px}}
@media(max-width:780px){{.sf-vs{{grid-template-columns:1fr}}}}
.sf-vsbox{{background:var(--card2);border:1px solid var(--border);border-radius:12px;padding:14px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.sf-vsbox h3{{font-size:14px;margin-bottom:8px;color:var(--txt);border:none!important;padding-left:0!important}}
.sf-card{{background:var(--card2);border:1px solid var(--border);border-radius:14px;padding:18px;margin-top:16px;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
.sf-card h2:first-child{{margin-top:0!important}}
</style>
"""


def section_header(title: str, subtitle: str = "", icon: str = "📊") -> None:
    if not _theme_is_dark():
        _bg = "#111827"; _accent = "#B8860B"; _sub = "#6B7280"
    else:
        _bg = "#e2e8f0"; _accent = "#667eea"; _sub = "#94a3b8"
    st.markdown(
        ("<div style='margin:14px 0 10px;padding-left:10px;border-left:4px solid " + _accent +
         ";background:linear-gradient(90deg,rgba(102,126,234,0.08),transparent);border-radius:0 8px 8px 0;'>"
         "<div style='font-size:1.15rem;font-weight:700;color:" + _bg + ";font-family:'Inter',sans-serif;'>"
         + str(icon) + " " + str(title) + "</div>"
         + ('<div style="font-size:0.85rem;color:' + _sub + ';margin-top:2px;">' + str(subtitle) + '</div>' if subtitle else '')
         + "</div>"),
        unsafe_allow_html=True,
    )


def card(body_html: str) -> None:
    if not _theme_is_dark():
        _bg = "#FFFFFF"; _bd = "rgba(17,24,39,0.08)"; _sh = "0 4px 16px rgba(17,24,39,0.06), inset 0 1px 0 rgba(255,255,255,0.8)"
    else:
        _bg = "rgba(26, 26, 46, 0.65)"; _bd = "rgba(102, 126, 234, 0.10)"; _sh = "0 8px 24px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.05), 0 0 24px rgba(102,126,234,0.06)"
    st.markdown(
        ("<div style='background:" + _bg + ";border:1px solid " + _bd +
         ";border-radius:16px;padding:18px 20px;box-shadow:" + _sh + ";backdrop-filter:blur(10px);'>" + body_html + "</div>"),
        unsafe_allow_html=True,
    )


def loading_spinner(text: str = "加载中...", variant: str = "default") -> None:
    if not _theme_is_dark():
        _g = "#B8860B"; _gl = "#F6D486"; _gs = "rgba(184,134,11,0.12)"; _fc = "#555B65"
    else:
        _g = "#667eea"; _gl = "#a5b4fc"; _gs = "rgba(102,126,234,0.12)"; _fc = "#94a3b8"
    _t = text
    variants = {
        "default": (
            "<div style='text-align:center;padding:20px;color:" + _fc + ";'>"
            "<div style='display:inline-block;width:36px;height:36px;border:3px solid " + _gs +
            ";border-top:3px solid " + _g + ";border-radius:50%;animation:ld-spin 0.8s linear infinite;'></div>"
            "<p style='margin-top:10px;font-size:0.9rem;'>" + _t + "</p></div>"
            "<style>@keyframes ld-spin{to{transform:rotate(360deg);}}</style>"
        ),
        "pulse": (
            "<div style='text-align:center;padding:20px;color:" + _fc + ";'>"
            "<div style='display:inline-block;width:40px;height:40px;background:" + _gs +
            ";border-radius:8px;animation:ld-pulse 1.2s ease-in-out infinite;'></div>"
            "<p style='margin-top:10px;font-size:0.9rem;'>" + _t + "</p></div>"
            "<style>@keyframes ld-pulse{0%,100%{opacity:0.4;transform:scale(0.95);}50%{opacity:1;transform:scale(1.05);}}</style>"
        ),
        "dots": (
            "<div style='text-align:center;padding:20px;color:" + _fc + ";'>"
            "<div style='display:flex;gap:6px;justify-content:center;'>"
            "<div style='width:8px;height:8px;background:" + _g + ";border-radius:50%;animation:ld-bounce 1s ease-in-out infinite;'></div>"
            "<div style='width:8px;height:8px;background:" + _g + ";border-radius:50%;animation:ld-bounce 1s ease-in-out 0.15s infinite;'></div>"
            "<div style='width:8px;height:8px;background:" + _g + ";border-radius:50%;animation:ld-bounce 1s ease-in-out 0.3s infinite;'></div>"
            "</div><p style='margin-top:10px;font-size:0.9rem;'>" + _t + "</p></div>"
            "<style>@keyframes ld-bounce{0%,80%,100%{transform:translateY(0);}40%{transform:translateY(-10px);}}</style>"
        ),
        "bar": (
            "<div style='text-align:center;padding:20px;color:" + _fc + ";'>"
            "<div style='display:inline-block;width:120px;height:4px;background:rgba(0,0,0,0.04);border-radius:2px;overflow:hidden;'>"
            "<div style='height:100%;background:linear-gradient(90deg," + _g + "," + _gl + ");border-radius:2px;"
            "animation:ld-slide 1.5s ease-in-out infinite;width:40%;'></div></div>"
            "<p style='margin-top:10px;font-size:0.9rem;'>" + _t + "</p></div>"
            "<style>@keyframes ld-slide{0%{margin-left:-40%;}100%{margin-left:120%;}}</style>"
        ),
    }
    html_content = variants.get(variant, variants["default"])
    st.markdown(html_content, unsafe_allow_html=True)
