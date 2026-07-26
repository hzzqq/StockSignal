"""
modules/market_utils.py
=======================
A 股代码 → 交易所 / 板块 的**统一**判定工具（DRY 收口）。

此前板块/交易所判定散落在 search_ui._derive_tag、search_ui._guess_market、
analysis_engine._board 等多处，前缀规则各写一份、易漂移。此模块集中一处，
供各调用方委托，保证同一套代码前缀约定。

三个公开函数保留各自历史输出语义，互不改变既有行为：
- guess_exchange(code) -> "SH" | "SZ" | ""           （交易所，用于行情源前缀）
- short_tag(code)      -> 科创板/北交所/沪B/深B/创业板/沪A/深A/—  （搜索下拉短标签）
- board_name(code)     -> 沪市主板/深市主板/创业板/科创板/北交所/A股  （分析用板块全名）
"""
from __future__ import annotations


def _digits(code) -> str:
    """规整为纯数字字符串；非数字返回空串。"""
    s = str(code).strip() if code is not None else ""
    return s if s.isdigit() else ""


def guess_exchange(code) -> str:
    """由代码首位推交易所：6→SH，0/3→SZ，其它→""。"""
    s = _digits(code)
    if not s:
        return ""
    if s.startswith("6"):
        return "SH"
    if s.startswith("0") or s.startswith("3"):
        return "SZ"
    return ""


def short_tag(code) -> str:
    """搜索下拉用短标签（含 B 股 / 科创板 CDR）。非法代码返回「—」。"""
    s = _digits(code)
    if not s:
        return "—"
    if s.startswith(("688", "689")):  # 689 为科创板 CDR
        return "科创板"
    if s.startswith("8") or s.startswith("4"):
        return "北交所"
    if s.startswith("9"):  # 900xxx 沪市 B 股
        return "沪B"
    if s.startswith("2"):  # 200xxx 深市 B 股
        return "深B"
    if s.startswith("3"):
        return "创业板"
    if s.startswith("6"):
        return "沪A"
    if s.startswith("0"):
        return "深A"
    return "—"


def board_name(code) -> str:
    """分析用板块全名。保持 analysis_engine._board 历史输出（else→A股）。"""
    s = str(code)
    if s.startswith("60"):
        return "沪市主板"
    if s.startswith("00"):
        return "深市主板"
    if s.startswith("30"):
        return "创业板"
    if s.startswith("68"):
        return "科创板"
    if s.startswith(("8", "4")):
        return "北交所"
    return "A股"
