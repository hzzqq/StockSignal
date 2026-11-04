"""深链契约静态断言（不进入 ScriptRunContext，纯源码级契约锁）。

覆盖 UI 递延项 #35 的 P2 深链契约（v3 §3/§4 D 阶段）：
22 基本面分析 → 24 个股研究 跳转时预选「🔬 深度分析」并回填 code；
24 页消费 hub_gyj_view / pick_stock 并补「← 返回基本面分析」控件。

不塞进 test_sidebar_nav.py（v3 §4 E 阶段明确要求独立文件）。
"""

from __future__ import annotations

import ast
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
P22 = REPO / "pages" / "22_基本面分析.py"
P24 = REPO / "pages" / "24_个股研究.py"


def _src(p: pathlib.Path) -> str:
    assert p.exists(), f"缺失约定文件: {p}"
    return p.read_text(encoding="utf-8", errors="replace")


def _has(src: str, *sub: str) -> bool:
    return all(s in src for s in sub)


def test_22_launches_24_with_deeplink_view():
    """22 页跳转 24 页时必须预选「🔬 深度分析」并回填 pick_stock。"""
    src = _src(P22)
    assert _has(
        src,
        "hub_gyj_view",
        "🔬 深度分析",
        "pick_stock",
        "safe_switch_page('pages/24_个股研究.py')",
    ), "22 页深链：缺少 hub_gyj_view / pick_stock / safe_switch_page 到 24 页"


def test_22_keeps_pick_stock_on_fundamental_launch():
    """22 页去 20 个股深度分析也带 pick_stock（保持既有契约）。"""
    src = _src(P22)
    assert "st.query_params['pick_stock'] = code" in src


def test_24_consumes_deeplink_view_and_code():
    """24 页消费端：从 query_params 读取 hub_gyj_view 并回填 pick_stock 到 session_state。"""
    src = _src(P24)
    assert _has(
        src,
        'st.query_params.get("hub_gyj_view")',
        'st.session_state["hub_gyj_view"]',
        'st.query_params.get("pick_stock")',
        'st.session_state["pick_stock_confirmed"]',
    ), "24 页消费端：未正确读取 hub_gyj_view / pick_stock 并写入 session_state"


def test_24_has_return_control():
    """24 页补「← 返回基本面分析」可见控件，回到 22 页并带 code。"""
    src = _src(P24)
    assert _has(
        src,
        "返回基本面分析",
        "safe_switch_page(\"pages/22_基本面分析.py\")",
    ), "24 页缺少返回基本面分析的可见控件"


def test_24_subpage_strings_unchanged():
    """_SUBPAGES 子页路径字符串与分段标签零改动（test_sidebar_nav.py 反向锁的同源校验）。"""
    src = _src(P24)
    # 反向锁要求 24 页源码必须仍含这两个被内嵌子页路径字符串
    assert "11_股票选取.py" in src and "20_个股分析.py" in src, \
        "24 页必须仍内嵌 11_股票选取.py / 20_个股分析.py（否则从导航不可达）"
    # 两个分段标签仍为消费端 radio 选项（不得被改）
    assert "⚡ 快速选取" in src and "🔬 深度分析" in src, \
        "24 页分段标签不应被改动"
