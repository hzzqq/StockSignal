"""修复 8-25 AST 批量清零引入的第二个 bug：

_ast_add_logger.py 在向 `except Exception as exc:`（变量非 e）的块插入
`logger.warning(f"[tag] 处理异常: {e}")` 时，硬编码了 `{e}`，导致原变量名
（exc/err/ex）未定义 -> NameError。

本脚本用 AST 精确找到每个 ExceptHandler 的真实变量名，若其块内的
`logger.warning(f"...{e}")` 引用了不存在的 `e`，则改写为真实变量名。

用法：python scripts/_fix_logger_var.py
"""
import ast
import glob
import sys


def _walk_no_nested_func(node):
    """遍历 node 子节点，但不进入嵌套 def/class（避免误判作用域）。"""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        yield child
        yield from _walk_no_nested_func(child)


def _fix_src(src: str):
    tree = ast.parse(src)
    fixes = []  # (lineno, real_var)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        var = node.name  # None 或 'exc' / 'err' 等
        if var is None or var == "e":
            # 裸 except: 或 except ... as e: -> 脚本补的 {e} 合法，跳过
            continue
        # 在该 except 块（不含嵌套函数）内找 logger.warning(f"...{e}")
        for stmt in _walk_no_nested_func(node):
            if (
                isinstance(stmt, ast.Call)
                and isinstance(stmt.func, ast.Attribute)
                and stmt.func.attr == "warning"
                and stmt.args
                and isinstance(stmt.args[0], ast.JoinedStr)
            ):
                for v in stmt.args[0].values:
                    if (
                        isinstance(v, ast.FormattedValue)
                        and isinstance(v.value, ast.Name)
                        and v.value.id == "e"
                    ):
                        fixes.append((stmt.lineno, var))
                        break
    if not fixes:
        return src, 0
    lines = src.split("\n")
    for lineno, real_var in fixes:
        lines[lineno - 1] = lines[lineno - 1].replace("{e}", "{" + real_var + "}", 1)
    return "\n".join(lines), len(fixes)


def main():
    total = 0
    for f in sorted(glob.glob("modules/*.py")):
        src = open(f, encoding="utf-8").read()
        new_src, n = _fix_src(src)
        if n:
            open(f, "w", encoding="utf-8").write(new_src)
            print(f"{f}: {n} 处 {{{{e}}}} -> {{{{'exc/err'}}}}")
            total += n
    print(f"=== 共修复 {total} 处变量名不匹配 ===")


if __name__ == "__main__":
    main()
