"""
backend/services/pinyin_util.py
-------------------------------
中文 -> 拼音首字母 / 全拼 转换工具。
依赖 pypinyin，无 pypinyin 时安全降级为空串。
"""
from __future__ import annotations

try:
    from pypinyin import lazy_pinyin, Style
    _HAS_PYPINYIN = True
except ImportError:
    _HAS_PYPINYIN = False


def to_initials(text: str) -> str:
    """'平安银行' -> 'payy'"""
    if not _HAS_PYPINYIN or not text:
        return ""
    parts = lazy_pinyin(text, style=Style.FIRST_LETTER)
    return "".join(p.lower() for p in parts if p)


def to_full_pinyin(text: str) -> str:
    """'平安银行' -> 'pinganyinhang'"""
    if not _HAS_PYPINYIN or not text:
        return ""
    parts = lazy_pinyin(text, style=Style.NORMAL)
    return "".join(parts).lower()
