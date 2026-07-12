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
    background: linear-gradient(180deg, #667eea, #764ba2) !important;
    border: none !important;
    color: #0f0f23 !important;
    font-weight: 700;
    box-shadow: 0 3px 12px rgba(102, 126, 234, 0.4);
}
.stApp .stButton button[kind="primary"]:hover { box-shadow: 0 6px 24px rgba(102, 126, 234, 0.55) !important; }

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
    """当前是否应呈现暗色：用户显式选择暗夜，或当前页面为强制暗色的「个股分析」。

    个股分析 / 多股票对比 是「决策仪表盘」暗色页面，过去直接改写全局 theme_mode 导致
    访问该页后所有页面都被强制变暗（用户投诉的「切功能模块黑白切换」）。
    改为按页面作用域判断，离开该页即恢复正常主题，不再污染全局。
    """
    if st.session_state.get("theme_mode", "light") == "dark":
        return True
    ap = str(st.session_state.get("_active_page", ""))
    return ("个股分析" in ap) or ("多股票对比" in ap)


def apply_theme() -> None:
    """注入全局润色 CSS（暗色/亮色）并设置 Plotly 模板。"""
    if _theme_is_dark():
        st.markdown(_DARK_CSS, unsafe_allow_html=True)
        inject_plotly_dark()
    else:
        st.markdown(_LIGHT_CSS, unsafe_allow_html=True)


def get_current_mode() -> str:
    return st.session_state.get("theme_mode", "light")


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
