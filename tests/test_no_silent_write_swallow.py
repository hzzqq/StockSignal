"""
T-160 守卫：写盘失败不得静默吞掉（except Exception: pass）。

【为什么只盯「写盘」】
  147 处 except...pass 里，UI 渲染兜底、回调保护等大多是可接受的宽捕获；
  但「写盘失败被吞」属于 R2/R7 同类缺陷族——数据/偏好/日志实际没落盘，
  界面与调用方却以为成功，是最难排查的一类静默数据丢失。
  本守卫用 AST 定点打击：try 块内含写盘调用（write/dump/to_csv/commit/
  open(...,'w')...）且 except 分支纯 pass（连 debug 日志都不留）→ 红。

  修复口径（与既有 backend/tests/test_no_silent_swallow.py 一致）：
  至少 logger.debug/warning 留痕，或改用具体异常类型窄捕获后如实处理。
"""
from __future__ import annotations

import ast
import glob
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 写盘/持久化调用白名单：方法名（attr）或函数名（id）
# pandas to_csv/to_excel/... 单独处理：仅带路径参数才算落盘（见 _is_write_call）

DIRS = ["modules", "pages", "backend"]


def _call_name(node: ast.Call):
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _is_write_call(call: ast.Call) -> bool:
    name = _call_name(call)
    if name in {"write", "writelines", "dump", "savefig", "commit", "flush",
                "save_to_local_storage", "save_prefs", "atomic_write"}:
        return True
    # pandas 风格导出：仅当指定了目标路径才算落盘；
    # 无 path（path_or_buf=None）是内存转换（如供 st.download_button），不算
    if name in {"to_csv", "to_excel", "to_json", "to_parquet", "to_pickle"}:
        if call.args:
            return True  # 位置参数 = 路径
        return any(kw.arg in {"path_or_buf", "path", "fname"} for kw in call.keywords)
    # open(path, 'w'/'a'/'x') —— 写模式打开
    if name == "open" and len(call.args) >= 2:
        mode = call.args[1]
        if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
            if any(c in mode.value for c in "wax"):
                return True
    return False


def _is_broad(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True  # 裸 except:
    t = handler.type
    names = []
    for n in (t.elts if isinstance(t, ast.Tuple) else [t]):
        if isinstance(n, ast.Name):
            names.append(n.id)
        elif isinstance(n, ast.Attribute):
            names.append(n.attr)
    # Exception/BaseException 及常见「宽」异常族
    return any(n in {"Exception", "BaseException"} for n in names)


def _is_silent(handler: ast.ExceptHandler) -> bool:
    """body 只含 pass / 纯字符串表达式（docstring）→ 静默。"""
    for stmt in handler.body:
        if isinstance(stmt, ast.Pass):
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            continue  # docstring
        return False
    return True


def _scan(path: str):
    bad = []
    try:
        tree = ast.parse(open(path, encoding="utf-8").read())
    except Exception:
        return bad
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        has_write = any(
            isinstance(n, ast.Call) and _is_write_call(n)
            for n in ast.walk(ast.Module(body=node.body, type_ignores=[]))
        )
        if not has_write:
            continue
        for handler in node.handlers:
            if _is_broad(handler) and _is_silent(handler):
                bad.append((path, handler.lineno))
    return bad


def test_write_failures_are_not_silently_swallowed():
    bad = []
    for d in DIRS:
        for path in sorted(glob.glob(os.path.join(ROOT, d, "**", "*.py"), recursive=True)):
            rel = os.path.relpath(path, ROOT).replace("\\", "/")
            if "/tests/" in rel or rel.endswith("conftest.py"):
                continue
            bad.extend(_scan(path))
    assert not bad, (
        "发现「写盘失败被静默吞掉」——数据/偏好/日志可能实际没落盘却无人知晓。\n"
        "至少留痕（logger.debug/warning）或窄化捕获后如实处理（T-160 口径）：\n"
        + "\n".join(f"  {r.replace(chr(92), '/')}:{ln}" for r, ln in bad)
    )
