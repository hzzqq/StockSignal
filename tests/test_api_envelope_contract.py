"""tests/test_api_envelope_contract.py

锁死后端安全基线：**所有 /api 路由的 HTTP 响应都必须经过统一信封
``utils.response.ok / fail``（或 ``abort`` / ``redirect``），严禁直接
``return {...}`` / ``jsonify(...)`` / ``make_response(...)`` 把裸 JSON 或
HTML 泄露给用户。

用 AST 在源码层扫描 ``backend/api/**`` 下所有被 Flask 路由装饰的函数，
断言其每个 ``return`` 都不是裸 dict/list 或裸 jsonify/make_response/Response
调用。这是「源码级防回退」测试：即使某个路由改坏，CI/本地也能立刻发现，
无需等到运行时 500 或 HTML 泄露才暴露。

2026-08-28 新增（Cycle 60）：补齐「响应信封」这一安全基线的回归护栏。
"""
import ast
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROUTE_DECOR = ("route", "get", "post", "put", "delete", "patch")
# 这些返回是被允许的（非裸 JSON/HTML 信封外泄）
ALLOWED_RETURN_CALLEES = {"ok", "fail", "abort", "redirect"}


def _is_route(node):
    for d in node.decorator_list:
        if isinstance(d, ast.Call):
            f = d.func
            if isinstance(f, ast.Attribute) and f.attr in ROUTE_DECOR:
                return True
            if isinstance(f, ast.Name) and f.id in ROUTE_DECOR:
                return True
    return False


def _callee_name(call):
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def test_all_api_routes_use_envelope():
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "api")
    violations = []
    for path in glob.glob(os.path.join(root, "**", "*.py"), recursive=True):
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except Exception as e:  # pragma: no cover
            raise AssertionError(f"无法解析 {path}: {e}")
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not _is_route(node):
                continue
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Return) or sub.value is None:
                    continue
                v = sub.value
                # 裸 dict / list 字面量 → 违例
                if isinstance(v, (ast.Dict, ast.List)):
                    violations.append((path, node.name, sub.lineno, "raw dict/list"))
                    continue
                # 裸 jsonify / make_response / Response 调用 → 违例
                if isinstance(v, ast.Call):
                    callee = _callee_name(v)
                    if callee in ("jsonify", "make_response", "Response"):
                        violations.append((path, node.name, sub.lineno, f"raw {callee}"))
                        continue
                    # 允许的 callee（ok/fail/abort/redirect）通过
                    if callee in ALLOWED_RETURN_CALLEES:
                        continue
                    # 其它调用（如 return some_var、return build_resp()）允许——无法在静态层判定
                    continue
                # 其它非调用返回值（变量、三元、字面量字符串等）允许
                continue
    assert not violations, (
        "发现未走统一信封的 API 路由返回（应改为 response.ok/fail）:\n"
        + "\n".join(f"  {p}:{ln} {n}() -> {kind}" for p, n, ln, kind in violations)
    )
