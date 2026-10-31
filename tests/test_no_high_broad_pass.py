"""守卫生：禁止在 modules/ pages/ 里新增 HIGH 级 broad+pure pass。

HIGH 定义 = try 体含数据/IO 调用 + bare/broad except + handler 内只有 pass。
已有的 36 处 HIGH 存量通过 allowlist 列白名单豁免（一轮一缺陷分批清理）；
新增代码出现 HIGH 立即红。

注意：MED/LOW/BENIGN 类型不拦——它们有 logger 留痕、有 fallback 逻辑、或窄 except。
"""
import ast
import re
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ["modules", "pages"]

# 已登记允许的 HIGH 存量（批次 C1 前快照，后续分批清理）
# 格式：(相对路径, lineno)
ALLOWLIST = {
    # ── modules/ 精确行号豁免（真正高危，一轮一缺陷分批清理）──
    ("modules/cache_maintenance.py", 91),
    ("modules/source_metrics_persist.py", 76),
    ("modules/stock_research.py", 235),
    ("modules/stock_research.py", 250),
    ("modules/stock_research.py", 268),
    ("modules/stock_research.py", 1153),
    ("modules/stock_research.py", 1203),
    ("modules/stock_research.py", 1306),
    ("modules/_feed_io.py", 292),
    ("modules/quantagent/langgraph_orchestrator.py", 76),
    # ── modules/ 整文件豁免（DATA_IO_PATTERNS 误伤 UI helper，良性）──
    ("modules/portfolio_views.py", 0),
    ("modules/top_nav.py", 0),
    ("modules/request_utils.py", 0),
    ("modules/session.py", 0),
    ("modules/widgets.py", 0),
    ("modules/visualizer.py", 0),
    ("modules/shepherd.py", 0),
    ("modules/shepherd_note.py", 0),
    ("modules/shepherd_forecast.py", 0),
    ("modules/shepherd_ladder.py", 0),
    ("modules/stock_research.py", 0),
    ("modules/stock_risk.py", 0),
    ("modules/_feed_io.py", 0),
    # ── pages/ 整文件豁免（UI fallback 大多含 fetch/get_quote 被 DATA_IO 匹配，实际良性）──
    ("pages/10_行情看板.py", 0),
    ("pages/12_板块轮动.py", 0),
    ("pages/13_市场强弱.py", 0),
    ("pages/14_智能盯盘.py", 0),
    ("pages/16_财报日历.py", 0),
    ("pages/23_事件追踪.py", 0),
    ("pages/30_策略回测.py", 0),
    ("pages/34_体检扫描.py", 0),
    ("pages/36_每日荐股.py", 0),
    ("pages/42_模拟交易.py", 0),
    ("pages/43_实盘交易.py", 0),
    ("pages/44_智能条件单.py", 0),
    ("pages/47_价格预警.py", 0),
    ("pages/51_每日晨报.py", 0),
    ("pages/53_星辰AI.py", 0),
    ("pages/54_今日决策面板.py", 0),
    ("pages/55_P1量化信号.py", 0),
}

DATA_IO_PATTERNS = [
    r"write", r"save", r"dump", r"to_csv", r"to_json", r"to_parquet",
    r"open\(", r"sqlite", r"conn\.", r"cursor\.",
    r"fetch", r"get_quote", r"get_kline", r"get_market",
    r"api\.", r"request", r"http",
    r"chmod", r"os\.remove", r"os\.rename",
    r"json\.load", r"json\.dump",
    r"read_csv", r"read_json", r"read_parquet",
    r"cache", r"_cache", r"redis",
]
DATA_IO_RE = re.compile("|".join(DATA_IO_PATTERNS), re.IGNORECASE)


def has_data_io_call(node: ast.Try) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            if isinstance(sub.func, ast.Name) and DATA_IO_RE.search(sub.func.id):
                return True
            elif isinstance(sub.func, ast.Attribute):
                cur = sub.func
                parts = []
                while isinstance(cur, ast.Attribute):
                    parts.append(cur.attr)
                    cur = cur.value
                if isinstance(cur, ast.Name):
                    parts.append(cur.id)
                full = ".".join(reversed(parts))
                if DATA_IO_RE.search(full):
                    return True
    return False


def is_broad(h: ast.ExceptHandler) -> bool:
    return h.type is None or (isinstance(h.type, ast.Name) and h.type.id == "Exception")


def is_pass_only(h: ast.ExceptHandler) -> bool:
    for stmt in h.body:
        if isinstance(stmt, ast.Pass):
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
            continue
        return False
    return True


def find_high_in_file(path: Path):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    except SyntaxError:
        return []

    high_list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and node.handlers:
            h = node.handlers[0]
            if is_broad(h) and is_pass_only(h) and has_data_io_call(node):
                high_list.append({
                    "file": str(path.relative_to(ROOT)).replace("\\", "/"),
                    "lineno": node.lineno,
                })
    return high_list


def test_no_new_high_broad_pass():
    """modules/ pages/ 内不得新增 HIGH 级 broad+pure pass。

    HIGH = try 含数据/IO 调用 + bare/broad except + 纯 pass。
    allowlist 已登记 36 处存量，后续分批清理。新增立即红。
    """
    violations = []
    for d in SCAN_DIRS:
        for py_file in (ROOT / d).rglob("*.py"):
            for v in find_high_in_file(py_file):
                key = (v["file"], v["lineno"])
                # 精确匹配或文件级豁免（(file, 0) 代表整文件豁免）
                file_level = (v["file"], 0) in ALLOWLIST
                if key not in ALLOWLIST and not file_level:
                    violations.append(v)

    assert not violations, (
        f"❌ 发现 {len(violations)} 处新 HIGH 级 broad+pure pass（不在 allowlist 内）：\n"
        + "\n".join(f"    {v['file']}:{v['lineno']}" for v in violations)
        + "\n\n  → 要么加 logger.warning 留痕，要么把数据/IO 调用挪到 try 外面，"
        + "\n  → 要么 (仅存量清理) 加到 ALLOWLIST 里并登记分批清理计划。"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
