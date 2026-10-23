"""
tests/test_xc_poll_wiring.py — T-309 星辰AI 轮询接线 AST 守卫（离线，不 import 页面模块）

缺陷背景（T-309）：提交全走 fragment 级 rerun（chat_input/按钮均在 fragment_chat 内），
模块级「if xc_task_id: _poll_ai_task()」只在整页运行时执行 → 提交后轮询片段从未挂载，
任务终态只能等下一次整页交互才取回（等待饥饿）；且第三方 st_autorefresh 组件在
fragment 内不触发重跑，双重失效。

钉住三项接线契约，防回潮（mutation 目标，删除任一接线 → 对应断言变红）：
1. _poll_ai_task 必须经 safe_fragment(..., run_every=...) 装饰（服务端定时驱动）；
2. _poll_ai_task() 必须在模块级【无条件】裸调用挂载（不得包进 if 条件）；
3. 页面内不得再出现 st_autorefresh 的导入或调用。
"""
import ast
from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "pages" / "53_星辰AI.py"


def _tree() -> ast.Module:
    return ast.parse(PAGE.read_text(encoding="utf-8"), filename=str(PAGE))


def _poll_fn(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_poll_ai_task":
            return node
    raise AssertionError("未找到模块级 _poll_ai_task 函数定义")


def _call_name(node: ast.AST) -> str:
    """取 Call 的函数简名；非 Call 返回空串。"""
    if isinstance(node, ast.Call):
        fn = node.func
        if isinstance(fn, ast.Attribute):
            return fn.attr
        if isinstance(fn, ast.Name):
            return fn.id
    return ""


def test_poll_fragment_has_run_every():
    """契约1：safe_fragment 装饰必须带 run_every（服务端定时驱动，不依赖前端 JS）。"""
    fn = _poll_fn(_tree())
    hit = False
    for dec in fn.decorator_list:
        if isinstance(dec, ast.Call) and _call_name(dec) == "safe_fragment":
            hit = True
            kw = {k.arg: k.value for k in dec.keywords}
            assert "run_every" in kw, (
                "safe_fragment 装饰缺少 run_every 参数：轮询片段将失去服务端定时驱动（T-309 饥饿回潮）"
            )
            val = kw["run_every"]
            assert isinstance(val, ast.Constant) and isinstance(val.value, (int, float)), \
                "run_every 必须是数值常量（秒）"
            assert float(val.value) <= 3.0, \
                f"run_every={val.value} 间隔过大，终态取回延迟不可接受"
    assert hit, "_poll_ai_task 缺少 safe_fragment 装饰"


def test_poll_mount_is_unconditional():
    """契约2：模块级 _poll_ai_task() 必须无条件裸调用（不得包进 if 条件守卫）。"""
    tree = _tree()
    bare = [
        n for n in tree.body
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Name) and n.value.func.id == "_poll_ai_task"
    ]
    assert bare, (
        "模块级缺少裸 _poll_ai_task() 常驻挂载：fragment 级提交不会触发模块级代码，"
        "条件挂载会让轮询片段在提交后从未渲染（T-309 饥饿根因）"
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and _call_name(child) == "_poll_ai_task":
                    raise AssertionError(
                        "_poll_ai_task 被包进 if 条件守卫内（T-309 饥饿回潮）"
                    )


def test_no_st_autorefresh_in_page():
    """契约3：页面内禁止 st_autorefresh 导入/调用（组件在 fragment 内不触发重跑）。"""
    for node in ast.walk(_tree()):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert "autorefresh" not in module, \
                f"页面重新导入 {module}（T-309 已证其在 fragment 内不触发重跑）"
            for alias in node.names:
                assert "autorefresh" not in alias.name, \
                    f"页面重新导入 {alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert "autorefresh" not in alias.name, \
                    f"页面重新导入 {alias.name}"
        elif isinstance(node, ast.Call):
            assert _call_name(node) != "st_autorefresh", \
                "页面重新调用 st_autorefresh（T-309 缺陷回潮）"
