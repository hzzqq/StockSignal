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
import logging
from modules.ui_kit import inject_kit_css
logger = logging.getLogger(__name__)
import os
import streamlit as st
import streamlit.config as _config
_ICON_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets')
ICON_SVG = os.path.join(_ICON_DIR, 'icon.svg')
UP = '#ff4d4f'
DOWN = '#00d486'
HOLD = '#ffa502'
SF_BG = '#0f0f23'
SF_CARD = '#1a1a2e'
SF_CARD_DARK = '#15152a'
SF_ACC1 = '#667eea'
SF_ACC2 = '#764ba2'
SF_TXT = '#e2e8f0'
SF_TXT2 = '#94a3b8'
SF_BORDER = '#2d2d44'
SF_GRID = '#23233c'
FONT_SCALE = {'small': '0.95rem', 'medium': '1.03rem', 'large': '1.12rem', 'xlarge': '1.22rem', 'xxlarge': '1.32rem'}
FONT_DEFAULT = 'medium'

def inject_font_size() -> None:
    """按 session_state 的 font_size 注入全局字号（覆盖 html/body/.stApp）。

    同时作用于 html，使所有 rem 子元素（表格/指标卡等）随档位整体缩放，
    真正实现「整个项目字体可调」。仅注入 CSS，不改任何功能逻辑。
    用户未单独设置时回落到 FONT_DEFAULT（1.03rem，已比旧默认更大）。
    """
    _key = st.session_state.get('font_size', FONT_DEFAULT)
    _rem = FONT_SCALE.get(_key, FONT_SCALE[FONT_DEFAULT])
    st.markdown(f'<style>\n        html, body, .stApp {{ font-size: {_rem} !important; }}\n        </style>', unsafe_allow_html=True)
_DARK_CSS = '\n<!-- Google Fonts: Fira Code (数据) + Inter (UI) -->\n<link rel="preconnect" href="https://fonts.googleapis.com">\n<link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">\n\n<style>\n/* ===== 星辰决策仪表盘 · 组件类（供页面按需使用） ===== */\n:root{\n  --bg:#0f0f23; --card:#1a1a2e; --buy:#ff4d4f; --sell:#00d486;\n  --hold:#ffa502; --acc1:#667eea; --acc2:#764ba2;\n  --txt:#e2e8f0; --txt2:#94a3b8; --border:#2d2d44; --grid:#23233c;\n}\n\n.sf-header{display:flex;align-items:center;justify-content:space-between;\n  flex-wrap:wrap;gap:10px;margin-bottom:20px;padding:16px 20px;\n  background:linear-gradient(90deg,#1a1a2e,#241b3a);\n  border:1px solid var(--border);border-radius:16px;\n  box-shadow:0 0 0 1px rgba(102,126,234,.08),0 8px 24px rgba(0,0,0,.35)}\n.sf-brand{font-size:15px;color:var(--txt2);letter-spacing:1px}\n.sf-brand b{color:var(--acc1)}\n\n.sf-card{background:var(--card);border:1px solid var(--border);\n  border-radius:16px;padding:20px;margin-top:18px;\n  box-shadow:0 0 0 1px rgba(102,126,234,.06),0 6px 20px rgba(0,0,0,.28)}\n.sf-card h2{font-size:16px;margin:0 0 14px;display:flex;align-items:center;gap:8px;\n  padding-bottom:10px;border-bottom:1px solid var(--border);color:var(--txt)}\n.sf-card h2::before{content:"";width:4px;height:16px;\n  background:linear-gradient(180deg,var(--acc1),var(--acc2));border-radius:3px}\n\n.sf-one-line{font-size:14.5px;font-weight:700;color:var(--buy);\n  background:rgba(255,77,79,.08);border-left:3px solid var(--buy);\n  padding:10px 14px;border-radius:8px;margin-bottom:14px;line-height:1.7}\n.sf-one-line.hold{color:var(--hold);border-left-color:var(--hold);\n  background:rgba(255,165,2,.08)}\n\n.sf-table{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:4px}\n.sf-table th,.sf-table td{padding:9px 8px;text-align:center;border-bottom:1px solid var(--border)}\n.sf-table th{color:var(--txt2);font-weight:600;font-size:12px;background:#15152a}\n.sf-table tr:hover td{background:rgba(102,126,234,.05)}\n.sf-table td.l{text-align:left}\n.sf-up{color:var(--buy);font-weight:700}\n.sf-down{color:var(--sell);font-weight:700}\n\n.sf-tag{display:inline-block;font-size:11px;padding:2px 9px;border-radius:14px;\n  font-weight:600;margin:2px}\n.sf-tag.win{background:rgba(0,212,134,.16);color:#00d4aa;border:1px solid rgba(0,212,134,.4)}\n.sf-tag.mid{background:rgba(255,165,2,.16);color:var(--hold);border:1px solid rgba(255,165,2,.4)}\n.sf-tag.weak{background:rgba(255,77,79,.14);color:var(--buy);border:1px solid rgba(255,77,79,.4)}\n.sf-tag.neu{background:rgba(148,163,184,.12);color:var(--txt2);border:1px solid var(--border)}\n\n.sf-vs{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:8px}\n@media(max-width:780px){.sf-vs{grid-template-columns:1fr}}\n.sf-vsbox{background:#15152a;border:1px solid var(--border);border-radius:12px;padding:14px}\n.sf-vsbox h3{font-size:14px;margin-bottom:8px;color:var(--txt)}\n.sf-verdict{font-size:13px;font-weight:700;margin:8px 0;padding:6px 10px;border-radius:8px}\n.sf-verdict.b{background:rgba(0,212,134,.12);color:#00d4aa}\n.sf-verdict.o{background:rgba(255,165,2,.12);color:var(--hold)}\n.sf-vsbox ul{margin:6px 0 0 16px;font-size:12.5px;color:var(--txt2)}\n.sf-vsbox ul li{margin:3px 0}\n\n.sf-alert{border-radius:12px;padding:12px 14px;margin-top:14px;font-size:13px;line-height:1.7}\n.sf-alert.risk{background:rgba(255,77,79,.10);border:1px solid rgba(255,77,79,.45);color:#ffb3bb}\n.sf-alert.cat{background:rgba(0,212,134,.10);border:1px solid rgba(0,212,134,.45);color:#9af0dd}\n.sf-alert b{display:block;margin-bottom:4px;font-size:13.5px}\n\n.sf-note{font-size:12.5px;color:var(--txt2);margin-top:10px;line-height:1.7}\n.sf-disclaimer{margin-top:14px;font-size:11.5px;color:#6b7280;\n  border-top:1px dashed var(--border);padding-top:10px}\n\n/* ===== 全局基调：深空黑 + 紫蓝极光 ===== */\n/* P0: html/body/.stApp bg + color 全 !important, 防 Streamlit 内联 样式压过 (spinner / 加载态不再闪老 light 底) */\nhtml, body {\n    background-color: #0f0f23 !important;\n}\nhtml, body, .stApp {\n    color: #e2e8f0 !important;\n    font-family: \'Inter\', -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;\n}\n.stApp {\n    background-color: #0f0f23 !important;\n    background-image:\n        radial-gradient(ellipse 80% 50% at 12% -8%, rgba(102, 126, 234, 0.10) 0%, transparent 55%),\n        radial-gradient(ellipse 60% 45% at 88% 5%, rgba(118, 75, 162, 0.08) 0%, transparent 50%),\n        radial-gradient(ellipse 90% 60% at 50% 108%, rgba(102, 126, 234, 0.10) 0%, transparent 55%),\n        url("data:image/svg+xml,%3Csvg viewBox=\'0 0 256 256\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cfilter id=\'n\'%3E%3CfeTurbulence type=\'fractalNoise\' baseFrequency=\'0.85\' numOctaves=\'4\' stitchTiles=\'stitch\'/%3E%3C/filter%3E%3Crect width=\'100%25\' height=\'100%25\' filter=\'url(%23n)\' opacity=\'0.03\'/%3E%3C/svg%3E");\n}\n\n/* ===== 隐藏 Streamlit 默认菜单/工具栏，但保留顶部 header 容器\n        以便侧边栏展开/折叠按钮始终可见；header 本身设为透明不占视觉空间 ===== */\n#MainMenu { display: none !important; }\nfooter { display: none !important; }\n[data-testid="stToolbar"] { padding: 0 !important; margin: 0 !important; min-height: 0 !important; background: transparent !important; border: none !important; box-shadow: none !important; }\n[data-testid="stDecoration"] { display: none !important; }\nheader[data-testid="stHeader"] {\n    background: transparent !important;\n    border: none !important;\n    box-shadow: none !important;\n    padding: 0 !important;\n    margin: 0 !important;\n    height: auto !important;\n    min-height: 0 !important;\n}\n\n/* 轻量化区块标题：1:1 复刻参考文档 .card h2（16px + 渐变竖条，去掉沉重标题框）。\n   作用于 st.header(h2) 与 st.subheader(h3)；页面主标题 st.title(h1) 保持醒目。 */\nh2[data-testid="stHeader"],\nh3[data-testid="stHeader"] {\n    font-size: 1rem !important;\n    font-weight: 600 !important;\n    line-height: 1.4 !important;\n    margin: 16px 0 10px !important;\n    padding: 0 0 0 12px !important;\n    position: relative !important;\n    display: flex !important;\n    align-items: center !important;\n    gap: 8px !important;\n    border: none !important;\n    background: transparent !important;\n    box-shadow: none !important;\n}\nh2[data-testid="stHeader"]::before,\nh3[data-testid="stHeader"]::before {\n    content: "" !important;\n    position: absolute !important;\n    left: 0 !important;\n    top: 50% !important;\n    transform: translateY(-50%) !important;\n    width: 4px !important;\n    height: 16px !important;\n    border-radius: 3px !important;\n    background: linear-gradient(180deg, #667eea, #764ba2) !important;\n    flex-shrink: 0 !important;\n}\n\n/* 折叠态的展开按钮：固定到左上角，避免被透明 header 压成 0×0 看不见/点不到 */\nbutton[data-testid="stExpandSidebarButton"] {\n    position: fixed !important;\n    top: 10px !important;\n    left: 10px !important;\n    z-index: 99999 !important;\n    display: flex !important;\n    align-items: center !important;\n    justify-content: center !important;\n    width: 38px !important;\n    height: 38px !important;\n    padding: 0 !important;\n    background: rgba(30, 30, 60, 0.92) !important;\n    border: 1px solid rgba(255, 255, 255, 0.25) !important;\n    border-radius: 8px !important;\n    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.45) !important;\n    cursor: pointer !important;\n    visibility: visible !important;\n    opacity: 1 !important;\n}\nbutton[data-testid="stExpandSidebarButton"]:hover {\n    background: rgba(102, 126, 234, 0.95) !important;\n    border-color: rgba(255, 255, 255, 0.55) !important;\n}\n\n/* ===== 侧边栏：深空黑玻璃拟态 ===== */\nsection[data-testid="stSidebar"] {\n    background: linear-gradient(180deg, rgba(21, 21, 46, 0.98) 0%, rgba(15, 15, 35, 0.99) 100%);\n    border-right: 1px solid rgba(255, 255, 255, 0.06);\n    backdrop-filter: blur(12px);\n}\nsection[data-testid="stSidebar"] .stMarkdown h1,\nsection[data-testid="stSidebar"] .stMarkdown h2,\nsection[data-testid="stSidebar"] .stMarkdown h3 {\n    color: #667eea;\n    border-bottom: 1px solid rgba(102, 126, 234, 0.20);\n    padding-bottom: 6px;\n    font-family: \'Inter\', sans-serif;\n}\nsection[data-testid="stSidebar"] a,\nsection[data-testid="stSidebar"] span,\nsection[data-testid="stSidebar"] p,\nsection[data-testid="stSidebar"] label,\nsection[data-testid="stSidebar"] div:not([class*="plotly"]):not([class*="canvas"]) {\n    color: #94a3b8 !important;\n}\nsection[data-testid="stSidebar"] a[aria-current="page"],\nsection[data-testid="stSidebar"] [aria-selected="true"] {\n    color: #667eea !important;\n    font-weight: 700 !important;\n}\nsection[data-testid="stSidebar"] a:hover {\n    color: #a5b4fc !important;\n    background-color: rgba(102, 126, 234, 0.08) !important;\n    border-radius: 6px !important;\n}\n\n/* ===== 标题：紫蓝渐变 ===== */\nh1, h2, h3 { font-weight: 700; letter-spacing: 0.3px; font-family: \'Inter\', sans-serif; }\n.stTitle h1 {\n    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);\n    -webkit-background-clip: text;\n    background-clip: text;\n    -webkit-text-fill-color: transparent;\n}\nh2 { border-left: 4px solid #667eea; padding-left: 10px; margin-top: 18px; position: relative; }\nh2::after { content:\'\'; position:absolute; left:-4px; top:0; bottom:0; width:4px; background:linear-gradient(180deg,#667eea,#764ba2); border-radius:2px; }\nh3 { border-left: 3px solid rgba(102, 126, 234, 0.55); padding-left: 8px; }\n\n/* ===== 指标卡：深空黑玻璃 + 紫蓝边光 ===== */\n.stMetric {\n    background: linear-gradient(145deg, rgba(26, 26, 46, 0.85), rgba(21, 21, 42, 0.92));\n    border: 1px solid rgba(102, 126, 234, 0.12);\n    border-left: 3px solid #667eea;\n    border-radius: 16px; padding: 16px 20px;\n    box-shadow: 0 8px 24px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.05), 0 0 20px rgba(102, 126, 234, 0.05);\n    backdrop-filter: blur(8px); transition: transform 0.2s ease, box-shadow 0.2s ease;\n}\n.stMetric:hover { transform: translateY(-1px); box-shadow: 0 12px 28px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.07), 0 0 28px rgba(102, 126, 234, 0.10); }\n.stMetric label, .stMetric .metric-label { color: #94a3b8 !important; font-size: 0.8rem; font-family:\'Inter\',sans-serif; font-weight: 500; }\n.stMetric [data-testid="stMetricValue"] {\n    color: #e2e8f0 !important;\n    font-family:\'Fira Code\',monospace !important;\n    font-weight: 600 !important;\n    font-size: 1.35rem !important;\n    text-shadow: 0 0 12px rgba(102, 126, 234, 0.15);\n}\n.stMetric [data-testid="stMetricDelta"] { color: #94a3b8 !important; }\n\n/* ===== 按钮 ===== */\n.stButton button {\n    border-radius: 10px;\n    border: 1px solid rgba(102, 126, 234, 0.35) !important;\n    background: linear-gradient(180deg, rgba(26, 26, 46, 0.9), rgba(15, 15, 35, 0.95)) !important;\n    color: #e2e8f0 !important;\n    font-weight: 600;\n    font-family: \'Inter\', sans-serif;\n    transition: all 0.2s cubic-bezier(0.4,0,0.2,1);\n    box-shadow: 0 2px 8px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.05);\n    position: relative;\n    overflow: hidden;\n}\n.stButton button::before { content:\'\'; position:absolute; top:0; left:-100%; width:100%; height:100%; background:linear-gradient(90deg,transparent,rgba(102,126,234,0.08),transparent); transition:left 0.5s ease; }\n.stButton button:hover::before { left:100%; }\n.stButton button:hover { transform: translateY(-1.5px); box-shadow: 0 6px 20px rgba(102,126,234,0.18), 0 0 20px rgba(102,126,234,0.08); border-color: rgba(102,126,234,0.6) !important; color: #FFFFFF !important; }\n.stApp .stButton button[kind="primary"] {\n    background: linear-gradient(180deg, #D4A02A, #B8860B) !important;\n    border: none !important;\n    color: #111827 !important;\n    font-weight: 700;\n    box-shadow: 0 3px 12px rgba(184, 134, 11, 0.4);\n}\n.stApp .stButton button[kind="primary"]:hover { box-shadow: 0 6px 24px rgba(184, 134, 11, 0.55) !important; }\n/* form submit primary button */\n.stApp [data-testid="stFormSubmitButton"] button,\n.stApp button[data-testid="stFormSubmitButton"] {\n    background: linear-gradient(180deg, #D4A02A, #B8860B) !important;\n    border: none !important;\n    color: #111827 !important;\n    font-weight: 700 !important;\n    box-shadow: 0 3px 12px rgba(184, 134, 11, 0.4) !important;\n}\n.stApp [data-testid="stFormSubmitButton"] button:hover,\n.stApp button[data-testid="stFormSubmitButton"]:hover {\n    box-shadow: 0 6px 24px rgba(184, 134, 11, 0.55) !important;\n}\n\n/* ===== Tabs ===== */\n.stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid rgba(255,255,255,0.08); }\n.stTabs [data-baseweb="tab"] {\n    border-radius: 8px 8px 0 0;\n    background: rgba(255,255,255,0.03);\n    border: 1px solid transparent;\n    border-bottom: none;\n    color: #94a3b8;\n    font-family: \'Inter\', sans-serif;\n    font-weight: 500;\n    transition: all 0.2s ease;\n    padding: 8px 16px;\n}\n.stTabs [data-baseweb="tab"]:hover { background: rgba(102, 126, 234, 0.08); color: #a5b4fc; }\n.stTabs [data-baseweb="tab"][aria-selected="true"] { background: rgba(102, 126, 234, 0.12) !important; color: #667eea !important; border-bottom: 2.5px solid #667eea !important; font-weight: 600; }\n\n/* ===== 表格 ===== */\n.stDataFrame, [data-testid="stTable"] { background: rgba(21, 21, 42, 0.75) !important; border: 1px solid rgba(102, 126, 234, 0.08) !important; border-radius: 10px !important; overflow: hidden !important; }\n.stDataFrame thead th, [data-testid="stTable"] thead th {\n    background: linear-gradient(180deg, #16162c, #101020) !important;\n    color: #667eea !important;\n    font-weight: 600 !important;\n    font-family: \'Inter\', sans-serif !important;\n    font-size: 0.85rem !important;\n    border-bottom: 1px solid rgba(102, 126, 234, 0.25) !important;\n}\n.stDataFrame tbody td, [data-testid="stTable"] tbody td {\n    color: #e2e8f0 !important;\n    background: transparent !important;\n    font-family: \'Fira Code\', monospace;\n    font-size: 0.82rem;\n    border-bottom: 1px solid rgba(255,255,255,0.05);\n}\n.stDataFrame tr:hover td, [data-testid="stTable"] tr:hover td { background: rgba(102, 126, 234, 0.06) !important; }\n\n/* ===== 输入框 / 下拉框 / 日期 / 数字 / 文本域：深空黑 + 高对比文字 ===== */\n/* 兼容 Streamlit 1.58 多种 DOM 层级：外层组件、data-baseweb 容器、内层 input/select */\n.stTextInput,\n.stTextArea,\n.stSelectbox,\n.stDateInput,\n.stNumberInput,\n.stMultiSelect,\n[data-testid="stTextInput"],\n[data-testid="stTextArea"],\n[data-testid="stSelectbox"],\n[data-testid="stDateInput"],\n[data-testid="stNumberInput"],\n[data-testid="stMultiSelect"] {\n    color: #e2e8f0 !important;\n}\n\n.stTextInput div[data-baseweb="input"],\n.stTextInput div[data-baseweb="base-input"],\n.stTextArea div[data-baseweb="textarea"],\n.stTextArea div[data-baseweb="base-input"],\n.stSelectbox div[data-baseweb="select"],\n.stSelectbox div[data-baseweb="base-input"],\n.stDateInput div[data-baseweb="date-input"],\n.stDateInput div[data-baseweb="base-input"],\n.stNumberInput div[data-baseweb="input"],\n.stNumberInput div[data-baseweb="base-input"],\n.stMultiSelect div[data-baseweb="select"],\n.stMultiSelect div[data-baseweb="base-input"],\n[data-testid="stTextInput"] div[data-baseweb="input"],\n[data-testid="stTextInput"] div[data-baseweb="base-input"],\n[data-testid="stTextInputRootElement"] div[data-baseweb="base-input"],\n[data-testid="stTextArea"] div[data-baseweb="textarea"],\n[data-testid="stTextArea"] div[data-baseweb="base-input"],\n[data-testid="stSelectbox"] div[data-baseweb="select"],\n[data-testid="stSelectbox"] div[data-baseweb="base-input"],\n[data-testid="stDateInput"] div[data-baseweb="date-input"],\n[data-testid="stDateInput"] div[data-baseweb="base-input"],\n[data-testid="stNumberInput"] div[data-baseweb="input"],\n[data-testid="stNumberInput"] div[data-baseweb="base-input"],\n[data-testid="stMultiSelect"] div[data-baseweb="select"],\n[data-testid="stMultiSelect"] div[data-baseweb="base-input"] {\n    background: rgba(21, 21, 42, 0.85) !important;\n    border: 1px solid rgba(255, 255, 255, 0.12) !important;\n    border-radius: 8px !important;\n}\n\n/* Streamlit 1.58 selectbox 真实可视框在 data-baseweb="select" 的直接 div 子元素中，\n   外层 select 容器已被染黑，但内层 div 仍被 baseweb 类设为白色背景 */\n.stSelectbox div[data-baseweb="select"] > div,\n[data-testid="stSelectbox"] div[data-baseweb="select"] > div,\n.stMultiSelect div[data-baseweb="select"] > div,\n[data-testid="stMultiSelect"] div[data-baseweb="select"] > div {\n    background: rgba(21, 21, 42, 0.85) !important;\n}\n\n\n.stTextInput input,\n.stTextArea textarea,\n.stSelectbox [role="combobox"],\n.stDateInput input,\n.stNumberInput input,\n.stMultiSelect input,\n[data-testid="stTextInput"] input,\n[data-testid="stTextArea"] textarea,\n[data-testid="stSelectbox"] [role="combobox"],\n[data-testid="stDateInput"] input,\n[data-testid="stNumberInput"] input,\n[data-testid="stMultiSelect"] input,\n[data-baseweb="input"] input,\n[data-baseweb="textarea"] textarea,\n[data-baseweb="select"] [role="combobox"],\n[data-baseweb="date-input"] input {\n    color: #f1f5f9 !important;\n    -webkit-text-fill-color: #f1f5f9 !important;\n    background: transparent !important;\n    caret-color: #667eea !important;\n}\n\n/* #264 下拉框（selectbox / multiselect）当前选中文字加粗，提升可读性 */\n.stSelectbox [role="combobox"],\n[data-testid="stSelectbox"] [role="combobox"],\n.stMultiSelect [role="combobox"],\n[data-testid="stMultiSelect"] [role="combobox"],\n.stSelectbox ul li,\n.stMultiSelect ul li {\n    font-weight: 600 !important;\n}\n\n/* placeholder 暗色提示 */\n.stTextInput input::placeholder,\n.stTextArea textarea::placeholder,\n.stDateInput input::placeholder,\n.stNumberInput input::placeholder,\n.stSelectbox [role="combobox"] [aria-placeholder] {\n    color: #94a3b8 !important;\n    opacity: 1 !important;\n}\n\n/* focus 状态：紫蓝光环 */\n.stTextInput div[data-baseweb="input"]:focus-within,\n.stTextInput div[data-baseweb="base-input"]:focus-within,\n.stTextArea div[data-baseweb="textarea"]:focus-within,\n.stTextArea div[data-baseweb="base-input"]:focus-within,\n.stSelectbox div[data-baseweb="select"]:focus-within,\n.stSelectbox div[data-baseweb="base-input"]:focus-within,\n.stDateInput div[data-baseweb="date-input"]:focus-within,\n.stDateInput div[data-baseweb="base-input"]:focus-within,\n.stNumberInput div[data-baseweb="input"]:focus-within,\n.stNumberInput div[data-baseweb="base-input"]:focus-within,\n.stMultiSelect div[data-baseweb="select"]:focus-within,\n.stMultiSelect div[data-baseweb="base-input"]:focus-within,\n[data-testid="stTextInput"] div[data-baseweb="input"]:focus-within,\n[data-testid="stTextInput"] div[data-baseweb="base-input"]:focus-within,\n[data-testid="stTextInputRootElement"] div[data-baseweb="base-input"]:focus-within,\n[data-testid="stTextArea"] div[data-baseweb="textarea"]:focus-within,\n[data-testid="stTextArea"] div[data-baseweb="base-input"]:focus-within,\n[data-testid="stSelectbox"] div[data-baseweb="select"]:focus-within,\n[data-testid="stSelectbox"] div[data-baseweb="base-input"]:focus-within,\n[data-testid="stDateInput"] div[data-baseweb="date-input"]:focus-within,\n[data-testid="stDateInput"] div[data-baseweb="base-input"]:focus-within,\n[data-testid="stNumberInput"] div[data-baseweb="input"]:focus-within,\n[data-testid="stNumberInput"] div[data-baseweb="base-input"]:focus-within,\n[data-testid="stMultiSelect"] div[data-baseweb="select"]:focus-within,\n[data-testid="stMultiSelect"] div[data-baseweb="base-input"]:focus-within {\n    border-color: #667eea !important;\n    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.20), 0 0 20px rgba(102, 126, 234, 0.08) !important;\n}\n\n/* 下拉菜单面板 */\ndiv[data-baseweb="select"] ul,\nul[data-baseweb="menu"] {\n    background: #1a1a2e !important;\n    border: 1px solid rgba(255, 255, 255, 0.12) !important;\n    border-radius: 8px !important;\n}\nul[data-baseweb="menu"] li,\nli[data-baseweb="menu-item"] {\n    color: #e2e8f0 !important;\n    background: #1a1a2e !important;\n}\nul[data-baseweb="menu"] li:hover,\nli[data-baseweb="menu-item"]:hover,\nli[data-baseweb="menu-item"][aria-selected="true"] {\n    background: rgba(102, 126, 234, 0.18) !important;\n    color: #FFFFFF !important;\n}\n\n/* Radio / Checkbox */\n.stRadio [role="radiogroup"],\n.stCheckbox [role="group"],\n.stRadio [data-baseweb="radio-group"],\n.stCheckbox [data-baseweb="checkbox-group"] {\n    color: #e2e8f0 !important;\n}\n.stRadio [role="radio"],\n.stCheckbox [role="checkbox"],\n[data-baseweb="radio"] [role="radio"],\n[data-baseweb="checkbox"] [role="checkbox"] {\n    background: rgba(21, 21, 42, 0.85) !important;\n    border: 2px solid rgba(255, 255, 255, 0.15) !important;\n}\n.stRadio [role="radio"]:checked,\n.stRadio [role="radio"][aria-checked="true"],\n.stCheckbox [role="checkbox"]:checked,\n.stCheckbox [role="checkbox"][aria-checked="true"] {\n    background: #667eea !important;\n    border-color: #667eea !important;\n}\n.stRadio [role="radio"]:checked + span,\n.stCheckbox [role="checkbox"]:checked + span,\n.stRadio label span,\n.stCheckbox label span {\n    color: #e2e8f0 !important;\n}\n\n/* disabled 状态 */\n.stTextInput div[data-baseweb="input"][disabled],\n.stSelectbox div[data-baseweb="select"][disabled],\n.stDateInput div[data-baseweb="date-input"][disabled] {\n    background: rgba(21, 21, 42, 0.45) !important;\n    border-color: rgba(255, 255, 255, 0.06) !important;\n    opacity: 0.6 !important;\n}\n\n/* ===== 标签文字 ===== */\nlabel, [data-baseweb="label"], .stTextInput label, .stTextArea label, .stSelectbox label,\n.stDateInput label, .stNumberInput label, .stCheckbox label, .stRadio label, .stFileUploader label {\n    color: #94a3b8 !important;\n    font-weight: 500 !important;\n}\n.stCaption, .caption, small, [data-testid="stCaption"] { color: #64748b !important; }\n\n/* ===== Checkbox / Radio（Streamlit 1.58 DOM 实测）=====\n   radio 圆框  : label[data-baseweb="radio"]    > div:first-child  （baseweb class st-g4 浅色底 / st-c1 选中金）\n   checkbox 方格: label[data-baseweb="checkbox"] > span:first-child （baseweb class st-dp 浅色底 / 选中金）\n   选中态由内部隐藏 <input>:checked 决定，用 :has() 覆盖 baseweb 默认浅色背景。\n   注意：不要使用 :not(#fake_id) 提权技巧——部分浏览器下该写法整条选择器不生效。 */\nlabel[data-baseweb="radio"],\nlabel[data-baseweb="checkbox"] { color: #e2e8f0 !important; }\nlabel[data-baseweb="radio"] > div:first-child,\nlabel[data-baseweb="checkbox"] > span:first-child {\n    background: rgba(21, 21, 42, 0.85) !important;\n    border: 1px solid rgba(255, 255, 255, 0.25) !important;\n    border-radius: 50% !important;\n}\nlabel[data-baseweb="checkbox"] > span:first-child { border-radius: 4px !important; }\nlabel[data-baseweb="radio"]:has(input:checked) > div:first-child,\nlabel[data-baseweb="checkbox"]:has(input:checked) > span:first-child {\n    background: #667eea !important;\n    border-color: #667eea !important;\n}\nlabel[data-baseweb="checkbox"]:has(input:checked) > span:first-child svg,\nlabel[data-baseweb="checkbox"]:has(input:checked) > span:first-child path {\n    fill: #e2e8f0 !important;\n    stroke: #e2e8f0 !important;\n}\nlabel[data-baseweb="radio"] > div:last-child,\nlabel[data-baseweb="checkbox"] > div:last-child { color: #e2e8f0 !important; }\n\n/* ===== 表单容器 ===== */\n[data-testid="stForm"], .stForm, form {\n    background: rgba(26, 26, 46, 0.7) !important;\n    border: 1px solid rgba(255, 255, 255, 0.08) !important;\n    border-radius: 12px !important;\n    padding: 18px 22px !important;\n    box-shadow: 0 8px 24px rgba(0,0,0,0.35) !important;\n}\n\n/* ===== 滚动条 ===== */\n::-webkit-scrollbar { width: 8px; height: 8px; }\n::-webkit-scrollbar-track { background: rgba(15, 15, 35, 0.9); border-radius: 10px; }\n::-webkit-scrollbar-thumb { background: linear-gradient(180deg, #1a1a2e, #2d2d44); border-radius: 10px; border: 1px solid rgba(255,255,255,0.05); }\n::-webkit-scrollbar-thumb:hover { background: linear-gradient(180deg, #2d2d44, #3a3a5c); }\n\n/* ===== 提示框 ===== */\n.stAlert { border-radius: 12px; border-left: 4px solid; font-family: \'Inter\', sans-serif; }\n.stAlert[data-baseweb="notification"][kind="success"] { border-left-color: #00d486; background: rgba(0, 212, 134, 0.10); color: #e2e8f0 !important; }\n.stAlert[data-baseweb="notification"][kind="error"] { border-left-color: #ff4d4f; background: rgba(255, 77, 79, 0.10); color: #e2e8f0 !important; }\n.stAlert[data-baseweb="notification"][kind="warning"] { border-left-color: #ffa502; background: rgba(255, 165, 2, 0.10); color: #e2e8f0 !important; }\n.stAlert[data-baseweb="notification"][kind="info"] { border-left-color: #667eea; background: rgba(102, 126, 234, 0.10); color: #e2e8f0 !important; }\n\nhr { border: none; border-top: 1px solid rgba(255,255,255,0.08); margin: 20px 0; }\n\n/* ===== Slider ===== */\n[data-testid="stSlider"] [role="slider"] { background: linear-gradient(90deg, #667eea, #764ba2) !important; }\n[data-testid="stSlider"] [role="slider"]:hover { box-shadow: 0 0 12px rgba(102, 126, 234, 0.35); }\n[data-testid="stSlider"] [role="slider"]::-webkit-slider-runnable-track { background: rgba(255,255,255,0.1) !important; border-radius: 4px !important; }\n\n/* ===== Plotly 图表容器 ===== */\n.js-plotly-plot .plotly .modebar { background: rgba(21, 21, 42, 0.92) !important; border-radius: 8px; backdrop-filter: blur(8px); border: 1px solid rgba(255,255,255,0.08); }\n.js-plotly-plot .xtick text, .js-plotly-plot .ytick text, .js-plotly-plot .axislabel,\n.js-plotly-plot .xaxislayer-above text, .js-plotly-plot .yaxislayer-above text { fill: #94a3b8 !important; color: #94a3b8 !important; }\n.js-plotly-plot .legend text { fill: #94a3b8 !important; font-size: 0.8rem !important; }\n.js-plotly-plot .gtitle, .js-plotly-plot .g-title { fill: #e2e8f0 !important; color: #e2e8f0 !important; font-weight: 600 !important; }\n\n/* ===== Expander ===== */\n.streamlit-expanderHeader { background: rgba(26, 26, 46, 0.6); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; font-family: \'Inter\', sans-serif; color: #e2e8f0 !important; }\n.streamlit-expanderHeader:hover { border-color: rgba(102, 126, 234, 0.4); background: rgba(102, 126, 234, 0.06); }\n\n/* ===== Spinner / 链接 / 代码 ===== */\n.stSpinner > div { color: #667eea !important; border-top-color: #667eea !important; }\na { color: #a5b4fc !important; }\na:hover { color: #667eea !important; }\n.stCode, code, pre { background: rgba(21, 21, 42, 0.9) !important; color: #e2e8f0 !important; border: 1px solid rgba(255,255,255,0.08) !important; border-radius: 8px !important; font-family: \'Fira Code\', monospace !important; }\n.stMarkdown, .stMarkdown p, .stMarkdown li, .stMarkdown span { color: #e2e8f0 !important; }\n.stText, [data-testid="stText"] { color: #e2e8f0 !important; }\n\n/* ===== 暗夜模式下原生控件配色（修复输入框白底 / 选择框白底 / 文字看不清） ===== */\n[data-testid="stTextInput"] input,\n[data-testid="stTextArea"] textarea,\n[data-testid="stNumberInput"] input {\n  background-color: #15152a !important;\n  color: #e2e8f0 !important;\n  border: 1px solid #2d2d44 !important;\n}\n[data-testid="stTextInput"] input::placeholder,\n[data-testid="stTextArea"] textarea::placeholder {\n  color: #94a3b8 !important;\n}\n/* selectbox 控件本体（非下拉） */\n[data-testid="stSelectbox"] [data-baseweb="select"] { background: transparent !important; }\n[data-testid="stSelectbox"] [data-baseweb="select"] > div {\n  background-color: #1a1a2e !important;\n  color: #f1f5f9 !important;\n  border: 1.5px solid #4b5563 !important;\n  border-radius: 8px !important;\n}\n[data-testid="stSelectbox"] [data-baseweb="select"] > div:hover {\n  border-color: #6366f1 !important;\n}\n[data-testid="stSelectbox"] [data-baseweb="select"] > div:focus-within {\n  border-color: #6366f1 !important;\n}\n[data-testid="stSelectbox"] input { color: #f1f5f9 !important; caret-color: #e2e8f0 !important; }\n[data-testid="stSelectbox"] input::placeholder {\n  color: #94a3b8 !important;\n  opacity: 1 !important;\n}\n[data-testid="stSelectbox"] svg { fill: #94a3b8 !important; stroke: #94a3b8 !important; }\n/* selectbox 下拉列表 */\nul[data-baseweb="listbox"],\nul[role="listbox"] {\n  background-color: #15152a !important;\n  border: 1px solid #2d2d44 !important;\n}\nli[data-baseweb="option"],\nli[role="option"] {\n  color: #e2e8f0 !important;\n  background-color: transparent !important;\n}\nli[data-baseweb="option"]:hover,\nli[role="option"]:hover,\nli[data-baseweb="option"][aria-selected="true"],\nli[role="option"][aria-selected="true"] {\n  background-color: #241b3a !important;\n  color: #ffffff !important;\n}\n/* ===== Popover 弹层（星辰 AI）暗色适配 =====\n   目标：覆盖 baseweb 默认白色浮层，强制深空黑底 + 高对比文字 */\n[data-testid="stPopoverBody"],\n[data-testid="stPopoverBody"] > div,\n[data-testid="stPopover"] [role="dialog"],\n[data-testid="stPopover"] [role="dialog"] > div,\n[data-testid="stPopover"] > div,\n[data-testid="stPopover"] [data-testid="stVerticalBlock"],\n[data-testid="stPopover"] [data-testid="stVerticalBlockBorderWrapper"] {\n  background: #1a1a2e !important;\n  color: #e2e8f0 !important;\n  border-color: #2d2d44 !important;\n}\n[data-testid="stPopoverBody"] p,\n[data-testid="stPopoverBody"] span,\n[data-testid="stPopoverBody"] div,\n[data-testid="stPopoverBody"] h4,\n[data-testid="stPopoverBody"] h5,\n[data-testid="stPopover"] p,\n[data-testid="stPopover"] span,\n[data-testid="stPopover"] h4,\n[data-testid="stPopover"] h5,\n[data-testid="stPopover"] .stMarkdown,\n[data-testid="stPopover"] .stMarkdown p,\n[data-testid="stPopover"] .stMarkdown span,\n[data-testid="stPopover"] .stMarkdown div {\n  color: #e2e8f0 !important;\n}\n[data-testid="stPopover"] .stMarkdown,\n[data-testid="stPopoverBody"] .stMarkdown {\n  background: transparent !important;\n}\n/* Popover 内文本域 */\n[data-testid="stPopoverBody"] textarea,\n[data-testid="stPopover"] textarea {\n  background: #15152a !important;\n  color: #e2e8f0 !important;\n  border: 1px solid #2d2d44 !important;\n}\n[data-testid="stPopoverBody"] textarea::placeholder,\n[data-testid="stPopover"] textarea::placeholder {\n  color: #64748b !important;\n}\n/* Popover 内按钮 */\n[data-testid="stPopoverBody"] button,\n[data-testid="stPopover"] button {\n  color: #111827 !important;\n  font-weight: 600 !important;\n}\n/* Popover 触发按钮（暗夜下默认白底，需强制深色渐变底+白字）\n   放在 popover 通用按钮规则之后，保证触发按钮自身文字为白色 */\n[data-testid="stPopover"] > button,\nbutton[data-testid="stPopoverButton"] {\n  background: linear-gradient(135deg, #667eea, #764ba2) !important;\n  color: #ffffff !important;\n  border: none !important;\n  font-weight: 600 !important;\n}\n[data-testid="stPopover"] > button:hover,\nbutton[data-testid="stPopoverButton"]:hover {\n  background: linear-gradient(135deg, #764ba2, #667eea) !important;\n  box-shadow: 0 4px 14px rgba(102, 126, 234, .35) !important;\n}\n/* radio / checkbox 文字与选中态 */\n[data-testid="stRadio"] label,\n[data-testid="stCheckbox"] label { color: #e2e8f0 !important; }\n[data-testid="stRadio"] > div,\n[data-testid="stRadio"] { background: transparent !important; }\n[data-baseweb="radio"] { background: #1a1a2e !important; border-color: #2d2d44 !important; }\n[data-baseweb="radio"][aria-checked="true"] { background: #667eea !important; border-color: #667eea !important; }\n/* slider 轨道与滑块 */\n[data-testid="stSlider"] { color: #e2e8f0 !important; }\n[data-baseweb="slider"] { background: transparent !important; }\n[data-baseweb="slider"] [data-testid="track"] { background: #2d2d44 !important; }\n[data-baseweb="slider"] [data-testid="thumb"] { background: #667eea !important; border-color: #667eea !important; }\n\n/* ★ Batch8 #276：输入框默认边框 = 焦点高亮色（默认即显色，无需点击） */\n.stTextInput > div[data-baseweb="input"],\n.stTextArea > div[data-baseweb="textarea"],\n.stNumberInput > div[data-baseweb="input"],\n.stSelectbox > div[data-baseweb="select"],\n.stDateInput > div[data-baseweb="date-input"],\n.stMultiSelect > div[data-baseweb="select"],\n[data-testid="stTextInput"] > div[data-baseweb="input"],\n[data-testid="stTextArea"] > div[data-baseweb="textarea"],\n[data-testid="stNumberInput"] > div[data-baseweb="input"],\n[data-testid="stSelectbox"] > div[data-baseweb="select"],\n[data-testid="stDateInput"] > div[data-baseweb="date-input"],\n[data-testid="stMultiSelect"] > div[data-baseweb="select"],\n[data-testid="stTextInput"] input,\n[data-testid="stTextArea"] textarea,\n[data-testid="stNumberInput"] input,\n[class*="stTextInput"] input,\n[class*="stTextArea"] textarea {\n  border-color: #667eea !important;\n}\n\n/* st.toast 暗夜可读性：深底 + 浅字，避免默认黑底白字在暗色页里刺眼/不可辨 */\n[data-testid="stToast"] {\n  background: #1a1a2e !important;\n  border: 1px solid #2d2d44 !important;\n  color: #e2e8f0 !important;\n}\n[data-testid="stToast"] [data-testid="stToastBody"],\n[data-testid="stToast"] [data-baseweb="toast"] { color: #e2e8f0 !important; }\n[data-testid="stToast"] svg { fill: #e2e8f0 !important; }\n\n/* ===== v10 深色玻璃终端增强层（T-176，additive-only）===== */\n:root{\n  --ss-glass-bg:linear-gradient(145deg,rgba(30,30,58,.60),rgba(22,22,44,.74));\n  --ss-up:#ff4d4f; --ss-down:#00d486; /* A股语义色显式钉住：红涨绿跌不可反转 */\n}\n.stApp{\n  background-image:\n    radial-gradient(ellipse 70% 45% at 15% -10%, rgba(102,126,234,.14) 0%, transparent 55%),\n    radial-gradient(ellipse 55% 40% at 85% 8%, rgba(34,211,238,.07) 0%, transparent 52%),\n    radial-gradient(ellipse 60% 45% at 80% 100%, rgba(244,114,182,.05) 0%, transparent 55%),\n    radial-gradient(ellipse 90% 55% at 40% 110%, rgba(102,126,234,.10) 0%, transparent 55%),\n    linear-gradient(rgba(255,255,255,.012) 1px, transparent 1px),\n    linear-gradient(90deg, rgba(255,255,255,.012) 1px, transparent 1px) !important;\n  background-size:auto,auto,auto,auto,44px 44px,44px 44px !important;\n}\n.stApp::before{content:"";position:fixed;top:0;left:0;right:0;height:2px;z-index:99990;\n  background:linear-gradient(90deg,transparent,rgba(102,126,234,.75),rgba(118,75,162,.7),rgba(34,211,238,.45),transparent);\n  opacity:.7;pointer-events:none}\n.stMetric,.sf-card,.sf-cta-card,[data-testid="stForm"]{\n  background:var(--ss-glass-bg) !important;\n  border:1px solid rgba(255,255,255,.09) !important;\n  backdrop-filter:blur(14px) saturate(1.3) !important;\n  -webkit-backdrop-filter:blur(14px) saturate(1.3) !important;\n  box-shadow:0 0 0 1px rgba(102,126,234,.06),0 12px 32px rgba(0,0,0,.42),inset 0 1px 0 rgba(255,255,255,.07) !important;\n}\n.stMetric:hover{box-shadow:0 0 0 1px rgba(102,126,234,.14),0 16px 40px rgba(0,0,0,.5),0 0 28px rgba(102,126,234,.10),inset 0 1px 0 rgba(255,255,255,.09) !important}\n.stMetric [data-testid="stMetricValue"]{\n  background:linear-gradient(180deg,#ffffff 15%,#c7d2fe 100%);\n  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;\n  font-variant-numeric:tabular-nums !important;\n  text-shadow:none !important;\n}\n.stMetric,.sf-card{animation:ss-fade-in .25s ease both}\n@keyframes ss-fade-in{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}\n::selection{background:rgba(102,126,234,.40);color:#fff}\n@media (prefers-reduced-motion: reduce){*{animation:none!important;transition:none!important}}\n</style>\n'
_LIGHT_CSS = '\n<!-- Google Fonts: Fira Code (数据) + Inter (UI) -->\n<link rel="preconnect" href="https://fonts.googleapis.com">\n<link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">\n\n<style>\nhtml, body, .stApp {\n    color: #374151 !important;\n    font-family: \'Inter\', -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif !important;\n}\n.stApp {\n    background-color: #F5F7FA !important;\n    background-image:\n        radial-gradient(ellipse 70% 40% at 10% -5%, rgba(184,134,11,0.035) 0%, transparent 55%),\n        radial-gradient(ellipse 80% 50% at 90% 105%, rgba(59,130,246,0.02) 0%, transparent 50%);\n}\n/* ===== 隐藏 Streamlit 默认菜单/工具栏，但保留顶部 header 容器\n        以便侧边栏展开/折叠按钮始终可见；header 本身设为透明不占视觉空间 ===== */\n#MainMenu { display: none !important; }\nfooter { display: none !important; }\n[data-testid="stToolbar"] { padding: 0 !important; margin: 0 !important; min-height: 0 !important; background: transparent !important; border: none !important; box-shadow: none !important; }\n[data-testid="stDecoration"] { display: none !important; }\nheader[data-testid="stHeader"] {\n    background: transparent !important;\n    border: none !important;\n    box-shadow: none !important;\n    padding: 0 !important;\n    margin: 0 !important;\n    height: auto !important;\n    min-height: 0 !important;\n}\n\n/* 轻量化区块标题：1:1 复刻参考文档 .card h2（16px + 渐变竖条，去掉沉重标题框）。\n   作用于 st.header(h2) 与 st.subheader(h3)；页面主标题 st.title(h1) 保持醒目。 */\nh2[data-testid="stHeader"],\nh3[data-testid="stHeader"] {\n    font-size: 1rem !important;\n    font-weight: 600 !important;\n    line-height: 1.4 !important;\n    margin: 16px 0 10px !important;\n    padding: 0 0 0 12px !important;\n    position: relative !important;\n    display: flex !important;\n    align-items: center !important;\n    gap: 8px !important;\n    border: none !important;\n    background: transparent !important;\n    box-shadow: none !important;\n}\nh2[data-testid="stHeader"]::before,\nh3[data-testid="stHeader"]::before {\n    content: "" !important;\n    position: absolute !important;\n    left: 0 !important;\n    top: 50% !important;\n    transform: translateY(-50%) !important;\n    width: 4px !important;\n    height: 16px !important;\n    border-radius: 3px !important;\n    background: linear-gradient(180deg, #667eea, #764ba2) !important;\n    flex-shrink: 0 !important;\n}\n\n/* 折叠态的展开按钮：固定到左上角，避免被透明 header 压成 0×0 看不见/点不到 */\nbutton[data-testid="stExpandSidebarButton"] {\n    position: fixed !important;\n    top: 10px !important;\n    left: 10px !important;\n    z-index: 99999 !important;\n    display: flex !important;\n    align-items: center !important;\n    justify-content: center !important;\n    width: 38px !important;\n    height: 38px !important;\n    padding: 0 !important;\n    background: #FFFFFF !important;\n    border: 1px solid #C9CCD1 !important;\n    border-radius: 8px !important;\n    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.18) !important;\n    cursor: pointer !important;\n    visibility: visible !important;\n    opacity: 1 !important;\n}\nbutton[data-testid="stExpandSidebarButton"]:hover {\n    background: #EAECEF !important;\n    border-color: #3B82F6 !important;\n}\n\nsection[data-testid="stSidebar"] {\n    background: #EEF0F2 !important;\n    border-right: 1px solid #D5D7DB !important;\n    color: #374151 !important;\n}\nsection[data-testid="stSidebar"] .stMarkdown h1,\nsection[data-testid="stSidebar"] .stMarkdown h2,\nsection[data-testid="stSidebar"] .stMarkdown h3 {\n    color: #92400E !important;\n    border-bottom: 1px solid rgba(184,134,11,0.18) !important;\n    padding-bottom: 6px;\n    font-family: \'Inter\', sans-serif !important;\n}\nsection[data-testid="stSidebar"] a,\nsection[data-testid="stSidebar"] [class*="link"],\nsection[data-testid="stSidebar"] span,\nsection[data-testid="stSidebar"] p,\nsection[data-testid="stSidebar"] label,\nsection[data-testid="stSidebar"] div:not([class*="plotly"]):not([class*="canvas"]) {\n    color: #374151 !important;\n}\nsection[data-testid="stSidebar"] a[aria-current="page"],\nsection[data-testid="stSidebar"] [aria-selected="true"] {\n    color: #92400E !important;\n    font-weight: 700 !important;\n}\nsection[data-testid="stSidebar"] a:hover {\n    color: #78350F !important;\n    background-color: rgba(184,134,11,0.08) !important;\n    border-radius: 6px !important;\n}\n\nh1, h2, h3, h4, h5, h6 {\n    color: #111827 !important;\n    font-weight: 700 !important;\n    letter-spacing: 0.3px !important;\n    font-family: \'Inter\', sans-serif !important;\n}\nh2 {\n    border-left: 4px solid #B8860B !important;\n    padding-left: 10px !important;\n    margin-top: 18px !important;\n}\nh3 {\n    border-left: 3px solid rgba(184,134,11,0.5) !important;\n    padding-left: 8px !important;\n}\n\n.stMetric {\n    background: #FFFFFF !important;\n    border: 1px solid #E5E7EB !important;\n    border-left: 3px solid #B8860B !important;\n    border-radius: 12px !important;\n    padding: 16px 20px !important;\n    box-shadow: 0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.02) !important;\n    transition: transform 0.2s ease, box-shadow 0.2s ease !important;\n}\n.stMetric:hover {\n    transform: translateY(-1px) !important;\n    box-shadow: 0 4px 12px rgba(0,0,0,0.08) !important;\n    border-color: #D1D5DB !important;\n}\n.stMetric label,\n.stMetric .metric-label {\n    color: #6B7280 !important;\n    font-size: 0.8rem !important;\n    font-family: \'Inter\', sans-serif !important;\n}\n.stMetric [data-testid="stMetricValue"] {\n    color: #111827 !important;\n    font-weight: 650 !important;\n    font-family: \'Fira Code\', monospace !important;\n}\n\n.stButton button {\n    border-radius: 8px !important;\n    border: 1px solid #D1D5DB !important;\n    font-weight: 600 !important;\n    font-family: \'Inter\', sans-serif !important;\n    color: #374151 !important;\n    background: linear-gradient(180deg, #FFFFFF, #F9FAFB) !important;\n    box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;\n    transition: all 0.15s ease !important;\n}\n.stButton button:hover {\n    border-color: #B8860B !important;\n    background: linear-gradient(180deg, #FFFBF0, #FEF3C7) !important;\n    box-shadow: 0 3px 10px rgba(184,134,11,0.12) !important;\n    transform: translateY(-1px) !important;\n    color: #111827 !important;\n}\n.stButton button[kind="primary"] {\n    background: linear-gradient(180deg, #D4A02A, #B8860B) !important;\n    border: none !important;\n    color: #FFFFFF !important;\n    font-weight: 700 !important;\n    box-shadow: 0 3px 10px rgba(184,134,11,0.25) !important;\n}\n.stButton button[kind="primary"]:hover {\n    background: linear-gradient(180deg, #E0AA2E, #C9941F) !important;\n    box-shadow: 0 5px 16px rgba(184,134,11,0.35) !important;\n}\n\n.stTabs [data-baseweb="tab-list"] {\n    gap: 6px !important;\n    border-bottom: 2px solid #E5E7EB !important;\n    background: transparent !important;\n}\n.stTabs [data-baseweb="tab"] {\n    border-radius: 8px 8px 0 0 !important;\n    background: #F8FAFC !important;\n    border: 1px solid #E5E7EB !important;\n    border-bottom: none !important;\n    color: #4B5563 !important;\n    font-family: \'Inter\', sans-serif !important;\n    font-weight: 500 !important;\n    transition: all 0.15s ease !important;\n    padding: 8px 18px !important;\n}\n.stTabs [data-baseweb="tab"]:hover {\n    background: #FFFBF0 !important;\n    color: #92400E !important;\n}\n.stTabs [data-baseweb="tab"][aria-selected="true"] {\n    background: #FFFFFF !important;\n    color: #B8860B !important;\n    font-weight: 700 !important;\n    border-bottom: 2.5px solid #B8860B !important;\n    box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;\n}\n\n.stDataFrame,\n[data-testid="stTable"] {\n    background: #FFFFFF !important;\n    border: 1px solid #E5E7EB !important;\n    border-radius: 10px !important;\n    overflow: hidden !important;\n}\n.stDataFrame thead th,\n[data-testid="stTable"] thead th {\n    background: linear-gradient(180deg, #F8FAFC, #F1F3F5) !important;\n    color: #111827 !important;\n    font-weight: 600 !important;\n    font-family: \'Inter\', sans-serif !important;\n    font-size: 0.83rem !important;\n    border-bottom: 2px solid #E5E7EB !important;\n}\n.stDataFrame tbody td,\n[data-testid="stTable"] tbody td {\n    color: #374151 !important;\n    background: #FFFFFF !important;\n    border-bottom: 1px solid #F3F4F6 !important;\n    font-family: \'Fira Code\', monospace !important;\n    font-size: 0.82rem !important;\n}\n.stDataFrame tr:hover td,\n[data-testid="stTable"] tr:hover td {\n    background: #FFFBF0 !important;\n}\n\n.stTextInput div[data-baseweb="input"],\n.stTextInput div[data-baseweb="base-input"],\n.stTextArea div[data-baseweb="textarea"],\n.stTextArea div[data-baseweb="base-input"],\n.stSelectbox div[data-baseweb="select"],\n.stSelectbox div[data-baseweb="base-input"],\n.stDateInput div[data-baseweb="date-input"],\n.stDateInput div[data-baseweb="base-input"],\n.stNumberInput div[data-baseweb="input"],\n.stNumberInput div[data-baseweb="base-input"],\n.stMultiSelect div[data-baseweb="select"],\n.stMultiSelect div[data-baseweb="base-input"],\n[data-testid="stTextInput"] div[data-baseweb="input"],\n[data-testid="stTextInput"] div[data-baseweb="base-input"],\n[data-testid="stTextInputRootElement"] div[data-baseweb="base-input"],\n[data-testid="stTextArea"] div[data-baseweb="textarea"],\n[data-testid="stTextArea"] div[data-baseweb="base-input"],\n[data-testid="stSelectbox"] div[data-baseweb="select"],\n[data-testid="stSelectbox"] div[data-baseweb="base-input"],\n[data-testid="stDateInput"] div[data-baseweb="date-input"],\n[data-testid="stDateInput"] div[data-baseweb="base-input"],\n[data-testid="stNumberInput"] div[data-baseweb="input"],\n[data-testid="stNumberInput"] div[data-baseweb="base-input"],\n[data-testid="stMultiSelect"] div[data-baseweb="select"],\n[data-testid="stMultiSelect"] div[data-baseweb="base-input"] {\n    background: #FFFFFF !important;\n    border: 1.5px solid #9ca3af !important;\n    border-radius: 8px !important;\n}\n.stSelectbox div[data-baseweb="select"]:hover,\n.stSelectbox div[data-baseweb="base-input"]:hover,\n.stMultiSelect div[data-baseweb="select"]:hover,\n.stMultiSelect div[data-baseweb="base-input"]:hover,\n[data-testid="stSelectbox"] div[data-baseweb="select"]:hover,\n[data-testid="stSelectbox"] div[data-baseweb="base-input"]:hover,\n[data-testid="stMultiSelect"] div[data-baseweb="select"]:hover,\n[data-testid="stMultiSelect"] div[data-baseweb="base-input"]:hover {\n    border-color: #6366F1 !important;\n}\n.stTextInput input,\n.stTextArea textarea,\n.stSelectbox [role="combobox"],\n.stDateInput input,\n.stNumberInput input {\n    color: #1f2937 !important;\n    -webkit-text-fill-color: #1f2937 !important;\n    background: transparent !important;\n}\n.stTextInput > div[data-baseweb="input"]:focus-within,\n.stTextArea > div[data-baseweb="textarea"]:focus-within,\n.stSelectbox > div[data-baseweb="select"]:focus-within,\n.stDateInput > div[data-baseweb="date-input"]:focus-within,\n.stNumberInput > div[data-baseweb="input"]:focus-within {\n    border-color: #6366f1 !important;\n    box-shadow: 0 0 0 3px rgba(99,102,241,0.15) !important;\n}\n/* 白天模式：selectbox 占位符 / 选中值更清晰 */\n.stSelectbox [role="combobox"] [aria-placeholder],\n[data-testid="stSelectbox"] [role="combobox"] [aria-placeholder] {\n    color: #4b5563 !important;\n    opacity: 1 !important;\n}\n[data-testid="stSelectbox"] input::placeholder {\n    color: #4b5563 !important;\n    opacity: 1 !important;\n}\n\n/* 白天模式：数字输入框 +/- 步进按钮改为浅色（默认为深色，视觉突兀） */\n.stNumberInput button,\n[data-testid="stNumberInput"] button,\n[data-testid="stNumberInputStepUp"],\n[data-testid="stNumberInputStepDown"] {\n    background: #F3F4F6 !important;\n    color: #374151 !important;\n    border: none !important;\n    border-left: 1px solid #E5E7EB !important;\n}\n.stNumberInput button:hover,\n[data-testid="stNumberInput"] button:hover,\n[data-testid="stNumberInputStepUp"]:hover,\n[data-testid="stNumberInputStepDown"]:hover {\n    background: #E5E7EB !important;\n    color: #111827 !important;\n}\n.stNumberInput button svg,\n[data-testid="stNumberInput"] button svg,\n[data-testid="stNumberInputStepUp"] svg,\n[data-testid="stNumberInputStepDown"] svg {\n    fill: #374151 !important;\n    color: #374151 !important;\n}\n\nlabel,\n[data-baseweb="label"],\n[data-baseweb="form-label"],\n.stTextInput label,\n.stTextArea label,\n.stSelectbox label,\n.stDateInput label,\n.stNumberInput label,\n.stCheckbox label,\n.stRadio label,\n.stFileUploader label {\n    color: #4B5563 !important;\n    font-weight: 500 !important;\n    font-size: 0.875rem !important;\n    font-family: \'Inter\', sans-serif !important;\n}\n.stCaption,\n.caption,\nsmall,\n[data-testid="stCaption"] {\n    color: #6B7280 !important;\n    font-size: 0.82rem !important;\n}\n\n/* Radio / Checkbox（Streamlit 1.58 DOM 实测）*/\nlabel[data-baseweb="radio"] > div:first-child,\nlabel[data-baseweb="checkbox"] > span:first-child {\n    background: #FFFFFF !important;\n    border: 1px solid #D1D5DB !important;\n    border-radius: 50% !important;\n}\nlabel[data-baseweb="checkbox"] > span:first-child { border-radius: 4px !important; }\nlabel[data-baseweb="radio"]:has(input:checked) > div:first-child,\nlabel[data-baseweb="checkbox"]:has(input:checked) > span:first-child {\n    background: #B8860B !important;\n    border-color: #996515 !important;\n}\nlabel[data-baseweb="checkbox"]:has(input:checked) > span:first-child svg,\nlabel[data-baseweb="checkbox"]:has(input:checked) > span:first-child path {\n    fill: #FFFFFF !important;\n    stroke: #FFFFFF !important;\n}\n\n[data-testid="stForm"],\n.stForm,\nform {\n    background: #FFFFFF !important;\n    border: 1px solid #E5E7EB !important;\n    border-radius: 12px !important;\n    padding: 18px 22px !important;\n    box-shadow: 0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.02) !important;\n}\n\n.streamlit-expanderHeader {\n    background: #FFFFFF !important;\n    border: 1px solid #E5E7EB !important;\n    border-radius: 10px !important;\n    color: #374151 !important;\n    font-family: \'Inter\', sans-serif !important;\n    font-weight: 500 !important;\n}\n.streamlit-expanderHeader:hover {\n    border-color: #B8860B !important;\n    background: #FFFBF0 !important;\n}\n\n.stAlert {\n    background: #FFFFFF !important;\n    border: 1px solid #E5E7EB !important;\n    border-radius: 10px !important;\n    color: #111827 !important;\n    font-family: \'Inter\', sans-serif !important;\n}\n.stAlert[data-baseweb="notification"][kind="success"] {\n    border-left-color: #0ECB81 !important;\n    background: rgba(14,203,129,0.06) !important;\n}\n.stAlert[data-baseweb="notification"][kind="error"] {\n    border-left-color: #EF4444 !important;\n    background: rgba(239,68,68,0.04) !important;\n}\n.stAlert[data-baseweb="notification"][kind="warning"] {\n    border-left-color: #F59E0B !important;\n    background: rgba(245,158,11,0.05) !important;\n}\n.stAlert[data-baseweb="notification"][kind="info"] {\n    border-left-color: #3B82F6 !important;\n    background: rgba(59,130,246,0.04) !important;\n}\n.stInfo {\n    background: rgba(255,255,255,0.95) !important;\n    border: 1px solid #E5E7EB !important;\n    border-radius: 10px !important;\n    color: #374151 !important;\n}\n\n.js-plotly-plot,\n.js-plotly-plot .js-plotly-plot,\ndiv[data-testid="stPlotlyChart"] {\n    background: #FFFFFF !important;\n    border: 1px solid #E5E7EB !important;\n    border-radius: 10px !important;\n    box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;\n    padding: 4px !important;\n}\n.js-plotly-plot .plotly .modebar {\n    background: rgba(255,255,255,0.92) !important;\n    border: 1px solid #E5E7EB !important;\n    border-radius: 6px !important;\n    box-shadow: 0 1px 4px rgba(0,0,0,0.06) !important;\n}\n.js-plotly-plot .xtick text,\n.js-plotly-plot .ytick text,\n.js-plotly-plot .axislabel,\n.js-plotly-plot .xaxislayer-above text,\n.js-plotly-plot .yaxislayer-above text {\n    fill: #6B7280 !important;\n    color: #6B7280 !important;\n    font-size: 0.78rem !important;\n}\n.js-plotly-plot .legend text {\n    fill: #4B5563 !important;\n    font-size: 0.8rem !important;\n}\n.js-plotly-plot .gtitle,\n.js-plotly-plot .g-title {\n    fill: #111827 !important;\n    color: #111827 !important;\n    font-weight: 600 !important;\n}\n.js-plotly-plot .gtitle text {\n    fill: #4B5563 !important;\n}\n\n::-webkit-scrollbar { width: 8px !important; height: 8px !important; }\n::-webkit-scrollbar-track {\n    background: #EEF0F2 !important;\n    border-radius: 6px !important;\n}\n::-webkit-scrollbar-thumb {\n    background: linear-gradient(180deg, #C4C8CE, #A8ADB6) !important;\n    border-radius: 6px !important;\n    border: 1px solid #D5D7DB !important;\n}\n::-webkit-scrollbar-thumb:hover {\n    background: linear-gradient(180deg, #A8ADB6, #9094A0) !important;\n}\n\n[data-testid="stSlider"] [role="slider"] {\n    background: linear-gradient(90deg, #B8860B, #996515) !important;\n    border: 2px solid #996515 !important;\n}\n[data-testid="stSlider"] [role="slider"]:hover {\n    box-shadow: 0 0 8px rgba(184,134,11,0.25) !important;\n}\n[data-testid="stSlider"] [role="slider"]::-webkit-slider-runnable-track {\n    background: #E5E7EB !important;\n    border-radius: 4px !important;\n}\n\nhr {\n    border: none !important;\n    border-top: 1px solid #E5E7EB !important;\n    margin: 20px 0 !important;\n}\n.stSpinner > div {\n    color: #B8860B !important;\n    border-top-color: #B8860B !important;\n}\na { color: #2563EB !important; }\na:hover { color: #1D4ED8 !important; }\n.stCode,\ncode,\npre {\n    background: #F8FAFC !important;\n    color: #111827 !important;\n    border: 1px solid #E5E7EB !important;\n    border-radius: 8px !important;\n    font-family: \'Fira Code\', monospace !important;\n}\n.stMarkdown { color: #374151 !important; }\n.stMarkdown p,\n.stMarkdown li,\n.stMarkdown span {\n    color: #374151 !important;\n}\n.stText,\n[data-testid="stText"] {\n    color: #374151 !important;\n}\n/* ===== Popover 弹层（星辰 AI）亮色适配 ===== */\n[data-testid="stPopover"],\n[data-testid="stPopover"] > div,\n[data-testid="stPopover"] [data-testid="stVerticalBlock"],\n[data-testid="stPopover"] [data-testid="stVerticalBlockBorderWrapper"] {\n  background: #ffffff !important;\n  color: #111827 !important;\n  border-color: #e5e7eb !important;\n}\n[data-testid="stPopover"] p,\n[data-testid="stPopover"] span,\n[data-testid="stPopover"] div,\n[data-testid="stPopover"] h4,\n[data-testid="stPopover"] h5,\n[data-testid="stPopover"] .stMarkdown,\n[data-testid="stPopover"] .stMarkdown p,\n[data-testid="stPopover"] .stMarkdown span,\n[data-testid="stPopover"] .stMarkdown div {\n  color: #111827 !important;\n}\n[data-testid="stPopover"] .stMarkdown {\n  background: transparent !important;\n}\n[data-testid="stPopover"] textarea {\n  background: #ffffff !important;\n  color: #111827 !important;\n  border: 1px solid #d1d5db !important;\n}\n[data-testid="stPopover"] textarea::placeholder {\n  color: #9ca3af !important;\n}\n[data-testid="stPopover"] button {\n  color: #ffffff !important;\n  font-weight: 600 !important;\n}\n\n/* ===== 亮色模式 Popover 触发按钮（右上角星辰 AI）适配 =====\n   避免白天模式下触发按钮仍使用暗色渐变，导致红圈内黑底看不清。 */\nbutton[data-testid="stPopoverButton"],\n[data-testid="stPopover"] > button {\n  background: linear-gradient(135deg, #667eea, #764ba2) !important;\n  color: #ffffff !important;\n  border: none !important;\n  font-weight: 600 !important;\n}\nbutton[data-testid="stPopoverButton"]:hover,\n[data-testid="stPopover"] > button:hover {\n  background: linear-gradient(135deg, #764ba2, #667eea) !important;\n  color: #ffffff !important;\n}\n\n/* ===== MultiSelect 已选标签（均线选择器等）亮色适配 =====\n   Streamlit 1.58+ baseweb 标签默认背景/文字在白天主题下对比不足，\n   统一改成白底浅灰边 + 深色文字，hover 高亮。 */\n.stMultiSelect [data-baseweb="tag"],\n[data-testid="stMultiSelect"] [data-baseweb="tag"] {\n  background: #F3F4F6 !important;\n  color: #111827 !important;\n  border: 1px solid #D1D5DB !important;\n  border-radius: 6px !important;\n}\n.stMultiSelect [data-baseweb="tag"] span,\n[data-testid="stMultiSelect"] [data-baseweb="tag"] span {\n  color: #111827 !important;\n}\n.stMultiSelect [data-baseweb="tag"] svg,\n[data-testid="stMultiSelect"] [data-baseweb="tag"] svg,\n.stMultiSelect [data-baseweb="tag"] path,\n[data-testid="stMultiSelect"] [data-baseweb="tag"] path {\n  fill: #6B7280 !important;\n}\n.stMultiSelect [data-baseweb="tag"]:hover,\n[data-testid="stMultiSelect"] [data-baseweb="tag"]:hover {\n  background: #E5E7EB !important;\n  border-color: #9CA3AF !important;\n}\n\n/* ★ Batch8 #276：输入框默认边框 = 焦点高亮色（默认即显色，无需点击） */\n.stTextInput > div[data-baseweb="input"],\n.stTextArea > div[data-baseweb="textarea"],\n.stNumberInput > div[data-baseweb="input"],\n.stSelectbox > div[data-baseweb="select"],\n.stDateInput > div[data-baseweb="date-input"],\n.stMultiSelect > div[data-baseweb="select"],\n[data-testid="stTextInput"] > div[data-baseweb="input"],\n[data-testid="stTextArea"] > div[data-baseweb="textarea"],\n[data-testid="stNumberInput"] > div[data-baseweb="input"],\n[data-testid="stSelectbox"] > div[data-baseweb="select"],\n[data-testid="stDateInput"] > div[data-baseweb="date-input"],\n[data-testid="stMultiSelect"] > div[data-baseweb="select"],\n[data-testid="stTextInput"] input,\n[data-testid="stTextArea"] textarea,\n[data-testid="stNumberInput"] input,\n[class*="stTextInput"] input,\n[class*="stTextArea"] textarea {\n  border-color: #6366f1 !important;\n}\n\n/* ===== v10 精致 SaaS 增强层（T-176，additive-only）===== */\n:root{\n  --ss-saas-shadow:0 1px 2px rgba(16,24,40,.04),0 8px 24px rgba(16,24,40,.05);\n  --ss-saas-shadow-hover:0 2px 4px rgba(16,24,40,.05),0 16px 36px rgba(79,70,229,.10);\n  --ss-up:#ff4d4f; --ss-down:#00d486; /* A股语义色显式钉住：红涨绿跌不可反转 */\n}\n.stApp{\n  background-color:#FAFBFD !important;\n  background-image:\n    radial-gradient(ellipse 60% 38% at 12% -6%, rgba(99,102,241,.05) 0%, transparent 55%),\n    radial-gradient(ellipse 55% 35% at 88% 108%, rgba(184,134,11,.03) 0%, transparent 50%) !important;\n}\n.stMetric,.sf-card,.sf-cta-card,[data-testid="stForm"]{\n  border-radius:16px !important;\n  border:1px solid #E9ECF2 !important;\n  box-shadow:var(--ss-saas-shadow) !important;\n}\n.stMetric:hover{box-shadow:var(--ss-saas-shadow-hover) !important;border-color:#D6DBE8 !important}\n.stMetric [data-testid="stMetricValue"]{\n  font-variant-numeric:tabular-nums !important;\n  letter-spacing:-.01em !important;\n}\n.stMetric,.sf-card{animation:ss-fade-in .22s ease both}\n@keyframes ss-fade-in{from{opacity:0;transform:translateY(3px)}to{opacity:1;transform:none}}\n::selection{background:rgba(99,102,241,.22)}\n@media (prefers-reduced-motion: reduce){*{animation:none!important;transition:none!important}}\n</style>\n'
PLOTLY_DARK = {'paper_bgcolor': 'rgba(0,0,0,0)', 'plot_bgcolor': 'rgba(0,0,0,0)', 'font': {'color': '#94a3b8', 'family': "system-ui, -apple-system, 'PingFang SC', sans-serif"}, 'xaxis': {'gridcolor': '#23233c', 'zerolinecolor': '#2d2d44', 'linecolor': '#2d2d44', 'tickcolor': '#2d2d44', 'title': {'font': {'color': '#94a3b8'}}}, 'yaxis': {'gridcolor': '#23233c', 'zerolinecolor': '#2d2d44', 'linecolor': '#2d2d44', 'tickcolor': '#2d2d44', 'title': {'font': {'color': '#94a3b8'}}}, 'legend': {'bgcolor': 'rgba(0,0,0,0)', 'font': {'color': '#94a3b8'}}}

def inject_plotly_dark() -> None:
    """若页面用到 Plotly（st.plotly_chart / K线），调用一次本函数
    让 Plotly 默认走暗色，根除白底白框。"""
    try:
        import plotly.io as pio
        import plotly.graph_objects as go
        if 'starfield_dark' not in pio.templates:
            pio.templates['starfield_dark'] = go.layout.Template(layout=PLOTLY_DARK)
        pio.templates.default = 'starfield_dark'
    except Exception as e:
        logger.warning(f"[ui_theme] 处理异常: {e}")
        pass

def _theme_is_dark() -> bool:
    """当前是否应呈现暗色：仅由用户全局主题 theme_mode 控制（默认亮色）。

    不再按页面强制暗色——之前「个股分析 / 多股对比」访问后所有页面被污染成暗色，
    用户投诉「切功能模块黑白切换」。现在所有页面统一跟随右上角主题开关，
    白天 / 暗夜两种模式都可手动切换，离开页面不残留。
    """
    return st.session_state.get('theme_mode', 'light') == 'dark'
STREAMLIT_THEME_LIGHT = {'base': 'light', 'primaryColor': '#4f46e5', 'backgroundColor': '#ffffff', 'secondaryBackgroundColor': '#f4f6fb', 'textColor': '#1e293b', 'font': 'sans serif'}
STREAMLIT_THEME_DARK = {'base': 'dark', 'primaryColor': '#667eea', 'backgroundColor': '#0f0f23', 'secondaryBackgroundColor': '#1a1a2e', 'textColor': '#e2e8f0', 'font': 'sans serif'}

def apply_page_config(page_title: str, page_icon: str=None, layout: str='wide') -> None:
    """统一页面配置：根据全局 theme_mode 同步 Streamlit 原生主题。

    必须在每个页面最顶部（任何其它 st.xxx 之前）调用。等价于 st.set_page_config，
    但通过 streamlit.config.set_option 设置 theme.* 选项，让 DataFrame / 下拉框 /
    聊天输入框等原生组件跟随暗夜 / 白天模式。

    当前环境（Streamlit 1.59.2）的 st.set_page_config 还不支持 theme 关键字参数，
    因此采用 config.set_option 方式在页面渲染前把原生主题写入配置。
    theme_mode 在首次加载（未切换过）时回落到 light，符合「默认白天」约定；
    用户一旦在右上角切换暗夜，session_state 中 theme_mode=dark，切页后原生主题即跟随变暗。
    """
    try:
        from modules.session import _restore_prefs_from_query_params, FONT_DEFAULT
        _p = _restore_prefs_from_query_params()
        if _p:
            st.session_state.setdefault('theme_mode', _p.get('theme_mode', 'light'))
            st.session_state.setdefault('font_size', _p.get('font_size', FONT_DEFAULT))
    except Exception as e:
        logger.warning(f"[ui_theme] 处理异常: {e}")
        pass
    theme = STREAMLIT_THEME_DARK if _theme_is_dark() else STREAMLIT_THEME_LIGHT
    try:
        for key, value in theme.items():
            _config.set_option(f'theme.{key}', value)
    except Exception as e:
        logger.warning(f"[ui_theme] 处理异常: {e}")
        pass
    try:
        _icon = page_icon or (ICON_SVG if os.path.exists(ICON_SVG) else '📈')
        st.set_page_config(page_title=page_title, page_icon=_icon, layout=layout, initial_sidebar_state='expanded')
    except Exception as e:
        logger.warning(f"[ui_theme] 处理异常: {e}")
        pass
    # ★ P0 主题前置注入（紧跟 set_page_config 之后，作为本页首条 st.markdown）：
    # 写入一段最小 CSS 把 html/body 染成主题色，解决「页面导航时 spinner 闪现老 light 底」。
    # 整段 CSS 后续会再被 apply_theme() 的 _DARK_CSS / _LIGHT_CSS 完整覆盖，此处只是抢在
    # spinner 出现之前先把外层底色定下来。
    try:
        if _theme_is_dark():
            _bg_pre, _fg_pre = "#0f0f23", "#e2e8f0"
        else:
            _bg_pre, _fg_pre = "#F5F7FA", "#1A2332"
        st.markdown(
            f'<style>html,body{{background:{_bg_pre}!important;color:{_fg_pre}!important}}</style>',
            unsafe_allow_html=True,
        )
    except Exception as e:
        logger.warning(f"[ui_theme] pre-inject 处理异常: {e}")
        pass
    st.markdown('<style>[data-testid="stSidebarNav"],[data-testid="stSidebarNavItems"],[data-testid="stSidebarNavSeparator"],[data-testid="stSidebarNavLink"]{display:none!important;}</style>', unsafe_allow_html=True)
    # ★ 根因修复（首页「首屏无星辰样式、刷新后才生效」）：
    # 此前完整主题仅由 require_auth→init_session_state 内部间接注入，注入点晚于 set_page_config，
    # 叠加 Streamlit 原生 theme（config.set_option）首屏需一次 rerun 才生效，导致首帧走默认样式。
    # 此处把 apply_theme() 紧耦合在 set_page_config 之后第一时间注入，所有页面（含首页入口）首帧即得完整样式。
    # apply_theme 幂等，重复调用（如 init_session_state 内再调一次）无害。
    try:
        apply_theme()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[ui_theme] apply_theme 处理异常: {e}")


def apply_theme() -> None:
    """注入全局润色 CSS（暗色/亮色）并设置 Plotly 模板。"""
    # 消除 Streamlit 默认顶部内边距（非嵌入态默认 paddingTop=6rem/8rem）。
    # 本项目已隐藏 stHeader/MainMenu/Toolbar（透明零高），若不缩减容器上边距，
    # 每块页顶部会留下约 96px 的固定空白。统一收敛到 1.2rem，保留少量呼吸感。
    # 用 !important 覆盖 Streamlit 写在该容器上的 inline style（未标 !important，可被覆盖）。
    _sync_style_mode()
    style_switcher()
    try:
        st.markdown(
            '<style>'
            '.block-container,[data-testid="stMainBlockContainer"],.stMainBlockContainer'
            '{padding-top:1.2rem!important}'
            '</style>',
            unsafe_allow_html=True,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[ui_theme] 顶部边距修正注入异常: {e}")
    if _theme_is_dark():
        st.markdown(_DARK_CSS, unsafe_allow_html=True)
        inject_plotly_dark()
    else:
        st.markdown(_LIGHT_CSS, unsafe_allow_html=True)
    inject_font_size()
    from modules.button_colors import inject_button_css
    inject_button_css(mode='dark' if _theme_is_dark() else 'light')
    from modules.dark_text_fix import inject_dark_text_css
    inject_dark_text_css(mode='dark' if _theme_is_dark() else 'light')
    from modules.scroll_nav import inject_scroll_nav
    inject_scroll_nav(show_bottom=True, bottom_marker='stChatInput', dark=_theme_is_dark())
    inject_kit_css()
    inject_style_css()
    st.markdown('<style>[data-testid="stSidebarNav"],[data-testid="stSidebarNavItems"],[data-testid="stSidebarNavSeparator"],[data-testid="stSidebarNavLink"]{display:none!important;}</style>', unsafe_allow_html=True)

def get_current_mode() -> str:
    return st.session_state.get('theme_mode', 'light')

_DASHBOARD_SF_CSS_CACHE: dict = {}


def dashboard_sf_css() -> str:
    """个股分析「决策仪表盘」的 .sf-* 组件样式（白天 / 暗夜双主题自适应）。

    通过 CSS 变量切换：暗夜用深空黑底 + 紫蓝渐变，白天用白卡 + 浅边框高对比。
    页面只需注入一次，:root 变量会覆盖全局主题里的同名变量，保证配色一致。

    性能（R88）：CSS 仅随主题(dark/light)变化，故按主题缓存整段字符串，
    避免每个页面重跑都重建这段等长 CSS。
    """
    from modules.ui_kit import _TOKEN_CSS  # T-145 A3：ui_kit 设计令牌单一来源
    dark = _theme_is_dark()
    _cached = _DASHBOARD_SF_CSS_CACHE.get(dark)
    if _cached is not None:
        return _cached
    if dark:
        root = '\n  --bg:#0f0f23; --card:#1a1a2e; --card2:#15152a; --buy:#009e60; --sell:#dc2626; --hold:#d97706;\n  --acc1:#4f46e5; --acc2:#7c3aed; --txt:#e2e8f0; --txt2:#94a3b8; --border:#2d2d44;\n  --hover:#15152a; --alert-risk:#ffb3bb; --alert-cat:#9af0dd; --disclaimer:#6b7280;\n  --header-g1:#1a1a2e; --header-g2:#241b3a; --icon-g1:#1a1a2e; --icon-g2:#241b3a;\n'
    else:
        root = '\n  --bg:#ffffff; --card:#ffffff; --card2:#f4f6fb; --buy:#009e60; --sell:#dc2626; --hold:#d97706;\n  --acc1:#4f46e5; --acc2:#7c3aed; --txt:#1e293b; --txt2:#64748b; --border:#e2e8f0;\n  --hover:#f1f5f9; --alert-risk:#991b1b; --alert-cat:#166534; --disclaimer:#94a3b8;\n  --header-g1:#eef2ff; --header-g2:#ede9fe; --icon-g1:#eef2ff; --icon-g2:#ede9fe;\n'
    _css = _TOKEN_CSS + f"""\n<style>\n:root{{{root}}}\n/* 通用星辰卡片（供任意页面在 dashboard_sf_css 内使用） */
/* 通用星辰卡片 → 2026-08-28 重渲染为「新城(xc)」视觉语言：深紫渐变描边 + 大圆角 + 抬升光晕 */
.sf-card{{background:var(--card);border:1px solid color-mix(in srgb,var(--acc1) 28%,var(--border));
  border-radius:18px;padding:18px 20px;margin-top:18px;position:relative;overflow:hidden;
  box-shadow:0 0 0 1px rgba(102,126,234,.10),0 10px 28px rgba(102,126,234,.10);
  transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease}}
.sf-card::before{{content:"";position:absolute;inset:0;
  background:radial-gradient(circle at 10% -12%, rgba(124,92,255,.12), transparent 52%);pointer-events:none}}
.sf-card:hover{{transform:translateY(-3px);border-color:var(--acc1);
  box-shadow:0 0 0 1px rgba(102,126,234,.18),0 14px 34px rgba(102,126,234,.18)}}
.sf-card-title{{display:flex;align-items:center;gap:9px;font-size:16px;font-weight:700;margin:0 0 14px;padding-bottom:10px;border-bottom:1px solid var(--border);color:var(--txt)}}
.sf-card-title::before{{content:"";width:4px;height:18px;border-radius:3px;
  background:linear-gradient(180deg,var(--acc1),var(--acc2));box-shadow:0 0 8px rgba(102,126,234,.40)}}
.sf-card-subtitle{{font-size:13px;color:var(--txt2);line-height:1.7;margin-bottom:6px}}
/* ════════ 标题等级体系（父/子模块严格分级，避免“只看标题像内容很多”）════════ */
.sf-card h2.sf-h1{{font-size:17px;font-weight:700;color:var(--txt);margin:0 0 14px;padding-bottom:10px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;letter-spacing:.3px}}
.sf-card h2.sf-h1::before{{content:"";width:5px;height:18px;border-radius:3px;background:linear-gradient(180deg,var(--acc1),var(--acc2));box-shadow:0 0 8px rgba(102,126,234,.45)}}
.sf-card h2.sf-h2{{font-size:14.5px;font-weight:600;color:var(--txt2);margin:0 0 12px;padding-bottom:8px;border-bottom:1px dashed var(--border);display:flex;align-items:center;gap:7px}}
.sf-card h2.sf-h2::before{{content:"";width:3px;height:14px;border-radius:2px;background:var(--acc1);opacity:.85}}
/* CTA 生成分析调用区（去丑渐变卡，统一组件视觉语言） */
.sf-cta-card{{margin:14px 0 4px;padding:16px 18px;border-radius:14px;background:var(--card2);border:1px solid color-mix(in srgb,var(--acc1) 26%,var(--border));box-shadow:0 0 0 1px rgba(102,126,234,.08),0 8px 22px rgba(102,126,234,.10);position:relative;overflow:hidden}}
.sf-cta-card::before{{content:"";position:absolute;inset:0;background:radial-gradient(circle at 12% -20%, rgba(124,92,255,.12), transparent 55%);pointer-events:none}}
.sf-cta-title{{font-size:15px;font-weight:700;color:var(--txt);margin:0 0 4px;display:flex;align-items:center;gap:8px}}
.sf-cta-sub{{font-size:12.5px;color:var(--txt2);line-height:1.7;margin:0 0 12px}}

.sf-page-link{{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--acc1);background:rgba(102,126,234,.10);border:1px solid rgba(102,126,234,.30);border-radius:10px;padding:8px 12px;margin:10px 0 4px;transition:all .2s ease}}
.sf-page-link:hover{{background:rgba(102,126,234,.18);border-color:rgba(102,126,234,.50)}}
.sf-page-link a{{color:var(--acc1)!important;text-decoration:none!important}}

/* 按钮式分段选择器：把 data-radio-pills 包裹下的 st.radio 渲染为 pills */
[data-radio-pills="true"] [data-testid="stRadio"] > div > div > div,
[data-radio-pills="true"] [data-testid="stRadio"] [role="radiogroup"] > div,
[data-radio-pills="true"] [data-testid="stRadio"] label[data-baseweb="radio"]{{display:inline-flex!important;align-items:center;border:1px solid var(--border);background:var(--card2);color:var(--txt);border-radius:999px;padding:6px 14px;margin:0 6px 6px 0;cursor:pointer;transition:all .2s ease;font-size:13px;font-weight:500}}
[data-radio-pills="true"] [data-testid="stRadio"] > div > div > div:hover,
[data-radio-pills="true"] [data-testid="stRadio"] [role="radiogroup"] > div:hover,
[data-radio-pills="true"] [data-testid="stRadio"] label[data-baseweb="radio"]:hover{{background:var(--hover);border-color:var(--acc1)}}
[data-radio-pills="true"] [data-testid="stRadio"] input[type="radio"]{{position:absolute;opacity:0;width:0;height:0}}
[data-radio-pills="true"] [data-testid="stRadio"] input[type="radio"]:checked + div,
[data-radio-pills="true"] [data-testid="stRadio"] input[type="radio"]:checked + span,
[data-radio-pills="true"] [data-testid="stRadio"] label:has(input[type="radio"]:checked),
[data-radio-pills="true"] [data-testid="stRadio"] div:has(> input[type="radio"]:checked){{background:linear-gradient(135deg,var(--acc1),var(--acc2))!important;color:#fff!important;border-color:transparent!important;box-shadow:0 0 12px rgba(102,126,234,.25)}}
[data-radio-pills="true"] [data-testid="stRadio"] [data-testid="stWidgetLabel"]{{display:none!important}}

/* 文档风格：绿涨红跌（参考 002947，本页统一采用） */\n.sf-doc-up{{color:var(--buy)!important}}\n.sf-doc-down{{color:var(--sell)!important}}\n.sf-doc-neu{{color:var(--hold)!important}}\n.sf-buy-badge{{display:inline-block;font-size:22px;font-weight:800;letter-spacing:2px;\n  padding:10px 28px;border-radius:14px;color:#fff;background:linear-gradient(135deg,#009e60,#047857);\n  box-shadow:0 0 20px rgba(0,158,96,.22)}}\n.sf-sell-badge{{background:linear-gradient(135deg,#dc2626,#b91c1c);color:#fff;box-shadow:0 0 20px rgba(220,38,38,.22)}}\n.sf-hold-badge{{background:linear-gradient(135deg,#d97706,#b45309);color:#fff;box-shadow:0 0 20px rgba(217,119,6,.22)}}\n.sf-price-big{{font-size:42px;font-weight:800;letter-spacing:-1px;font-family:'Fira Code',monospace;color:var(--buy)}}\n.sf-triangle{{font-size:22px;margin-right:4px}}\n.sf-metric-card{{background:var(--card2);border:1px solid var(--border);border-radius:12px;padding:14px;text-align:center}}\n.sf-metric-card .label{{font-size:12px;color:var(--txt2);margin-bottom:6px}}\n.sf-metric-card .value{{font-size:22px;font-weight:700;font-family:'Fira Code',monospace;color:var(--txt)}}\n.sf-insight-box{{background:rgba(0,158,96,.10);border:1px solid rgba(0,158,96,.35);\n  border-radius:12px;padding:14px 16px;line-height:1.8;font-size:14px;color:var(--txt)}}\n.sf-insight-box.hold{{background:rgba(217,119,6,.10);border-color:rgba(217,119,6,.35);color:var(--txt)}}\n.sf-grid-4{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0}}\n@media(max-width:900px){{.sf-grid-4{{grid-template-columns:repeat(2,1fr)}}}}\n@media(max-width:540px){{.sf-grid-4{{grid-template-columns:1fr}}}}\n.sf-perspective-card{{background:var(--card2);border:1px solid var(--border);border-radius:14px;padding:16px;box-shadow:0 1px 4px rgba(0,0,0,.08)}}\n.sf-perspective-card .title{{font-size:12px;color:var(--txt2);margin-bottom:10px}}\n.sf-perspective-card .body{{font-size:14px;color:var(--txt);line-height:1.6}}\n.sf-pill{{display:inline-block;font-size:11px;font-weight:600;padding:3px 10px;border-radius:12px;margin:2px 2px 2px 0}}\n.sf-pill.up{{background:rgba(0,158,96,.12);color:var(--buy);border:1px solid rgba(0,158,96,.35)}}\n.sf-pill.down{{background:rgba(220,38,38,.12);color:var(--sell);border:1px solid rgba(220,38,38,.35)}}\n.sf-pill.mid{{background:rgba(217,119,6,.12);color:var(--hold);border:1px solid rgba(217,119,6,.35)}}\n.sf-intel-header{{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:12px}}\n.sf-intel-header h2{{margin:0;padding:0;border:0}}\n.sf-intel-bar{{height:6px;border-radius:3px;overflow:hidden;display:flex;margin:10px 0 18px;background:var(--border)}}\n.sf-intel-bar .bar-pos{{height:100%;background:var(--buy)}}\n.sf-intel-bar .bar-neu{{height:100%;background:var(--hold)}}\n.sf-intel-bar .bar-neg{{height:100%;background:var(--sell)}}\n.sf-card h2{{font-size:16px;margin:0 0 12px;display:flex;align-items:center;gap:8px;color:var(--txt);border-left:none;padding-left:0;border-bottom:none;padding-bottom:0;position:static}}\n.sf-card h2::before{{content:"";width:4px;height:16px;background:linear-gradient(180deg,var(--acc1),var(--acc2));border-radius:3px;flex-shrink:0}}\n.sf-card h2::after{{content:none}}\n.sf-scale{{margin-top:10px;background:var(--card2);border:1px solid var(--border);border-radius:10px;padding:14px;position:relative;height:64px}}\n.sf-scale-bar{{position:absolute;top:28px;left:14px;right:14px;height:8px;border-radius:4px}}\n.sf-scale-mk{{position:absolute;top:13px;transform:translateX(-50%);font-size:11px;color:var(--txt);text-align:center;white-space:nowrap}}\n.sf-scale-mk b{{display:block;font-size:13px;font-weight:700}}\n.sf-scale-lab{{position:absolute;bottom:5px;font-size:10px;color:var(--txt2)}}\n.sf-risk-iron{{background:rgba(220,38,38,.08);border:1px solid rgba(220,38,38,.30);border-radius:10px;padding:14px;margin-top:10px}}\n.sf-risk-iron h3{{color:var(--sell);font-size:14px;margin-bottom:8px}}\n.sf-risk-iron li{{font-size:12.5px;color:var(--txt);margin-left:18px;margin-bottom:4px}}\n.sf-header{{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;margin-bottom:18px;padding:14px 18px;background:linear-gradient(90deg,var(--header-g1),var(--header-g2));border:1px solid var(--border);border-radius:14px}}\n.sf-brand{{font-size:15px;color:var(--txt2);letter-spacing:1px}}\n.sf-brand b{{color:var(--acc1)}}\n.sf-tag{{display:inline-block;font-size:11px;font-weight:600;padding:3px 10px;border-radius:12px;margin:2px 2px 2px 0}}\n.sf-tag.up{{background:rgba(0,158,96,.14);color:var(--buy);border:1px solid rgba(0,158,96,.38)}}\n.sf-tag.down{{background:rgba(220,38,38,.14);color:var(--sell);border:1px solid rgba(220,38,38,.38)}}\n.sf-tag.mid{{background:rgba(217,119,6,.14);color:var(--hold);border:1px solid rgba(217,119,6,.38)}}\n.sf-tag.neu{{background:rgba(148,163,184,.12);color:var(--txt2);border:1px solid var(--border)}}\n.sf-alert{{border-radius:12px;padding:13px 15px;margin-top:14px;font-size:13.5px;color:var(--txt);line-height:1.7}}\n.sf-alert.risk{{background:rgba(220,38,38,.10);border:1px solid rgba(220,38,38,.30);color:var(--alert-risk)}}\n.sf-alert.cat{{background:rgba(0,158,96,.10);border:1px solid rgba(0,158,96,.30);color:var(--alert-cat)}}\n.sf-alert b{{display:block;margin-bottom:5px;font-size:14px}}\n.sf-table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}}\n.sf-table th,.sf-table td{{padding:9px 10px;text-align:left;border-bottom:1px solid var(--border)}}\n.sf-table th{{color:var(--txt2);font-weight:600;font-size:12px}}\n.sf-table tr:hover td{{background:var(--hover)}}\n.sf-disclaimer{{margin-top:14px;font-size:11.5px;color:var(--disclaimer);border-top:1px dashed var(--border);padding-top:10px}}\n.sf-vs{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:8px}}\n@media(max-width:780px){{.sf-vs{{grid-template-columns:1fr}}}}\n.sf-vsbox{{background:var(--card2);border:1px solid var(--border);border-radius:12px;padding:14px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}\n.sf-vsbox h3{{font-size:14px;margin-bottom:8px;color:var(--txt);border:none!important;padding-left:0!important}}\n.sf-card{{background:var(--card2);border:1px solid var(--border);border-radius:14px;padding:18px;margin-top:16px;box-shadow:0 1px 4px rgba(0,0,0,.08)}}\n.sf-card h2:first-child{{margin-top:0!important}}\n/* 全局表格美化：Streamlit 原生 dataframe/table 斑马纹 + 表头吸顶（金融专业观感） */\n.stDataFrame table{{border-collapse:separate;border-spacing:0;width:100%!important;font-size:13px}}\n.stDataFrame thead th{{position:sticky;top:0;z-index:2;background:var(--card2)!important;\n  color:var(--txt2)!important;font-weight:700;border-bottom:2px solid var(--border)!important}}\n.stDataFrame tbody tr:nth-child(even) td{{background:rgba(127,127,127,.06)}}\n.stDataFrame tbody tr:hover td{{background:rgba(102,126,234,.10)!important}}\n.stDataFrame td{{border-bottom:1px solid var(--border)!important;color:var(--txt)}}\n/* 折叠面板标题强化金融质感：左侧渐变竖条 + 悬停高亮 */\n.streamlit-expanderHeader{{border-left:3px solid transparent!important}}\n.streamlit-expanderHeader:hover{{border-left:3px solid var(--acc1, #4f46e5)!important}}

/* ===== 星辰主题·全局原生组件覆盖（自动应用到所有 render_standard_page 页面） ===== */
/* 说明：以下样式只改颜色/圆角/边框/阴影，不改 DOM 结构与功能，不破坏业务逻辑。 */

/* 1. caption 小卡片化 */
[data-testid="stCaption"],
.stCaption{{font-size:12.5px!important;color:var(--txt2)!important;line-height:1.7!important;
  background:var(--card2)!important;border-left:3px solid var(--acc1)!important;
  border-radius:0 10px 10px 0!important;padding:8px 12px!important;margin:10px 0 14px!important}}

/* 2. 按钮统一圆角+渐变 hover */
[data-testid="stButton"] > button,
[data-testid="stButton"] button{{border-radius:10px!important;font-weight:500!important;
  border:1px solid var(--border)!important;background:var(--card2)!important;color:var(--txt)!important;
  transition:all .2s ease!important}}
[data-testid="stButton"] > button:hover,
[data-testid="stButton"] button:hover{{border-color:var(--acc1)!important;background:rgba(102,126,234,.12)!important;
  box-shadow:0 0 12px rgba(102,126,234,.15)!important}}
[data-testid="stButton"] > button:active,
[data-testid="stButton"] button:active{{transform:translateY(1px)!important}}
/* 主按钮（primary）保持主题色填充 */
[data-testid="stButton"] > button[kind="primary"],
[data-testid="stButton"] button[kind="primary"]{{background:linear-gradient(135deg,var(--acc1),var(--acc2))!important;
  color:#fff!important;border-color:transparent!important}}

/* 3. 水平 radio 全局 pills（垂直 radio 保持原样） */
[data-testid="stRadio"] [role="radiogroup"][aria-orientation="horizontal"] > label,
[data-testid="stRadio"] > div > div > div > label{{display:inline-flex!important;align-items:center!important;
  border:1px solid var(--border)!important;background:var(--card2)!important;color:var(--txt)!important;
  border-radius:999px!important;padding:5px 13px!important;margin:0 6px 6px 0!important;
  cursor:pointer!important;transition:all .2s ease!important;font-size:13px!important;font-weight:500!important}}
[data-testid="stRadio"] [role="radiogroup"][aria-orientation="horizontal"] > label:hover,
[data-testid="stRadio"] > div > div > div > label:hover{{background:var(--hover)!important;border-color:var(--acc1)!important}}
[data-testid="stRadio"] [role="radiogroup"][aria-orientation="horizontal"] > label:has(input:checked),
[data-testid="stRadio"] > div > div > div > label:has(input:checked){{background:linear-gradient(135deg,var(--acc1),var(--acc2))!important;
  color:#fff!important;border-color:transparent!important;box-shadow:0 0 10px rgba(102,126,234,.22)!important}}
[data-testid="stRadio"] [role="radiogroup"][aria-orientation="horizontal"] input,
[data-testid="stRadio"] > div > div > div > label input{{position:absolute!important;opacity:0!important;width:0!important;height:0!important}}
[data-testid="stRadio"] [data-testid="stWidgetLabel"]{{font-weight:600!important;color:var(--txt)!important}}

/* 4. page_link 胶囊链接 */
[data-testid="stPageLink"] a,
a[data-testid="stPageLink"]{{display:inline-flex!important;align-items:center!important;gap:6px!important;
  font-size:13px!important;color:var(--acc1)!important;background:rgba(102,126,234,.10)!important;
  border:1px solid rgba(102,126,234,.30)!important;border-radius:10px!important;
  padding:8px 12px!important;margin:4px 0!important;transition:all .2s ease!important;
  text-decoration:none!important}}
[data-testid="stPageLink"] a:hover,
a[data-testid="stPageLink"]:hover{{background:rgba(102,126,234,.18)!important;border-color:rgba(102,126,234,.50)!important}}

/* 5. info/warning/error/success 卡片化 */
[data-testid="stAlert"],
.stAlert{{border-radius:12px!important;border:1px solid var(--border)!important;
  background:var(--card2)!important;color:var(--txt)!important;padding:12px 14px!important}}
[data-testid="stAlert"] [data-testid="stAlertContent"],
.stAlert [data-testid="stAlertContent"]{{color:var(--txt)!important}}
[data-testid="stAlert"]::before{{content:"";width:4px;height:100%;position:absolute;left:0;top:0;border-radius:12px 0 0 12px}}
[data-baseweb="notification"][data-kind="info"],
[data-testid="stAlert"][data-baseweb="notification"][data-kind="info"]{{border-left:4px solid var(--acc1)!important}}
[data-baseweb="notification"][data-kind="warning"],
[data-testid="stAlert"][data-baseweb="notification"][data-kind="warning"]{{border-left:4px solid var(--hold)!important}}
[data-baseweb="notification"][data-kind="error"],
[data-testid="stAlert"][data-baseweb="notification"][data-kind="error"]{{border-left:4px solid var(--sell)!important}}
[data-baseweb="notification"][data-kind="success"],
[data-testid="stAlert"][data-baseweb="notification"][data-kind="success"]{{border-left:4px solid var(--buy)!important}}

/* 6. 滑动条/进度条强调色 */
[data-testid="stSlider"] [role="slider"]{{background:var(--acc1)!important}}
[data-testid="stSlider"] [data-testid="stTickBar"]{{background:var(--border)!important}}
[data-testid="stSlider"] [data-testid="stThumbValue"]{{color:var(--txt)!important;font-weight:500!important}}
[data-testid="stProgress"] > div > div{{background:linear-gradient(90deg,var(--acc1),var(--acc2))!important}}

/* 7. 分割线/展开面板统一 */
[data-testid="stHorizontalBlock"] hr,
hr{{border-color:var(--border)!important}}
[data-testid="stExpander"]{{border:1px solid var(--border)!important;border-radius:12px!important;background:var(--card)!important}}

/* 8. 代码/标签页统一 */
[data-testid="stTabs"] [role="tab"]{{color:var(--txt2)!important;border-radius:8px 8px 0 0!important}}
[data-testid="stTabs"] [role="tab"][aria-selected="true"]{{color:var(--acc1)!important;border-bottom:2px solid var(--acc1)!important}}
[data-testid="stCodeBlock"] pre{{background:var(--card2)!important;border:1px solid var(--border)!important;border-radius:10px!important}}

/* ===== 新城(xc)风格·全局原生组件增强（2026-08-28 接入，沿用 xc 视觉语言） =====
   只改颜色/圆角/边框/阴影/表格观感，不改 DOM 结构与业务逻辑。 */
/* 1. 原生标题（st.header→h2 / st.subheader→h3 / st.title→h1）统一渐变竖条 */
.stApp h1,.stApp h2,.stApp h3,.stApp h4{{position:relative;padding-left:14px;font-weight:700;color:var(--txt)!important}}
.stApp h2::before,.stApp h3::before,.stApp h4::before{{content:"";position:absolute;left:0;top:.16em;width:4px;height:1em;min-height:14px;border-radius:3px;background:linear-gradient(180deg,var(--acc1),var(--acc2));box-shadow:0 0 8px rgba(102,126,234,.35)}}
/* 2. 原生表格（st.dataframe/st.table）统一 xc 表格观感：圆角容器 + 粘性表头 + 斑马纹 + hover */
.stDataFrame,.stTable{{border:1px solid var(--border)!important;border-radius:12px!important;overflow:hidden!important;box-shadow:0 1px 6px rgba(15,15,35,.06)}}
.stDataFrame table,.stTable table{{border-collapse:collapse!important;width:100%!important;font-size:12.5px}}
.stDataFrame thead th,.stTable thead th{{background:var(--card2)!important;color:var(--txt2)!important;font-weight:600!important;padding:9px 10px!important;text-align:center!important;border-bottom:1px solid var(--border)!important;position:sticky;top:0;z-index:1}}
.stDataFrame tbody td,.stTable tbody td{{padding:8px 10px!important;border-bottom:1px solid var(--border)!important;color:var(--txt)!important;text-align:center!important}}
.stDataFrame tbody tr:nth-child(even),.stTable tbody tr:nth-child(even){{background:color-mix(in srgb,var(--card2) 55%,transparent)!important}}
.stDataFrame tbody tr:hover,.stTable tbody tr:hover{{background:color-mix(in srgb,var(--acc1) 10%,var(--card2))!important}}
/* 3. st.metric 卡片化：逐 token 对齐 canonical .xc-card（ui_kit._KIT_CSS）——同一种 KPI 卡、单一视觉源。
   A 股红涨绿跌由页面 delta_color="inverse"/tone 控制，此处只统一容器/字体，不碰颜色语义。 */
[data-testid="stMetric"]{{background:var(--card)!important;border:1px solid color-mix(in srgb,var(--ss-accent) 22%,var(--ss-line))!important;border-radius:var(--ss-radius-card)!important;padding:14px 16px!important;box-shadow:var(--ss-shadow-card)!important;transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease!important}}
[data-testid="stMetric"]:hover{{transform:translateY(-4px);border-color:var(--acc1)!important;box-shadow:var(--ss-shadow-lift)!important}}
[data-testid="stMetric"] label{{color:var(--txt2)!important;font-size:12px!important;font-weight:500!important}}
[data-testid="stMetricValue"]{{color:var(--txt)!important;font-weight:800!important;font-size:22px!important;font-family:var(--ss-font-num)!important;letter-spacing:.2px!important}}
[data-testid="stMetricDelta"]{{font-size:13px!important;font-weight:700!important}}
/* 4. 原生 info/warning/error/success 左条改用主题强调紫（与 xc 一致） */
[data-testid="stAlert"][data-baseweb="notification"][data-kind="info"]{{border-left:4px solid var(--acc1)!important}}

/* ===== xc 统一覆盖：旧 .sf-* 子类继承「新城(xc)」视觉（后定义优先，零调用点改动） ===== */
.sf-metric-card{{background:var(--card);border:1px solid color-mix(in srgb,var(--acc1) 28%,var(--border));border-radius:14px;padding:14px;text-align:center;position:relative;overflow:hidden;box-shadow:0 0 0 1px rgba(102,126,234,.08),0 6px 18px rgba(102,126,234,.08);transition:transform .18s ease,border-color .18s ease}}
.sf-metric-card:hover{{transform:translateY(-3px);border-color:var(--acc1)}}
.sf-metric-card .label{{font-size:12px;color:var(--txt2);margin-bottom:6px}}
.sf-metric-card .value{{font-size:22px;font-weight:700;font-family:'Fira Code',monospace;color:var(--txt)}}
.sf-perspective-card{{background:var(--card);border:1px solid color-mix(in srgb,var(--acc1) 28%,var(--border));border-radius:16px;padding:16px;position:relative;overflow:hidden;box-shadow:0 0 0 1px rgba(102,126,234,.08),0 8px 22px rgba(102,126,234,.10);transition:transform .18s ease,border-color .18s ease}}
.sf-perspective-card:hover{{transform:translateY(-3px);border-color:var(--acc1)}}
.sf-perspective-card .title{{font-size:12px;color:var(--txt2);margin-bottom:10px}}
.sf-perspective-card .body{{font-size:14px;color:var(--txt);line-height:1.6}}
.sf-insight-box{{background:color-mix(in srgb,var(--acc1) 10%,var(--card2));border:1px solid color-mix(in srgb,var(--acc1) 35%,var(--border));border-radius:14px;padding:14px 16px;line-height:1.8;font-size:14px;color:var(--txt)}}
.sf-insight-box.hold{{background:color-mix(in srgb,var(--hold) 10%,var(--card2));border-color:color-mix(in srgb,var(--hold) 35%,var(--border));color:var(--txt)}}
.sf-grid-4{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0}}
@media(max-width:900px){{.sf-grid-4{{grid-template-columns:repeat(2,1fr)}}}}
@media(max-width:540px){{.sf-grid-4{{grid-template-columns:1fr}}}}
.sf-pill,.sf-tag{{display:inline-block;font-size:11px;font-weight:600;padding:3px 10px;border-radius:999px;background:rgba(102,126,234,.12);border:1px solid color-mix(in srgb,var(--acc1) 35%,var(--border));color:var(--acc1)}}
.sf-vsbox{{display:inline-flex;align-items:center;justify-content:center;gap:6px;font-size:12px;font-weight:600;padding:6px 12px;border-radius:10px;background:var(--card2);border:1px solid var(--border);color:var(--txt)}}
.sf-intel-bar{{height:4px;border-radius:3px;background:linear-gradient(90deg,var(--acc1),var(--acc2));box-shadow:0 0 8px rgba(102,126,234,.25)}}
.sf-intel-header{{font-size:13px;font-weight:700;color:var(--acc1);margin-bottom:8px;display:flex;align-items:center;gap:6px}}
.sf-scale{{display:flex;flex-direction:column;gap:4px}}
.sf-scale-bar{{height:6px;border-radius:3px;background:color-mix(in srgb,var(--acc1) 30%,var(--border));overflow:hidden}}
.sf-scale-mk{{height:100%;border-radius:3px;background:linear-gradient(90deg,var(--acc1),var(--acc2))}}
.sf-scale-lab{{font-size:11px;color:var(--txt2)}}
.sf-header{{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;margin-bottom:20px;padding:16px 20px;background:linear-gradient(120deg,color-mix(in srgb,var(--acc1) 16%,var(--card)),color-mix(in srgb,var(--acc2) 14%,var(--card)));border:1px solid var(--border);border-radius:16px;box-shadow:0 0 0 1px rgba(102,126,234,.10),0 8px 24px rgba(102,126,234,.10)}}
.sf-brand{{font-size:15px;color:var(--txt2);letter-spacing:1px}}
.sf-brand b{{color:var(--acc1)}}
.sf-note{{font-size:13px;color:var(--txt2);line-height:1.7}}
.sf-one-line{{font-size:14.5px;font-weight:700;color:var(--buy);background:color-mix(in srgb,var(--buy) 8%,var(--card2));border-left:3px solid var(--buy);padding:10px 14px;border-radius:8px;margin-bottom:14px;line-height:1.7}}
.sf-one-line.hold{{color:var(--hold);border-left-color:var(--hold);background:color-mix(in srgb,var(--hold) 8%,var(--card2))}}
.sf-verdict{{font-size:15px;font-weight:700;padding:14px 18px;border-radius:14px;background:color-mix(in srgb,var(--acc1) 12%,var(--card));border:1px solid color-mix(in srgb,var(--acc1) 35%,var(--border));color:var(--txt)}}
.sf-disclaimer{{font-size:12px;color:var(--txt2);line-height:1.7;opacity:.9}}
.sf-price-big{{font-size:40px;font-weight:800;letter-spacing:-1px;font-family:'Fira Code',monospace;color:var(--buy)}}
.sf-triangle{{font-size:22px;margin-right:4px}}
.sf-buy-badge,.sf-sell-badge,.sf-hold-badge{{display:inline-block;font-size:20px;font-weight:800;letter-spacing:1px;padding:10px 26px;border-radius:14px;color:#fff;box-shadow:0 0 20px rgba(102,126,234,.20)}}
.sf-buy-badge{{background:linear-gradient(135deg,#009e60,#047857)}}
.sf-sell-badge{{background:linear-gradient(135deg,#dc2626,#b91c1c)}}
.sf-hold-badge{{background:linear-gradient(135deg,#d97706,#b45309)}}
.sf-doc-up,.sf-up{{color:var(--buy)!important}}
.sf-doc-down,.sf-down{{color:var(--sell)!important}}
.sf-doc-neu{{color:var(--hold)!important}}
.sf-alert{{font-size:13px;color:var(--txt2);line-height:1.6}}
.sf-table{{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:4px;border:1px solid var(--border);border-radius:12px;overflow:hidden}}
.sf-table th,.sf-table td{{padding:9px 8px;text-align:center;border-bottom:1px solid var(--border)}}
.sf-table th{{color:var(--txt2);font-weight:600;font-size:12px;background:var(--card2)}}

/* 行情看板·行业板块涨跌卡（xc 风，动态涨跌色经 inline 传入） */
.xc-sector-card{{background:color-mix(in srgb,var(--acc1) 8%,var(--card));border:1px solid color-mix(in srgb,var(--acc1) 22%,var(--border));border-left:3px solid var(--acc1);border-radius:14px;padding:12px 14px;min-height:64px;box-sizing:border-box;display:flex;flex-direction:column;justify-content:center;box-shadow:0 0 0 1px rgba(102,126,234,.06),0 4px 14px rgba(102,126,234,.08);transition:transform .18s ease,border-color .18s ease}}
.xc-sector-card:hover{{transform:translateY(-3px);border-color:var(--acc1)}}
.xc-sector-name{{color:var(--txt);font-size:12px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.xc-sector-pct{{font-size:18px;font-weight:700;margin-top:2px}}
.xc-sector-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));gap:8px;margin-top:0}}
.xc-note{{padding:12px 14px;border-radius:12px;background:color-mix(in srgb,var(--acc1) 10%,var(--card2));border:1px solid color-mix(in srgb,var(--acc1) 30%,var(--border));font-size:14px;line-height:1.7;color:var(--txt)}}
</style>
"""
    _DASHBOARD_SF_CSS_CACHE[dark] = _css
    return _css


def section_header(title: str, subtitle: str='', icon: str='📊') -> None:
    """轻量化模块标题（图标 + 标题 + 渐变竖条），与参考文档 .card h2 一致。

    注：当前各页面统一改用 st.header / st.subheader（已由全局 CSS 轻量化）。
    本函数保留为兼容 / 兜底，仅渲染轻量标题，不再使用沉重标题框。
    """
    st.markdown(f"<div style='display:flex;align-items:center;gap:8px;margin:16px 0 10px;font-size:1rem;font-weight:600;'><span style='display:inline-block;width:4px;height:16px;border-radius:3px;background:linear-gradient(180deg,#667eea,#764ba2);flex-shrink:0;'></span><span>{icon} {title}</span></div>", unsafe_allow_html=True)

def card(body_html: str) -> None:
    if not _theme_is_dark():
        _bg = '#FFFFFF'
        _bd = 'rgba(17,24,39,0.08)'
        _sh = '0 4px 16px rgba(17,24,39,0.06), inset 0 1px 0 rgba(255,255,255,0.8)'
    else:
        _bg = 'rgba(26, 26, 46, 0.65)'
        _bd = 'rgba(102, 126, 234, 0.10)'
        _sh = '0 8px 24px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.05), 0 0 24px rgba(102,126,234,0.06)'
    st.markdown("<div style='background:" + _bg + ';border:1px solid ' + _bd + ';border-radius:16px;padding:18px 20px;box-shadow:' + _sh + ";backdrop-filter:blur(10px);'>" + body_html + '</div>', unsafe_allow_html=True)

def loading_spinner(text: str='加载中...', variant: str='default') -> None:
    if not _theme_is_dark():
        _g = '#B8860B'
        _gl = '#F6D486'
        _gs = 'rgba(184,134,11,0.12)'
        _fc = '#555B65'
    else:
        _g = '#667eea'
        _gl = '#a5b4fc'
        _gs = 'rgba(102,126,234,0.12)'
        _fc = '#94a3b8'
    _t = text
    variants = {'default': "<div style='text-align:center;padding:20px;color:" + _fc + ";'><div style='display:inline-block;width:36px;height:36px;border:3px solid " + _gs + ';border-top:3px solid ' + _g + ";border-radius:50%;animation:ld-spin 0.8s linear infinite;'></div><p style='margin-top:10px;font-size:0.9rem;'>" + _t + '</p></div><style>@keyframes ld-spin{to{transform:rotate(360deg);}}</style>', 'pulse': "<div style='text-align:center;padding:20px;color:" + _fc + ";'><div style='display:inline-block;width:40px;height:40px;background:" + _gs + ";border-radius:8px;animation:ld-pulse 1.2s ease-in-out infinite;'></div><p style='margin-top:10px;font-size:0.9rem;'>" + _t + '</p></div><style>@keyframes ld-pulse{0%,100%{opacity:0.4;transform:scale(0.95);}50%{opacity:1;transform:scale(1.05);}}</style>', 'dots': "<div style='text-align:center;padding:20px;color:" + _fc + ";'><div style='display:flex;gap:6px;justify-content:center;'><div style='width:8px;height:8px;background:" + _g + ";border-radius:50%;animation:ld-bounce 1s ease-in-out infinite;'></div><div style='width:8px;height:8px;background:" + _g + ";border-radius:50%;animation:ld-bounce 1s ease-in-out 0.15s infinite;'></div><div style='width:8px;height:8px;background:" + _g + ";border-radius:50%;animation:ld-bounce 1s ease-in-out 0.3s infinite;'></div></div><p style='margin-top:10px;font-size:0.9rem;'>" + _t + '</p></div><style>@keyframes ld-bounce{0%,80%,100%{transform:translateY(0);}40%{transform:translateY(-10px);}}</style>', 'bar': "<div style='text-align:center;padding:20px;color:" + _fc + ";'><div style='display:inline-block;width:120px;height:4px;background:rgba(0,0,0,0.04);border-radius:2px;overflow:hidden;'><div style='height:100%;background:linear-gradient(90deg," + _g + ',' + _gl + ");border-radius:2px;animation:ld-slide 1.5s ease-in-out infinite;width:40%;'></div></div><p style='margin-top:10px;font-size:0.9rem;'>" + _t + '</p></div><style>@keyframes ld-slide{0%{margin-left:-40%;}100%{margin-left:120%;}}</style>'}
    html_content = variants.get(variant, variants['default'])
    st.markdown(html_content, unsafe_allow_html=True)


def sf_card(title: str, body: str, icon: str = "") -> None:
    """渲染带标题的星辰卡片（.sf-card）。标题/正文做 html.escape，避免注入。

    用于把页面中的说明/控制区/结果区包装成统一卡片，提升视觉层次。
    纯视觉，不改动业务逻辑。
    """
    import html as _html
    title = _html.escape(str(title))
    body = _html.escape(str(body))
    icon = _html.escape(str(icon)) if icon else ""
    icon_html = f"{icon} " if icon else ""
    st.markdown(
        f'<div class="sf-card">'
        f'<div class="sf-card-title">{icon_html}{title}</div>'
        f'<div class="sf-card-subtitle">{body}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def sf_metric(label: str, value, delta: str = "") -> None:
    """渲染指标卡 —— 已收敛到 ui_kit 的 canonical ``.xc-card``（全站单一 KPI 卡视觉）。

    保留原签名（label/value/delta）以兼容既有调用点，视觉统一走 ``_xc_card_html``，
    消除 ``.sf-metric-card`` 与 ``.xc-card`` 两套并存的重复。数值/标签均 html.escape。
    """
    from modules.ui_kit import _xc_card_html, inject_kit_css  # 惰性导入，规避循环依赖
    inject_kit_css()
    st.markdown(
        _xc_card_html(label=label, value=value, delta=delta, delta_dir="flat"),
        unsafe_allow_html=True,
    )


# ───────────── T-186 四风格主题切换（additive-only，classic 默认零影响） ─────────────
# 设计：每套风格 = 一组 :root 变量覆盖（vars）+ 组件特征层（extra），在既有
# _DARK/_LIGHT CSS 之后注入（同特异性下后到者胜）。mode 锁定联动 theme_mode：
# terminal/aurora→dark，swiss/ink→light；classic（默认）不注入任何东西，
# 行为与本特性上线前逐位一致。红涨绿跌语义四套全保留（--buy/--sell/--ss-up/--ss-down）。
STYLE_PRESETS = {
    'classic': {'label': '经典星辰（默认）', 'mode': None, 'vars': '', 'extra': ''},
    'terminal': {'label': 'A · 彭博终端风（琥珀黑）', 'mode': 'dark',
        'vars': ('--bg:#0a0a0a; --card:#141414; --card2:#101010; --acc1:#e8a33d; '
                 '--acc2:#b8860b; --txt:#d4d4d4; --txt2:#8a8a8a; --border:#262626; '
                 '--grid:#1c1c1c; --buy:#ff5c5c; --sell:#3ddc97; --hold:#e8a33d; '
                 '--ss-up:#ff5c5c; --ss-down:#3ddc97; '
                 '--ss-glass-bg:linear-gradient(145deg,#141414,#101010);'),
        'extra': '''
:root{--ss-login-radius:6px;--ss-login-btn-text:#050505}.ss-login-card{border-radius:6px!important;backdrop-filter:none!important}.ss-login-title{background:none!important;-webkit-text-fill-color:#e8a33d!important;color:#e8a33d!important;font-family:Consolas,monospace!important;letter-spacing:1px!important}.ss-login-btn{border-radius:0!important;font-family:Consolas,monospace!important;text-transform:uppercase!important}.ss-login-badge{font-family:Consolas,monospace!important;border-radius:0!important}
.stApp{background-color:#050505
.stApp{background-color:#050505!important;
  background-image:radial-gradient(rgba(232,163,61,.055) 1px,transparent 1px),
  repeating-linear-gradient(0deg,rgba(232,163,61,.02) 0 1px,transparent 1px 3px)!important;
  background-size:18px 18px,auto!important;
  font-size:.9rem!important;line-height:1.42!important;
  font-family:'Fira Code',Consolas,'PingFang SC','Microsoft YaHei',monospace!important}
.stApp::before{display:block!important;height:3px!important;border-radius:0!important;
  background:linear-gradient(90deg,#e8a33d,#7a5a17,#e8a33d)!important;opacity:.95!important}
.stMarkdown p,.stMarkdown li{margin:.35em 0!important}
section[data-testid="stSidebar"]{background:#0b0b0b!important;
  border-right:1px solid #262626!important;backdrop-filter:none!important}
section[data-testid="stSidebar"] .stMarkdown h1,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3{color:#e8a33d!important;
  border-bottom:1px dashed #3a3a3a!important;font-family:Consolas,monospace!important}
section[data-testid="stSidebar"] a{border-left:3px solid transparent!important}
section[data-testid="stSidebar"] a[aria-current="page"]{border-left-color:#e8a33d!important;
  background:rgba(232,163,61,.08)!important}
h1,.stTitle h1{background:none!important;-webkit-text-fill-color:#e8a33d!important;
  color:#e8a33d!important;font-family:Consolas,monospace!important;letter-spacing:1px!important}
.stTitle h1::after{content:"\2588";color:#e8a33d;margin-left:10px;
  animation:ss-crt-blink 1.1s steps(1) infinite}
@keyframes ss-crt-blink{50%{opacity:0}}
h2{border-left:4px solid #e8a33d!important;font-family:Consolas,monospace!important;margin-top:10px!important}
h2[data-testid="stHeader"]::before,h3[data-testid="stHeader"]::before{
  background:#e8a33d!important;border-radius:0!important}
.stMetric{border-radius:0!important;background:#101010!important;position:relative!important;
  border:1px solid #262626!important;border-left:4px solid #e8a33d!important;
  box-shadow:none!important;backdrop-filter:none!important;-webkit-backdrop-filter:none!important;
  padding:8px 12px!important;animation:none!important}
.stMetric::after,.sf-card::after{content:"";position:absolute;inset:0;pointer-events:none;
  opacity:.7;background:
  linear-gradient(#e8a33d,#e8a33d) top left/12px 1.5px,linear-gradient(#e8a33d,#e8a33d) top left/1.5px 12px,
  linear-gradient(#e8a33d,#e8a33d) top right/12px 1.5px,linear-gradient(#e8a33d,#e8a33d) top right/1.5px 12px,
  linear-gradient(#e8a33d,#e8a33d) bottom left/12px 1.5px,linear-gradient(#e8a33d,#e8a33d) bottom left/1.5px 12px,
  linear-gradient(#e8a33d,#e8a33d) bottom right/12px 1.5px,linear-gradient(#e8a33d,#e8a33d) bottom right/1.5px 12px;
  background-repeat:no-repeat}
.stMetric:hover{border-color:#e8a33d!important;box-shadow:0 0 0 1px #e8a33d!important;transform:none!important}
.stMetric label{font-family:Consolas,monospace!important;text-transform:uppercase!important;
  letter-spacing:1px!important}
.stMetric label::before{content:"> ";color:#e8a33d}
.stMetric [data-testid="stMetricValue"]{background:none!important;
  -webkit-text-fill-color:#e8a33d!important;color:#e8a33d!important;
  font-family:Consolas,monospace!important;font-size:1.08rem!important}
.stApp .stButton button,.stApp [data-testid="stFormSubmitButton"] button{border-radius:0!important;
  background:#101010!important;border:1px solid #3a3a3a!important;box-shadow:none!important;
  font-family:Consolas,monospace!important;text-transform:uppercase!important;color:#d4d4d4!important}
.stApp .stButton button:hover{border-color:#e8a33d!important;color:#e8a33d!important;transform:none!important}
.stApp .stButton button[kind="primary"],.stApp [data-testid="stFormSubmitButton"] button{
  background:#e8a33d!important;color:#050505!important;border:none!important}
.stTabs [data-baseweb="tab"]{font-family:Consolas,monospace!important;text-transform:uppercase!important;
  letter-spacing:1px!important;border-radius:0!important;padding:5px 12px!important}
.stTabs [data-baseweb="tab"][aria-selected="true"]{color:#e8a33d!important;
  border-bottom:3px solid #e8a33d!important;background:transparent!important}
.stDataFrame,[data-testid="stTable"]{border-radius:0!important;background:#0e0e0e!important;
  border:1px solid #262626!important}
.stDataFrame thead th{background:#1a1a1a!important;color:#e8a33d!important;
  font-family:Consolas,monospace!important;border-bottom:1px solid #e8a33d!important;
  padding:4px 7px!important}
.stDataFrame tbody td{color:#d4d4d4!important;font-family:Consolas,monospace!important;padding:4px 7px!important}
.stDataFrame tr:hover td{background:rgba(232,163,61,.07)!important}
.stTextInput div[data-baseweb="input"],.stSelectbox div[data-baseweb="select"]>div{
  border-radius:0!important;background:#101010!important;border-color:#3a3a3a!important}
.stAlert{border-radius:0!important;font-family:Consolas,monospace!important}
[data-testid="stForm"]{padding:10px 12px!important;border-radius:0!important;background:#101010!important;
  border:1px solid #262626!important;box-shadow:none!important}
.sf-card,.sf-cta-card{border-radius:0!important;background:#101010!important;
  border:1px solid #262626!important;box-shadow:none!important;padding:10px 12px!important;
  margin-top:10px!important;backdrop-filter:none!important;-webkit-backdrop-filter:none!important;
  animation:none!important;position:relative!important}
.sf-card::before{display:none!important}
.sf-card-title{font-size:13px!important;margin-bottom:8px!important;padding-bottom:6px!important}
.sf-card-title::before{background:#e8a33d!important;border-radius:0!important}
.sf-table th,.sf-table td{padding:5px 6px!important;font-size:11.5px!important}
::-webkit-scrollbar{width:10px!important;height:10px!important}
::-webkit-scrollbar-thumb{background:#3a3a3a!important;border-radius:0!important}
::-webkit-scrollbar-thumb:hover{background:#e8a33d!important}
a{color:#e8a33d!important}a:hover{color:#ffc76b!important}
.js-plotly-plot .plotly .modebar{background:#141414!important;border-radius:0!important}
'''},
    'swiss': {'label': 'B · 瑞士极简白', 'mode': 'light',
        'vars': ('--bg:#ffffff; --card:#ffffff; --card2:#fafafa; --acc1:#111111; '
                 '--acc2:#1a56db; --txt:#111111; --txt2:#666666; --border:#e2e2e2; '
                 '--buy:#d93025; --sell:#0f9d58; --hold:#111111; '
                 '--ss-up:#d93025; --ss-down:#0f9d58;'),
        'extra': '''
:root{--ss-login-radius:4px;--ss-login-btn-text:#ffffff}.ss-login-card{border-radius:4px!important;border:2px solid #111111!important;backdrop-filter:none!important}.ss-login-title{background:none!important;-webkit-text-fill-color:#111111!important;color:#111111!important;font-weight:900!important;letter-spacing:-.02em!important}.ss-login-btn{border-radius:0!important;background:#111111!important;color:#ffffff!important;font-weight:700!important}.ss-login-btn:hover{background:#ffffff!important;color:#111111!important;box-shadow:4px 4px 0 #111111!important}
.stApp{background-color:#ffffff
.stApp{background-color:#ffffff!important;
  background-image:linear-gradient(#f2f2f2 1px,transparent 1px),
  linear-gradient(90deg,#f2f2f2 1px,transparent 1px)!important;
  background-size:34px 34px,34px 34px!important}
.stApp::before{display:block!important;height:5px!important;border-radius:0!important;
  background:#111111!important;opacity:1!important}
.stMarkdown p,.stMarkdown li{letter-spacing:.01em!important}
section[data-testid="stSidebar"]{background:#ffffff!important;
  border-right:2px solid #111111!important;backdrop-filter:none!important}
section[data-testid="stSidebar"] .stMarkdown h1,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3{color:#111111!important;
  border-bottom:2px solid #111111!important;border-radius:0!important}
section[data-testid="stSidebar"] .stMarkdown h3{font-weight:900!important;
  text-transform:uppercase!important;letter-spacing:2px!important;font-size:.82rem!important}
section[data-testid="stSidebar"] a[aria-current="page"]{color:#111111!important;
  font-weight:800!important;background:#f2f2f2!important;border-radius:0!important;
  text-decoration:underline!important;text-decoration-color:#111111!important;text-underline-offset:4px!important}
h1,.stTitle h1{background:none!important;-webkit-text-fill-color:#111111!important;
  color:#111111!important;font-weight:900!important;letter-spacing:-.03em!important}
.stTitle h1::after{content:"";display:inline-block;width:14px;height:14px;background:#d93025;margin-left:14px}
h2{border-left:none!important;font-weight:800!important;border-bottom:3px solid #111111!important;
  padding-left:0!important;padding-bottom:6px!important}
h2::after{display:none!important}
h2[data-testid="stHeader"]::before,h3[data-testid="stHeader"]::before{
  background:#111111!important;border-radius:0!important;width:14px!important}
.stMetric{border-radius:0!important;background:#fff!important;border:2px solid #111111!important;
  box-shadow:none!important;backdrop-filter:none!important;animation:none!important}
.stMetric:hover{transform:none!important;box-shadow:4px 4px 0 #111111!important;border-color:#111111!important}
.stMetric label{text-transform:uppercase!important;letter-spacing:1.5px!important;
  font-weight:700!important;color:#111111!important}
.stMetric [data-testid="stMetricValue"]{background:none!important;
  -webkit-text-fill-color:#111111!important;color:#111111!important;font-weight:800!important}
.stApp .stButton button,.stApp [data-testid="stFormSubmitButton"] button{border-radius:0!important;
  background:#fff!important;border:1.5px solid #111111!important;box-shadow:none!important;
  font-weight:700!important;color:#111111!important}
.stApp .stButton button:hover{background:#111111!important;color:#fff!important;transform:none!important;
  box-shadow:none!important}
.stApp .stButton button[kind="primary"],.stApp [data-testid="stFormSubmitButton"] button{
  background:#111111!important;color:#ffffff!important;border:1.5px solid #111111!important}
.stApp .stButton button[kind="primary"]:hover{background:#fff!important;color:#111111!important}
.stTabs [data-baseweb="tab"]{border-radius:0!important;background:transparent!important;
  border:none!important;font-weight:600!important;text-transform:uppercase!important;
  letter-spacing:1.5px!important;font-size:.78rem!important}
.stTabs [data-baseweb="tab"][aria-selected="true"]{color:#111111!important;
  border-bottom:4px solid #111111!important;background:transparent!important}
.stDataFrame,[data-testid="stTable"]{border-radius:0!important;border:1.5px solid #111111!important;
  box-shadow:none!important}
.stDataFrame thead th{background:#fff!important;color:#111111!important;
  border-bottom:2.5px solid #111111!important;text-transform:uppercase!important;
  letter-spacing:1px!important;font-size:.75rem!important}
.stAlert{border-radius:0!important;border:1.5px solid #111111!important;border-left-width:6px!important}
.sf-card,.sf-cta-card{border-radius:0!important;border:1.5px solid #111111!important;
  box-shadow:none!important;backdrop-filter:none!important;animation:none!important}
.sf-card:hover{transform:none!important;box-shadow:5px 5px 0 #111111!important}
.sf-card::before{display:none!important}
.sf-card-title{font-weight:800!important;text-transform:uppercase!important;
  letter-spacing:1.5px!important;font-size:13px!important}
.sf-card-title::before{background:#111111!important;border-radius:0!important}
::-webkit-scrollbar{width:6px!important;height:6px!important}
::-webkit-scrollbar-thumb{background:#111111!important;border-radius:0!important}
a{color:#111111!important;text-decoration:underline!important;text-underline-offset:3px!important}
a:hover{color:#1a56db!important}
'''},
    'aurora': {'label': 'C · 极光玻璃 2.0', 'mode': 'dark',
        'vars': ('--bg:#101334; --card:#181a44; --card2:#14163a; --acc1:#8b7cff; '
                 '--acc2:#5d5fef; --txt:#e9ecff; --txt2:#a5acdf; --border:#2c2f66; '
                 '--buy:#ff5c7a; --sell:#2fe0a8; --hold:#f5a623; '
                 '--ss-up:#ff5c7a; --ss-down:#2fe0a8; '
                 '--ss-glass-bg:linear-gradient(145deg,rgba(40,42,100,.66),rgba(28,29,80,.78));'),
        'extra': '''
:root{--ss-login-radius:26px;--ss-login-btn-text:#ffffff}.ss-login-card{border-radius:26px!important;box-shadow:0 0 0 1px rgba(139,124,255,.22),0 24px 70px rgba(8,8,32,.55),0 0 44px rgba(139,124,255,.16)!important;animation:ss-glow-breathe 3.5s ease-in-out infinite!important}.ss-login-btn{background:linear-gradient(90deg,#8b7cff,#5d5fef,#2dd4ff,#8b7cff)!important;background-size:250% 100%!important;animation:ss-btn-flow 4s linear infinite!important}
.stApp{background-color:#0d1030
.stApp{background-color:#0d1030!important;
  background-image:radial-gradient(1.5px 1.5px at 20% 30%,rgba(255,255,255,.5),transparent),
  radial-gradient(1px 1px at 70% 15%,rgba(255,255,255,.4),transparent),
  radial-gradient(1.5px 1.5px at 45% 70%,rgba(199,201,255,.45),transparent),
  radial-gradient(1px 1px at 88% 55%,rgba(45,212,255,.5),transparent),
  radial-gradient(ellipse 55% 42% at 12% -6%,rgba(139,124,255,.30) 0%,transparent 60%),
  radial-gradient(ellipse 45% 38% at 88% 2%,rgba(45,212,255,.20) 0%,transparent 55%),
  radial-gradient(ellipse 50% 40% at 92% 55%,rgba(244,114,182,.12) 0%,transparent 52%),
  radial-gradient(ellipse 70% 45% at 30% 110%,rgba(93,95,239,.22) 0%,transparent 60%)!important;
  background-size:170% 170%,150% 150%,160% 160%,170% 170%,170% 170%,150% 150%,160% 160%,170% 170%!important;
  animation:ss-aurora-drift 22s ease-in-out infinite alternate!important}
@keyframes ss-aurora-drift{
  0%{background-position:0% 0,100% 0,50% 100%,20% 80%,0% 0%,100% 0%,50% 100%,20% 80%}
  50%{background-position:60% 30%,20% 60%,80% 20%,60% 100%,60% 30%,20% 60%,80% 20%,60% 100%}
  100%{background-position:100% 60%,0% 30%,30% 0%,80% 20%,100% 60%,0% 30%,30% 0%,80% 20%}}
.stApp::before{display:block!important;height:5px!important;border-radius:0!important;
  background:linear-gradient(90deg,#8b7cff,#5d5fef,#2dd4ff,#ff5c7a,#8b7cff)!important;
  background-size:200% 100%!important;opacity:1!important;
  animation:ss-aurora-slide 5s linear infinite!important}
@keyframes ss-aurora-slide{0%{background-position:0% 0}100%{background-position:200% 0}}
section[data-testid="stSidebar"]{background:linear-gradient(180deg,rgba(28,29,84,.97),rgba(16,17,52,.99))!important;
  border-right:1px solid rgba(139,124,255,.35)!important}
section[data-testid="stSidebar"] .stMarkdown h1,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3{color:#b9c0ff!important;
  border-bottom:1px solid rgba(139,124,255,.4)!important}
h1,.stTitle h1{background:linear-gradient(135deg,#c7c9ff 0%,#8b7cff 45%,#5d5fef 100%);
  background-size:200% 100%!important;
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;
  animation:ss-title-flow 6s linear infinite!important}
@keyframes ss-title-flow{0%{background-position:0% 0}100%{background-position:200% 0}}
h2{border-left:4px solid #8b7cff!important}
h2::after{background:linear-gradient(180deg,#8b7cff,#5d5fef)!important}
h2[data-testid="stHeader"]::before,h3[data-testid="stHeader"]::before{
  background:linear-gradient(180deg,#8b7cff,#5d5fef)!important}
.stMetric,.sf-card,.sf-cta-card,[data-testid="stForm"]{border-radius:18px!important;
  border:1.5px solid transparent!important;
  background:linear-gradient(145deg,rgba(46,48,110,.72),rgba(30,31,86,.85))!important;
  backdrop-filter:blur(16px) saturate(1.4)!important;
  -webkit-backdrop-filter:blur(16px) saturate(1.4)!important;
  box-shadow:0 0 0 1px rgba(139,124,255,.22),0 14px 40px rgba(8,8,32,.5),
  0 0 30px rgba(139,124,255,.14),inset 0 1px 0 rgba(255,255,255,.10)!important;
  animation:ss-glow-breathe 3.5s ease-in-out infinite!important}
@keyframes ss-glow-breathe{0%,100%{box-shadow:0 0 0 1px rgba(139,124,255,.22),
  0 14px 40px rgba(8,8,32,.5),0 0 30px rgba(139,124,255,.14)}
  50%{box-shadow:0 0 0 1px rgba(139,124,255,.36),0 14px 40px rgba(8,8,32,.5),
  0 0 46px rgba(139,124,255,.26)}}
.stMetric:hover{animation-duration:1.6s!important;transform:translateY(-2px)!important}
.stMetric [data-testid="stMetricValue"]{background:linear-gradient(180deg,#ffffff 10%,#b9c0ff 90%);
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;
  text-shadow:none!important}
.stApp .stButton button[kind="primary"],.stApp [data-testid="stFormSubmitButton"] button{
  background:linear-gradient(90deg,#8b7cff,#5d5fef,#2dd4ff,#8b7cff)!important;
  background-size:250% 100%!important;animation:ss-btn-flow 4s linear infinite!important;
  color:#fff!important;box-shadow:0 4px 18px rgba(139,124,255,.45)!important}
@keyframes ss-btn-flow{0%{background-position:0% 0}100%{background-position:250% 0}}
.stTabs [data-baseweb="tab"][aria-selected="true"]{color:#c7c9ff!important;
  border-bottom:2.5px solid #8b7cff!important;
  background:linear-gradient(180deg,rgba(139,124,255,.16),transparent)!important;
  border-radius:8px 8px 0 0!important}
.stDataFrame,[data-testid="stTable"]{border-radius:14px!important;
  border:1px solid rgba(139,124,255,.25)!important;background:rgba(24,26,68,.6)!important}
.stDataFrame thead th{color:#b9c0ff!important;background:rgba(44,47,102,.5)!important}
.sf-card-title::before{background:linear-gradient(180deg,#8b7cff,#5d5fef)!important}
a{color:#b9c0ff!important}a:hover{color:#8b7cff!important}
'''},
    'ink': {'label': 'D · 东方墨韵（宣纸朱砂）', 'mode': 'light',
        'vars': ('--bg:#f7f3ea; --card:#fbf8f1; --card2:#f3eee2; --acc1:#b03a2e; '
                 '--acc2:#1e7f6b; --txt:#2b2b2b; --txt2:#7a7263; --border:#ddd3bd; '
                 '--buy:#c0392b; --sell:#1e7f6b; --hold:#8a6d3b; '
                 '--ss-up:#c0392b; --ss-down:#1e7f6b;'),
        'extra': '''
:root{--ss-login-radius:8px;--ss-login-btn-text:#f5f0e4}.ss-login-card{border-radius:8px!important;outline:1px solid #ddd3bd!important;outline-offset:4px!important;backdrop-filter:none!important;animation:none!important}.ss-login-title{font-family:serif!important;letter-spacing:3px!important;font-weight:800!important}.ss-login-subtitle{font-family:serif!important;letter-spacing:2px!important}.ss-login-btn{font-family:serif!important;letter-spacing:2px!important;border-radius:2px!important}.ss-login-badge{font-family:serif!important;border-radius:2px!important}
.stApp{background-color:#f5f0e4
.stApp{background-color:#f5f0e4!important;
  background-image:radial-gradient(ellipse 30% 22% at 82% 18%,rgba(43,43,43,.05),transparent 70%),
  radial-gradient(ellipse 22% 18% at 12% 78%,rgba(43,43,43,.045),transparent 70%),
  radial-gradient(ellipse 16% 14% at 55% 40%,rgba(120,100,60,.04),transparent 70%),
  linear-gradient(rgba(90,80,60,.028) 1px,transparent 1px),
  linear-gradient(90deg,rgba(90,80,60,.028) 1px,transparent 1px)!important;
  background-size:auto,auto,auto,26px 26px,26px 26px!important}
.stApp::before{display:none!important}
.stApp::after{content:"量策";position:fixed;top:16px;right:16px;z-index:99989;
  width:38px;height:72px;font-size:24px;writing-mode:vertical-rl;letter-spacing:5px;
  padding-top:6px;transform:rotate(-4deg);border:2.5px solid #8a2f24;border-radius:5px;
  background:radial-gradient(circle at 30% 28%,#c1483a,#a63327 68%,#8f2a20);
  box-shadow:inset 0 0 0 3px rgba(245,240,228,.5),0 4px 12px rgba(176,58,46,.4);
  text-shadow:0 0 2px rgba(245,240,228,.4);opacity:.94;pointer-events:none;
  display:flex;align-items:center;justify-content:center;
  font-family:'Songti SC','STSong','SimSun',serif;font-weight:700}
h1,.stTitle h1{background:none!important;-webkit-text-fill-color:#2b2b2b!important;
  color:#2b2b2b!important;font-family:serif!important;font-weight:800!important;
  letter-spacing:3px!important}
h2{border-left:none!important;font-family:serif!important;font-weight:800!important;
  letter-spacing:2px!important;border-bottom:2px solid #b03a2e!important;
  padding-left:0!important;padding-bottom:6px!important;display:inline-block!important}
h2::after{display:none!important}
h2[data-testid="stHeader"]::before,h3[data-testid="stHeader"]::before{display:none!important}
section[data-testid="stSidebar"]{position:relative!important;background:#f0e9da!important;
  border-right:1px solid #c9bfa8!important;backdrop-filter:none!important}
section[data-testid="stSidebar"]::before{content:"观市";position:absolute;top:14px;right:10px;
  writing-mode:vertical-rl;font-family:serif;font-size:15px;letter-spacing:8px;
  color:rgba(176,58,46,.35);pointer-events:none;z-index:1}
section[data-testid="stSidebar"] .stMarkdown h1,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3{color:#8a2f24!important;
  font-family:serif!important;letter-spacing:2px!important;
  border-bottom:1px solid rgba(176,58,46,.3)!important}
section[data-testid="stSidebar"] a[aria-current="page"]{color:#8a2f24!important;
  background:rgba(176,58,46,.08)!important;border-left:3px solid #b03a2e!important;
  border-radius:0!important}
.stMetric{background:#fbf8f1!important;border:1px solid #b03a2e!important;
  outline:1px solid #ddd3bd!important;outline-offset:3px!important;
  border-radius:2px!important;box-shadow:none!important;
  backdrop-filter:none!important;-webkit-backdrop-filter:none!important;animation:none!important}
.stMetric:hover{transform:none!important;outline-color:#b03a2e!important}
.stMetric label{font-family:serif!important;letter-spacing:2px!important;color:#7a7263!important}
.stMetric [data-testid="stMetricValue"]{background:none!important;
  -webkit-text-fill-color:#2b2b2b!important;color:#2b2b2b!important;
  font-family:'Fira Code',Consolas,monospace!important}
.stApp .stButton button,.stApp [data-testid="stFormSubmitButton"] button{
  border-radius:2px!important;background:transparent!important;
  border:1.5px solid #8a7a5c!important;color:#4a4436!important;
  box-shadow:none!important;font-family:serif!important;letter-spacing:2px!important}
.stApp .stButton button:hover{border-color:#b03a2e!important;color:#b03a2e!important;transform:none!important}
.stApp .stButton button[kind="primary"],.stApp [data-testid="stFormSubmitButton"] button{
  background:#b03a2e!important;color:#f5f0e4!important;border:1.5px solid #8a2f24!important}
.stTabs [data-baseweb="tab"]{border-radius:0!important;background:transparent!important;
  border:none!important;font-family:serif!important;letter-spacing:2px!important}
.stTabs [data-baseweb="tab"][aria-selected="true"]{color:#8a2f24!important;
  border-bottom:3px double #b03a2e!important;background:transparent!important}
.stDataFrame,[data-testid="stTable"]{border-radius:2px!important;
  border:1px solid #c9bfa8!important;background:#fbf8f1!important;box-shadow:none!important}
.stDataFrame thead th{background:#f0e9da!important;color:#8a2f24!important;
  font-family:serif!important;letter-spacing:1px!important;border-bottom:2px solid #b03a2e!important}
.stDataFrame tbody td{color:#4a4436!important}
.stDataFrame tr:hover td{background:rgba(176,58,46,.05)!important}
.stAlert{border-radius:2px!important;border:1px solid #c9bfa8!important;border-left-width:5px!important;
  font-family:serif!important;font-style:italic!important;letter-spacing:.5px!important}
.sf-card,.sf-cta-card{background:#fbf8f1!important;border:1px solid #c9bfa8!important;
  outline:1px solid #ddd3bd!important;outline-offset:4px!important;
  border-radius:2px!important;box-shadow:none!important;
  backdrop-filter:none!important;-webkit-backdrop-filter:none!important;animation:none!important;
  margin-top:22px!important}
.sf-card:hover{transform:none!important;outline-color:#b03a2e!important}
.sf-card::before{display:none!important}
.sf-card-title{font-family:serif!important;letter-spacing:2px!important;
  border-bottom:1px dashed #c9bfa8!important}
.sf-card-title::before{background:#b03a2e!important;border-radius:1px!important;width:12px!important}
.sf-note,.sf-disclaimer{font-family:serif!important}
::-webkit-scrollbar{width:9px!important;height:9px!important}
::-webkit-scrollbar-track{background:#f0e9da!important}
::-webkit-scrollbar-thumb{background:#c9bfa8!important;border-radius:2px!important}
::-webkit-scrollbar-thumb:hover{background:#b03a2e!important}
a{color:#8a2f24!important}a:hover{color:#b03a2e!important}
.stMarkdown code,code{background:#f0e9da!important;border:1px dashed #c9bfa8!important}
'''},
    'cyber': {'label': 'E · 赛博朋克 2077（霓虹故障）', 'mode': 'dark',
        'vars': ('--bg:#0a0e17; --card:#101624; --card2:#0c111d; --acc1:#fcee0a; '
                 '--acc2:#00f0ff; --txt:#e8f6ff; --txt2:#5c7a9e; --border:#1e2a3d; '
                 '--buy:#ff2a6d; --sell:#00ff9f; --hold:#fcee0a; '
                 '--ss-up:#ff2a6d; --ss-down:#00ff9f;'),
        'extra': '''
:root{--ss-login-radius:0px;--ss-login-btn-text:#0a0e17}.ss-login-card{border-radius:0!important;clip-path:polygon(0 0,calc(100% - 18px) 0,100% 18px,100% 100%,18px 100%,0 calc(100% - 18px))!important;box-shadow:0 0 26px rgba(0,240,255,.14),inset 0 0 30px rgba(0,240,255,.05)!important}.ss-login-title{text-shadow:2px 0 rgba(255,42,109,.75),-2px 0 rgba(0,240,255,.75)!important;animation:ss-glitch 3.2s infinite steps(1)!important;font-family:Consolas,monospace!important;letter-spacing:2px!important}.ss-login-btn{clip-path:polygon(0 0,calc(100% - 10px) 0,100% 10px,100% 100%,10px 100%,0 calc(100% - 10px))!important;border-radius:0!important;font-family:Consolas,monospace!important;text-transform:uppercase!important;font-weight:800!important}.ss-login-badge{font-family:Consolas,monospace!important;border-radius:0!important;text-transform:uppercase!important}
.stApp{background-color:#0a0e17
.stApp{background-color:#0a0e17!important;
  background-image:repeating-linear-gradient(0deg,rgba(0,240,255,.025) 0 1px,transparent 1px 4px),
  linear-gradient(rgba(0,240,255,.06) 1px,transparent 1px),
  linear-gradient(90deg,rgba(0,240,255,.06) 1px,transparent 1px),
  radial-gradient(ellipse 80% 45% at 50% 118%,rgba(255,42,109,.20),transparent 62%),
  radial-gradient(ellipse 55% 35% at 82% -8%,rgba(252,238,10,.10),transparent 55%)!important;
  background-size:auto,40px 40px,40px 40px,auto,auto!important}
.stApp::before{display:block!important;height:3px!important;border-radius:0!important;
  background:repeating-linear-gradient(90deg,#fcee0a 0 18px,#00f0ff 18px 36px,#ff2a6d 36px 54px)!important;
  opacity:.85!important}
.stTitle h1{background:none!important;-webkit-text-fill-color:#fcee0a!important;
  color:#fcee0a!important;font-family:Consolas,monospace!important;letter-spacing:2px!important;
  text-shadow:2px 0 rgba(255,42,109,.75),-2px 0 rgba(0,240,255,.75)!important;
  animation:ss-glitch 3.2s infinite steps(1)!important}
@keyframes ss-glitch{
  0%,91%,100%{text-shadow:2px 0 rgba(255,42,109,.75),-2px 0 rgba(0,240,255,.75);transform:none}
  92%{text-shadow:-3px 0 rgba(255,42,109,.9),3px 0 rgba(0,240,255,.9);transform:translate(2px,-1px)}
  95%{text-shadow:3px 0 rgba(255,42,109,.9),-3px 0 rgba(0,240,255,.9);transform:translate(-2px,1px)}
  97%{transform:translate(1px,0)}}
.stMetric,.sf-card,.sf-cta-card,[data-testid="stForm"]{
  clip-path:polygon(0 0,calc(100% - 16px) 0,100% 16px,100% 100%,16px 100%,0 calc(100% - 16px))!important;
  border-radius:0!important;border:1px solid rgba(252,238,10,.35)!important;
  background:linear-gradient(160deg,rgba(16,22,36,.96),rgba(10,14,23,.98))!important;
  box-shadow:0 0 18px rgba(0,240,255,.12),inset 0 0 24px rgba(0,240,255,.05)!important;
  backdrop-filter:none!important;-webkit-backdrop-filter:none!important;animation:none!important}
.stMetric:hover{box-shadow:0 0 26px rgba(252,238,10,.20),inset 0 0 24px rgba(0,240,255,.08)!important;
  border-color:rgba(252,238,10,.65)!important;transform:none!important}
.stMetric [data-testid="stMetricValue"]{background:none!important;
  -webkit-text-fill-color:#00f0ff!important;color:#00f0ff!important;
  font-family:Consolas,monospace!important;text-shadow:0 0 10px rgba(0,240,255,.5)!important}
.stMetric label{text-transform:uppercase!important;letter-spacing:1.5px!important;
  font-family:Consolas,monospace!important}
h2{border-left:4px solid #fcee0a!important}
h2[data-testid="stHeader"]::before,h3[data-testid="stHeader"]::before{
  background:#fcee0a!important;border-radius:0!important}
.stApp .stButton button,.stApp [data-testid="stFormSubmitButton"] button{
  border-radius:0!important;
  clip-path:polygon(0 0,calc(100% - 10px) 0,100% 10px,100% 100%,10px 100%,0 calc(100% - 10px))!important;
  background:#101624!important;border:1px solid rgba(0,240,255,.5)!important;
  color:#e8f6ff!important;font-family:Consolas,monospace!important;
  text-transform:uppercase!important;box-shadow:none!important}
.stApp .stButton button:hover{border-color:#fcee0a!important;color:#fcee0a!important;
  box-shadow:0 0 14px rgba(252,238,10,.3)!important;transform:none!important}
.stApp .stButton button[kind="primary"],.stApp [data-testid="stFormSubmitButton"] button{
  background:#fcee0a!important;color:#0a0e17!important;border:none!important;
  text-shadow:none!important;font-weight:800!important}
.stTabs [data-baseweb="tab"]{border-radius:0!important;font-family:Consolas,monospace!important;
  text-transform:uppercase!important}
.stTabs [data-baseweb="tab"]:hover{color:#00f0ff!important}
.stTabs [data-baseweb="tab"][aria-selected="true"]{color:#fcee0a!important;
  border-bottom:3px solid #fcee0a!important;background:transparent!important}
.stDataFrame,[data-testid="stTable"]{border-radius:0!important;
  border:1px solid rgba(0,240,255,.3)!important;background:#0c111d!important}
.stDataFrame thead th{background:#101624!important;color:#00f0ff!important;
  font-family:Consolas,monospace!important;text-transform:uppercase!important}
.stDataFrame tbody td{color:#c9d9e8!important;font-family:Consolas,monospace!important}
.stAlert{border-radius:0!important;font-family:Consolas,monospace!important}
.sf-card-title::before{background:#fcee0a!important;border-radius:0!important}
.sf-card::before{display:none!important}
section[data-testid="stSidebar"]{background:#0c111d!important;
  border-right:1px solid rgba(252,238,10,.25)!important}
section[data-testid="stSidebar"] .stMarkdown h1,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3{color:#fcee0a!important;
  font-family:Consolas,monospace!important;text-transform:uppercase!important;
  border-bottom:1px dashed rgba(0,240,255,.35)!important}
::-webkit-scrollbar{width:10px!important;height:10px!important}
::-webkit-scrollbar-track{background:#0a0e17!important}
::-webkit-scrollbar-thumb{background:#1e2a3d!important;border-radius:0!important}
::-webkit-scrollbar-thumb:hover{background:#fcee0a!important}
a{color:#00f0ff!important}
a:hover{color:#fcee0a!important;text-shadow:0 0 8px rgba(252,238,10,.5)!important}
'''},
}

def _sync_style_mode() -> None:
    """非 classic 风格锁定 theme_mode（terminal/aurora→dark，swiss/ink→light）。

    classic 不动用户自己的暗/亮切换；风格层接管底色后，原右上角暗/亮按钮
    对新风格不再生效（风格即底色，避免两套开关打架）。
    """
    try:
        preset = STYLE_PRESETS.get(st.session_state.get('ui_style', 'classic'))
        if preset and preset.get('mode'):
            st.session_state['theme_mode'] = preset['mode']
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[ui_theme] _sync_style_mode 处理异常: {e}")


def get_current_style() -> str:
    return st.session_state.get('ui_style', 'classic')


def style_switcher() -> None:
    """侧边栏界面风格切换器（T-186 additive）：经典默认 + 四套新风格。"""
    try:
        labels = {k: v['label'] for k, v in STYLE_PRESETS.items()}
        cur = get_current_style()
        if cur not in labels:
            cur = 'classic'
        with st.sidebar:
            choice = st.selectbox(
                '🎨 界面风格', list(labels.keys()),
                index=list(labels.keys()).index(cur),
                format_func=lambda k: labels[k], key='ui_style_select')
        if choice != cur:
            st.session_state['ui_style'] = choice
            try:
                from modules.session import persist_prefs
                persist_prefs()  # URL prefs + localStorage + 后端 settings 三路持久化
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[ui_theme] 风格持久化失败: {e}")
            st.rerun()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[ui_theme] style_switcher 处理异常: {e}")


def inject_style_css() -> None:
    """非 classic 风格注入 :root 变量覆盖 + 组件特征层（后到者胜）。"""
    style = st.session_state.get('ui_style', 'classic')
    preset = STYLE_PRESETS.get(style)
    if not preset or style == 'classic':
        return
    try:
        if preset.get('vars'):
            st.markdown(f'<style>:root{{{preset["vars"]}}}</style>', unsafe_allow_html=True)
        if preset.get('extra'):
            st.markdown(f'<style>{preset["extra"]}</style>', unsafe_allow_html=True)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[ui_theme] inject_style_css 处理异常: {e}")

