"""tests/test_pages_use_standard_setup.py

锁死页面标准化入口约定。

背景：项目约定所有页面统一走 ``modules.page_utils.render_standard_page``，
它一次性完成 ``apply_page_config`` + ``require_auth`` + 用户徽章 + 全局 CSS +
标题，并自动标记 ``_active_page``（侧边栏高亮）。此前 ``pages/Q_quantagent投研.py``
裸调 ``st.set_page_config`` 绕过该入口，导致：
  1. **该页未做登录校验**（require_auth 缺失），与其余页面不一致——越权访问面；
  2. 侧边栏高亮失效（未标记 _active_page）。
Cycle 66 已修复该页。

本测试锁定三条源码级不变量：
  1. 除显式登记的白名单页外，所有 pages/*.py 必须调用 render_standard_page；
  2. 白名单条目必须真实存在（函数/文件改名后不得变成死条目）；
  3. 已调用 render_standard_page 的页面，不得再自行调用 st.set_page_config
     （Streamlit 只允许设置一次，重复调用会抛异常）。

2026-08-28 新增（Cycle 66）。
"""
import ast
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 显式登记的不走标准入口的页面（必须写明原因）
STANDARD_SETUP_EXCLUSIONS = {
    # 登录页本身就是「未认证入口」，不能 require_auth，否则死循环
    "pages/0_登录.py",
    # 自带整套自定义 CSS / 主题体系，布局完全独立
    "pages/🌟_星辰AI.py",
}


def _page_files():
    return sorted(glob.glob(os.path.join(ROOT, "pages", "*.py")))


def _rel(path):
    return os.path.relpath(path, ROOT).replace("\\", "/")


def _calls_any(tree, names):
    """判断 AST 中是否调用了给定名字之一（支持 st.xxx 属性调用形式）。"""
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Attribute):
            found.add(fn.attr)
        elif isinstance(fn, ast.Name):
            found.add(fn.id)
    return found & set(names)


def test_all_pages_use_render_standard_page():
    missing = []
    for path in _page_files():
        rel = _rel(path)
        if rel in STANDARD_SETUP_EXCLUSIONS:
            continue
        try:
            src = open(path, encoding="utf-8").read()
            tree = ast.parse(src)
        except Exception as e:  # pragma: no cover
            raise AssertionError(f"无法解析 {rel}: {e}")
        if not _calls_any(tree, ("render_standard_page",)):
            missing.append(rel)
    assert not missing, (
        "以下页面未使用标准入口 render_standard_page（会缺失登录校验与侧边栏高亮）。\n"
        "若确需例外，请加入 STANDARD_SETUP_EXCLUSIONS 并写明原因:\n"
        + "\n".join(f"  {m}" for m in missing)
    )


def test_exclusions_still_exist():
    present = {_rel(p) for p in _page_files()}
    stale = sorted(e for e in STANDARD_SETUP_EXCLUSIONS if e not in present)
    assert not stale, (
        "STANDARD_SETUP_EXCLUSIONS 中存在已失效条目（文件已不存在），请清理或更正: "
        + ", ".join(stale)
    )


def test_no_duplicate_set_page_config():
    """render_standard_page 内部已调 set_page_config，页面不得重复调用。"""
    bad = []
    for path in _page_files():
        rel = _rel(path)
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except Exception:
            continue
        calls = _calls_any(tree, ("render_standard_page", "set_page_config"))
        if "render_standard_page" in calls and "set_page_config" in calls:
            bad.append(rel)
    assert not bad, (
        "以下页面同时调用了 render_standard_page 与 st.set_page_config"
        "（后者只允许调用一次，重复会抛异常）:\n"
        + "\n".join(f"  {b}" for b in bad)
    )
