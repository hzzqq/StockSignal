# -*- coding: utf-8 -*-
"""守卫：/api/v2/read/diagnostics 的端点清单必须真实反映「必填 query 参数」。

真实故障（2026-11-09）：_diag_endpoints() 只用 `"<" in path` 判断参数需求，
把 10 个缺参即 400 的端点当成可直接探测，接真实后端时接口检测大面积假报
HTTP 400、功能全景的「查看数据」入口一选就报错；而 MSW 夹具恰好给这些
端点补了 query / 默认参数，开发态全绿，把缺陷完全掩盖。

本守卫从 AST 结构真扫，不依赖字符串包含、不依赖 ast.unparse 的引号风格、
也不会被 docstring / 注释里的 "400" 喂饱。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
READ_ROUTES = ROOT / "backend/api/read_routes.py"
FIXTURES = ROOT / "frontend-v2/src/mocks/fixtures.ts"
SCHEMA = ROOT / "frontend-v2/src/api/schemas/diagnostics.ts"
QUERIES = ROOT / "frontend-v2/src/lib/queries.ts"
DIAG_VIEW = ROOT / "frontend-v2/src/features/ops/DiagnosticsView.tsx"

_PREFIX = "/api/v2/read"


def _tree() -> ast.Module:
    return ast.parse(READ_ROUTES.read_text(encoding="utf-8"))


def _get_routes(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    """从 AST 结构提取 bp.get 路由，不依赖 ast.unparse 的单/双引号风格。"""
    out: dict[str, ast.FunctionDef] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            fn = dec.func
            if not (
                isinstance(fn, ast.Attribute)
                and fn.attr == "get"
                and isinstance(fn.value, ast.Name)
                and fn.value.id == "bp"
            ):
                continue
            if not dec.args or not isinstance(dec.args[0], ast.Constant):
                continue
            rel = dec.args[0].value
            if isinstance(rel, str):
                out[rel] = node
    return out


def _has_400(node: ast.FunctionDef) -> bool:
    """函数体里是否真的 return fail(..., http_status=400)。docstring/注释不算。"""
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        for kw in sub.keywords:
            if (
                kw.arg == "http_status"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value == 400
            ):
                return True
    return False


def _required_query_map(tree: ast.Module) -> dict[str, dict[str, str]]:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", None) == "_DIAG_REQUIRED_QUERY" for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("read_routes.py 缺少 _DIAG_REQUIRED_QUERY 单一真理源")


def _scanned_required(tree: ast.Module) -> set[str]:
    routes = _get_routes(tree)
    assert len(routes) >= 20, f"只解析到 {len(routes)} 个 GET 端点，AST 扫描疑似失效"
    return {
        f"{_PREFIX}{rel}"
        for rel, node in routes.items()
        if "<" not in rel and _has_400(node)
    }


def test_every_400_get_endpoint_is_registered():
    """真会 400 的无参 GET 端点集合必须与登记映射完全相等（双向防漏/防编造）。"""
    tree = _tree()
    scanned = _scanned_required(tree)
    mapping = _required_query_map(tree)
    assert len(scanned) >= 8, f"只扫到 {len(scanned)} 个 400 端点，AST 扫描疑似失效"
    missing = sorted(scanned - set(mapping))
    extra = sorted(set(mapping) - scanned)
    assert not missing, (
        f"缺参即 400 却未登记 _DIAG_REQUIRED_QUERY，会被接口检测假报故障: {missing}"
    )
    assert not extra, f"登记了不会 400 的端点或僵尸路径: {extra}"


def test_registered_paths_are_real_routes():
    """登记的端点必须真实存在且带可用示例参数，不能留僵尸路径。"""
    tree = _tree()
    routes = _get_routes(tree)
    mapping = _required_query_map(tree)
    assert mapping, "映射为空，守卫失效"
    for full, params in mapping.items():
        assert full.startswith(_PREFIX), f"{full} 前缀不属于只读端点"
        rel = full.removeprefix(_PREFIX)
        assert "<" not in rel, f"{full} 是路径参数端点，不该用 query 映射"
        assert rel in routes, f"{full} 未在 Flask 路由表注册"
        assert params, f"{full} 没有示例参数，数据浏览器仍会拿到 400"


def test_msw_never_marks_required_endpoints_as_probeable():
    """MSW 不得把需参端点伪装成 needs_params:false / 带 query 的 probe_path。"""
    text = FIXTURES.read_text(encoding="utf-8")
    mapping = _required_query_map(_tree())
    seen = 0
    for full in mapping:
        m = re.search(r"\{ path: '" + re.escape(full) + r"'[^\n]*\}", text)
        if not m:
            continue
        row = m.group(0)
        assert "needs_params: true" in row, f"MSW 把需参端点标成可探测: {full}"
        assert "probe_path: null" in row, f"MSW 给需参端点编造了 probe_path: {full}"
        assert "sample_query:" in row, f"MSW 需参端点缺少示例参数: {full}"
        seen += 1
    assert seen >= 1, "fixtures 里没有任何需参端点样本，无法验证一致性"
    assert "six-dim?code=" not in text, "不得再把带 query 的路径当成端点 path"


def test_frontend_contract_follows_backend():
    schema = SCHEMA.read_text(encoding="utf-8")
    assert "required_query" in schema and "sample_query" in schema
    queries = QUERIES.read_text(encoding="utf-8")
    assert "['read', 'diagnostics', probe, nonce]" in queries, "重新探测必须换 queryKey"
    view = DIAG_VIEW.read_text(encoding="utf-8")
    assert "useDiagnostics(wantProbe, probeNonce)" in view
    assert "setProbeNonce((n) => n + 1)" in view, "按钮只在首次点击生效就是 no-op"
    assert "需参数（路径或 query）" in view
