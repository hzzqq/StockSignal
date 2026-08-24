"""AST 安全转换：给裸吞 except 块接 logger。

规则（踩坑后修正版）：
- 只处理 `except Exception` / `except:` 且处理器内**无** logging / 无 raise / 无 print 的块。
- 自动探测模块实际日志器名（logger / _logger / log，或 logging.getLogger 赋值目标）。
- 模块无日志器则在其顶部 import logging 后补 `logger = logging.getLogger(__name__)`。
- 处理器无 `as e` 则补 `as e`，插入 `LOGGER.warning(f"[{tag}] 处理异常: {e}")`。
- 不删原有 `pass`（若块内只剩 pass，保留，避免结构破坏）。
仅做 AST 文本变换，不运行被改模块。
"""
import ast
import re
import sys


def detect_logger_name(src):
    """返回模块实际日志器名（logger/_logger/log/...），None 表示无。"""
    for m in re.finditer(r"^(\w+)\s*=\s*logging\.getLogger", src, re.M):
        return m.group(1)
    # 退化：模块内是否直接用了 logger / _logger / log 变量
    for name in ("_logger", "logger", "log"):
        if re.search(rf"\b{name}\.(debug|info|warning|error|exception|critical)\b", src):
            return name
    return None


def transform(path, tag):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    logger_name = detect_logger_name(src)
    need_inject_logger_def = False
    if logger_name is None:
        logger_name = "logger"
        need_inject_logger_def = True

    inserts = []  # (except_node_lineno, asname_present, body_has_only_pass)
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None or (isinstance(node.type, ast.Name) and node.type.id == "Exception"):
                body = node.body
                if not body:
                    continue
                has_log = any(
                    isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr in ("debug", "info", "warning", "error", "exception", "critical")
                    for n in ast.walk(ast.Module(body=body, type_ignores=[]))
                )
                has_raise = any(isinstance(n, ast.Raise) for n in ast.walk(ast.Module(body=body, type_ignores=[])))
                has_print = any(
                    isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "print"
                    for n in ast.walk(ast.Module(body=body, type_ignores=[]))
                )
                if has_log or has_raise or has_print:
                    continue
                asname = node.name  # None 表示 except Exception: （无 as）
                inserts.append((node.lineno, asname is not None))

    if not inserts:
        return False, "no bare except"

    # 从后往前插入，避免行号偏移
    lines = src.splitlines(keepends=True)
    for lineno, has_as in sorted(inserts, key=lambda x: -x[0]):
        indent_match = re.match(r"(\s*)", lines[lineno - 1])
        base_indent = indent_match.group(1)
        inner = base_indent + "    "
        log_line = f'{inner}{logger_name}.warning(f"[{tag}] 处理异常: {{e}}")\n'
        if not has_as:
            # 把 `except Exception:` 改为 `except Exception as e:`
            orig = lines[lineno - 1].rstrip("\n")
            # 去掉末尾冒号（如有），再拼 " as e:"
            orig = orig.rstrip().rstrip(":")
            lines[lineno - 1] = orig + " as e:\n"
        # 在 except 行后插入 log（保留原有 body）
        lines.insert(lineno, log_line)

    new_src = "".join(lines)
    if need_inject_logger_def:
        # 在 import logging 后补 logger 定义
        if "import logging" in new_src:
            new_src = new_src.replace(
                "import logging\n",
                "import logging\nlogger = logging.getLogger(__name__)\n",
                1,
            )
        else:
            new_src = "import logging\nlogger = logging.getLogger(__name__)\n" + new_src

    open(path, "w", encoding="utf-8").write(new_src)
    return True, f"patched {len(inserts)} blocks"


if __name__ == "__main__":
    p = sys.argv[1]
    tag = sys.argv[2] if len(sys.argv) > 2 else p.split("/")[-1].replace(".py", "")
    ok, msg = transform(p, tag)
    print(f"{p}: {msg}")
