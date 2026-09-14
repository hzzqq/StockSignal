"""Sidebar 导航补全 + 当前位置高亮的回归测试（锐评迭代：决策面板入栏 + 防迷路）。

不依赖网络：只校验 _NAV_GROUPS 结构、_current_nav_label / _current_page_basename 逻辑。
导航现为「6 个一级类目 → 若干子簇 (sub_label, [items])」两级结构。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import modules.widgets as w
from unittest.mock import patch
from collections import Counter


def _all_nav_paths():
    paths = []
    for _it in w._iter_nav_items():
        paths.append(_it[0].replace('\\', '/'))
    for _it in getattr(w, '_NAV_HERO', []):
        paths.append(_it[0].replace('\\', '/'))
    return paths


def test_decision_panel_in_nav():
    """决策面板（54）必须出现在侧边栏导航中（用户核心诉求：不再「隐藏」）。"""
    paths = _all_nav_paths()
    assert 'pages/54_今日决策面板.py' in paths


def test_key_pages_present_and_absorbed_pages_deduped():
    """导航既不能缺关键页，也不能重复登记已被「合并页」内嵌的子页。

    沿革：这些页曾被补进侧边栏（当时确实无从进入）；后来 24_个股研究 / 45_持仓中心
    把 11/20 与 46/40/41 内嵌为 radio 子视图 —— 此时再并列登记就是「同一件事三个入口」，
    正是导航「乱/重叠」的根源。故守卫改为：关键页仍在，被吸收页只在合并页内部出现。
    """
    paths = set(_all_nav_paths())
    for p in [
        'pages/15_市场驱动力.py',
        'pages/32_智能选股.py',
        'pages/25_QuantAgent投研.py',
        'pages/55_P1量化信号.py',
        'pages/24_个股研究.py',
        'pages/45_持仓中心.py',
    ]:
        assert p in paths, f"{p} 未出现在侧边栏导航"
    for p in [
        'pages/11_股票选取.py',
        'pages/20_个股分析.py',
        'pages/40_仓位管理.py',
        'pages/41_组合收益.py',
        'pages/46_自选股监控.py',
    ]:
        assert p not in paths, f"{p} 已被合并页内嵌，不应再单独登记导航项"


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
    """锐评重构后一级类目收敛到 6（8 个扁平分组 → 6 个一级类目两级结构）。"""
    _names = [g for g, _ in w._NAV_GROUPS]
    assert len(w._NAV_GROUPS) == 6, f"一级类目数应为 6，实际 {len(w._NAV_GROUPS)}: {_names}"
    # 旧的扁平分组（已被合并为两级结构）不应再作为一级类目出现
    _forbidden = ['📈 行情盯盘', '🧩 板块结构', '🌐 市场宽度', '🛠 工具', '💬 社区与 AI',
                  '🎯 决策核心', '📘 新手引导', '💰 实盘 & 条件单', '🧪 策略工具', '💼 我的持仓']
    for f in _forbidden:
        assert f not in _names, f"旧扁平分组仍残留为一级类目: {f}"


def test_hero_is_decision_panel():
    """顶部 Hero 入口为决策面板（54），体现决策闭环主线。"""
    assert len(w._NAV_HERO) == 1
    assert w._NAV_HERO[0][0] == 'pages/54_今日决策面板.py'
    assert w._NAV_HERO[0][1] == '今日决策面板'


def test_no_sub_markers_and_hubs_absorb_subpages():
    """侧边栏已无 sub 叠层；可达性改由「合并页真的内嵌了被吸收子页」这份代码事实保证。

    这是比「子页也登记一份」更强的守卫：既不重复，也不丢可达性。
    """
    _subs = [
        _it[0]
        for _top, _clusters in w._NAV_GROUPS
        for _sub, _items in _clusters
        for _it in _items
        if len(_it) >= 4 and _it[3] == 'sub'
    ]
    assert not _subs, f"已并入合并页的重叠页不应再以 sub 标记并列: {_subs}"

    _pages = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'pages')
    with open(os.path.join(_pages, '24_个股研究.py'), encoding='utf-8') as _f:
        _hub24 = _f.read()
    with open(os.path.join(_pages, '45_持仓中心.py'), encoding='utf-8') as _f:
        _hub45 = _f.read()
    for _p in ('11_股票选取.py', '20_个股分析.py'):
        assert _p in _hub24, f"24_个股研究 必须内嵌 {_p}（否则该页从导航不可达）"
    for _p in ('46_自选股监控.py', '40_仓位管理.py', '41_组合收益.py'):
        assert _p in _hub45, f"45_持仓中心 必须内嵌 {_p}（否则该页从导航不可达）"


def test_icon_global_uniqueness():
    """所有导航图标（一级类目头 + Hero + item + admin）全局唯一，无撞车。"""
    _icons = []
    for _top, _clusters in w._NAV_GROUPS:
        _icons.append(_top.split()[0])  # 一级类目头图标
        for _sub, _items in _clusters:
            for _it in _items:
                _icons.append(_it[2])
    for _it in getattr(w, '_NAV_HERO', []):
        _icons.append(_it[2])
    for _it in w._NAV_ADMIN:
        _icons.append(_it[2])
    _dup = [k for k, v in Counter(_icons).items() if v > 1]
    assert not _dup, f"图标撞车: {_dup}"


def test_no_duplicate_paths():
    """任一页面路径在 hero + 各分组中至多出现一次（无重复登记）。"""
    _paths = [_it[0].replace('\\', '/') for _it in w._iter_nav_items()]
    for _it in getattr(w, '_NAV_HERO', []):
        _paths.append(_it[0].replace('\\', '/'))
    _dup = [k for k, v in Counter(_paths).items() if v > 1]
    assert not _dup, f"路径重复登记: {_dup}"


def test_personal_center_label():
    """91_我的 标签已统一为『个人中心』，与分组命名解耦。"""
    assert w._current_nav_label('91_我的.py') == '个人中心'
    assert w._current_nav_label('pages/91_我的.py') == '个人中心'


def test_group_order_mental_flow():
    """一级类目顺序遵循用户心智流：行情→广度温度→个股研究→量化选股→持仓交易→工具与社区。"""
    _order = [g for g, _ in w._NAV_GROUPS]
    _expected = ['📈 行情与板块', '🌐 市场广度·温度', '🔎 个股研究',
                 '🧪 量化选股', '💼 持仓交易', '🛠 工具与社区']
    assert _order == _expected, f"一级类目顺序偏离心智流: {_order}"


def test_hold_group_split_reduces_oversized():
    """两级重构后任何『子簇』item 数均 ≤ 8（旧的 20 项『市场宽度』大杂烩已拆解，无超长簇）；
    合并后的持仓交易与工具/社区子簇均落在 4–6 的合理区间。"""
    _max_cluster = 0
    for _top, _clusters in w._NAV_GROUPS:
        for _sub, _items in _clusters:
            _max_cluster = max(_max_cluster, len(_items))
    assert _max_cluster <= 8, f"存在超过 8 项的子簇，违背两级拆解初衷: {_max_cluster}"
    _counts = {}
    for _top, _clusters in w._NAV_GROUPS:
        if '持仓交易' in _top:
            _counts['持仓交易'] = sum(len(_i) for _s, _i in _clusters)
        if '工具与社区' in _top:
            for _sub, _items in _clusters:
                _counts[_sub] = len(_items)
    assert 2 <= _counts['持仓交易'] <= 6, f"持仓交易应 2–6 项，实际 {_counts['持仓交易']}"
    assert 4 <= _counts.get('工具', 0) <= 6, f"工具子簇应 4–6 项，实际 {_counts.get('工具')}"
    assert 4 <= _counts.get('社区与AI', 0) <= 6, f"社区与AI子簇应 4–6 项，实际 {_counts.get('社区与AI')}"


def test_tool_group_contains_expected_low_freq_items():
    """『工具』子簇（位于『🛠 工具与社区』一级类目下）应包含低频工具页（体检/预警/导出/条件单）。"""
    _tool_paths = set()
    for _top, _clusters in w._NAV_GROUPS:
        if '工具与社区' in _top:
            for _sub, _items in _clusters:
                if _sub == '工具':
                    _tool_paths = {it[0].split('/')[-1] for it in _items}
    for _p in ('34_体检扫描.py', '47_价格预警.py', '95_数据导出.py', '44_智能条件单.py'):
        assert _p in _tool_paths, f"{_p} 应归入工具子簇"


def test_favorites_present_and_reachable():
    """⭐ 常用区默认 Top5 高频页，且每个都在 hero/分组中真实可达（不是悬空链接）。"""
    _all_paths = {p.replace('\\', '/').split('/')[-1] for p in _all_nav_paths()}
    assert len(w._NAV_FAVORITES) == 5, "常用区应为 5 个高频页"
    for _f in w._NAV_FAVORITES:
        assert _f[0].replace('\\', '/').split('/')[-1] in _all_paths, f"{_f} 指向的页面不存在于导航"


# ── 搜索框实验（R20）：按关键字实时过滤 _NAV_GROUPS ──

def test_filter_empty_kw_returns_all():
    """空关键字=不过滤，返回与原列表等价（组数与每组扁平 item 数一致）。"""
    out = w._filter_nav_groups(w._NAV_GROUPS, "")
    assert len(out) == len(w._NAV_GROUPS)
    for (_g1, _i1), (_g2, _clusters) in zip(out, w._NAV_GROUPS):
        _expected = sum(len(_items) for _sub, _items in _clusters)
        assert _g1 == _g2
        assert len(_i1) == _expected


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
    # 『星辰 AI』只在『🛠 工具与社区』的『社区与AI』子簇，命中 1 项；其他组应被剔除
    _gnames = [g for g, _ in out]
    assert "🛠 工具与社区" in _gnames
    assert "📈 行情与板块" not in _gnames, "行情与板块组应被剔除（无匹配）"
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


def test_home_entry_pinned_above_groups():
    """🏠 首页入口必须置顶（先于分组导航渲染）。

    回归锁定：首页链接原先写在侧边栏**最底部**，等于不可见，用户进任一分页后
    找不到回首页的路（原生 stSidebarNav 已被 display:none 隐藏）。
    """
    _src_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'modules', 'widgets.py'
    )
    with open(_src_path, encoding='utf-8') as _f:
        _src = _f.read()
    assert _src.count("label='🏠 首页'") == 1, "首页入口应恰好出现一次（不得重复登记）"
    assert _src.index("label='🏠 首页'") < _src.index(
        "for _i, (top_label, clusters) in enumerate(_NAV_GROUPS)"
    ), "首页入口必须渲染在分组导航之前（置顶）"
