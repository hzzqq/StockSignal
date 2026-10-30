"""
tests/test_silent_failure_triage_guard.py — T-317 静默失败分诊清理守卫（离线）

T-316 体检发现 69 页 + modules 有 89 处纯 `except: pass/continue`；AST 分诊出
try 体含 IO/请求调用的 14 处，逐条复核后确认 3 处需处理，其余为读文件/内存生成
CSV 的良性降级（有默认值或已回退），不在本轮改。

三条契约（mutation 目标）：
1. 13_市场强弱 `_watchlist_codes`：失败必须与「确实没有自选股」区分——返回
   (codes, ok)，不再把请求失败谎报成空列表（诚实数据语义）；调用方按 ok 分支出
   错误提示而非「暂无自选股」。
2. 46_自选股监控 后端取价失败：静默回退前必须 logger 留痕（降级仍继续）。
3. cache_maintenance 单文件 unlink 失败：必须 logger 留痕（控制流不变，
   失败仍不中断其余文件）。
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P_STRENGTH = ROOT / "pages" / "13_市场强弱.py"
# P0-1c 定位修正：46 页实现体已抽取至 modules/portfolio_views.py（断言本体零改动）
P_WATCH = ROOT / "modules" / "portfolio_views.py"
M_CACHE = ROOT / "modules" / "cache_maintenance.py"


def _src(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _fn(tree: ast.Module, name: str):
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return n
    return None


def test_watchlist_codes_distinguishes_failure():
    src = _src(P_STRENGTH)
    tree = ast.parse(src)
    fn = _fn(tree, "_watchlist_codes")
    assert fn is not None, "未找到 _watchlist_codes"
    seg = ast.get_source_segment(src, fn) or ""
    assert "logger.warning" in seg, "请求失败必须留痕"

    # 所有 return 必须为二元组 (codes, ok)；不得再有裸列表返回
    for n in ast.walk(fn):
        if isinstance(n, ast.Return) and isinstance(n.value, ast.List):
            raise AssertionError("仍有裸列表返回：失败与「真的没有自选股」不可区分")
    tuples = [n.value for n in ast.walk(fn)
              if isinstance(n, ast.Return) and isinstance(n.value, ast.Tuple)
              and len(n.value.elts) == 2]
    assert tuples, "未找到 (codes, ok) 二元组返回"

    def _is_empty_list(node) -> bool:
        return isinstance(node, ast.List) and len(node.elts) == 0

    def _is_const(node, val) -> bool:
        return isinstance(node, ast.Constant) and node.value is val

    assert any(_is_empty_list(t.elts[0]) and _is_const(t.elts[1], False) for t in tuples), \
        "失败分支必须返回 ([], False)"
    assert any(_is_const(t.elts[1], True) for t in tuples), "成功分支必须返回 ok=True"


def test_watchlist_codes_caller_branches_on_ok():
    src = _src(P_STRENGTH)
    tree = ast.parse(src)
    ok_names = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call):
            fn = n.value.func
            if isinstance(fn, ast.Name) and fn.id == "_watchlist_codes":
                tgt = n.targets[0] if n.targets else None
                if isinstance(tgt, ast.Tuple) and len(tgt.elts) == 2:
                    ok_names.add(getattr(tgt.elts[1], "id", ""))
    assert ok_names, "调用方未解包 (codes, ok)"

    # 必须存在 `if not <ok>:` 分支且体内给出「加载失败」提示
    for name in ok_names:
        for n in ast.walk(tree):
            if (isinstance(n, ast.If) and isinstance(n.test, ast.UnaryOp)
                    and isinstance(n.test.op, ast.Not)
                    and isinstance(n.test.operand, ast.Name)
                    and n.test.operand.id == name):
                body = "".join(ast.get_source_segment(src, s) or "" for s in n.body)
                if "加载失败" in body:
                    return
    raise AssertionError("未找到对 ok=False 的「加载失败」分支（仍会把失败显示成暂无自选股）")


def test_watch_page_logs_fallback():
    src = _src(P_WATCH)
    tree = ast.parse(src)
    fn = _fn(tree, "_quote_one")
    assert fn is not None, "未找到 _quote_one"
    seg = ast.get_source_segment(src, fn) or ""
    assert seg.count("logger.warning") >= 2, "后端失败与本地失败两处都必须留痕（否则空态无法诊断）"
    for n in ast.walk(fn):
        if isinstance(n, ast.ExceptHandler) and len(n.body) == 1 and isinstance(n.body[0], ast.Pass):
            raise AssertionError("取价函数内仍有纯 except: pass")


def test_cache_unlink_failure_logged():
    src = _src(M_CACHE)
    tree = ast.parse(src)
    assert "logger" in src, "cache_maintenance 缺少 logger"
    # unlink 的 except 体不得只有 pass
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            has_unlink = any(
                isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "unlink"
                for n in ast.walk(node)
            )
            if not has_unlink:
                continue
            for h in node.handlers:
                if len(h.body) == 1 and isinstance(h.body[0], ast.Pass):
                    continue
                if any(isinstance(n, ast.Call) and getattr(n.func, "attr", "") in ("warning", "error")
                       for n in ast.walk(h)):
                    found = True
    assert found, "unlink 失败分支必须 logger 留痕（仍不中断其余文件）"
