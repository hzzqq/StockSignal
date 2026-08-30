"""tests/test_fragment_rerun_rule.py

锁死项目铁律：**``@safe_fragment`` 内禁止整页 ``st.rerun()``**。

原因（项目既定约定）：
- ``@safe_fragment`` 的意义是「只重跑该片段」，隔离重绘、保住其他片段状态、
  避免整页重算（本项目大量页面是有网络取数的重页面）。
- 在 fragment 内调用无 scope 的 ``st.rerun()`` 会退化成整页重跑，
  既破坏片段隔离，又把整页（含其它 fragment 的网络请求）全部重算一遍，
  是典型的性能/体验回退，且极难在 review 中肉眼发现。
- 正确写法：``st.rerun(scope="fragment")``（只重跑当前片段）。

``st.switch_page()`` 同样是整页导航，本应禁止；但存在一处**刻意的例外**
（见 ``SWITCH_PAGE_ALLOWLIST``）：重新登录分支需要先 ``session_state.clear()``
再跳转，且**必须丢弃 URL 上的过期 token**——项目自带的 ``safe_switch_page``
会保留 query 参数（包括旧 token），反而会把过期凭证带到登录页，因此这里
刻意使用原生 ``st.switch_page``。例外必须有注释说明，且不得随意扩列。

2026-08-28 新增（Cycle 63）。
"""
import ast
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (相对路径, 函数名) —— 刻意的整页跳转例外，必须附原因
SWITCH_PAGE_ALLOWLIST = {
    # 重新登录分支：session 已 clear，需丢弃 URL 上过期 token，
    # 故不用 safe_switch_page（它会保留 query 参数/旧 token）。
    ("pages/21_多股对比.py", "fragment_compare_setup"),
}


def _deco_name(d):
    f = d.func if isinstance(d, ast.Call) else d
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return None


def _is_fragment(node):
    return any(_deco_name(d) == "safe_fragment" for d in node.decorator_list)


def _callee(call):
    fn = call.func
    if isinstance(fn, ast.Attribute):
        return fn.attr
    if isinstance(fn, ast.Name):
        return fn.id
    return None


def _iter_fragments():
    for path in sorted(glob.glob(os.path.join(ROOT, "pages", "**", "*.py"), recursive=True)
                       + glob.glob(os.path.join(ROOT, "modules", "**", "*.py"), recursive=True)):
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except Exception:
            continue
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_fragment(node):
                yield rel, node


def test_no_whole_page_rerun_inside_fragment():
    bad = []
    for rel, node in _iter_fragments():
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            if _callee(sub) != "rerun":
                continue
            kwargs = {k.arg for k in sub.keywords}
            if "scope" not in kwargs:
                bad.append((rel, node.name, sub.lineno))
    assert not bad, (
        "发现 @safe_fragment 内的整页 st.rerun()（应改为 st.rerun(scope=\"fragment\")）:\n"
        + "\n".join(f"  {r}:{ln} {fn}()" for r, fn, ln in bad)
    )


def test_switch_page_inside_fragment_is_allowlisted():
    bad = []
    for rel, node in _iter_fragments():
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and _callee(sub) == "switch_page":
                if (rel, node.name) not in SWITCH_PAGE_ALLOWLIST:
                    bad.append((rel, node.name, sub.lineno))
    assert not bad, (
        "发现未登记的 @safe_fragment 内 st.switch_page()（整页导航）。\n"
        "若确为必需，请加入 SWITCH_PAGE_ALLOWLIST 并在注释写明原因；\n"
        "通常应改用 st.rerun(scope='fragment') 或把跳转移到 fragment 之外:\n"
        + "\n".join(f"  {r}:{ln} {fn}()" for r, fn, ln in bad)
    )


def test_allowlist_entries_still_exist():
    """防止 allowlist 里的函数名被改掉后白名单变成死条目（失去约束力）。"""
    present = {(rel, node.name) for rel, node in _iter_fragments()}
    stale = [e for e in SWITCH_PAGE_ALLOWLIST if e not in present]
    assert not stale, (
        "SWITCH_PAGE_ALLOWLIST 中存在已失效条目（函数已不存在），请清理或更正: "
        + ", ".join(f"{r}::{f}" for r, f in stale)
    )
