# -*- coding: utf-8 -*-
"""守卫：/breadth-analytics 与 /breadth-zseries 的诚实契约（零网络、零 DB）。

防三类真实缺陷：
  1. window/dim 白名单被悄悄放宽或改成静默兜底（非法值不报错 = 说谎）；
  2. 逐段降级被删（一个模块异常拖垮整包，或 available=False 却仍编造数值）；
  3. 前后端/MSW 字段漂移（历史缺陷：财报日历 MSW 全绿、接真后端三列全显「—」）。
本守卫从后端 AST 真扫 data 键，与 Zod schema、MSW 夹具逐项比对，不许 skip。
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from backend.api.read_routes import (
    _ANALYTICS_WINDOWS,
    _analytics_section,
    _parse_analytics_window,
    _zseries_slice,
)

ROOT = Path(__file__).resolve().parents[1]
READ_ROUTES = ROOT / "backend" / "api" / "read_routes.py"
SCHEMAS = ROOT / "frontend-v2" / "src" / "api" / "schemas" / "read.ts"
FIXTURES = ROOT / "frontend-v2" / "src" / "mocks" / "fixtures.ts"


# ───────────────────────── 1. 参数白名单 ─────────────────────────
def test_window_whitelist_is_strict():
    """合法窗口全放行；缺省回落 250；非法值必须带出错误，绝不静默兜底。"""
    assert _ANALYTICS_WINDOWS == (60, 120, 250, 750, 2000)
    for w in _ANALYTICS_WINDOWS:
        assert _parse_analytics_window(str(w)) == (w, None)
        assert _parse_analytics_window(w) == (w, None)
    for raw in (None, "", "  "):
        assert _parse_analytics_window(raw) == (250, None)
    for raw in ("999", "0", "-1", "abc", "60; DROP", "1e3", "250.0"):
        value, err = _parse_analytics_window(raw)
        assert value == 250 and err, f"非法 window {raw!r} 未被拒绝"


# ───────────────────────── 2. 序列截断与下标重映射 ─────────────────────────
def test_zseries_slice_invariants():
    """截尾后三数组等长、markers 下标重映射、truncated 如实标记。"""
    raw = {
        "dates": [f"d{i}" for i in range(100)],
        "z": [float(i) for i in range(100)],
        "raw": [float(i) * 2 for i in range(100)],
        "markers": [0, 50, 99, 500],  # 越界下标必须被丢弃，不能越界画点
    }
    out = _zseries_slice(raw, 60)
    assert len(out["dates"]) == len(out["z"]) == len(out["raw"]) == 60
    assert out["dates"][0] == "d40" and out["dates"][-1] == "d99"
    assert out["markers"] == [10, 59]
    assert out["truncated"] is True

    full = _zseries_slice(raw, 2000)
    assert full["dates"] == raw["dates"]
    assert full["markers"] == [0, 50, 99]
    assert full["truncated"] is False

    one = _zseries_slice(raw, 1)
    assert one["dates"] == ["d99"] and one["markers"] == [0]

    empty = _zseries_slice({"dates": [], "z": [], "raw": [], "markers": []}, 250)
    assert empty["dates"] == [] and empty["markers"] == [] and empty["truncated"] is False


# ───────────────────────── 3. 逐段独立降级 ─────────────────────────
def test_analytics_section_is_isolated_and_honest():
    """模块抛异常/返回异常结构/数据不足，都只让该段 available=False + 真原因。"""
    def boom():
        raise ValueError("离线镜像损坏")

    out = _analytics_section(boom)
    assert out == {"available": False, "reason": "ValueError: 离线镜像损坏"}

    assert _analytics_section(lambda: [1, 2]) == {
        "available": False, "reason": "计算结果结构异常"
    }
    assert _analytics_section(lambda: {"available": False, "reason": "红盘占比历史缺失"}) == {
        "available": False, "reason": "红盘占比历史缺失"
    }
    assert _analytics_section(lambda: {"available": False}) == {
        "available": False, "reason": "该段数据不可用"
    }
    good = _analytics_section(lambda: {"available": True, "dates": ["2026-08-21"], "z": [1.0]})
    assert good["available"] is True and good["dates"] == ["2026-08-21"]


# ───────────────────────── 4. 端点注册 / 鉴权 / 需参登记 ─────────────────────────
def _routes() -> dict[str, ast.FunctionDef]:
    tree = ast.parse(READ_ROUTES.read_text(encoding="utf-8"))
    out: dict[str, ast.FunctionDef] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and dec.func.attr == "get"
                and isinstance(dec.func.value, ast.Name)
                and dec.func.value.id == "bp"
                and dec.args
                and isinstance(dec.args[0], ast.Constant)
            ):
                out[str(dec.args[0].value)] = node
    assert len(out) >= 20, "GET 端点扫描疑似失效"
    return out


def _decorator_names(node: ast.FunctionDef) -> set[str]:
    names: set[str] = set()
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


def test_endpoints_registered_with_auth_and_diag_contract():
    routes = _routes()
    for path in ("/breadth-analytics", "/breadth-zseries"):
        assert path in routes, f"{path} 未注册"
        assert "jwt_required" in _decorator_names(routes[path]), f"{path} 缺 JWT 鉴权"

    tree = ast.parse(READ_ROUTES.read_text(encoding="utf-8"))
    diag = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", None) == "_DIAG_REQUIRED_QUERY" for t in node.targets
        ):
            diag = ast.literal_eval(node.value)
    assert diag is not None
    assert diag.get("/api/v2/read/breadth-zseries") == {"dim": "up_count"}, (
        "zseries 缺 dim 即 400，必须登记示例参数（否则接口检测假报故障）"
    )
    assert "/api/v2/read/breadth-analytics" not in diag, (
        "analytics 的 window 可选、缺参不 400，不该被登记为需参端点"
    )


# ───────────────────────── 5. 后端 ↔ Zod ↔ MSW 字段三重对齐 ─────────────────────────
def _endpoint_data_keys(func_name: str) -> set[str]:
    """从端点函数体里 data = {...} 的 Dict 字面量抽顶层键（不靠注释）。"""
    tree = ast.parse(READ_ROUTES.read_text(encoding="utf-8"))
    fn = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == func_name),
        None,
    )
    assert fn is not None, f"缺函数 {func_name}"
    keys: set[str] = set()
    for sub in ast.walk(fn):
        if not (isinstance(sub, ast.Assign) and isinstance(sub.value, ast.Dict)):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "data" for t in sub.targets):
            continue
        for k in sub.value.keys:
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                keys.add(k.value)
    assert keys, f"{func_name} 没扫到 data 键，AST 扫描疑似失效"
    return keys


def _zod_keys(schema_name: str) -> set[str]:
    """抽 `export const X = z.object({ ... })` 顶层键（按缩进 2 空格判定，避开子对象）。"""
    text = SCHEMAS.read_text(encoding="utf-8")
    m = re.search(rf"export const {schema_name} = z\.object\(\{{\n(.*?)\n\}}\)", text, re.S)
    assert m, f"schemas/read.ts 缺 {schema_name}"
    return set(re.findall(r"^  ([A-Za-z_][A-Za-z0-9_]*): z\.", m.group(1), re.M))


def _extract_balanced_braces(text: str, open_idx: int) -> str:
    """从开括号起，按括号深度抽取完整对象字面量；忽略字符串/注释内的括号，避免被夹具间注释或字符串值干扰。"""
    depth = 0
    i = open_idx
    n = len(text)
    in_str = None  # '"' | "'" | '`'
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
            i += 1
            continue
        if c in ('"', "'", "`"):
            in_str = c
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = n if j == -1 else j + 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[open_idx : i + 1]
        i += 1
    return text[open_idx:]


def _fixture_object(name: str, next_name: str | None = None) -> dict:  # next_name 已弃用：现按括号深度解析
    text = FIXTURES.read_text(encoding="utf-8")
    start_marker = f"export const {name} = "
    at = text.find(start_marker)
    assert at >= 0, f"fixtures.ts 缺 {name}"
    start = at + len(start_marker)
    brace = text.find("{", start)
    assert brace != -1, f"{name} 未找到对象起始 {{"
    obj = _extract_balanced_braces(text, brace)
    return json.loads(obj)


def test_backend_schema_and_fixture_keys_match_exactly():
    """真端点 data 键 == Zod schema 键 == MSW 夹具键（财报日历漂移防线）。"""
    pairs = [
        ("breadth_analytics", "BreadthAnalyticsSchema", "breadthAnalytics", "breadthZSeries"),
        ("breadth_zseries", "ZSeriesSchema", "breadthZSeries", None),
    ]
    for fn, schema, fixture, next_fixture in pairs:
        backend = _endpoint_data_keys(fn)
        zod = _zod_keys(schema)
        fixture_obj = _fixture_object(fixture, next_fixture)
        assert backend == zod, (
            f"{fn}: 后端键与 Zod 不一致 后端-only={sorted(backend - zod)} "
            f"前端-only={sorted(zod - backend)}"
        )
        assert set(fixture_obj) == backend, (
            f"{fixture}: 夹具键与真端点不一致 "
            f"夹具-only={sorted(set(fixture_obj) - backend)} "
            f"端点-only={sorted(backend - set(fixture_obj))}"
        )
        assert "data_as_of" in fixture_obj and fixture_obj["data_as_of"], (
            "权威数据日不得缺失/编造"
        )


def test_fixture_sections_match_backend_sections():
    """sections 四段与 phase 两子段齐全；夹具各段 available 为真且带真实数值。"""
    fx = _fixture_object("breadthAnalytics", "breadthZSeries")
    sections = fx["sections"]
    assert set(sections) == {"phase", "similar", "inflection", "duration"}
    assert set(sections["phase"]) == {"current", "series"}
    for name in ("similar", "inflection", "duration"):
        assert sections[name]["available"] is True, f"{name} 段夹具不可用"
    assert sections["phase"]["current"]["available"] is True
    assert sections["phase"]["series"]["available"] is True
    ser = sections["phase"]["series"]
    n = len(ser["dates"])
    assert n >= 1
    assert all(len(v) == n for v in ser["series"].values()), "series 各维长度必须等长"

    z = _fixture_object("breadthZSeries", None)
    assert len(z["dates"]) == len(z["z"]) == len(z["raw"])
    assert all(0 <= m < len(z["dates"]) for m in z["markers"]), "markers 下标越界"
    assert len(fx["offline_missing"]) == 10, "离线缺真值维度必须逐条披露"
