"""tests/test_api_auth_coverage.py

锁死后端鉴权基线：**``backend/api/**`` 下每一个 Flask 路由都必须显式携带
鉴权装饰器（``@jwt_required`` 或 ``@admin_required``）**。

为什么只扫 ``backend/api/``：
- ``backend/auth/routes.py`` 里的登录/注册/刷新本身就是「未认证入口」，刻意不鉴权；
- ``backend/admin_ui.py`` 是独立 HTML 后台，不走 /api 蓝图；
- 因此 ``backend/api/`` 是「必须全部鉴权」的受保护面。

这是「源码级防回退」测试：将来任何人新增 /api 路由却忘了加 @jwt_required，
本测试立刻失败，而不用等到线上出现越权（IDOR / 数据泄露）才被发现。

若将来确实需要开放某个公开 /api 端点（例如健康检查），请把它加入
``PUBLIC_ALLOWLIST`` 并在注释中写明原因——即「显式登记」而非「默默裸奔」。

2026-08-28 新增（Cycle 62）。
"""
import ast
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

AUTH_DECORATORS = {"jwt_required", "admin_required"}
ROUTE_METHODS = ("route", "get", "post", "put", "delete", "patch")

# 显式登记的公开端点（当前为空：backend/api 全量鉴权）。
# 新增公开端点时必须同时在此登记 + 写明原因。
PUBLIC_ALLOWLIST = set()


def _decorator_names(node):
    names = []
    for d in node.decorator_list:
        f = d.func if isinstance(d, ast.Call) else d
        if isinstance(f, ast.Attribute):
            names.append(f.attr)
        elif isinstance(f, ast.Name):
            names.append(f.id)
    return names


def _route_of(node):
    """返回 (方法, 路径) 或 None。"""
    for d in node.decorator_list:
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) \
                and d.func.attr in ROUTE_METHODS:
            if d.args and isinstance(d.args[0], ast.Constant):
                return d.func.attr.upper(), d.args[0].value
            return d.func.attr.upper(), "<dynamic>"
    return None


def test_every_api_route_has_auth_decorator():
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "api")
    unprotected = []
    total = 0
    for path in sorted(glob.glob(os.path.join(root, "**", "*.py"), recursive=True)):
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except Exception as e:  # pragma: no cover
            raise AssertionError(f"无法解析 {path}: {e}")
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            route = _route_of(node)
            if not route:
                continue
            method, route_path = route
            total += 1
            if route_path in PUBLIC_ALLOWLIST:
                continue
            names = set(_decorator_names(node))
            if not (names & AUTH_DECORATORS):
                unprotected.append((path, node.name, method, route_path))

    # 受保护面不应为空（防止 glob/路径写错导致测试假通过）
    assert total >= 50, f"扫描到的 /api 路由仅 {total} 个，疑似路径或解析有误"

    assert not unprotected, (
        "发现未鉴权的 /api 路由（应加 @jwt_required 或 @admin_required，"
        "若确为公开端点请登记到 PUBLIC_ALLOWLIST）:\n"
        + "\n".join(f"  {p}::{fn}  {m} {rp}" for p, fn, m, rp in unprotected)
    )
