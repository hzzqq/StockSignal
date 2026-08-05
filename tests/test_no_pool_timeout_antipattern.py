"""架构护栏：禁止「with ThreadPoolExecutor(...) + 带 timeout 的等待」反模式。

背景（真实 bug，2026-08 修复）：
    with ThreadPoolExecutor(max_workers=4) as ex:
        fut = ex.submit(slow_network_call)
        r = fut.result(timeout=15)       # 看似有超时保护

超时抛 TimeoutError 后会退出 with，而 Executor.__exit__ 调用
``shutdown(wait=True)``，**反过来阻塞等待那个慢任务真正跑完**。
即：超时保护被完全抵消，页面仍然会卡死。项目里曾有 5 处这种写法，
注释都写着「加超时避免整页卡住」，实际一处都没生效。

正确做法：用 modules.timeout_exec.run_with_timeout /
modules.fetch_parallel.fetch_many（共享有界池，不 shutdown，超时立即返回）。

本测试用 AST 静态检测，任何人新写出该模式都会在 CI 失败。
"""
import ast
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[1]
# 共享池实现本身允许出现（它们不 shutdown，是正确实现）
_ALLOWLIST = {"timeout_exec.py", "fetch_parallel.py"}
_WAIT_FUNCS = {"result", "as_completed", "wait"}


def _scan(path: pathlib.Path):
    """返回该文件内命中反模式的 (with 行号, 等待函数名, 等待行号) 列表。"""
    hits = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return hits
    for node in ast.walk(tree):
        if not isinstance(node, ast.With):
            continue
        if not any("ThreadPoolExecutor" in ast.dump(i.context_expr) for i in node.items):
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            name = getattr(sub.func, "attr", None) or getattr(sub.func, "id", None)
            if name in _WAIT_FUNCS and any(k.arg == "timeout" for k in sub.keywords):
                hits.append((node.lineno, name, sub.lineno))
                break
    return hits


def _targets():
    for d in ("pages", "modules"):
        for p in sorted((_ROOT / d).glob("*.py")):
            if p.name not in _ALLOWLIST:
                yield p


def test_no_with_pool_plus_timeout_wait():
    bad = []
    for p in _targets():
        for wline, fn, cline in _scan(p):
            bad.append(f"{p.relative_to(_ROOT)}:{wline} 的 with 池内使用了 {fn}(timeout=) @ 行 {cline}")
    assert not bad, (
        "检测到「with ThreadPoolExecutor + 带 timeout 的等待」反模式：\n  "
        + "\n  ".join(bad)
        + "\n退出 with 时 shutdown(wait=True) 会抵消超时保护，页面仍会卡死。"
        "\n请改用 modules.timeout_exec.run_with_timeout 或 modules.fetch_parallel.fetch_many。"
    )


def test_scanner_actually_detects(tmp_path):
    """自检：确保扫描器不是永远返回空（防止护栏本身失效变成安慰剂）。"""
    f = tmp_path / "bad_sample.py"
    f.write_text(
        "from concurrent.futures import ThreadPoolExecutor\n"
        "def go(fn):\n"
        "    with ThreadPoolExecutor(max_workers=1) as ex:\n"
        "        return ex.submit(fn).result(timeout=5)\n",
        encoding="utf-8",
    )
    assert _scan(f), "AST 扫描器未能识别已知的反模式样本"
