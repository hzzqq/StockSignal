# -*- coding: utf-8 -*-
"""AST 安全改写：把 Streamlit 弃用参数 use_container_width 迁移到 width。

官方 shim 语义（已逐元素从 Streamlit 1.58.0 源码取证，全元素一致）：
    if use_container_width: width = "stretch"
    elif not isinstance(width, int): width = "content"

因此忠实等价替换为：
    use_container_width=True   ->  width="stretch"
    use_container_width=False  ->  width="content"
    use_container_width=EXPR   ->  width=("stretch" if EXPR else "content")

跳过规则：
  - back_to_top_button（项目自定义函数 modules/scroll_nav.py:104，其 use_container_width
    是自家参数控制 CSS width:100%，不在 Streamlit 弃用范围）
  - 非 Streamlit 元素调用

用法：
    python scripts/_codemod_ucw.py           # dry-run，仅列改动计划
    python scripts/_codemod_ucw.py --apply   # 真正写盘
"""
import ast
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "build", "dist"}
SKIP_FILES = {"_codemod_ucw.py", "_scan_ucw.py"}
# 项目自定义函数，其 use_container_width 是自家参数，非 Streamlit 弃用参数
SKIP_ELEMENTS = {"back_to_top_button"}

APPLY = "--apply" in sys.argv


def iter_py_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".py") and fn not in SKIP_FILES:
                yield os.path.join(dirpath, fn)


# ───────── 字节偏移 → 字符索引（含 CJK 的 .py 必须换算，否则插错位置）─────────
def line_byte_starts(src):
    starts = [0]
    for line in src.split("\n"):
        starts.append(starts[-1] + len(line.encode("utf-8")) + 1)
    return starts


def byte_to_char(src, byte_pos):
    if byte_pos <= 0:
        return 0
    b = 0
    for i, ch in enumerate(src):
        if b >= byte_pos:
            return i
        b += len(ch.encode("utf-8"))
    return len(src)


def element_name(call_node):
    f = call_node.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return None


def span_of_kwarg_removal(src, start, end):
    """删除一个关键字参数时，连带处理逗号，避免留下 `f(a, , b)` 或 `f(, a)`。"""
    j = start - 1
    while j >= 0 and src[j] in " \t\r\n":
        j -= 1
    if j >= 0 and src[j] == ",":
        return j, end  # 删前导逗号 + kwarg
    k = end
    while k < len(src) and src[k] in " \t\r\n":
        k += 1
    if k < len(src) and src[k] == ",":
        return start, k + 1  # 删 kwarg + 后随逗号
    return start, end


def plan_file(fp):
    """返回 (edits, notes)；edits = [(start_char, end_char, new_text, lineno)]。"""
    edits, notes = [], []
    src = open(fp, encoding="utf-8").read()
    if "use_container_width" not in src:
        return edits, notes
    try:
        tree = ast.parse(src, fp)
    except SyntaxError as e:
        notes.append(f"PARSE-FAIL 跳过: {e}")
        return edits, notes

    lb = line_byte_starts(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        elem = element_name(node)
        if elem is None or elem in SKIP_ELEMENTS:
            continue
        kw_ucw = next((k for k in node.keywords if k.arg == "use_container_width"), None)
        if kw_ucw is None:
            continue
        kw_width = next((k for k in node.keywords if k.arg == "width"), None)

        # 起止字符索引（字节偏移换算）
        def to_char(n):
            return byte_to_char(src, lb[n.lineno - 1] + n.col_offset)

        start = to_char(kw_ucw)
        # ⚠️ 必须取 keyword 节点自身的结束位置，而非 kw_ucw.value 的结束位置：
        # 形如 use_container_width=(a == b) 时，value(Compare) 在右括号「之前」就结束，
        # 用 value 的 end 会残留一个 ')' → 替换后变成双闭括号 → SyntaxError。
        # keyword 节点覆盖完整 `name=value`（含值自身的括号），才是正确替换区间。
        end = byte_to_char(src, lb[kw_ucw.end_lineno - 1] + kw_ucw.end_col_offset)

        # ── 情形 A：同时存在 width= ──
        if kw_width is not None:
            ucw_true = isinstance(kw_ucw.value, ast.Constant) and kw_ucw.value.value is True
            w_stretch = (
                isinstance(kw_width.value, ast.Constant) and kw_width.value.value == "stretch"
            )
            if ucw_true and w_stretch:
                # ucw=True 的结果就是 "stretch"，与现有 width 一致 → 直接删 ucw，零行为变化
                s, e = span_of_kwarg_removal(src, start, end)
                edits.append((s, e, "", kw_ucw.lineno))
                notes.append(f"L{kw_ucw.lineno} {elem}: 删冗余 ucw=True（width 已是 stretch）")
            else:
                notes.append(
                    f"L{kw_ucw.lineno} {elem}: ⚠️ ucw 与 width 共现且非 (True,'stretch')，人工处理，跳过"
                )
            continue

        # ── 情形 B：仅 ucw ──
        v = kw_ucw.value
        if isinstance(v, ast.Constant) and isinstance(v.value, bool):
            new = 'width="stretch"' if v.value else 'width="content"'
        else:
            expr = ast.unparse(v)
            new = f'width=("stretch" if {expr} else "content")'
        edits.append((start, end, new, kw_ucw.lineno))
        notes.append(f"L{kw_ucw.lineno} {elem}: {ast.unparse(kw_ucw)[:44]} -> {new}")

    return edits, notes


def main():
    stat = Counter()
    plan_by_file = {}
    for fp in iter_py_files():
        edits, notes = plan_file(fp)
        if edits or notes:
            plan_by_file[fp] = (edits, notes)
        stat["files_with_hits"] += 1 if (edits or notes) else 0
        stat["edits"] += len(edits)
        stat["notes"] += len(notes)

    print(f"扫描完成：{stat['files_with_hits']} 个文件有命中，计划 {stat['edits']} 处改写\n")
    if not APPLY:
        for fp, (edits, notes) in sorted(plan_by_file.items()):
            print(f"── {os.path.relpath(fp, ROOT)}  ({len(edits)} 改)")
            for n in notes:
                print(f"     {n}")
        print(f"\n[DRY-RUN] 未写盘。确认无误后加 --apply 执行。")
        return

    # ── 应用：逐文件、降序偏移、写前 ast.parse 校验 ──
    changed, failed = 0, 0
    for fp, (edits, notes) in sorted(plan_by_file.items()):
        if not edits:
            continue
        src = open(fp, encoding="utf-8").read()
        new_src = src
        for s, e, new, _ln in sorted(edits, key=lambda x: -x[0]):
            if not (0 <= s <= e <= len(new_src)):
                print(f"!! 越界跳过 {fp}: [{s},{e}]")
                failed += 1
                continue
            new_src = new_src[:s] + new + new_src[e:]
        try:
            ast.parse(new_src, fp)  # 语法护栏：坏则绝不写盘
        except SyntaxError as e:
            print(f"!! 语法校验失败，跳过写盘 {fp}: {e}")
            failed += 1
            continue
        with open(fp, "w", encoding="utf-8", newline="") as f:
            f.write(new_src)
        changed += 1
    print(f"\n[APPLY] 已改写 {changed} 个文件，失败/跳过 {failed} 个。")


if __name__ == "__main__":
    main()
