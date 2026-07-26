"""
tests/test_network_hygiene.py
=============================
项目级「网络卫生」静态回归门（AST 精确匹配，非文本 grep）：

规则：任何 ``requests.<verb>(...)`` 调用（get/post/put/delete/head/patch/request）
必须显式带 ``timeout=`` 关键字实参。缺省 timeout 的请求在数据源抖动/被墙时会
无限阻塞，拖垮 Streamlit 页面线程或后端调度线程——本项目 4 源竞速 + 缓存兜底的
韧性设计要求每一处网络调用都能「快速失败」。

本测试遍历 modules/ 与 backend/ 全部源码（排除 tests/），一旦发现无 timeout 的
requests 调用即失败，把此前靠人工 review 维持的纪律固化为自动门禁，防止回归。
"""
from __future__ import annotations

import ast
import pathlib

import pytest

_VERBS = {"get", "post", "put", "delete", "head", "patch", "request"}
_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SCAN_DIRS = ["modules", "backend"]


def _iter_source_files():
    for d in _SCAN_DIRS:
        base = _ROOT / d
        if not base.is_dir():
            continue
        for p in base.rglob("*.py"):
            parts = set(p.parts)
            if "tests" in parts or "__pycache__" in parts:
                continue
            yield p


def _is_requests_call(node: ast.Call) -> bool:
    """判断是否 ``requests.<verb>(...)`` 形式的调用。"""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr not in _VERBS:
        return False
    # 形如 requests.get —— value 为 Name('requests')
    val = func.value
    return isinstance(val, ast.Name) and val.id == "requests"


def _find_missing_timeout(path: pathlib.Path):
    """返回 [(lineno, verb)]：该文件里无 timeout 的 requests 调用。"""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_requests_call(node):
            kw_names = {k.arg for k in node.keywords if k.arg is not None}
            has_dstar = any(k.arg is None for k in node.keywords)  # **kwargs 视为可能含 timeout
            if "timeout" not in kw_names and not has_dstar:
                offenders.append((node.lineno, node.func.attr))
    return offenders


def test_all_requests_calls_have_timeout():
    problems = []
    scanned = 0
    for path in _iter_source_files():
        scanned += 1
        for lineno, verb in _find_missing_timeout(path):
            rel = path.relative_to(_ROOT).as_posix()
            problems.append(f"{rel}:{lineno} requests.{verb}() 缺少 timeout=")
    assert scanned > 0, "未扫描到任何源码文件，glob 规则可能失效"
    assert not problems, "发现无 timeout 的网络调用（会导致无限阻塞）：\n" + "\n".join(problems)


def test_scan_covers_known_network_module():
    """守护：扫描集必须包含已知含网络调用的模块，避免过滤规则把它们漏掉。"""
    files = {p.relative_to(_ROOT).as_posix() for p in _iter_source_files()}
    assert "modules/fetcher.py" in files
    assert "modules/session.py" in files
