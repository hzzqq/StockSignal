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
