"""
tests/test_no_redundant_help.py
===============================
A 阶段守卫：页面内冗余「⌨️ 快捷键」说明框已收敛至「我的→偏好设置」键盘快捷键卡。

锁定的不变量：
  - 52_股吧 / 14_智能盯盘 / 23_事件追踪 / 33_ETF筛选 / 45_持仓中心 不得再含页面级
    「⌨️ 快捷键」/「⌨️ 快捷键提示」说明框（内容=浏览器常识+回顶描述，纯冗余）。
  - 91_我的 偏好设置必须含「键盘快捷键」卡（平台真实存在的键盘快捷键归位处）。
  - 52_股吧 底部帮助区不得再含「一键回顶」之类的误导性快捷键说明文字。
"""

from __future__ import annotations

from pathlib import Path

PAGES = Path("pages")


def _src(name: str) -> str:
    return (PAGES / name).read_text(encoding="utf-8")


# 被清理的页面级冗余快捷键框（标签字面量）
_REDUNDANT_LABELS = (
    'st.expander("⌨️ 快捷键提示")',
    "st.expander('⌨️ 快捷键')",
    'st.expander("⌨️ 快捷键提示")',
)


def test_cleaned_pages_have_no_shortcut_expander():
    for name in (
        "52_股吧.py",
        "14_智能盯盘.py",
        "23_事件追踪.py",
        "33_ETF筛选.py",
        "45_持仓中心.py",
    ):
        src = _src(name)
        for lab in _REDUNDANT_LABELS:
            assert lab not in src, f"{name} 仍含冗余快捷键框标签：{lab}"


def test_52_no_misleading_back_to_top_help():
    src = _src("52_股吧.py")
    # 误导性帮助文字（曾指向“看不到”的悬浮按钮）已删除
    assert "一键回顶" not in src, "52_股吧 仍含误导性「一键回顶」帮助文字"
    assert "长列表滚动后点击右下角" not in src, "52_股吧 仍含过时回顶帮助描述"


def test_91_has_keyboard_shortcuts_card():
    src = _src("91_我的.py")
    assert "键盘快捷键" in src, "91_我的 偏好设置缺少「键盘快捷键」卡（快捷键应归位设置页）"
    # 卡内须列出平台真实存在的键盘快捷键（命令面板 / 刷新 / 清缓存拦截）
    assert "Ctrl / ⌘ + K" in src, "键盘快捷键卡缺少命令面板（Ctrl/⌘+K）说明"
    assert "清除缓存" in src, "键盘快捷键卡缺少 C 键清缓存拦截说明"


def test_52_filter_search_not_collapsed():
    """C 阶段：52_股吧 的筛选 / 搜索须常驻可见，不得再折进 expander。"""
    src = _src("52_股吧.py")
    assert "with st.expander(_flt_label" not in src, "52_股吧 筛选/搜索仍被折叠进 expander"
    assert "按代码筛选" in src, "52_股吧 缺少「按代码筛选」输入"
    assert "标题关键字" in src, "52_股吧 缺少「标题关键字」搜索输入"


def test_52_no_redundant_search_hints():
    """搜索框须常驻可见、标签轻量化，旧冗余括号提示（如「（可选，纯前端过滤）」）彻底消失。
    内部代码注释与发帖表单的合法可选字段不在此限。"""
    src = _src("52_股吧.py")
    # 搜索框须常驻可见（C 阶段已去折叠），标签轻量化
    assert 'st.text_input("按代码筛选"' in src, "52_股吧 缺少「按代码筛选」输入"
    assert 'st.text_input("标题关键字"' in src, "52_股吧 缺少「标题关键字」搜索输入"
    # 旧冗余搜索标签/占位符彻底消失（用户明确不要括号实现细节提示）
    assert "按股票代码筛选（可选）" not in src
    assert "帖子标题关键字搜索（可选，纯前端过滤）" not in src
    assert 'placeholder="搜索帖子标题，实时过滤"' in src, "搜索占位符应轻量化、不含纯前端过滤"
    # 不再折叠
    assert 'with st.expander(_flt_label' not in src, "52_股吧 筛选/搜索仍被折叠"
