"""需求 → 测试 → 实证 追溯矩阵生成器（评估报告 P2-9）。

评估报告原文：
    「需求-测试显式追踪矩阵缺失（契约测试已隐含映射，但无一张表把需求条目对应到测试文件）」
    P2-9：需求→测试→实证追踪矩阵文档化。

本脚本不做人工编表，全部从仓库静态结构推导，保证「表里的每一行都能指回代码」：

  第 1 层 功能域：按 pages/ 文件编号段归组（10-17 行情 / 20-25 个股 / …），
                 域内页面清单直接来自 pages/*.py 文件名。
  第 2 层 模块：解析每个页面的 import，取它实际依赖的 modules/* 模块（AST，不执行代码）。
  第 3 层 测试：解析 tests/ + backend/tests/ + modules/tests 的 import，反查「哪些测试文件覆盖该模块」，
                 并据此算出「域内模块被测试覆盖的比例」——这是报告里说的「追踪矩阵」的量化部分。
  第 4 层 实证：扫 reports/*.json，反查生产代码里谁写/读它（文件名字符串出现在哪些模块/脚本），
                 得到「结论 ← 产物 ← 代码 ← 测试」的可追溯链。

输出 docs/质量追溯矩阵_2026-11-04.md（含复跑命令），可随时重跑刷新。

用法：
    python scripts/gen_trace_matrix.py            # 生成并打印摘要
    python scripts/gen_trace_matrix.py --dry-run  # 只打印，不写文件
"""
from __future__ import annotations

import argparse
import ast
import os
import re
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_REL = "docs/质量追溯矩阵_2026-11-04.md"

TEST_DIRS = ("tests", "backend/tests", "modules/tests")

# 功能域：按页面编号段归组（段边界来自 pages/ 实际编号，见下表「页面」列）
DOMAINS = [
    ("行情与市场认知", 10, 19),
    ("个股研究与事件", 20, 29),
    ("策略与选股", 30, 39),
    ("交易与持仓", 40, 49),
    ("情绪与市场状态", 50, 59),
    ("深度研究（温度/广度/因子）", 60, 69),
    ("复盘与扫描", 70, 79),
    ("数据基座与工具", 80, 89),
    ("用户与系统", 90, 99),
]

_IMPORT_MOD_RE = re.compile(r"from\s+modules(?:\.(\w+))?\s+import\s+([\w\s,()*]+)")
_PLAIN_IMPORT_RE = re.compile(r"import\s+modules\.(\w+)")
_MENTION_RE = re.compile(r"\bmodules[./](\w+)")


def _py_files(sub: str) -> list[str]:
    base = os.path.join(ROOT, sub)
    if not os.path.isdir(base):
        return []
    out = []
    for dirpath, _dirs, files in os.walk(base):
        if "__pycache__" in dirpath:
            continue
        out += [os.path.join(dirpath, f) for f in files if f.endswith(".py")]
    return out


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except OSError:
        # ui_audit_exempt: 读不出的文件按空源码处理（该文件即不贡献 import 边）
        return ""


def _modules_of(path: str) -> set[str]:
    """解析一个 .py 真正 import 了哪些 modules/* 模块（纯 AST，不执行代码、不看文本提及）。

    只用 import 而不用「源码里出现过 modules/xxx 字样」：后者会把「某个测试扫描目录、
    在断言里列举模块文件名」误算成依赖，把无关测试排进代表测试里（实测发生过）。
    """
    try:
        tree = ast.parse(_read(path))
    except SyntaxError:
        return set()
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if base == "modules":
                mods.update(a.name.split(".")[0] for a in node.names)
            elif base.startswith("modules."):
                mods.add(base.split(".")[1])
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("modules."):
                    mods.add(a.name.split(".")[1])
    return mods


def _page_no(name: str) -> int | None:
    m = re.match(r"(\d+)_", name)
    return int(m.group(1)) if m else None


def _domain_of(no: int) -> str:
    for name, lo, hi in DOMAINS:
        if lo <= no <= hi:
            return name
    return "未归类"


def build() -> dict:
    # 只认 modules/ 下真实存在的业务模块文件（stem）；文本里出现的 "modules.xxx" 若不在
    # 该集合内（子包名、章节名、文档里的举例）一律丢弃，否则覆盖率会算出 >100% 的荒谬值。
    # 排除：modules/tests/ 下的测试文件、__init__.py、下划线私有实现（不是需求单元）。
    stems = {
        os.path.splitext(os.path.basename(p))[0]
        for p in _py_files("modules")
        if not os.path.relpath(p, ROOT).replace("\\", "/").startswith("modules/tests/")
        and os.path.basename(p) != "__init__.py"
        and not os.path.basename(p).startswith("_")
    }

    # ── 页面 → 域 → 依赖模块
    pages = [p for p in _py_files("pages") if os.path.basename(p).endswith(".py")]
    page_info = {}
    for p in sorted(pages):
        no = _page_no(os.path.basename(p))
        if no is None:
            continue
        page_info[os.path.basename(p)] = {
            "no": no,
            "domain": _domain_of(no),
            "modules": _modules_of(p) & stems,
        }

    # ── 测试文件 → 覆盖模块
    module_tests: dict[str, set[str]] = defaultdict(set)
    test_files: list[str] = []
    for d in TEST_DIRS:
        for p in _py_files(d):
            if not os.path.basename(p).startswith("test"):
                continue
            rel = os.path.relpath(p, ROOT).replace("\\", "/")
            test_files.append(rel)
            for mod in _modules_of(p) & stems:
                module_tests[mod].add(rel)

    # ── 实证产物 → 引用它的代码文件
    reports_dir = os.path.join(ROOT, "reports")
    report_refs: dict[str, list[str]] = {}
    if os.path.isdir(reports_dir):
        for fn in sorted(os.listdir(reports_dir)):
            if not fn.endswith(".json"):
                continue
            hits = []
            for p in (_py_files("scripts") + _py_files("modules") + _py_files("tests")
                      + _py_files("thesis/素材")):
                if fn in _read(p):
                    hits.append(os.path.relpath(p, ROOT).replace("\\", "/"))
            report_refs[fn] = hits

    # ── 域汇总
    domains = []
    for name, _lo, _hi in DOMAINS:
        rows = {k: v for k, v in page_info.items() if v["domain"] == name}
        mods = set().union(*[v["modules"] for v in rows.values()]) if rows else set()
        covered = {m for m in mods if module_tests.get(m)}
        tests = set()
        for m in mods:
            tests |= module_tests.get(m, set())
        # 代表测试：按「覆盖该域多少个模块」排序，而不是按字典序随便取 5 个
        # （字典序会把与本域无关的契约测试排到前面，读起来像凑数）
        overlap = {t: len({m for m in mods if t in module_tests.get(m, set())}) for t in tests}
        top_tests = sorted(overlap.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        domains.append({
            "domain": name,
            "pages": sorted(rows, key=lambda k: rows[k]["no"]),
            "modules": sorted(mods),
            "covered_modules": sorted(covered),
            "tests": sorted(tests),
            "top_tests": top_tests,
        })

    return {
        "page_info": page_info,
        "domain_rows": domains,
        "module_tests": {k: sorted(v) for k, v in module_tests.items()},
        "report_refs": report_refs,
        "test_files": test_files,
        "all_modules": sorted(stems),
    }


def render(data: dict, stats: dict) -> str:
    lines: list[str] = []
    lines.append("# StockSignal 质量追溯矩阵（需求 → 测试 → 实证 · 2026-11-04）")
    lines.append("")
    lines.append("> 对应《StockSignal 软件开发质量评估报告》**P2-9「需求→测试→实证追踪矩阵文档化」**。")
    lines.append("> 本表由 `scripts/gen_trace_matrix.py` 从仓库静态结构自动生成，不是手写清单：")
    lines.append("> 每一行的页面、模块、测试文件都可直接点回代码路径，复跑命令见文末。")
    lines.append("")
    lines.append("## 一、口径说明")
    lines.append("")
    lines.append("| 层 | 数据来源 | 判定方式 |")
    lines.append("| --- | --- | --- |")
    lines.append("| 功能域 | `pages/*.py` 文件名编号 | 按编号段归组（10-19 / 20-29 / … / 90-99） |")
    lines.append("| 模块 | 页面源码的 `import` | AST 解析 `from modules.X import …`，不执行代码 |")
    lines.append("| 测试 | `tests/` + `backend/tests/` + `modules/tests` | 测试文件 `import` 到该模块即计入「已覆盖」 |")
    lines.append("| 实证 | `reports/*.json` | 扫描全仓文本，找出读写该产物的脚本/模块/论文素材 |")
    lines.append("")
    lines.append("「覆盖」只表示**有测试文件引用该模块**，不代表分支覆盖充分；分支覆盖以覆盖率门禁"
                 "（`--cov-fail-under`）为准，两者互补而非替代。")
    lines.append("")
    lines.append("## 二、功能域覆盖总览")
    lines.append("")
    lines.append("| 功能域 | 页面数 | 涉及模块 | 已被测试引用的模块 | 模块引用覆盖率 | 相关测试文件 |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for row in data["domain_rows"]:
        n_mod = len(row["modules"])
        n_cov = len(row["covered_modules"])
        pct = f"{n_cov / n_mod * 100:.1f}%" if n_mod else "—"
        lines.append(f"| {row['domain']} | {len(row['pages'])} | {n_mod} | {n_cov} | {pct} | {len(row['tests'])} |")
    total_pages = sum(len(r["pages"]) for r in data["domain_rows"])
    lines.append("")
    lines.append(f"合计：**{total_pages} 个页面**、{stats['modules_total']} 个业务模块、"
                 f"{stats['modules_covered']} 个模块被测试引用"
                 f"（{stats['modules_covered_pct']}），{len(data['test_files'])} 个测试文件。")
    lines.append("")
    lines.append("## 三、逐域明细（页面 → 依赖模块 → 测试文件）")
    lines.append("")
    for row in data["domain_rows"]:
        lines.append(f"### {row['domain']}（{len(row['pages'])} 页 / {len(row['modules'])} 模块 / "
                     f"{len(row['tests'])} 个相关测试文件）")
        lines.append("")
        lines.append("| 页面 | 依赖模块（节选） |")
        lines.append("| --- | --- |")
        for page in row["pages"]:
            mods = sorted(data["page_info"][page]["modules"])
            sample = "、".join(f"`{m}`" for m in mods[:6])
            if len(mods) > 6:
                sample += f" 等 {len(mods)} 个"
            lines.append(f"| `pages/{page}` | {sample or '（无 modules 依赖）'} |")
        lines.append("")
        verified = [(t, n) for t, n in row["top_tests"] if n > 0]
        lines.append(
            "代表测试（按覆盖该域模块数量排序）： "
            + ("、".join(f"`{t}`（{n} 个域内模块）" for t, n in verified) if verified else "（无）")
        )
        lines.append("")
    lines.append("## 四、未被任何测试文件引用的模块（可执行的补测口径）")
    lines.append("")
    uncovered = [m for m in sorted(data["all_modules"]) if m not in data["module_tests"]]
    lines.append(f"共 **{len(uncovered)}** 个（占 {len(data['all_modules'])} 个业务模块的 "
                 f"{len(uncovered) / len(data['all_modules']) * 100:.1f}%）：")
    lines.append("")
    for m in uncovered:
        lines.append(f"- `modules/{m}.py`")
    lines.append("")
    lines.append("## 五、实证产物追溯（结论 ← 产物 ← 代码 ← 测试）")
    lines.append("")
    lines.append("| 实证产物 | 仓库内引用点（写/读该文件的代码） |")
    lines.append("| --- | --- |")
    for fn, hits in sorted(data["report_refs"].items()):
        refs = "、".join(f"`{h}`" for h in hits[:6]) if hits else "**无代码引用（需复核是否手工放置）**"
        if len(hits) > 6:
            refs += f" 等 {len(hits)} 处"
        lines.append(f"| `reports/{fn}` | {refs} |")
    lines.append("")
    lines.append("## 六、复跑与限制")
    lines.append("")
    lines.append("```bash")
    lines.append("python scripts/gen_trace_matrix.py            # 重新生成本表")
    lines.append("python scripts/gen_trace_matrix.py --dry-run  # 只打印摘要，不写盘")
    lines.append("```")
    lines.append("")
    lines.append("已知限制：")
    lines.append("")
    lines.append("1. 只做**静态 import 追溯**，不做运行时插桩——「测试文件 import 了该模块」不等于该模块每条分支都被断言过。")
    lines.append("2. 功能域按页面编号段归组，编号本身即产品设计的一部分；新增页面落在已有编号段会自动归入对应域。")
    lines.append("3. `reports/*.json` 若由外部交接放入（代码里无引用），本表会显式标红「无代码引用」，不做粉饰。")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="生成需求→测试→实证追溯矩阵")
    ap.add_argument("--dry-run", action="store_true", help="只打印摘要，不写文件")
    args = ap.parse_args()

    data = build()
    modules_total = len(data["all_modules"])
    covered = len(data["module_tests"])
    stats = {
        "modules_total": modules_total,
        "modules_covered": covered,
        "modules_covered_pct": f"{covered / modules_total * 100:.1f}%" if modules_total else "—",
    }
    doc = render(data, stats)

    for row in data["domain_rows"]:
        print(f"[trace] {row['domain']}: {len(row['pages'])} 页 / {len(row['modules'])} 模块 / "
              f"{len(row['covered_modules'])} 已覆盖 / {len(row['tests'])} 测试文件")
    print(f"[trace] 模块 {covered}/{modules_total}（{stats['modules_covered_pct']}）被测试引用 · "
          f"实证产物 {len(data['report_refs'])} 个")

    if args.dry_run:
        print(f"[trace] DRY-RUN：生成 {len(doc):,} 字符，未写盘")
        return 0
    out = os.path.join(ROOT, OUT_REL)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(doc)
    print(f"[trace] 已生成 {OUT_REL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
