"""
tests/test_back_to_top_poller.py
===============================
B 阶段守卫：全局「▲ 回到顶部」悬浮按钮的可见性兜底轮询（setInterval 加固）。

锁定不变量：
  - 启用回顶（show_top=True）时，生成的导航脚本须含 setInterval 轮询兜底（__sfTopPoll），
    确保任意 Streamlit 动态滚动容器下按钮都可靠显现（根治「滚动了却看不到回顶」）。
  - 点击回顶仍走容器探测 C_top()、位置探测 C_pos()，不得回退到裸 window.scrollTo。
  - 关闭回顶（show_top=False）时不得注入轮询定时器（避免无谓开销）。
"""

from __future__ import annotations

from modules import scroll_nav as sn


def test_back_to_top_poller_reliable():
    body = sn._nav_script(
        dark=False, threshold_px=120, bottom_threshold=150,
        show_top=True, show_bottom=False,
    )
    assert "__sfTopPoll" in body, "回顶按钮缺少 setInterval 轮询兜底（__sfTopPoll）"
    assert "setInterval" in body, "回顶按钮缺少轮询机制（setInterval）"
    # 点击仍走容器探测（C_top），非裸 window.scrollTo（v2 缺陷修复不可回退）
    assert "C_top()" in body, "回顶点击须走容器探测 C_top()"
    assert "C_pos()" in body, "回顶位置探测须走容器探测 C_pos()"


def test_back_top_poller_guarded_by_show_top():
    body_false = sn._nav_script(
        dark=False, threshold_px=120, bottom_threshold=150,
        show_top=False, show_bottom=False,
    )
    body_true = sn._nav_script(
        dark=False, threshold_px=120, bottom_threshold=150,
        show_top=True, show_bottom=False,
    )
    # 轮询必在 show_top 条件块内：show_top=False 时运行时 if(false) 不执行（惰性、零开销）；
    # 不得逃逸到全局作用域。
    assert body_false.find("__sfTopPoll") > body_false.find("if (false)"), "关闭回顶时轮询须包在 if(false) 内"
    assert body_true.find("__sfTopPoll") > body_true.find("if (true)"), "启用回顶时轮询须包在 if(true) 内"
