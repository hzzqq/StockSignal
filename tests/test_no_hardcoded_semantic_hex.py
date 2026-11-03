# -*- coding: utf-8 -*-
"""tests/test_no_hardcoded_semantic_hex.py

Phase A 设计系统落地守卫：
1. pages/ 交易屏不得再硬编码 A 股语义色裸字面量 #ff4d4f(红涨) / #00d486(绿跌)，
   必须走 modules.colors.UP_COLOR / DOWN_COLOR。
2. modules/ui_theme.py 的 docs/report-body 作用域必须把 --buy/--sell 改名
   --doc-up/--doc-down（绿涨红跌双轨），且 _DARK_CSS 的 --buy:#ff4d4f（A股红涨）必须保留。

排除项：
- modules/colors.py 的常量定义（UP_COLOR/DOWN_COLOR 本身就是真理源）。
- 报告体有意双轨 #009e60/#dc2626（绿涨红跌），不计入交易屏语义 hex 扫描。
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = os.path.join(ROOT, "pages")
UI_THEME = os.path.join(ROOT, "modules", "ui_theme.py")

SEMANTIC_HEX = re.compile(r"#(ff4d4f|00d486)", re.IGNORECASE)
REPORT_HEX = re.compile(r"#(009e60|dc2626)", re.IGNORECASE)


def test_no_hardcoded_semantic_hex():
    """pages/ 交易屏不得再出现 #ff4d4f / #00d486 裸字面量。"""
    hits = []
    for dirpath, _, files in os.walk(PAGES):
        if "pycache" in dirpath:
            continue
        for fn in files:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(dirpath, fn)
            with open(p, encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    if SEMANTIC_HEX.search(line) and not REPORT_HEX.search(line):
                        hits.append((fn, i, line.strip()))
    assert not hits, (
        "发现交易屏仍硬编码 A 股语义色（应改用 colors.UP_COLOR / colors.DOWN_COLOR）：\n"
        + "\n".join(f"  {fn}:{i}  {ln}" for fn, i, ln in hits)
    )


def test_ui_theme_docs_scope_renamed():
    """ui_theme.py docs 域 --buy/--sell 已改名 --doc-up/--doc-down；
    _DARK_CSS 的 --buy:#ff4d4f（A股红涨）必须保留，不得误改。"""
    with open(UI_THEME, encoding="utf-8") as f:
        src = f.read()
    # docs 域双轨绿涨红跌已改名：旧的 --buy:#009e60 / --sell:#dc2626 不应存在
    assert "--buy:#009e60" not in src, "ui_theme.py docs 域 --buy:#009e60 未改名 --doc-up"
    assert "--sell:#dc2626" not in src, "ui_theme.py docs 域 --sell:#dc2626 未改名 --doc-down"
    # 新命名已落地
    assert "--doc-up:#009e60" in src, "ui_theme.py 缺少 --doc-up 定义"
    assert "--doc-down:#dc2626" in src, "ui_theme.py 缺少 --doc-down 定义"
    # _DARK_CSS 的 A股红涨语义（--buy:#ff4d4f）必须保留，不得误删/误改
    assert "--buy:#ff4d4f" in src, "_DARK_CSS 的 --buy:#ff4d4f（A股红涨）被误改"
