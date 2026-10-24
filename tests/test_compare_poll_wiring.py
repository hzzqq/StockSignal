"""
tests/test_compare_poll_wiring.py — T-318 多股对比轮询接线 AST 守卫（离线）

缺陷背景（与 T-309 / T-313 同族）：pages/21_多股对比.py 的 fragment_compare_result
在任务 pending/running 分支内调用 st_autorefresh(2500ms)。该第三方组件在 fragment
内不触发 fragment 重跑（T-309 实证），提交又发生在另一个 fragment（fragment_compare_setup）
内 —— 提交后不产生整页重跑，结果区的自动刷新不生效，对比结果永不自动出现，
需用户手动交互才取回（等待饥饿）。

钉住三项契约（mutation 目标）：
1. fragment_compare_result 必须经 safe_fragment(..., run_every=...) 装饰（服务端定时驱动）；
2. 页面内禁止 st_autorefresh 的导入 / 调用 / 名字引用；
3. 模块级必须存在无条件的 fragment_compare_result() 常驻挂载（否则提交后片段消失）。
"""
import ast
from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "pages" / "21_多股对比.py"


def _tree() -> ast.Module:
    return ast.parse(PAGE.read_text(encoding="utf-8"), filename=str(PAGE))


def _fn(tree: ast.Module, name: str):
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return n
    return None


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Call):
        f = node.func
        return getattr(f, "attr", getattr(f, "id", ""))
    return ""


def test_result_fragment_has_run_every():
    fn = _fn(_tree(), "fragment_compare_result")
    assert fn is not None, "未找到 fragment_compare_result"
    hit = False
    for dec in fn.decorator_list:
        if isinstance(dec, ast.Call) and _call_name(dec) == "safe_fragment":
            hit = True
            kw = {k.arg: k.value for k in dec.keywords}
            assert "run_every" in kw, (
                "缺少 run_every：结果区轮询将依赖 st_autorefresh（fragment 内不触发重跑，"
                "对比结果永不自动出现）"
            )
            val = kw["run_every"]
            assert isinstance(val, ast.Constant) and isinstance(val.value, (int, float))
            assert 1.0 <= float(val.value) <= 5.0, f"run_every={val.value} 超出合理区间"
    assert hit, "fragment_compare_result 缺少 safe_fragment 装饰"


def test_no_st_autorefresh_in_page():
    for node in ast.walk(_tree()):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert "autorefresh" not in module, f"页面重新导入 {module}（T-309 已证 fragment 内不生效）"
            for alias in node.names:
                assert "autorefresh" not in alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert "autorefresh" not in alias.name
        elif isinstance(node, ast.Call):
            assert _call_name(node) != "st_autorefresh", "页面重新调用 st_autorefresh"
        elif isinstance(node, ast.Name):
            assert node.id != "st_autorefresh", "页面存在 st_autorefresh 名字引用"


def test_result_fragment_mounted_unconditionally():
    tree = _tree()
    bare = [
        n for n in tree.body
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Name) and n.value.func.id == "fragment_compare_result"
    ]
    assert bare, "模块级缺少无条件 fragment_compare_result() 常驻挂载"
