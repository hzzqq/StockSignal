"""
tests/test_quant_poll_wiring.py — T-313 QuantAgent 任务轮询接线 AST 守卫（离线，不 import 页面模块）

缺陷背景（T-313，T-309 同族收尾）：pages/25_QuantAgent投研.py 的 _result_panel
（safe_fragment）在任务 pending/running 分支内调用 st_autorefresh(interval=2500)
驱动进度刷新——T-309 已实证该第三方组件在 fragment 内不触发重跑，任务进度不刷新、
终态需下一次整页交互才取回（等待饥饿）。

钉住三项接线契约，防回潮（mutation 目标，破坏任一接线 → 对应断言变红）：
1. _result_panel 必须经 safe_fragment(..., run_every=...) 装饰（服务端定时驱动）；
2. 页面内禁止 st_autorefresh 的导入、调用或名字引用（含 `if st_autorefresh is not None`
   式的回潮）；
3. main 函数体内必须存在不被 if 条件包裹的 _result_panel() 裸调用（整页任意执行
   路径都有常驻挂载点——提交按钮在整页层，fragment 级提交依赖该挂载）。
"""
import ast
from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "pages" / "25_QuantAgent投研.py"


def _tree() -> ast.Module:
    return ast.parse(PAGE.read_text(encoding="utf-8"), filename=str(PAGE))


def _panel_fn(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_result_panel":
            return node
    raise AssertionError("未找到模块级 _result_panel 函数定义")


def _call_name(node: ast.AST) -> str:
    """取 Call 的函数简名；非 Call 返回空串。"""
    if isinstance(node, ast.Call):
        fn = node.func
        if isinstance(fn, ast.Attribute):
            return fn.attr
        if isinstance(fn, ast.Name):
            return fn.id
    return ""


def test_panel_fragment_has_run_every():
    """契约1：safe_fragment 装饰必须带 run_every 数值常量（服务端定时驱动）。"""
    fn = _panel_fn(_tree())
    hit = False
    for dec in fn.decorator_list:
        if isinstance(dec, ast.Call) and _call_name(dec) == "safe_fragment":
            hit = True
            kw = {k.arg: k.value for k in dec.keywords}
            assert "run_every" in kw, (
                "_result_panel 的 safe_fragment 装饰缺少 run_every："
                "进度/终态将依赖 st_autorefresh（fragment 内不触发重跑，T-309 饥饿回潮）"
            )
            val = kw["run_every"]
            assert isinstance(val, ast.Constant) and isinstance(val.value, (int, float)), \
                "run_every 必须是数值常量（秒）"
            assert 1.0 <= float(val.value) <= 3.0, \
                f"run_every={val.value} 超出合理区间（过快扰流/过慢终态取回延迟）"
    assert hit, "_result_panel 缺少 safe_fragment 装饰"


def test_no_st_autorefresh_anywhere():
    """契约2：页面内禁止 st_autorefresh 导入/调用/名字引用（含 try-import 回潮）。"""
    for node in ast.walk(_tree()):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert "autorefresh" not in module, \
                f"页面重新导入 {module}（T-309 已证其在 fragment 内不触发重跑）"
            for alias in node.names:
                assert "autorefresh" not in alias.name, f"页面重新导入 {alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert "autorefresh" not in alias.name, f"页面重新导入 {alias.name}"
        elif isinstance(node, ast.Call):
            assert _call_name(node) != "st_autorefresh", \
                "页面重新调用 st_autorefresh（T-313 缺陷回潮）"
        elif isinstance(node, ast.Name):
            assert node.id != "st_autorefresh", \
                "页面存在 st_autorefresh 名字引用（如 if st_autorefresh is not None 守卫回潮）"


def test_panel_mounted_unconditionally_in_main():
    """契约3：main 体内存在不被 if 包裹的 _result_panel() 裸调用（常驻挂载点）。"""
    tree = _tree()
    main_fn = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            main_fn = node
            break
    assert main_fn is not None, "未找到 main 函数定义"
    bare = [
        n for n in main_fn.body
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Name) and n.value.func.id == "_result_panel"
    ]
    assert bare, (
        "main 函数体顶层缺少 _result_panel() 裸调用：若仅包在 if 分支内，"
        "提交后（另一分支）整页重跑不会挂载轮询片段，终态永不取回"
    )
