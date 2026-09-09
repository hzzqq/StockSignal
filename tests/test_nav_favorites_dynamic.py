"""动态⭐常用区（按真实访问频率 Top5）回归测试。

锁定 R22 的核心不变量：
- record_nav_visit 跨页切换累计计数（不丢历史）
- session 内同页连续 rerun 去重（只统计真实跳转）
- 持久化到 data/nav_freq.json（跟随 SS_DATA_DIR），fail-safe
- load_nav_favorites 返回 TopN（按 count 降序），且为 3 元组（剥离 sub 标记，常用区不缩进）
- 无数据时回退到默认 _NAV_FAVORITES
"""
import os
import json
import sys

import pytest
import streamlit as st
import modules.widgets as w


@pytest.fixture
def fake_session(tmp_path, monkeypatch):
    """构造假 session_state + 临时 nav_freq.json 路径，隔离真实 data/。"""
    fake_ss = {}
    monkeypatch.setattr(st, "session_state", fake_ss, raising=False)
    freq_file = os.path.join(str(tmp_path), "nav_freq.json")
    monkeypatch.setattr(w, "_nav_freq_path", lambda: freq_file, raising=False)
    return fake_ss, freq_file


def test_visit_across_pages_merges_counts(fake_session):
    """跨页切换：30 计 1、切到 20 计 1，文件应同时保留 30 与 20（修复前丢历史）。"""
    _ss, freq_file = fake_session
    w.record_nav_visit("30_策略回测.py")
    w.record_nav_visit("20_个股分析.py")
    data = json.load(open(freq_file, encoding="utf-8"))
    assert data.get("30_策略回测.py") == 1
    assert data.get("20_个股分析.py") == 1


def test_session_dedup_counts_transitions_only(fake_session):
    """同页连续访问（页内 rerun）只计一次，不污染计数。"""
    _ss, freq_file = fake_session
    w.record_nav_visit("30_策略回测.py")          # 跳转：计 1
    for _ in range(3):
        w.record_nav_visit("30_策略回测.py")       # 同页 rerun：去重
    w.record_nav_visit("20_个股分析.py")          # 切页：计 1
    w.record_nav_visit("20_个股分析.py")          # 同页 rerun：去重
    data = json.load(open(freq_file, encoding="utf-8"))
    assert data.get("30_策略回测.py") == 1
    assert data.get("20_个股分析.py") == 1


def test_frequency_ranking_drives_top5(fake_session):
    """访问频次不同 → Top5 按 count 降序返回，且为 3 元组（无 sub 标记）。"""
    _ss, _ = fake_session
    # 30 访问 3 次、20 访问 2 次、10 访问 1 次
    for _ in range(3):
        w.record_nav_visit("30_策略回测.py")
        if _ < 2:
            w.record_nav_visit("20_个股分析.py")
        if _ < 1:
            w.record_nav_visit("10_行情看板.py")
    favs = w.load_nav_favorites()
    assert len(favs) == 3
    labels = [f[1] for f in favs]
    assert labels[0] == "策略回测"      # 频次最高
    assert labels[1] == "个股分析"
    assert labels[2] == "行情看板"
    # 全部 3 元组（path, label, icon），无 sub 标记
    for f in favs:
        assert len(f) == 3


def test_sub_marker_stripped_in_favorites(fake_session):
    """20_个股分析 在导航里是 sub（4 元组），但常用区应剥离 sub 标记。"""
    _ss, _ = fake_session
    w.record_nav_visit("20_个股分析.py")
    favs = w.load_nav_favorites()
    assert favs[0][0] == "pages/20_个股分析.py"
    assert len(favs[0]) == 3


def test_favorites_fallback_when_no_data(tmp_path, monkeypatch):
    """无访问数据时回退到默认 _NAV_FAVORITES（5 项静态推荐）。"""
    freq_file = os.path.join(str(tmp_path), "nav_freq.json")  # 不存在
    monkeypatch.setattr(w, "_nav_freq_path", lambda: freq_file, raising=False)
    favs = w.load_nav_favorites()
    assert len(favs) == len(w._NAV_FAVORITES) == 5
    assert favs[0][0] == "pages/10_行情看板.py"


def test_homepage_not_counted(fake_session):
    """app.py（首页/概览）不计入高频。"""
    _ss, freq_file = fake_session
    w.record_nav_visit("app.py")
    assert not os.path.exists(freq_file)
