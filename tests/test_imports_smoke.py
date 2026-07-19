"""R20：全包 import / 语法守卫测试（无网依赖）。

作为整包安全网，捕获任何「导入期 / 语法级」回归：
1. 对 modules/ 与 pages/ 下所有 .py 跑 py_compile，任一语法错误即失败；
2. 逐一 import 全部 modules.* 子模块，确认无导入期异常
   （如缺失依赖、模块级未捕获异常、循环 import 死锁等）。

不 import pages.*（页面模块在顶层调用 st.set_page_config，需 streamlit
运行时，不属于「代码可导入性」回归范畴，由页面冒烟测试另行覆盖）。
"""

import importlib
import os
import pkgutil
import py_compile

import modules

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _iter_py(directory):
    for root, _dirs, files in os.walk(directory):
        # 跳过隐藏 / 缓存目录
        if "/." in root or "\\." in root or "__pycache__" in root:
            continue
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(root, f)


def test_all_source_compiles():
    """全包所有 .py 语法体检：modules + pages。"""
    targets = list(_iter_py(os.path.join(ROOT, "modules"))) + \
              list(_iter_py(os.path.join(ROOT, "pages")))
    assert targets, "未找到任何 .py 源文件"
    failed = []
    for f in targets:
        try:
            py_compile.compile(f, doraise=True)
        except py_compile.PyCompileError as e:
            failed.append((f, str(e)))
    assert not failed, f"语法错误：{failed}"


def test_all_modules_importable():
    """逐一 import modules.* 子模块，确认无导入期异常。"""
    failed = []
    count = 0
    for _, name, _ in pkgutil.iter_modules(modules.__path__):
        count += 1
        try:
            importlib.import_module(f"modules.{name}")
        except Exception as e:  # noqa: BLE001
            failed.append((name, type(e).__name__, str(e)[:120]))
    assert count > 0, "未扫描到任何 modules 子模块"
    assert not failed, f"模块导入失败：{failed}"
