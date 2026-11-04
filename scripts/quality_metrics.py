"""StockSignal 质量数字统一口径统计（单一真理源）。

背景（软件开发质量评估报告 P0-1）：论文第 6 章、README、仓库实测三套数字并存
（用例 4394 / 5069 / 5086，测试文件 405 / 487，py 文件 131 / 881，端点 89 / 75+9）。
若答辩被追问"论文说 4394，实测 5086"，必须能一句话解释差异来源。

本脚本把差异来源固定为**两种可复现口径**，而不是拍一个新数字：

  A. 静态定义口径（AST）：数源码里的 `def test_*` 函数个数。
     这是论文"4394 个测试函数"的来源——它数的是**函数定义**，不含参数化展开。
  B. 收集口径（pytest --collect-only）：pytest 实际会跑多少个用例。
     一个 `@pytest.mark.parametrize` 带 5 组参数 = 5 个用例，因此必然大于 A。
     README / 作品集对外报的是这个口径（"用户实际会跑多少"）。

两条口径都正确，错的只是"混用不提口径"。本脚本输出两者并标注定义，
论文引用时写明"4394 个测试函数（静态口径）/5086 个用例（参数化展开后）"即可自洽。

用法：
    python scripts/quality_metrics.py                 # 打印对照表（含 pytest 收集，约 15s）
    python scripts/quality_metrics.py --fast           # 跳过 pytest 收集，仅 AST 静态口径（秒出）
    python scripts/quality_metrics.py --json out.json  # 同时落盘机器可读结果

设计约束：
  - 无网络、无外部依赖、确定性输出（同一 commit 两次运行数字一致）；
  - 目录排除口径写死在 EXCLUDE_DIRS，与论文/README 说明必须一致；
  - 文档 docs/质量数字口径说明_2026-11-04.md 的数字块由 --write 自动回填，
    并由 tests/test_quality_numbers_sync.py 静态守卫（防文档与代码漂移）。
"""
from __future__ import annotations

import argparse
import ast
import datetime
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 统计排除口径（论文/README 必须与本表一致，否则数字不可比）
EXCLUDE_DIRS = {
    ".git", ".venv", "venv", "build", "dist", "__pycache__",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", ".trae", "node_modules",
    "backups", "screenshots", "data",  # data=运行数据，backups/screenshots=产物快照
}

# 业务源码范围（"自研源码"口径）：前端页面 + 业务模块 + 后端 + 增量试点 + MCP
SRC_DIRS = ("modules", "pages", "backend", "backend_fastapi", "mcp_server")
SRC_ROOT_FILES = ("app.py",)  # 根目录入口文件（Streamlit 主入口）

# 测试范围（三处，缺一不可：modules/tests 曾被漏数导致少报 ~35 用例）
TEST_DIRS = ("tests", "backend/tests", "modules/tests")

MARK_BLOCK_BEGIN = "<!-- AUTO:METRICS:BEGIN -->"
MARK_BLOCK_END = "<!-- AUTO:METRICS:END -->"


def _iter_files(sub: str, suffix: str):
    base = os.path.join(ROOT, sub)
    if not os.path.isdir(base):
        return
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if fn.endswith(suffix):
                yield os.path.join(dirpath, fn)


def _rel(path: str) -> str:
    return os.path.relpath(path, ROOT).replace("\\", "/")


def _in_tests(rel_path: str) -> bool:
    parts = rel_path.split("/")
    return "tests" in parts


def _count_lines(paths) -> int:
    total = 0
    for p in paths:
        try:
            with open(p, encoding="utf-8", errors="ignore") as f:
                total += sum(1 for _ in f)
        # ui_audit_exempt: 行数统计遇到不可读文件直接跳过——缺失即不计入，宁可少算也不猜
        except OSError:
            continue
    return total


def _ast_test_defs(paths) -> int:
    """静态口径：源码中 `def test_*` 函数定义数（不含 parametrize 展开）。"""
    n = 0
    for p in paths:
        try:
            tree = ast.parse(open(p, encoding="utf-8", errors="ignore").read())
        # ui_audit_exempt: 解析不了的测试文件不计入静态口径（语法错误本身由 CI 其它环节负责）
        except (SyntaxError, OSError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                n += 1
    return n


def _guard_files(paths) -> int:
    """含源码级 AST 护栏（ast.parse + assert）的测试文件数。"""
    n = 0
    for p in paths:
        try:
            src = open(p, encoding="utf-8", errors="ignore").read()
        # ui_audit_exempt: 读不出的测试文件不计入守卫文件数，缺失即不计
        except OSError:
            continue
        if "ast.parse" in src and "assert" in src:
            n += 1
    return n


_ROUTE_RE = re.compile(r"@[A-Za-z_][A-Za-z0-9_]*\.(?:route|get|post|put|delete|patch)\(")
_FASTAPI_RE = re.compile(r"@[A-Za-z_][A-Za-z0-9_]*\.(?:get|post|put|delete|patch)\(")


def _count_routes() -> tuple[int, int]:
    """(Flask 路由装饰器数, FastAPI 端点装饰器数)；均排除 tests 目录。"""
    flask_n = 0
    for p in _iter_files("backend", ".py"):
        if _in_tests(_rel(p)) or _rel(p).startswith("backend/tests/"):
            continue
        try:
            flask_n += len(_ROUTE_RE.findall(open(p, encoding="utf-8", errors="ignore").read()))
        # ui_audit_exempt: 读不出的后端文件不计入 Flask 路由数，缺失即不计
        except OSError:
            continue
    fastapi_n = 0
    for p in _iter_files("backend_fastapi", ".py"):
        try:
            fastapi_n += len(_FASTAPI_RE.findall(open(p, encoding="utf-8", errors="ignore").read()))
        # ui_audit_exempt: 读不出的 FastAPI 文件不计入端点数，缺失即不计
        except OSError:
            continue
    return flask_n, fastapi_n


def _pytest_collected() -> int | None:
    """收集口径：pytest 实际用例数（parametrize 已展开）。失败返回 None，不猜。"""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", *TEST_DIRS, "--collect-only", "-q",
             "-p", "no:cacheprovider"],
            cwd=ROOT, capture_output=True, text=True, timeout=900,
        )
    # ui_audit_exempt: 收集超时/收集失败返回 None（不猜数），对外只暴露静态口径并注明
    except (subprocess.TimeoutExpired, OSError):
        return None
    total = 0
    for line in r.stdout.splitlines():
        m = re.match(r"^(?:tests|backend/tests|modules/tests)/.*: (\d+)$", line.strip())
        if m:
            total += int(m.group(1))
    return total or None


def collect(fast: bool = False) -> dict:
    all_py = list(_iter_files(".", ".py"))
    src_py = [p for p in all_py if _rel(p).split("/")[0] in SRC_DIRS]
    src_py = [p for p in src_py if not _rel(p).startswith(("backend/tests/", "modules/tests/"))]
    src_py += [os.path.join(ROOT, f) for f in SRC_ROOT_FILES
               if os.path.exists(os.path.join(ROOT, f))]

    test_py = [p for d in TEST_DIRS for p in _iter_files(d, ".py")]
    test_files = [p for p in test_py if os.path.basename(p).startswith("test")]
    flask_routes, fastapi_routes = _count_routes()

    collected = None if fast else _pytest_collected()

    return {
        "py_files_total": len(all_py),
        "py_files_tests": len(test_py),
        "src_files": len(src_py),
        "src_loc": _count_lines(src_py),
        "test_files": len(test_files),
        "test_loc": _count_lines(test_py),
        "pages": len([p for p in _iter_files("pages", ".py")]),
        "modules": len([p for p in _iter_files("modules", ".py")]),
        "test_defs_static": _ast_test_defs(test_py),
        "tests_collected": collected,
        "guard_files": _guard_files(test_py),
        "flask_routes": flask_routes,
        "fastapi_routes": fastapi_routes,
        "rest_routes_total": flask_routes + fastapi_routes,
        "exclude_dirs": sorted(EXCLUDE_DIRS),
    }


def _fmt(n) -> str:
    return "—" if n is None else f"{n:,}"


def render_table(s: dict) -> str:
    collected = s["tests_collected"]
    delta = "—" if collected is None else f"{collected - s['test_defs_static']:+,}"
    rows = [
        ("Python 文件（全仓）", _fmt(s["py_files_total"]), "排除目录见口径表；含 tests/scripts/thesis 等"),
        ("业务源码文件", _fmt(s["src_files"]), "modules+pages+backend(非 tests)+backend_fastapi+mcp_server+app.py"),
        ("业务源码行数", _fmt(s["src_loc"]), "同上范围，按行计数"),
        ("功能页面", _fmt(s["pages"]), "pages/*.py 文件数（Streamlit 多页）"),
        ("业务模块", _fmt(s["modules"]), "modules/*.py 文件数"),
        ("REST 端点", _fmt(s["rest_routes_total"]),
         f"Flask 装饰器 {s['flask_routes']} + FastAPI {s['fastapi_routes']}（均排除 tests）"),
        ("测试文件", _fmt(s["test_files"]), "tests/ + backend/tests/ + modules/tests/ 中 test*.py"),
        ("测试代码行数", _fmt(s["test_loc"]), "同上范围，按行计数"),
        ("测试函数（静态口径 A）", _fmt(s["test_defs_static"]), "AST 数 `def test_*`，不含参数化展开 —— 论文口径"),
        ("测试用例（收集口径 B）", _fmt(collected), "pytest --collect-only，parametrize 已展开 —— README 口径"),
        ("A→B 展开增量", delta, "参数化用例数（同一次提交内两口径差即此值）"),
        ("AST 静态守卫文件", _fmt(s["guard_files"]), "测试文件内含 ast.parse + assert"),
    ]
    out = ["| 指标 | 数值 | 口径定义 |", "| --- | ---: | --- |"]
    out += [f"| {a} | {b} | {c} |" for a, b, c in rows]
    return "\n".join(out)


def _git_head() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                           capture_output=True, text=True, timeout=30)
        return (r.stdout or "").strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def snapshot_meta() -> dict:
    """快照元信息：没有时点的数字等于没有口径的数字，必须一起记。"""
    return {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "git_head": _git_head(),
    }


def render_block(stats: dict, meta: dict) -> str:
    """文档数字块 = 时点/基线 commit 头 + 口径对照表。"""
    return (
        f"> 生成时点：{meta['generated_at']}｜基线 commit：`{meta['git_head']}`\n"
        ">\n"
        "> 规模数字随代码增删而变，属正常：以本快照为引用基准，复跑 `python scripts/quality_metrics.py` "
        "刷新；结构类数字（页面/模块/端点）由 `tests/test_quality_numbers_sync.py` 与**实时值**比对。\n"
        "\n"
        f"{render_table(stats)}"
    )


def write_doc(doc_path: str, block: str) -> None:
    try:
        with open(doc_path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        print(f"[metrics] 文档不存在，跳过回填：{doc_path}")
        return
    if MARK_BLOCK_BEGIN not in text or MARK_BLOCK_END not in text:
        print("[metrics] 未找到 AUTO:METRICS 标记块，跳过回填")
        return
    head, rest = text.split(MARK_BLOCK_BEGIN, 1)
    _, tail = rest.split(MARK_BLOCK_END, 1)
    new = f"{head}{MARK_BLOCK_BEGIN}\n{block}\n{MARK_BLOCK_END}{tail}"
    with open(doc_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(new)
    print(f"[metrics] 已回填数字块：{os.path.relpath(doc_path, ROOT)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="StockSignal 质量数字统一口径统计")
    ap.add_argument("--fast", action="store_true", help="跳过 pytest 收集（仅静态口径，秒出）")
    ap.add_argument("--json", default="", help="结果落盘到指定 json 路径")
    ap.add_argument("--snapshot", default="", help="快照落盘（含生成时点与基线 commit，供文档守卫比对）")
    ap.add_argument("--write", default="", help="把数字块回填到指定 Markdown 文档")
    args = ap.parse_args()

    stats = collect(fast=args.fast)
    meta = snapshot_meta()
    table = render_table(stats)
    print(f"生成时点：{meta['generated_at']}｜基线 commit：{meta['git_head']}")
    print(table)
    if stats["tests_collected"] is None:
        print("\n[metrics] 收集口径未取得（pytest 收集失败或被 --fast 跳过）；对外引用请只用静态口径并注明。")

    if args.json:
        with open(args.json, "w", encoding="utf-8", newline="\n") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        print(f"[metrics] 已写出 {args.json}")
    if args.snapshot:
        with open(args.snapshot, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"meta": meta, "stats": stats}, f, ensure_ascii=False, indent=2)
        print(f"[metrics] 已写出快照 {args.snapshot}")
    if args.write:
        write_doc(args.write, render_block(stats, meta))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
