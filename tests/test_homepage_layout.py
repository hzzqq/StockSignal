"""T-367 首页布局守卫：删「全部功能模块」折叠 + 说明置顶 + 合并快捷入口。

红线：首页不得再出现大面积折叠的功能模块清单（侧栏导航已是唯一全量目录）；
项目说明以轻量卡片置于页面顶部；「常用直达」与「快捷入口」合并为单一区块。
"""
import pathlib

APP = pathlib.Path(__file__).resolve().parents[1] / "app.py"
SRC = APP.read_text(encoding="utf-8")


def test_no_all_modules_collapsible():
    # 「📦 全部功能模块」区块标题已删除
    assert "📦 全部功能模块" not in SRC
    # 旧的折叠分组数据/渲染函数彻底移除（不再有 25+ 卡片平铺）
    assert "HOME_GROUPS" not in SRC
    assert "_render_group" not in SRC
    # 底部折叠的「项目简介」也移除（已上移为顶部说明卡）
    assert "📖 项目简介" not in SRC


def test_project_intro_on_top_and_today_decision_below():
    # 顶部项目说明卡片已注入
    assert "_render_project_intro" in SRC
    # 今日决策调用仍在（置于说明之后）。注意：函数定义 `def _render_today_decision():`
    # 也含 `()` 子串，故取最后一次出现（即真正的调用点）。
    assert "_render_today_decision()" in SRC
    # 说明调用出现在今日决策调用之前（排版：说明在顶，决策在下）
    pos_intro = SRC.index("_render_project_intro()")
    pos_decision = SRC.rfind("_render_today_decision()")
    assert pos_intro < pos_decision, "项目说明应置于今日决策之前"


def test_quick_sections_merged():
    # 合并后「⚡ 快捷入口」作为唯一 header 仅出现一次
    assert SRC.count('st.header("⚡ 快捷入口")') == 1
    # 旧的「⚡ 常用直达」独立 header 已移除
    assert 'st.header("⚡ 常用直达")' not in SRC
    # 合并区块内仍保留高频直达按钮与最近浏览
    assert "今日决策面板" in SRC
    assert "最近浏览" in SRC


def test_account_group_is_lightweight_not_collapsed():
    # 账户组改为内联轻量卡片行，不再用 expander 折叠
    assert 'st.header("👤 账户")' in SRC
    assert "_render_group(" not in SRC
    # 仍提供「我的 / 用户管理 / 系统配置」入口
    assert "我的" in SRC
