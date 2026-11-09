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


# 这些端点的函数体里虽有 http_status=400，但都是「取值/格式/数量违规」类校验，
# 缺失 query 参数时会回落默认值——factor-analysis 缺 codes 回落演示标的、
# trading-account 缺 user 回落 admin——因此不会「缺参即 400」，不属于需参集合，
# 哨兵不把它们误报成漏登记。（与 _DIAG_REQUIRED_QUERY 双向契约仍覆盖真正缺参即 400 的端点。）
_VALIDATION_ONLY_400 = {
    "/api/v2/read/factor-analysis",
    "/api/v2/read/trading-account",
}


def _scanned_required(tree: ast.Module) -> set[str]:
    routes = _get_routes(tree)
    assert len(routes) >= 20, f"只解析到 {len(routes)} 个 GET 端点，AST 扫描疑似失效"
    return {
        f"{_PREFIX}{rel}"
        for rel, node in routes.items()
        if "<" not in rel and _has_400(node)
    } - _VALIDATION_ONLY_400


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


def _endpoint_objects(text: str) -> dict[str, str]:
    """从 fixtures.ts 抽出每个 ``{ path: '/api/v2/read/…', … }`` 完整对象块（跨行安全）。

    历史缺陷（2026-11-09 实测，不是理论风险）：旧守卫用单行正则
    ``\{ path: '<full>'[^\n]*\}``，prettier 一格式化成多行就匹配不到；配合
    ``if not m: continue`` 与 ``seen >= 1``，后端登记的 10 个需参端点只有
    4 条被真校验，其余 6 条静默跳过且测试全绿 —— 守卫自我静音。
    """
    marker = "export const diagnosticsEndpoints = ["
    arr_at = text.find(marker)
    assert arr_at >= 0, "fixtures.ts 缺少 diagnosticsEndpoints 端点清单"
    open_at = arr_at + len(marker) - 1  # 指向 '['
    depth = 0
    arr_end = -1
    for i in range(open_at, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                arr_end = i + 1
                break
    assert arr_end > 0, "diagnosticsEndpoints 数组未闭合，fixtures 疑似被截断"
    scope = text[open_at:arr_end]

    out: dict[str, str] = {}
    # 负向后视排除 probe_path: 等同名字段；只在端点清单数组内解析，
    # 避免 fixtures 其它对象里的 path 键把守卫撑成「重复登记」。
    for m in re.finditer(r"(?<![A-Za-z0-9_])path:\s*'(/api/v2/read/[^']+)'", scope):
        start = scope.rfind("{", 0, m.start())
        assert start >= 0, f"端点 {m.group(1)} 找不到对象起始花括号"
        brace = 0
        end = -1
        for i in range(start, len(scope)):
            if scope[i] == "{":
                brace += 1
            elif scope[i] == "}":
                brace -= 1
                if brace == 0:
                    end = i + 1
                    break
        assert end > 0, f"端点 {m.group(1)} 对象块未闭合，fixtures 疑似被截断"
        path = m.group(1)
        assert path not in out, f"fixtures 里端点 {path} 重复登记"
        out[path] = scope[start:end]
    assert out, "fixtures.ts 未解析到任何诊断端点对象，扫描器失效"
    return out


def _msw_contract_errors(objects: dict[str, str],
                         mapping: dict[str, dict[str, str]]) -> list[str]:
    """返回 MSW 端点清单与后端真值之间的全部不一致（空列表 = 通过）。

    抽成纯函数是为了让守卫自身可被反例验证：删条目 / 改标记 /
    编造 probe_path 都必须产生错误，而不是被 continue 吞掉。
    """
    errors: list[str] = []
    if not objects:
        return ["fixtures 中未解析到任何端点对象"]
    if not any("<" in p for p in objects):
        errors.append("fixtures 未包含路径参数端点样例（守卫覆盖面退化）")

    msw_required: set[str] = set()
    for path, block in objects.items():
        is_true = "needs_params: true" in block
        is_false = "needs_params: false" in block
        if is_true == is_false:
            errors.append(f"{path}: 缺少唯一明确的 needs_params 标记")
            continue
        if is_true and "<" not in path:
            msw_required.add(path)

    for full in sorted(set(mapping) - msw_required):
        errors.append(f"MSW 缺少后端登记的需参端点: {full}")
    for full in sorted(msw_required - set(mapping)):
        errors.append(f"MSW 把不会因缺 query 而 400 的端点标成需参: {full}")

    for full, params in mapping.items():
        block = objects.get(full)
        if block is None:
            continue  # 缺失已由上面的 missing 分支报错，不重复计算
        if "probe_path: null" not in block:
            errors.append(f"{full}: 编造了可直接探测的 probe_path")
        if "sample_query:" not in block:
            errors.append(f"{full}: 缺示例参数 sample_query")
        for key, val in params.items():
            if f"'{key}'" not in block:
                errors.append(f"{full}: required_query 缺 '{key}'")
            if f"{key}={val}" not in block:
                errors.append(f"{full}: sample_query 缺 {key}={val}")
    return errors


def test_msw_required_endpoints_match_backend_exactly():
    """MSW 需参端点集合与后端登记**双向等值**，零静默跳过。"""
    text = FIXTURES.read_text(encoding="utf-8")
    objects = _endpoint_objects(text)
    mapping = _required_query_map(_tree())
    assert len(mapping) >= 10, "后端需参端点登记疑似被掏空"
    errors = _msw_contract_errors(objects, mapping)
    assert not errors, "MSW 与真后端需参契约不一致:\n" + "\n".join(errors)
    assert "six-dim?code=" not in text, "不得再把带 query 的路径当成端点 path"


def test_msw_contract_guard_is_not_self_silencing():
    """反例自测：多行格式可解析；删条目 / 改标记 / 编造 probe_path 都会被抓。"""
    mapping = _required_query_map(_tree())
    good = _endpoint_objects(FIXTURES.read_text(encoding="utf-8"))
    assert _msw_contract_errors(good, mapping) == [], "当前 fixtures 必须通过契约校验"

    # 1) prettier 风格的多行对象仍能被完整抽取（旧单行正则会直接漏掉）
    multiline = """export const diagnosticsEndpoints = [
  {
    path: '/api/v2/read/six-dim',
    needs_params: true,
    probe_path: null,
    required_query: ['code'],
    sample_query: 'code=600519',
  },
]
"""
    parsed = _endpoint_objects(multiline)
    assert list(parsed) == ["/api/v2/read/six-dim"]
    assert "needs_params: true" in parsed["/api/v2/read/six-dim"]
    assert "probe_path: null" in parsed["/api/v2/read/six-dim"]

    key = "/api/v2/read/six-dim"
    # 2) 删掉一个登记端点，必须报错而不是 continue 静默跳过
    dropped = {k: v for k, v in good.items() if k != key}
    assert any("six-dim" in e for e in _msw_contract_errors(dropped, mapping))

    # 3) 把需参端点标成可直接探测，必须报错
    tampered = dict(good)
    tampered[key] = good[key].replace("needs_params: true", "needs_params: false")
    assert any("six-dim" in e for e in _msw_contract_errors(tampered, mapping))

    # 4) 给需参端点编造 probe_path，必须报错
    tampered2 = dict(good)
    tampered2[key] = good[key].replace(
        "probe_path: null", "probe_path: '/api/v2/read/six-dim?code=600519'")
    assert any("probe_path" in e for e in _msw_contract_errors(tampered2, mapping))

    # 5) 空对象集合必须被视为守卫失效
    assert _msw_contract_errors({}, mapping)


def test_frontend_contract_follows_backend():
    schema = SCHEMA.read_text(encoding="utf-8")
    assert "required_query" in schema and "sample_query" in schema
    queries = QUERIES.read_text(encoding="utf-8")
    assert "['read', 'diagnostics', probe, nonce]" in queries, "重新探测必须换 queryKey"
    view = DIAG_VIEW.read_text(encoding="utf-8")
    assert "useDiagnostics(wantProbe, probeNonce)" in view
    assert "setProbeNonce((n) => n + 1)" in view, "按钮只在首次点击生效就是 no-op"
    assert "需参数（路径或 query）" in view
