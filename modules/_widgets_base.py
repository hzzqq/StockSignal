"""modules/_widgets_base.py
跨页面组件共享的纯函数（无依赖，避免 widgets 拆分产生环引用）。
"""
from __future__ import annotations

import html

def STAR_AI_LOGO(size: int = 20) -> str:
    """返回「星辰 AI」内联 SVG（可直接 unsafe_allow_html 渲染）。

    size 控制高/宽像素；vertical-align:middle 使其与同行文字基线对齐。
    None/非数值/非正数安全降级为 20（R2：不崩溃）。
    """
    try:
        size = int(size)
    except (TypeError, ValueError):
        size = 20
    if size <= 0:
        size = 20
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 32 32" fill="none" '
        f'style="vertical-align:middle;flex-shrink:0;display:inline-block" '
        f'role="img" aria-label="星辰 AI">'
        # 数据轨道（卫星环绕感）
        f'<ellipse cx="16" cy="16" rx="13" ry="5.5" transform="rotate(-32 16 16)" '
        f'stroke="#764ba2" stroke-width="1.4" opacity="0.65"/>'
        # 上行股价折线（K线/价格趋势）
        f'<polyline points="3,24 9,19 13,21 18,13 22,15 28,6" fill="none" '
        f'stroke="#667eea" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"/>'
        # 折线顶点的数据节点
        f'<circle cx="28" cy="6" r="2" fill="#667eea"/>'
        # 金色四射星芒（"星"）
        f'<path d="M16 6 C16.7 12.3 19.7 15.3 26 16 C19.7 16.7 16.7 19.7 16 26 '
        f'C15.3 19.7 12.3 16.7 6 16 C12.3 15.3 15.3 12.3 16 6 Z" fill="#f5c542"/>'
        f'</svg>'
    )


# ──────────────────────────────────────────────────────────────
# 三大指数迷你行情卡片（行情看板 / 每日晨报顶部）
# ──────────────────────────────────────────────────────────────
_INDEX_INFOS = [
    {"name": "上证指数", "code": "000001", "label": "指数"},
    {"name": "深证成指", "code": "399001", "label": "指数"},
    {"name": "创业板指", "code": "399006", "label": "指数"},
    # 海外指数：美股实时 via 新浪；富时100 / 韩国KOSPI via 新浪日线
    {"name": "道琼斯", "code": "DJI", "label": "美股", "global": True, "sina_rt": "gb_$dji"},
    {"name": "纳斯达克", "code": "IXIC", "label": "美股", "global": True, "sina_rt": "gb_$ixic"},
    {"name": "标普500", "code": "INX", "label": "美股", "global": True, "sina_rt": "gb_$inx"},
    {"name": "富时100", "code": "FTSE", "label": "英国", "global": True, "sina_hist": "英国富时100指数"},
    {"name": "韩国KOSPI", "code": "KS11", "label": "韩国", "global": True, "sina_hist": "首尔综合指数"},
]


# ──────────────────────────────────────────────────────────────
# 统一空状态 / 加载态（T12 基建：避免数据缺失时白屏）
# ──────────────────────────────────────────────────────────────
def render_empty_state(message: str, icon: str = "📭", hint: str = "") -> str:
    """返回友好的「空状态」HTML 片段（数据缺失 / 加载失败时展示）。

    调用方用 ``st.markdown(html, unsafe_allow_html=True)`` 渲染即可。
    统一暗/亮主题（走 --txt / --txt2 CSS 变量），避免数据缺失时白屏或裸报错。
    message 为必填核心文案；icon 为 emoji 图标；hint 为可选的补充提示（如换代码/稍后重试）。
    message / hint 为数据派生文本时做 html.escape，防止结构注入（R73 对齐 _empty_info 既有 XSS 契约）。
    """
    message = "" if message is None else html.escape(str(message))
    hint = "" if hint is None else html.escape(str(hint))
    hint_html = (
        f'<div style="font-size:12px;color:var(--txt2);margin-top:6px">{hint}</div>'
        if hint else ""
    )
    return (
        f'<div style="text-align:center;padding:32px 16px;color:var(--txt2);">'
        f'<div style="font-size:32px;margin-bottom:8px">{icon}</div>'
        f'<div style="font-size:14px;font-weight:600;color:var(--txt)">{message}</div>'
        f'{hint_html}</div>'
    )
