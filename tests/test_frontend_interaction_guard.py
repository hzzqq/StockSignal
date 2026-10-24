"""
tests/test_frontend_interaction_guard.py — T-316 全站前端交互体检守卫（离线）

体检结论（2026-10-24 扫描 69 页，详见 docs/frontend-interaction-audit.md）：
- 破坏性操作单击即执行：仅 83_分析规则库「删除」为真实高危（不可恢复），本轮已加二次确认；
  10_行情看板「移除自选」有下拉选择前置、33_ETF筛选「清空筛选/清空选择」均可逆，属误报。
- 静默失败（纯 except: pass/continue）：89 处存量，按项目「一轮一缺陷」原则不在本轮批量清，
  但必须先钉基线防继续增长。

三条守卫：
1. 规则删除必须二次确认（确认态 → 确认删除 / 取消 两键，删除调用只在确认分支内）；
2. 全站破坏性按钮：要么同文件存在确认机制，要么在白名单（有其它防误触设计）；
3. 静默 except 基线不得增长（只允许减少）。
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "pages"

DESTRUCTIVE = re.compile(r"(删除|清空|重置|覆盖|解绑|撤销|注销)")
CONFIRM = re.compile(r"(确认|confirm|_cfm|二次)")

# 有其它防误触设计（下拉选择前置 / 可逆操作）的破坏性按钮白名单：文件 → 按钮标签片段
_SAFE_BY_DESIGN = {
    "10_行情看板.py": "移除",     # 需先在「移除自选」下拉选中标的，再点按钮
    "33_ETF筛选.py": "清空",      # 清空的是筛选条件/勾选状态，均可逆、无数据损失
}

SILENT_BASELINE = 89  # 2026-10-24 基线（AST 实测）


def _pages():
    return sorted(PAGES.glob("*.py"))


def test_rule_delete_requires_confirm():
    """83 页规则删除必须走「二次确认」态，删除调用不得出现在首次点击分支。"""
    src = (PAGES / "83_分析规则库.py").read_text(encoding="utf-8")
    assert "_skill_del_cfm_" in src, "缺少删除确认态 key"
    assert "确认删除" in src, "缺少「确认删除」按钮"
    assert "取消" in src, "缺少取消入口（只能确认不能反悔）"
    # 结构断言：delete_skill 必须在确认分支内，首次点击只置位不删除
    tree = ast.parse(src)
    first_click_del = False
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            seg = ast.get_source_segment(src, node.test) or ""
            body_seg = "".join(ast.get_source_segment(src, b) or "" for b in node.body)
            # 首次点击分支：test 含 del_{sid}，body 不应含 delete_skill
            if 'del_' in seg and 'del_cfm' not in seg and 'delete_skill' in body_seg:
                first_click_del = True
    assert not first_click_del, "删除调用出现在首次点击分支（二次确认被绕过）"


def test_destructive_buttons_guarded():
    """全站破坏性按钮：未在白名单者，同文件必须有确认机制。"""
    offenders = []
    for p in _pages():
        src = p.read_text(encoding="utf-8", errors="replace")
        labels = [m.group(1) for m in re.finditer(r'st\.button\(\s*["\']([^"\']{1,60})', src)]
        hits = [lb for lb in labels if DESTRUCTIVE.search(lb)]
        if not hits:
            continue
        wl = _SAFE_BY_DESIGN.get(p.name, "")
        rest = [h for h in hits if wl and wl in h]
        real = [h for h in hits if h not in rest]
        if real and not CONFIRM.search(src):
            offenders.append(f"{p.name}: {real}")
    assert not offenders, "以下破坏性按钮缺二次确认（新增需配套确认态或加入白名单）: " + "; ".join(offenders)


def test_silent_except_baseline():
    """纯 except: pass/continue 只许减少，不许增长（防静默失败回潮）。"""
    total = 0
    for p in _pages():
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and len(node.body) == 1:
                b = node.body[0]
                if isinstance(b, (ast.Pass, ast.Continue)):
                    total += 1
    assert total <= SILENT_BASELINE, (
        f"静默 except 从基线 {SILENT_BASELINE} 增长到 {total}：新增吞异常必须留痕（logger）"
    )


def test_audit_report_exists():
    assert (ROOT / "docs" / "frontend-interaction-audit.md").is_file(), "缺少体检报告"
