"""P2-3 内联 widget key 注册表守卫
────────────────────────────────
意图（防散装 key 流失）：pages 页面直接内联的 widget key 必须在
modules/widgets.py 的 `_INLINE_WIDGET_KEYS` / `_INLINE_WIDGET_KEY_PREFIXES`
登记在册，再使用。本守卫用 AST 提取受管页面的全部 key 实参：

① 注册表存在且形态正确（frozenset / tuple / is_inline_widget_key 可用）；
② 受管页面（首批：pages/52_股吧.py）全部 key= 字面量与 f-string 动态键
   已登记 —— 静态键精确命中、动态键前缀命中；
③ st.form 的 key 是首位置参数（非 key= 形态），单独提取，同样必须登记；
④ 反向校验：注册表里的 forum_* 静态键与前缀必须真实出现在页面源码中，
   防止「登记了却没人用」的死键悄悄堆积。

离线静态检查：AST + 源码字符串，无需 Streamlit runtime。
"""
import ast
from pathlib import Path

import pytest

import modules.widgets as w

ROOT = Path(__file__).resolve().parent.parent
# 受管页面清单：后续页面接入内联键登记制时在此追加
GUARDED_PAGES = ["52_股吧.py"]


def _load_page_source(page_name: str) -> str:
    return (ROOT / "pages" / page_name).read_text(encoding="utf-8")


def _extract_widget_keys(src: str):
    """AST 提取页面全部 widget key 实参。

    返回 (static_keys, dynamic_prefixes)：
    - static_keys: key="xxx" / st.form("xxx") 等字符串字面量形态；
    - dynamic_prefixes: key=f"xxx_{id}" 形态的首段字面量前缀。
    无法解析的形态（变量名 / 非字符串常量）直接抛错 —— 防止绕过登记。
    sorted(key=lambda ...) 这类排序键是 ast.Lambda，与 widget 无关，跳过。
    """
    tree = ast.parse(src)
    static, dynamic = [], []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # st.form / st.form_submit_button 之外的表单容器：key 是首位置参数
        func = node.func
        if (isinstance(func, ast.Attribute) and func.attr == "form"
                and node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            static.append(node.args[0].value)
        for kw in node.keywords:
            if kw.arg != "key":
                continue
            val = kw.value
            if isinstance(val, ast.Lambda):
                continue  # min/max/sorted 的排序键，不是 widget key
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                static.append(val.value)
            elif isinstance(val, ast.JoinedStr):
                prefix = next(
                    (v.value for v in val.values
                     if isinstance(v, ast.Constant) and isinstance(v.value, str)),
                    None,
                )
                if prefix is None:
                    raise AssertionError(
                        f"f-string key 无字面量前缀，无法登记：{ast.dump(val)}")
                dynamic.append(prefix)
            else:
                raise AssertionError(
                    f"key= 实参非常量（{type(val).__name__}），会绕过登记制，"
                    f"请改为字面量并在 widgets.py 注册表登记")
    return static, dynamic


def test_registry_exists_and_shape():
    assert isinstance(w._INLINE_WIDGET_KEYS, frozenset), "注册表必须是 frozenset（不可变台账）"
    assert w._INLINE_WIDGET_KEYS, "注册表为空，登记制名存实亡"
    assert isinstance(w._INLINE_WIDGET_KEY_PREFIXES, tuple)
    assert w._INLINE_WIDGET_KEY_PREFIXES
    assert callable(w.is_inline_widget_key)
    # 公开 API 行为：静态精确命中 / 动态前缀命中 / 未登记拒绝 / 非字符串拒绝
    assert w.is_inline_widget_key("forum_like") is True
    assert w.is_inline_widget_key("forum_emo_0_1") is True
    assert w.is_inline_widget_key("rogue_key_not_registered") is False
    assert w.is_inline_widget_key(123) is False
    assert w.is_inline_widget_key(None) is False


@pytest.mark.parametrize("page_name", GUARDED_PAGES)
def test_page_keys_all_registered(page_name):
    src = _load_page_source(page_name)
    static, dynamic = _extract_widget_keys(src)
    assert static, f"{page_name} 未提取到任何 widget key，提取逻辑疑似失效"

    unregistered_static = [k for k in static if not w.is_inline_widget_key(k)]
    assert not unregistered_static, (
        f"{page_name} 存在未登记的内联 widget key：{sorted(set(unregistered_static))}；"
        f"请先在 modules/widgets.py `_INLINE_WIDGET_KEYS` 登记再使用（防散装 key 流失）")

    unregistered_dynamic = [p for p in dynamic
                            if not w.is_inline_widget_key(f"{p}__probe__")]
    assert not unregistered_dynamic, (
        f"{page_name} 存在未登记的动态 key 前缀：{sorted(set(unregistered_dynamic))}；"
        f"请先在 modules/widgets.py `_INLINE_WIDGET_KEY_PREFIXES` 登记再使用")


@pytest.mark.parametrize("page_name", GUARDED_PAGES)
def test_registry_has_no_dead_keys(page_name):
    """反向校验：登记表不得堆积「页面已不再使用」的死键。"""
    src = _load_page_source(page_name)
    dead = [k for k in w._INLINE_WIDGET_KEYS if k not in src]
    assert not dead, (
        f"注册表中的键已不在 {page_name} 源码中出现（死键）：{sorted(dead)}；"
        f"请同步清理注册表")
    dead_prefixes = [p for p in w._INLINE_WIDGET_KEY_PREFIXES if p not in src]
    assert not dead_prefixes, (
        f"注册表中的动态前缀已不在 {page_name} 源码中出现（死前缀）：{sorted(dead_prefixes)}")


def test_intent_documented_in_registry():
    """意图留痕：注册表注释必须写明「防散装 key 流失」的登记制动机。"""
    widgets_src = (ROOT / "modules" / "widgets.py").read_text(encoding="utf-8")
    assert "防「散装 key」无序流失" in widgets_src, (
        "widgets.py 注册表缺少意图注释：新增内联 key 必须先登记再使用")


def test_guard_extracts_expected_counts():
    """提取器自校验：52 页应提取到 27 个静态键 + 6 个动态前缀。
    数量变化时（页面新增/删除内联键）本测试会给出明确锚点。"""
    static, dynamic = _extract_widget_keys(_load_page_source("52_股吧.py"))
    assert len(set(static)) == 27, f"静态键数漂移：实际 {sorted(set(static))}"
    assert len(set(dynamic)) == 6, f"动态前缀数漂移：实际 {sorted(set(dynamic))}"
