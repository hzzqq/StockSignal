"""Sidebar 导航补全 + 当前位置高亮的回归测试（锐评迭代：决策面板入栏 + 防迷路）。

不依赖网络：只校验 _NAV_GROUPS 结构、_current_nav_label / _current_page_basename 逻辑。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import modules.widgets as w
from unittest.mock import patch


def _all_nav_paths():
    paths = []
    for _g, items in w._NAV_GROUPS:
        for _it in items:
            paths.append(_it[0].replace('\\', '/'))
    for _it in getattr(w, '_NAV_HERO', []):
        paths.append(_it[0].replace('\\', '/'))
    return paths


def test_decision_panel_in_nav():
    """决策面板（54）必须出现在侧边栏导航中（用户核心诉求：不再「隐藏」）。"""
    paths = _all_nav_paths()
    assert 'pages/54_今日决策面板.py' in paths


def test_missing_key_pages_now_present():
    """原缺失的关键页面已补入侧边栏：市场驱动力/智能选股/QuantAgent/仓位管理/组合收益/自选股监控/P1量化信号/个股分析/股票选取。"""
    paths = set(_all_nav_paths())
    for p in [
        'pages/15_市场驱动力.py',
        'pages/32_智能选股.py',
        'pages/25_QuantAgent投研.py',
        'pages/40_仓位管理.py',
        'pages/41_组合收益.py',
        'pages/46_自选股监控.py',
        'pages/55_P1量化信号.py',
        'pages/20_个股分析.py',
        'pages/11_股票选取.py',
    ]:
        assert p in paths, f"{p} 未出现在侧边栏导航"


def test_nav_label_lookup():
    """_current_nav_label 能反查决策面板与首页标签。"""
    assert w._current_nav_label('54_今日决策面板.py') == '今日决策面板'
    assert w._current_nav_label('app.py') == '首页'
    # 不存在的脚本返回空串
    assert w._current_nav_label('zzz.py') == ''


def test_current_basename_none_ctx():
    """非运行上下文（AppTest/探针）安全返回 ''。"""
    class FakeCtx:
        session = None
    with patch('streamlit.runtime.scriptrunner.get_script_run_ctx', lambda: None):
        assert w._current_page_basename() == ''
    # 有 ctx 但 session 无路径 → 仍安全返回 ''
    with patch('streamlit.runtime.scriptrunner.get_script_run_ctx', lambda: FakeCtx()):
        assert w._current_page_basename() == ''


def test_current_basename_parses_path():
    """从 script run ctx 的主脚本路径正确取出文件名。"""

    class FakeSess:
        _main_script_path = 'E:/project/ks/StockSignal/pages/54_今日决策面板.py'

    class FakeCtx:
        session = FakeSess()

    with patch('streamlit.runtime.scriptrunner.get_script_run_ctx', lambda: FakeCtx()):
        assert w._current_page_basename() == '54_今日决策面板.py'


def test_group_count_after_reorg():
    """锐评重构后分组数收敛到 8（去单元素/合并单薄分组；R21 把超长『持仓交易』拆出『工具』子组）。"""
    from collections import Counter
    _names = [g for g, _ in w._NAV_GROUPS]
    assert len(w._NAV_GROUPS) == 8, f"分组数应为 8，实际 {len(w._NAV_GROUPS)}: {_names}"
    # 已删除的反模式单元素/单薄分组不应再出现
    _forbidden = ['🎯 决策核心', '📘 新手引导', '💰 实盘 & 条件单', '🧪 策略工具', '💼 我的持仓']
    for f in _forbidden:
        assert f not in _names, f"反模式分组仍残留: {f}"


def test_hero_is_decision_panel():
    """顶部 Hero 入口为决策面板（54），体现决策闭环主线。"""
    assert len(w._NAV_HERO) == 1
    assert w._NAV_HERO[0][0] == 'pages/54_今日决策面板.py'
    assert w._NAV_HERO[0][1] == '今日决策面板'


def test_sub_item_hierarchy():
    """合并页子项以 4 元组 sub 标记：11/20 是 24 子项，40/41/46 是 45 子项。"""
    _subs = {}
    for _g, _items in w._NAV_GROUPS:
        for _it in _items:
            if len(_it) >= 4 and _it[3] == 'sub':
                _subs.setdefault(_g, []).append(_it[0].split('/')[-1])
    # 个股研究 分组下应有 11/20 两个 sub
    _g_indiv = [g for g, _ in w._NAV_GROUPS if '个股研究' in g][0]
    assert '11_股票选取.py' in _subs.get(_g_indiv, [])
    assert '20_个股分析.py' in _subs.get(_g_indiv, [])
    # 持仓交易 分组下应有 40/41/46 三个 sub
    _g_hold = [g for g, _ in w._NAV_GROUPS if '持仓交易' in g][0]
    for _p in ['40_仓位管理.py', '41_组合收益.py', '46_自选股监控.py']:
        assert _p in _subs.get(_g_hold, []), f"{_p} 应标记为 45 子项"


def test_icon_global_uniqueness():
    """所有导航图标（分组头 + Hero + item + admin）全局唯一，无撞车。"""
    _icons = []
    for _g, _items in w._NAV_GROUPS:
        _icons.append(_g.split()[0])  # 分组头图标
        for _it in _items:
            _icons.append(_it[2])
    for _it in getattr(w, '_NAV_HERO', []):
        _icons.append(_it[2])
    for _it in w._NAV_ADMIN:
        _icons.append(_it[2])
    _dup = [k for k, v in __import__('collections').Counter(_icons).items() if v > 1]
    assert not _dup, f"图标撞车: {_dup}"


def test_no_duplicate_paths():
    """任一页面路径在 hero + 各分组中至多出现一次（无重复登记）。"""
    from collections import Counter
    _paths = []
    for _g, _items in w._NAV_GROUPS:
        for _it in _items:
            _paths.append(_it[0].replace('\\', '/'))
    for _it in getattr(w, '_NAV_HERO', []):
        _paths.append(_it[0].replace('\\', '/'))
    _dup = [k for k, v in Counter(_paths).items() if v > 1]
    assert not _dup, f"路径重复登记: {_dup}"


def test_personal_center_label():
    """91_我的 标签已统一为『个人中心』，与分组命名解耦。"""
    assert w._current_nav_label('91_我的.py') == '个人中心'
    assert w._current_nav_label('pages/91_我的.py') == '个人中心'


def test_group_order_mental_flow():
    """分组顺序遵循用户心智流：行情→板块→宽度→个股研究→量化选股→持仓交易→工具→社区与AI。"""
    _order = [g for g, _ in w._NAV_GROUPS]
    _expected = ['📈 行情盯盘', '🧩 板块结构', '🌐 市场宽度', '🔎 个股研究',
                 '🧪 量化选股', '💼 持仓交易', '🛠 工具', '💬 社区与 AI']
    assert _order == _expected, f"分组顺序偏离心智流: {_order}"


def test_hold_group_split_reduces_oversized():
    """持仓交易拆出『工具』子组后，两组均符合 4-6 项封顶原则（不再有 10 项超长组）。"""
    _by_group = {g: len(items) for g, items in w._NAV_GROUPS}
    assert _by_group['💼 持仓交易'] <= 6, f"持仓交易应 ≤6 项，实际 {_by_group['💼 持仓交易']}"
    assert _by_group['🛠 工具'] <= 6, f"工具应 ≤6 项，实际 {_by_group['🛠 工具']}"
    assert _by_group['💼 持仓交易'] >= 4
    assert _by_group['🛠 工具'] >= 4


def test_tool_group_contains_expected_low_freq_items():
    """『🛠 工具』组应包含低频工具类页面（体检/预警/导出/条件单），而非核心交易动作。"""
    _tool_paths = {it[0].split('/')[-1] for g, items in w._NAV_GROUPS
                   if g == '🛠 工具' for it in items}
    for _p in ('34_体检扫描.py', '47_价格预警.py', '95_数据导出.py', '44_智能条件单.py'):
        assert _p in _tool_paths, f"{_p} 应归入工具组"


def test_favorites_present_and_reachable():
    """⭐ 常用区默认 Top5 高频页，且每个都在 hero/分组中真实可达（不是悬空链接）。"""
    _all_paths = {it[0].replace('\\', '/').split('/')[-1] for g, items in w._NAV_GROUPS for it in items}
    _all_paths |= {it[0].replace('\\', '/').split('/')[-1] for it in w._NAV_HERO}
    assert len(w._NAV_FAVORITES) == 5, "常用区应为 5 个高频页"
    for _f in w._NAV_FAVORITES:
        assert _f[0].replace('\\', '/').split('/')[-1] in _all_paths, f"{_f} 指向的页面不存在于导航"


# ── 搜索框实验（R20）：按关键字实时过滤 _NAV_GROUPS ──

def test_filter_empty_kw_returns_all():
    """空关键字=不过滤，返回与原列表等价（组数与每组 items 数一致）。"""
    out = w._filter_nav_groups(w._NAV_GROUPS, "")
    assert len(out) == len(w._NAV_GROUPS)
    for (_g1, _i1), (_g2, _i2) in zip(out, w._NAV_GROUPS):
        assert _g1 == _g2
        assert len(_i1) == len(_i2)


def test_filter_keyword_matches_label():
    """关键字命中 label（如『回测』）：只保留命中的项；空组被剔除。"""
    out = w._filter_nav_groups(w._NAV_GROUPS, "回测")
    _hits = sum(len(items) for _, items in out)
    assert _hits >= 1, "应至少命中 1 项（含『策略回测』）"
    for gname, items in out:
        for it in items:
            assert "回测" in it[1] or "回测" in it[0], f"{it} 不应出现"


def test_filter_keyword_matches_path():
    """关键字命中 path（中文文件名 URL 编码前的局部）：能筛出文件名含关键字的项。"""
    out = w._filter_nav_groups(w._NAV_GROUPS, "回测")
    _all = [it for _, items in out for it in items]
    assert any("30_策略回测" in it[0] for it in _all), "应命中『30_策略回测.py』"


def test_filter_keyword_drops_empty_groups():
    """过滤后空组被剔除（不渲染无条目的分组头）。"""
    out = w._filter_nav_groups(w._NAV_GROUPS, "星辰")
    # 『星辰 AI』只在『💬 社区与 AI』组，命中 1 项；其他组应被剔除
    _gnames = [g for g, _ in out]
    assert "💬 社区与 AI" in _gnames
    assert "📈 行情盯盘" not in _gnames, "行情盯盘组应被剔除（无匹配）"
    assert "🔎 个股研究" not in _gnames
    assert len(out) == 1, f"应只返回 1 个分组，实际 {len(out)}: {_gnames}"


def test_filter_keyword_case_insensitive():
    """英文路径/标签大小写不敏感。"""
    out_lower = w._filter_nav_groups(w._NAV_GROUPS, "p1")
    out_upper = w._filter_nav_groups(w._NAV_GROUPS, "P1")
    assert len(out_lower) == len(out_upper)
    assert out_lower == out_upper


def test_filter_unknown_keyword_returns_empty():
    """无任何匹配的 keyword：返回空列表（侧边栏不渲染任何分组头）。"""
    out = w._filter_nav_groups(w._NAV_GROUPS, "不存在的关键字xyz123")
    assert out == []


def test_version_chip_constant_present():
    """版本指纹常量 _GIT_SHA 已注入；不为空，方便用户刷新后核对新代码已加载。"""
    assert hasattr(w, '_GIT_SHA'), "缺少 _GIT_SHA 版本指纹常量"
    assert isinstance(w._GIT_SHA, str) and w._GIT_SHA, "_GIT_SHA 应为非空字符串"


def test_nav_active_css_obvious_and_theme_aware():
    """当前页高亮必须一眼可见且随主题自适应。

    锁死 R26 修复前的回归：旧 .ss-nav-active 写死 color:#E2E8F0（近白字）+ 20% 透明渐变，
    在默认亮色侧边栏上≈隐形，用户感知不到「我在哪」。
    """
    dark = w._nav_active_css(True)
    light = w._nav_active_css(False)
    for css in (dark, light):
        assert ".ss-nav-active" in css
        # 实色填充（不再用 20% 透明度的淡背景）
        assert "background:linear-gradient(90deg,#667eea,#764ba2)" in css
        # 白字：在紫蓝实底上亮/暗主题均清晰可辨
        assert "color:#FFFFFF" in css
        # 明显加粗，区别于普通项
        assert "font-weight:800" in css
        # 旧实现的「亮色下隐形白字 / 20% alpha 残影」不得再出现
        assert "#E2E8F0" not in css
        assert "#667eea33" not in css
    # 主题自适应：暗色金色描边 + 微光，亮色橙色高对比描边
    assert "#FFD166" in dark and "#FF8C00" in light
    assert dark != light

