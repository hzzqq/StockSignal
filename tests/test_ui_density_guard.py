"""
tests/test_ui_density_guard.py — T-319 交互密度减法守卫（离线 AST）

T-316 体检报告第三优先建议：交互密度高的页面（股吧 / 数据导出）优先做
「次要控件收进折叠区」的减法。本轮只动布局，不改业务逻辑、不改 widget key。

五条契约（mutation 目标）：
1. 52_股吧 `fragment_list`：股票代码筛选 / 排序 / 清空筛选 / 标题关键字搜索
   四个筛选类控件必须**常驻行内直出、不收进任何 st.expander**。
   【T-319 折叠契约已于 96bd358 按用户要求撤销（「搜索框直接摆出、轻量化，不折叠」），
   守卫随之反转为「不得再折叠」——防止把用户明确要求摆出的筛选又藏回去】。
2. 生效中的筛选条件必须以轻量 caption（「当前筛选生效：…」）回显，不得静默。
3. 主控件（视图 Tab / 发帖）不得被收进折叠区——减法是收次要控件，不是收入口。
4. 95_数据导出：`sf_card` 首参不得与 expander 标签同名（expander 已显示标题，
   卡片再渲染一次同名标题属重复装饰）。
5. 95_数据导出：11 个数据集片段仍各自挂在 expander 内（减法不得减少功能入口）。
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P_FORUM = ROOT / "pages" / "52_股吧.py"
P_EXPORT = ROOT / "pages" / "95_数据导出.py"

FILTER_KEYS = {"forum_filter_code", "forum_sort", "forum_clear", "forum_kw_search"}
PRIMARY_KEYS = {"forum_view_tab", "forum_new_btn"}
WIDGETS = {
    "button", "radio", "text_input", "text_area", "checkbox", "selectbox",
    "multiselect", "download_button", "form_submit_button", "toggle",
}
SF_CARD_KEYS = {"sf_card"}


def _src(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _fn(tree: ast.Module, name: str):
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return n
    return None


def _is_st_call(node, attr: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == attr
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "st"
    )


def _widget_keys(node) -> set:
    """收集子树内 st.<widget>(key=...) 的 key 常量。"""
    keys = set()
    for n in ast.walk(node):
        if not isinstance(n, ast.Call) or not isinstance(n.func, ast.Attribute):
            continue
        if n.func.attr not in WIDGETS:
            continue
        for kw in n.keywords:
            if kw.arg == "key" and isinstance(kw.value, ast.Constant):
                keys.add(kw.value.value)
    return keys


def _expander_blocks(fn):
    """返回 [(expander_call, with_node)]，仅限该函数体内。"""
    out = []
    for n in ast.walk(fn):
        if isinstance(n, ast.With):
            for item in n.items:
                if _is_st_call(item.context_expr, "expander"):
                    out.append((item.context_expr, n))
    return out


def _consts_with_locals(node, fn, depth: int = 3, seen=None) -> set:
    """收集表达式里的字符串常量，并沿函数内局部变量赋值链递归展开（限深）。"""
    seen = seen if seen is not None else set()
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Constant):
            out.add(n.value)
        elif isinstance(n, ast.Name) and depth > 0 and n.id not in seen:
            seen.add(n.id)
            for stmt in ast.walk(fn):
                if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                        and isinstance(stmt.targets[0], ast.Name)
                        and stmt.targets[0].id == n.id):
                    out |= _consts_with_locals(stmt.value, fn, depth - 1, seen)
    return out


# ── 契约 1：四个筛选控件常驻行内直出，不收进折叠区（96bd358 反转 T-319）──
def test_forum_filters_inline_not_folded():
    tree = ast.parse(_src(P_FORUM))
    fn = _fn(tree, "fragment_list")
    assert fn is not None, "未找到 fragment_list"

    # 四个筛选 key 必须仍然存在（减法不删功能）
    present = _widget_keys(fn)
    missing = FILTER_KEYS - present
    assert not missing, f"筛选控件丢失（减法不得删功能入口）：{sorted(missing)}"

    # 且任何一个都不得落在 st.expander 内（用户要求搜索框直接摆出，不得再折叠）
    blocks = _expander_blocks(fn)
    folded_union = set()
    for _, with_node in blocks:
        folded_union |= _widget_keys(with_node)
    refolded = FILTER_KEYS & folded_union
    assert not refolded, (
        f"筛选控件被重新收进折叠区（96bd358 已按用户要求撤销折叠，搜索框必须直接摆出）：{sorted(refolded)}"
    )

    # 每个 key 在函数内只出现一次（防「行内一套 + 折叠一套」双份）
    def _direct_key(node):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in WIDGETS):
            for kw in node.keywords:
                if kw.arg == "key" and isinstance(kw.value, ast.Constant):
                    return kw.value.value
        return None

    all_keys = [k for k in (_direct_key(n) for n in ast.walk(fn)) if k is not None]
    for k in sorted(FILTER_KEYS):
        n = all_keys.count(k)
        assert n == 1, f"筛选控件 key={k} 出现 {n} 次（应为 1，防重复渲染）"


# ── 契约 2：生效筛选条件必须行内 caption 回显（不静默） ────────────────
def test_forum_filter_state_echoed_inline():
    src = _src(P_FORUM)
    tree = ast.parse(src)
    fn = _fn(tree, "fragment_list")
    assert fn is not None, "未找到 fragment_list"

    fn_src = ast.get_source_segment(src, fn) or ""
    assert "当前筛选生效" in fn_src, "生效筛选条件的行内 caption 回显不得移除"
    # 回显必须条件化（无筛选时不输出空回显）：if _flt_on 才渲染
    assert "if _flt_on:" in fn_src, "回显 caption 必须挂在生效条件判断下（无筛选不空转）"


# ── 契约 3：主控件不得被收进折叠区 ───────────────────────────────────
def test_forum_primary_controls_stay_visible():
    tree = ast.parse(_src(P_FORUM))
    fn = _fn(tree, "fragment_list")
    folded = set()
    for _, with_node in _expander_blocks(fn):
        folded |= _widget_keys(with_node)
    leaked = PRIMARY_KEYS & folded
    assert not leaked, f"主入口控件被收进折叠区（应保持首屏可见）：{sorted(leaked)}"


# ── 契约 4：导出页不得再重复渲染同名标题 ─────────────────────────────
def test_export_page_has_no_duplicate_titles():
    tree = ast.parse(_src(P_EXPORT))
    expander_labels = set()
    for n in ast.walk(tree):
        if _is_st_call(n, "expander") and n.args and isinstance(n.args[0], ast.Constant):
            expander_labels.add(n.args[0].value)

    dup = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call) or not isinstance(n.func, ast.Name):
            continue
        if n.func.id not in SF_CARD_KEYS or not n.args:
            continue
        if isinstance(n.args[0], ast.Constant) and n.args[0].value in expander_labels:
            dup.append(n.args[0].value)
    assert not dup, f"expander 标签与内部 sf_card 同名（重复装饰标题）：{dup}"


# ── 契约 5：11 个数据集片段仍全部挂载 ────────────────────────────────
def test_export_all_fragments_still_mounted():
    tree = ast.parse(_src(P_EXPORT))
    defined = {
        n.name for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name.startswith("frag_")
    }
    assert len(defined) == 11, f"数据集片段数量变化（预期 11）：{sorted(defined)}"

    called = set()
    for n in ast.walk(tree):
        if (isinstance(n, ast.With)
                and any(_is_st_call(i.context_expr, "expander") for i in n.items)):
            for sub in ast.walk(n):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                    if sub.func.id in defined:
                        called.add(sub.func.id)
    missing = defined - called
    assert not missing, f"以下数据集片段未挂在 expander 内（功能入口丢失）：{sorted(missing)}"
