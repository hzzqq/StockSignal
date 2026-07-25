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


def _normalize_parts(parts) -> list:
    """把 pypinyin 的分词结果清洗为小写、无空白的片段。

    隐性缺陷修复：pypinyin 会把原文里的空格/标点原样返回（如 ``' 平安银行 '``
    得到 ``[' ', 'p', 'a', 'y', 'h', ' ']``），而旧实现仅用 ``if p`` 过滤——
    空格字符串是真值，不会被剔除，导致首尾/内嵌空格泄漏到拼音结果，
    破坏了 stock_service 里的精确拼音匹配（``pi == q`` 永远对不上）。
    """
    out = []
    for p in parts:
        p = (p or "").strip().lower()
        if p and not p.isspace():
            out.append(p)
    return out


def to_initials(text: str) -> str:
    """'平安银行' -> 'payy'（已剔除空格/空白片段）"""
    if not _HAS_PYPINYIN or not text:
        return ""
    parts = lazy_pinyin(text, style=Style.FIRST_LETTER)
    return "".join(_normalize_parts(parts))


def to_full_pinyin(text: str) -> str:
    """'平安银行' -> 'pinganyinhang'（已剔除空格/空白片段）"""
    if not _HAS_PYPINYIN or not text:
        return ""
    parts = lazy_pinyin(text, style=Style.NORMAL)
    return "".join(_normalize_parts(parts))


def search_key(text: str) -> str:
    """生成用于搜索/去重的归一化拼音键：全拼 + '|' + 首字母。

    新能力：stock_service 等可按此键做大小写/空格无关的模糊匹配与去重，
    避免每次现拼。无 pypinyin 时安全降级为空串。
    """
    if not _HAS_PYPINYIN or not text:
        return ""
    return f"{to_full_pinyin(text)}|{to_initials(text)}"


def matches(text: str, query: str) -> bool:
    """判断 query 是否命中 text（原始名 / 全拼 / 首字母 / 拼音键均可）。

    新能力：统一「名称 or 拼音」的包含匹配判断，供前端/搜索复用。
    query 会被小写化、去空白后比较。
    """
    if not text or not query:
        return False
    q = query.strip().lower()
    if not q:
        return False
    raw = (text or "").lower()
    if q in raw:
        return True
    if _HAS_PYPINYIN:
        full = to_full_pinyin(text)
        init = to_initials(text)
        return q in full or q in init or q in search_key(text)
    return False
