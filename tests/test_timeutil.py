"""
tests/test_timeutil.py
======================
- 校验 ``backend.utils.timeutil`` 的 UTC 辅助函数行为（naive UTC、时区正确）。
- 回归：源码中不得再出现已弃用的 ``datetime.utcnow()`` / ``datetime.utcfromtimestamp()``。
"""
from __future__ import annotations

import ast
import os

from backend.utils.timeutil import utc_now, utc_fromtimestamp


def test_utc_now_is_naive_utc():
    """utc_now 返回 tzinfo=None 的 UTC 时间（兼容 DB 按 naive UTC 存储的约定）。"""
    now = utc_now()
    assert now.tzinfo is None
    # 与「标准 UTC 当前时刻」相差不超过 2 秒
    from datetime import datetime, timezone

    ref = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((now - ref).total_seconds()) < 2


def test_utc_now_monotonic_increasing():
    a = utc_now()
    b = utc_now()
    assert b >= a


def test_utc_fromtimestamp_epoch():
    """utc_fromtimestamp(0) 应为 1970-01-01T00:00:00Z（感知型）。"""
    dt = utc_fromtimestamp(0)
    assert dt.tzinfo is not None
    assert dt.year == 1970 and dt.month == 1 and dt.day == 1
    assert dt.hour == 0 and dt.minute == 0 and dt.second == 0


def test_no_deprecated_utcnow_in_source():
    """回归：非测试源码不得再出现已弃用的 datetime.utcnow() / utcfromtimestamp() 调用。

    使用 AST 仅匹配**真实调用**，避免误伤文档字符串/注释中的提及。
    """
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    banned = {"utcnow", "utcfromtimestamp"}
    offenders = []
    for dirpath, _dirs, files in os.walk(root):
        # 跳过测试目录、venv、缓存与仓库元数据
        if any(seg in dirpath for seg in ("/tests/", "/.git/", "/__pycache__/", "/.pytest_cache/", "/venv", "/.venv/")):
            continue
        if dirpath.endswith("/tests"):
            continue
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                tree = ast.parse(open(path, encoding="utf-8").read())
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    val = node.func.value
                    if isinstance(val, ast.Name) and val.id == "datetime" and node.func.attr in banned:
                        offenders.append(f"{os.path.relpath(path, root)}:{node.lineno}: {node.func.attr}()")
    assert not offenders, "发现已弃用的 UTC 时间调用，应统一改用 backend.utils.timeutil:\n" + "\n".join(offenders)


def test_source_files_parse():
    """辅助：所有被扫描的源码文件均可正常解析（避免误把语法错误当弃用）。"""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    count = 0
    for dirpath, _dirs, files in os.walk(root):
        if any(seg in dirpath for seg in ("/tests/", "/.git/", "/__pycache__/", "/.pytest_cache/", "/venv", "/.venv/")):
            continue
        if dirpath.endswith("/tests"):
            continue
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                ast.parse(open(path, encoding="utf-8").read())
            except (OSError, UnicodeDecodeError, SyntaxError) as exc:
                raise AssertionError(f"语法错误: {path}: {exc}")
            count += 1
    assert count > 0
