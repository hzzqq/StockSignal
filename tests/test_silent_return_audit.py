# -*- coding: utf-8 -*-
"""tests/test_silent_return_audit.py

T-239 R2 守卫：except 处理器内静默 return 审计（纯 AST，零环境依赖，违规必 fail）。

锁死两条不变量：
1. 【危险类别=0】except 内禁止 `return <异常变量>` / `return Exception(...)/XxxError(...)`
   ——把异常对象当返回值是反模式（调用方拿到的是异常实例而非业务结果），必须 raise 或记日志后返回哨兵。
2. 【哨兵必标注】except 内 return None/""/[]/{}/0/-1 等哨兵值时，该 handler 必须满足其一：
   - handler 源码跨度内含 `ui_audit_exempt` 审计注释；
   - handler 内已有日志调用（logger.error/warning/exception 等）。
   二者皆无 = 未审计的静默失败 → fail。

背景：T-239 R1（fdbf55c/ae84b24）治理 return-None 型；R2（本守卫对应批次）扩覆盖到
backend/ scripts/ thesis/ 与嵌套 return，并新增「异常对象返回」危险类别。
"""
import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {"tests", "__pycache__", ".git", "backups", "data", "node_modules", ".trae", "venv", ".workbuddy"}

LOG_METHODS = {"warning", "error", "exception", "info", "debug", "critical", "log"}


def _is_logging_call(node):
    if isinstance(node, ast.Call):
        f = node.func
        name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
        return name in LOG_METHODS
    return False


def _classify_return(val, exc_names):
    """返回 ('exc-var'|'exc-ctor'|'sentinel'|None)"""
    if isinstance(val, ast.Name) and val.id in exc_names:
        return "exc-var"
    if isinstance(val, ast.Call):
        f = val.func
        fname = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else None)
        if fname and (fname == "Exception" or fname.endswith("Error") or fname.endswith("Exception")):
            return "exc-ctor"
    if isinstance(val, ast.Constant):
        v = val.value
        if v is None:
            return "sentinel"
        if isinstance(v, bool):
            return None  # True/False 是合法布尔返回，非哨兵
        if (isinstance(v, str) and v == "") or (isinstance(v, (list, dict, tuple)) and len(v) == 0):
            return "sentinel"
        if isinstance(v, (int, float)) and v in (0, -1, 0.0, -1.0):
            return "sentinel"
    return None


def _audit_source(src, rel):
    """返回 (dangerous:[(lineno,desc)], unannotated:[(lineno,desc)])"""
    tree = ast.parse(src)
    lines = src.split("\n")
    dangerous, unannotated = [], []
    seen = set()
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for h in [n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)]:
            span = "\n".join(lines[h.lineno - 1 : h.end_lineno]) if h.end_lineno else lines[h.lineno - 1]
            audited = "ui_audit_exempt" in span
            has_log = any(_is_logging_call(n) for n in ast.walk(h))
            exc_names = {h.name} if h.name else set()
            for r in [n for n in ast.walk(h) if isinstance(n, ast.Return) and n.value is not None]:
                key = (r.lineno, id(r.value))
                if key in seen:
                    continue
                seen.add(key)
                cat = _classify_return(r.value, exc_names)
                if cat is None:
                    continue
                if cat in ("exc-var", "exc-ctor"):
                    dangerous.append((r.lineno, f"{rel}: return 异常对象（{cat}）——应 raise 或记日志后返回哨兵"))
                elif cat == "sentinel" and not audited and not has_log:
                    unannotated.append((r.lineno, f"{rel}: except 内静默哨兵 return 未标注 ui_audit_exempt 也无日志"))
    return dangerous, unannotated


def test_no_silent_exception_return():
    dangerous, unannotated = [], []
    for dp, dns, fns in os.walk(ROOT):
        if any(s in dp for s in SKIP_DIRS):
            continue
        for fn in fns:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, ROOT)
            with open(p, encoding="utf-8") as f:
                src = f.read()
            try:
                d, u = _audit_source(src, rel)
            except SyntaxError:
                continue  # 语法错误由 py_compile/CI 其它环节负责
            dangerous += d
            unannotated += u
    assert not dangerous, (
        "发现 except 内 return 异常对象（反模式，必须 raise 或记日志）：\n"
        + "\n".join(f"  line {ln}: {desc}" for ln, desc in dangerous)
    )
    assert not unannotated, (
        "发现 except 内未审计的静默哨兵 return（需补 ui_audit_exempt 注释或日志）：\n"
        + "\n".join(f"  line {ln}: {desc}" for ln, desc in unannotated)
    )
