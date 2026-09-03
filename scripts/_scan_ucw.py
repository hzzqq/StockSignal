# -*- coding: utf-8 -*-
"""只读扫描：全仓 use_container_width 调用点分布（元素类型 × 值 × 是否与原 width 共现）。"""
import ast
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "build", "dist"}


def iter_py_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


def element_name(call_node):
    """从 Call 节点提取元素名，如 st.plotly_chart -> plotly_chart。"""
    f = call_node.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return "<expr>"


def literal_desc(node):
    """把字面量节点描述成可读字符串。"""
    if isinstance(node, ast.Constant):
        v = node.value
        if isinstance(v, bool):
            return "True" if v else "False"
        if isinstance(v, int):
            return f"int({v})"
        if isinstance(v, str):
            return f"str({v!r})"
        return f"{type(v).__name__}({v!r})"
    if isinstance(node, ast.Name):
        return f"Name({node.id})"
    if isinstance(node, ast.Attribute):
        return f"Attr({node.attr})"
    return type(node).__name__


stats = Counter()
by_elem = defaultdict(Counter)
examples = defaultdict(list)
total = 0
files_hit = 0

for fp in iter_py_files():
    try:
        src = open(fp, encoding="utf-8").read()
    except Exception:
        continue
    if "use_container_width" not in src:
        continue
    try:
        tree = ast.parse(src, fp)
    except SyntaxError as e:
        print(f"!! PARSE FAIL {fp}: {e}")
        continue
    hit_in_file = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "use_container_width":
                continue
            total += 1
            hit_in_file += 1
            elem = element_name(node)
            val = literal_desc(kw.value)
            # 是否同时指定了 width
            width_kw = next((k for k in node.keywords if k.arg == "width"), None)
            co = literal_desc(width_kw.value) if width_kw is not None else "NONE"
            key = (elem, val, co)
            stats[key] += 1
            by_elem[elem][val] += 1
            if width_kw is not None:
                rel = os.path.relpath(fp, ROOT)
                examples["CO_SPEC"].append(f"{rel}:{node.lineno} {elem} ucw={val} width={co}")
    if hit_in_file:
        files_hit += 1

print(f"=== 总计 {total} 处 / {files_hit} 个文件 ===\n")
print("--- 按 (元素, ucw值, 共现width) 分组 ---")
for (elem, val, co), n in sorted(stats.items(), key=lambda x: (-x[1], x[0])):
    flag = "  <<< 需特判" if co != "NONE" else ""
    print(f"{n:5d}  {elem:28s} ucw={val:12s} width={co}{flag}")

print("\n--- 各元素 True/False 小计 ---")
for elem, c in sorted(by_elem.items(), key=lambda x: -sum(x[1].values())):
    print(f"{sum(c.values()):5d}  {elem:28s} {dict(c)}")

if examples["CO_SPEC"]:
    print(f"\n--- 与 width 共现的调用点 ({len(examples['CO_SPEC'])} 处) ---")
    for line in examples["CO_SPEC"][:40]:
        print("   " + line)
else:
    print("\n--- 与 width 共现的调用点：无（全部可安全机械替换） ---")

# 非字面量（无法静态判定）的调用点
print("\n--- 非字面量 ucw 值（无法静态判定，需人工） ---")
nonlit = [(e, v, c) for (e, v, c), n in stats.items() if not v.startswith(("True", "False"))]
if nonlit:
    for e, v, c in nonlit:
        print(f"   {e} ucw={v} width={c}")
else:
    print("   无")
