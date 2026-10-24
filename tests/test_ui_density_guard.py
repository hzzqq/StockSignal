"""
tests/test_ui_density_guard.py — T-319 交互密度减法守卫（离线 AST）

T-316 体检报告第三优先建议：交互密度高的页面（股吧 / 数据导出）优先做
「次要控件收进折叠区」的减法。本轮只动布局，不改业务逻辑、不改 widget key。

五条契约（mutation 目标）：
1. 52_股吧 `fragment_list`：股票代码筛选 / 排序 / 清空筛选 / 标题关键字搜索
   四个筛选类控件必须全部位于同一个 `st.expander` 内，且函数内其它位置不再有
   这四个 key 的控件（避免「折叠了一套、平铺又留一套」）。
2. 折叠区不得默认展开（`expanded=True` 会抵消减法效果），且折叠标签必须是
   动态表达式、回显当前生效条件（否则筛选被隐藏后用户会忘记自己开着筛选）。
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


# ── 契约 1：四个筛选控件收进同一个折叠区 ──────────────────────────────
def test_forum_filters_folded_into_one_expander():
    tree = ast.parse(_src(P_FORUM))
    fn = _fn(tree, "fragment_list")
    assert fn is not None, "未找到 fragment_list"

    blocks = _expander_blocks(fn)
    assert blocks, "fragment_list 内未找到任何 st.expander（筛选区未收进折叠区）"

    folded_union = set()
    for _, with_node in blocks:
        folded_union |= _widget_keys(with_node)

    missing = FILTER_KEYS - folded_union
    assert not missing, f"仍有筛选控件平铺在折叠区外：{sorted(missing)}"

    # 四个 key 必须落在同一个折叠区（分散多个 expander 不算减法）
    holders = [w for _, w in blocks if FILTER_KEYS <= _widget_keys(w)]
    assert holders, "四个筛选控件未收进同一个 st.expander"

    # 折叠区外不得再出现同名 key（防「折叠 + 平铺」双份）
    outside = _widget_keys(fn) - folded_union
    dup = FILTER_KEYS & outside
    assert not dup, f"筛选控件在折叠区外重复出现：{sorted(dup)}"


# ── 契约 2：折叠区默认收起 + 标签回显生效条件 ────────────────────────
def test_forum_filter_expander_collapsed_and_echoes_state():
    src = _src(P_FORUM)
    tree = ast.parse(src)
    fn = _fn(tree, "fragment_list")
    holder = None
    for call, with_node in _expander_blocks(fn):
        if FILTER_KEYS <= _widget_keys(with_node):
            holder = call
            break
    assert holder is not None, "未找到承载筛选控件的 expander"

    for kw in holder.keywords:
        if kw.arg == "expanded":
            assert not (isinstance(kw.value, ast.Constant) and kw.value.value is True), \
                "筛选折叠区不得默认展开（expanded=True 会抵消减法）"

    assert holder.args, "expander 缺少标签"
    label = holder.args[0]
    assert not isinstance(label, ast.Constant), \
        "折叠标签必须是动态表达式（回显当前生效筛选条件），不得为写死字符串"
    # 允许标签引用函数内局部变量（如 _flt_on），沿赋值链解析其字符串常量
    consts = _consts_with_locals(label, fn)
    assert any(isinstance(c, str) and "筛选" in c for c in consts), \
        "折叠标签缺少「筛选」语义文案"
    assert "forum_filter_code" in consts, "折叠标签必须回显股票代码筛选状态"
    assert "forum_kw_search" in consts, "折叠标签必须回显关键字搜索状态"


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
