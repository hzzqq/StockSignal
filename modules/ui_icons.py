# -*- coding: utf-8 -*-
"""modules/ui_icons.py — 统一内联 SVG 图标系统（零 emoji，currentColor 自适应主题）。

设计纪律（对齐 ui-ux-pro-max / design-critique）：
  · 禁 emoji 当 UI 图标（不专业、不可缩放、与令牌化精密感冲突）。一律 SVG。
  · 统一 24×24 viewBox，描边用 currentColor → 自动跟随 --ss-text / --ss-accent 主题色。
  · 纯展示，无副作用；未命中图标名或 emoji 映射时安全回退（绝不抛）。

用法：
  from modules.ui_icons import svg_icon, render_nav_icon
  html = svg_icon("home", size=16)          # 直接按名称取
  html = render_nav_icon("📈")               # 传入原 emoji → 命中则转 SVG，未命中回退原 emoji
"""
from __future__ import annotations

import re

# 每个图标 = SVG 内部内容（不含外层 <svg>）。统一 24x24、stroke=currentColor、fill=none。
_ICONS: dict[str, str] = {
    "home": '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M9.5 21v-6h5v6"/>',
    "target": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="1"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3c2.5 2.5 2.5 15 0 18M12 3c-2.5 2.5-2.5 15 0 18"/>',
    "chart": '<path d="M4 20V4"/><path d="M4 20h16"/><path d="M8 16l3-4 3 2 4-6"/>',
    "chart-bar": '<path d="M4 20V4"/><path d="M4 20h16"/><rect x="7" y="11" width="3" height="6"/><rect x="13" y="7" width="3" height="10"/>',
    "wallet": '<path d="M3 7h15a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H3z"/><path d="M3 7V5a2 2 0 0 1 2-2h11"/><circle cx="17" cy="13" r="1.4"/>',
    "gear": '<circle cx="12" cy="12" r="3.2"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
    "sparkles": '<path d="M12 3l1.8 4.7L18 9.5l-4.2 1.8L12 16l-1.8-4.7L6 9.5l4.2-1.8z"/><path d="M18 15l.9 2.3L21 18l-2.1.7L18 21l-.9-2.3L15 18l2.1-.7z"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "palette": '<path d="M12 3a9 9 0 1 0 0 18c1.5 0 2-1 2-2 0-1.2-1-1.5-1-2.5 0-1 1-1.5 2-1.5h1a4 4 0 0 0 4-4c0-4.4-4-8-10-8z"/><circle cx="7.5" cy="11.5" r="1"/><circle cx="11" cy="7.5" r="1"/><circle cx="15.5" cy="8.5" r="1"/>',
    "book": '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 5v16"/><path d="M9 7h6M9 11h6"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
    "brand": '<path d="M4 18 9 6l3 6 3-6 5 12"/><path d="M7.5 14h9"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "moon": '<path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z" fill="currentColor" stroke="none"/>',
    "tv": '<rect x="3" y="5" width="18" height="13" rx="2"/><path d="M8 21h8"/>',
    "microscope": '<path d="M6 21h7"/><path d="M9 21a5 5 0 0 0 5-5V9"/><path d="M12 9 9 6 6 9l3 3"/><circle cx="14.5" cy="6.5" r="2"/>',
    "chat": '<path d="M4 5h16v11H9l-5 4z"/><path d="M8 9h8M8 12h5"/>',
    "bank": '<path d="M3 9 12 4l9 5"/><path d="M5 9v9M9 9v9M15 9v9M19 9v9"/><path d="M3 21h18"/>',
    "trend-up": '<path d="M3 17l6-6 4 4 7-7"/><path d="M14 8h6v6"/>',
    "trend-down": '<path d="M3 7l6 6 4-4 7 7"/><path d="M14 16h6v-6"/>',
    "star": '<path d="M12 3l2.6 5.6 6 .7-4.4 4.1 1.2 6L12 16.8 6.6 19.4l1.2-6L3.4 9.3l6-.7z" fill="currentColor" stroke="none"/>',
    "fire": '<path d="M12 3c1 3-2 4-2 7a2 2 0 0 0 4 0c0-1 0-1 0-1 2 2 3 4 3 6a5 5 0 0 1-10 0c0-4 4-6 5-12z"/>',
    "compass": '<circle cx="12" cy="12" r="9"/><path d="M15.5 8.5 13 13l-4.5 2.5L11 11z" fill="currentColor" stroke="none"/>',
    "briefcase": '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M3 12h18"/>',
    "robot": '<rect x="5" y="8" width="14" height="11" rx="2"/><circle cx="9" cy="13" r="1.3" fill="currentColor" stroke="none"/><circle cx="15" cy="13" r="1.3" fill="currentColor" stroke="none"/><path d="M12 4v4M9 4h6"/>',
    "bulb": '<path d="M9 18h6"/><path d="M10 21h4"/><path d="M12 3a6 6 0 0 0-4 10.5c.7.7 1 1.3 1 2.5h6c0-1.2.3-1.8 1-2.5A6 6 0 0 0 12 3z"/>',
    "rocket": '<path d="M12 3c3 2 5 6 5 11l-3 3H10l-3-3c0-5 2-9 5-11z"/><circle cx="12" cy="10" r="1.6"/><path d="M9 19l-2 3M15 19l2 3"/>',
    "heart": '<path d="M12 20s-7-4.5-7-9a4 4 0 0 1 7-2 4 4 0 0 1 7 2c0 4.5-7 9-7 9z" fill="currentColor" stroke="none"/>',
    "pin": '<path d="M12 21s-6-5.3-6-10a6 6 0 1 1 12 0c0 4.7-6 10-6 10z"/><circle cx="12" cy="11" r="2.2"/>',
    "bell": '<path d="M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6z"/><path d="M10 19a2 2 0 0 0 4 0"/>',
    "link": '<path d="M9 15l6-6"/><path d="M10 7l1-1a4 4 0 0 1 6 6l-1 1"/><path d="M14 17l-1 1a4 4 0 0 1-6-6l1-1"/>',
    "check": '<path d="M5 13l4 4 10-11"/>',
    "warning": '<path d="M12 3 2 20h20z"/><path d="M12 10v5M12 17.5v.5"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
    "package": '<path d="M12 3 21 8v8l-9 5-9-5V8z"/><path d="M3 8l9 5 9-5M12 13v8"/>',
    "trophy": '<path d="M7 4h10v4a5 5 0 0 1-10 0z"/><path d="M7 5H4v2a3 3 0 0 0 3 3M17 5h3v2a3 3 0 0 1-3 3M9 14h6l1 6H8z"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 9h18M8 3v4M16 3v4"/>',
    "refresh": '<path d="M20 11a8 8 0 0 0-14-4M4 13a8 8 0 0 0 14 4"/><path d="M18 4v3h-3M6 20v-3h3"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "minus": '<path d="M5 12h14"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M14 6l4 4"/>',
    "zap": '<path d="M13 3 4 14h6l-1 7 9-11h-6z" fill="currentColor" stroke="none"/>',
    "lock": '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    "clipboard": '<rect x="6" y="4" width="12" height="17" rx="2"/><path d="M9 4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2"/><path d="M9 11h6M9 15h6"/>',
    "map": '<path d="M9 4 4 6v14l5-2 6 2 5-2V4l-5 2z"/><path d="M9 4v14M15 6v14"/>',
    "phone": '<path d="M5 4h4l2 5-3 2a12 12 0 0 0 5 5l2-3 5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/>',
    "flask": '<path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3"/><path d="M8 14h8"/>',
}

# emoji → 图标名 映射（顶栏/导航数据里残留的 emoji 自动转 SVG，未命中回退原 emoji）
_EMOJI_MAP: dict[str, str] = {
    "🏠": "home", "🎯": "target", "🌐": "globe", "📊": "chart-bar", "💰": "wallet",
    "⚙️": "gear", "🔧": "gear", "🔍": "search", "✦": "sparkles", "✨": "sparkles",
    "👤": "user", "🕘": "clock", "🎨": "palette", "📘": "book", "🛡": "shield",
    "📈": "trend-up", "📉": "trend-down", "📺": "tv", "🔬": "microscope", "💬": "chat",
    "🏦": "bank", "⭐": "star", "🔥": "fire", "🧭": "compass", "💼": "briefcase",
    "🤖": "robot", "💡": "bulb", "🚀": "rocket", "❤️": "heart", "📌": "pin",
    "🔔": "bell", "🔗": "link", "✅": "check", "⚠️": "warning", "📭": "mail",
    "📦": "package", "🏆": "trophy", "📅": "calendar", "🔄": "refresh", "➕": "plus",
    "➖": "minus", "✏️": "edit", "⚡": "zap", "🔒": "lock", "📋": "clipboard",
    "🗺️": "map", "📱": "phone", "🐑": "flask", "🧪": "flask", "📍": "pin",
    "🧭": "compass", "💹": "trend-up", "📎": "link", "📞": "phone",
}

_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\u2705\u26a0\ufe0f\u2728\u2757\u274c\u2716\u2795\u2796\u270f\u26d3\u2b50\u2049\u2139\u23f3\u23f0\u231b\u26ab\u26aa\u2b55\u25c0\u25b6\u23ef\u23ed\u23ee\u2728\u2757]",
)


def strip_emoji(text: str) -> str:
    """剥除字符串中所有 emoji（保留文字）。用于「emoji + 文案」组合标签的清洁渲染。"""
    if not text:
        return ""
    return _EMOJI_RE.sub("", str(text)).strip()


def svg_icon(name: str, size: int = 16, stroke_width: int = 2) -> str:
    """按名称返回内联 SVG 图标字符串（currentColor 描边，主题自适应）。

    未命中名称时回退为中性方块占位（绝不抛、绝不返回 emoji）。
    """
    inner = _ICONS.get(name)
    if inner is None:
        inner = '<rect x="4" y="4" width="16" height="16" rx="3"/>'
    return (
        f'<svg class="ss-ic" width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'fill="none" stroke="currentColor" stroke-width="{stroke_width}" '
        f'stroke-linecap="round" stroke-linejoin="round" '
        f'style="flex:none;vertical-align:middle" aria-hidden="true">{inner}</svg>'
    )


def render_nav_icon(icon: str, size: int = 16) -> str:
    """传入原 emoji（或图标名）→ 命中转 SVG，未命中安全回退原字符串。

    用于迁移导航/页头里残留的 emoji 图标，保证视觉统一且零破坏性。
    """
    if not icon:
        return ""
    icon = str(icon).strip()
    # 直接给图标名
    if icon in _ICONS:
        return svg_icon(icon, size=size)
    # 单 emoji → 映射
    if icon in _EMOJI_MAP:
        return svg_icon(_EMOJI_MAP[icon], size=size)
    # 含 emoji 前缀（如 "🎯 决策中枢" 这种不带，但保险处理）
    m = _EMOJI_RE.search(icon)
    if m and m.group() in _EMOJI_MAP:
        return svg_icon(_EMOJI_MAP[m.group()], size=size)
    # 未命中：原样返回（可能是文字/已为 SVG），不抛不静默吞
    return icon
