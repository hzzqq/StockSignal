"""全站锁定：禁止 8 位 hex 颜色字面量（RGBA 缩写 bug 的回归护栏）。

迭代20 已根治「#rrggbb22 这类 8 位 hex 在 Plotly 中非法导致配色/样式异常」的隐患。
本测试扫描 modules/ 与 pages/ 所有 .py，确保不出现 8 位 hex（及 4/5 位非法长度）。
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 排除 HTML 实体（如 &#9660; 箭头）中的 #，只盯颜色字面量
_HEX8 = re.compile(r"(?<!\&)#[0-9a-fA-F]{8}(?![0-9a-fA-F])")
_HEX_BAD = re.compile(r"(?<!\&)#[0-9a-fA-F]{4,5}(?![0-9a-fA-F])")


def _py_files():
    for base in ("modules", "pages"):
        d = os.path.join(ROOT, base)
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if name.endswith(".py") and name != "__init__.py":
                yield os.path.join(d, name)


def test_no_8digit_hex_colors():
    bad = []
    for fp in _py_files():
        with open(fp, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if _HEX8.search(line):
                    bad.append((os.path.relpath(fp, ROOT), i, line.strip()[:80]))
    assert not bad, f"发现8位hex(非法RGBA缩写)残留: {bad[:5]}"


def test_no_4or5_digit_hex_colors():
    bad = []
    for fp in _py_files():
        with open(fp, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if _HEX_BAD.search(line):
                    bad.append((os.path.relpath(fp, ROOT), i, line.strip()[:80]))
    assert not bad, f"发现4/5位非法hex: {bad[:5]}"
