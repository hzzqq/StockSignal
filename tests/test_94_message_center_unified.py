"""守卫：消息/通知中心（94）顶部「统计 + 操作」必须收进同一张卡片。

T-367 之后合并：原散落的「未读/总消息」stat 卡、「全部标为已读」按钮、以及独立的
「更多操作」折叠区（清除已读标记 / 重新加载）必须统一为一个「通知概览」组件，
不得再拆成 st.columns 散卡 + 独立 st.expander 把低频操作藏起来。

纯源码字符串 / AST 检查，离线可跑，不依赖运行期。
"""
from pathlib import Path

import pytest

PAGE = Path(__file__).resolve().parent.parent / "pages" / "94_消息中心.py"
SRC = PAGE.read_text(encoding="utf-8")


def test_no_scattered_more_operations_expander():
    """旧「更多操作」折叠区必须消失——所有操作都并进同一张卡片。"""
    assert 'st.expander("⚙️ 更多操作' not in SRC, \
        "94 仍残留独立『更多操作』折叠区，违背合并为单一『通知概览』组件的决策"


def test_overview_actions_collocated():
    """三个操作按钮的 key 必须共存于同一文件（它们现已收进同一张卡片）。"""
    for key in ("mark_all", "clear_read_marks", "msg_reload"):
        assert f'key="{key}"' in SRC, f"94 缺少操作按钮 key={key}，合并可能遗漏动作"


def test_unified_card_wrapper_present():
    """顶部概览须用统一的带边框卡片包裹（st.container(border=True)）。"""
    assert "st.container(border=True)" in SRC, \
        "94 顶部概览未用统一卡片容器包裹，合并不完整"


def test_stats_still_rendered():
    """未读 / 总消息 两个统计仍须渲染（合并不能丢数据）。"""
    # P1-5 批1（2026）：st.metric → stat_tile（ui_kit canonical .xc-card 视觉），统计仍须渲染
    assert 'stat_tile("未读"' in SRC, "94 合并后丢失『未读』统计"
    assert 'stat_tile("总消息"' in SRC, "94 合并后丢失『总消息』统计"
