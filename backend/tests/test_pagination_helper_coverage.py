"""backend/tests/test_pagination_helper_coverage.py

**分页参数必须走有界 helper** —— 源码级防回退。

背景（Cycle 43 已修）：分页 ``limit / per_page / offset`` 若只钳上界不钳下界，
SQLite 的 ``LIMIT -1`` 等于「不限制行数」，
``?limit=-1`` 可绕过 200 条上限拉全表（用户表 / 帖子 / 告警），
造成数据过度暴露 + 内存 DoS。

``backend/utils/params.py`` 已提供 ``parse_limit_param`` / ``parse_page_param``
（内部走 ``parse_int_param`` 同时钳上下界）。本测试锁定：
**任何路由都不得再用 ``request.args.get('limit')`` / ``int(request.args.get(...))``
这类裸解析**，必须统一走 helper，防止后续新增接口悄悄把洞开回来。

判定方式（AST）：若某次赋值的目标变量名命中分页关键词
（limit / page / per_page / offset / pagesize），且值里出现了
``request.args.get`` 之类的裸取值、又没有调用 parse_* helper，即判违规。

2026-08-28 新增（Cycle 69）。
"""
from __future__ import annotations

import ast
import glob
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(BACKEND_DIR)
for p in (ROOT, BACKEND_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

PAGINATION_KEYS = {"limit", "page", "per_page", "offset", "pagesize", "page_size"}
HELPERS = {"parse_limit_param", "parse_page_param", "parse_int_param", "parse_str_param"}
# 裸取值入口（分片参数绝不能从这里直接拿）
RAW_ACCESS = {"get", "args"}


def _target_names(node):
    names = []
    for t in node.targets:
        for sub in ast.walk(t):
            if isinstance(sub, ast.Name):
                names.append(sub.id)
    return names


def _called_names(node):
    out = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            f = sub.func
            if isinstance(f, ast.Attribute):
                out.add(f.attr)
            elif isinstance(f, ast.Name):
                out.add(f.id)
    return out


def _uses_raw_args(node) -> bool:
    """值里是否出现 request.args.get(...) 这类裸解析。"""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
            # request.args.get / args.get
            if sub.func.attr == "get":
                owner = sub.func.value
                owner_name = None
                if isinstance(owner, ast.Attribute):
                    owner_name = owner.attr
                elif isinstance(owner, ast.Name):
                    owner_name = owner.id
                if owner_name in ("args",):
                    return True
    return False


def test_pagination_params_must_use_bounded_helpers():
    bad = []
    for path in sorted(glob.glob(os.path.join(BACKEND_DIR, "api", "**", "*.py"), recursive=True)):
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except Exception as e:  # pragma: no cover
            raise AssertionError(f"无法解析 {path}: {e}")
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            names = [n.lower() for n in _target_names(node)]
            if not any(k in names for k in PAGINATION_KEYS):
                continue
            called = _called_names(node.value)
            if called & HELPERS:
                continue  # 已走有界 helper，合规
            if _uses_raw_args(node.value):
                bad.append((rel, node.lineno, "/".join(_target_names(node))))

    assert not bad, (
        "发现分页参数使用裸解析（应改用 parse_limit_param / parse_page_param，"
        "否则 ?limit=-1 可绕过条数上限拉全表）:\n"
        + "\n".join(f"  {r}:{ln} {target} = request.args.get(...)" for r, ln, target in bad)
    )


def test_bounded_helpers_still_exist():
    """helper 被改名/删除时立刻暴露，避免上面那条测试变成空转。"""
    from backend.utils import params
    for name in ("parse_limit_param", "parse_page_param", "parse_int_param"):
        assert hasattr(params, name), f"backend/utils/params.py 缺少 {name}"
    # 上限必须存在且为正（默认 200）
    import inspect
    sig = inspect.signature(params.parse_limit_param)
    assert "hi" in sig.parameters, "parse_limit_param 必须提供上界参数 hi"
    assert sig.parameters["hi"].default > 0, "parse_limit_param 的上界默认值必须为正"
