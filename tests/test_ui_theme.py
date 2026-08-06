"""
tests/test_ui_theme.py
======================
锁定 modules/ui_theme.py 的纯函数与注入行为（项目内零测试覆盖，1763 行）。

重点验证：
  - dashboard_sf_css：决策仪表盘 CSS 单一来源；暗/亮两套 :root 变量正确切换
    （个股分析页采用「绿涨红跌」约定，--buy 为绿、--sell 为红，与全局相反，须锁定）
  - loading_spinner：default/pulse/dots/bar 四种变体 + 未知变体回退 default
    （空态/加载态 UX 单一来源，回归会让加载态样式错乱）
  - get_current_mode：从 session_state 读主题模式
  - inject_plotly_dark：plotly 缺失时静默跳过不抛异常
"""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components
import modules.ui_theme as sf


class _FakeSS:
    def __init__(self, data):
        self._d = data

    def get(self, k, default=None):
        return self._d.get(k, default)


def _stub_st(monkeypatch):
    calls = {}

    def fake_markdown(*a, **k):
        calls.setdefault("md", []).append(a[0] if a else "")

    monkeypatch.setattr(st, "markdown", fake_markdown)
    return calls


def test_dashboard_sf_css_dark_uses_deep_space_tokens(monkeypatch):
    monkeypatch.setattr(sf, "_theme_is_dark", lambda: True)
    css = sf.dashboard_sf_css()
    assert ":root" in css
    assert "--bg:#0f0f23" in css          # 暗夜深空黑底
    assert "--buy:#009e60" in css          # 个股分析页：绿涨
    assert "--sell:#dc2626" in css         # 红跌
    assert "绿涨红跌" in css               # 文档约定注释


def test_dashboard_sf_css_light_uses_white_tokens(monkeypatch):
    monkeypatch.setattr(sf, "_theme_is_dark", lambda: False)
    css = sf.dashboard_sf_css()
    assert "--bg:#ffffff" in css          # 白天白卡
    assert "--buy:#009e60" in css


def test_loading_spinner_variants_and_fallback(monkeypatch):
    calls = _stub_st(monkeypatch)
    # default 变体
    sf.loading_spinner("读取中", variant="default")
    assert "ld-spin" in calls["md"][-1]
    assert "读取中" in calls["md"][-1]

    sf.loading_spinner("脉冲", variant="pulse")
    assert "ld-pulse" in calls["md"][-1]

    sf.loading_spinner("点", variant="dots")
    assert "ld-bounce" in calls["md"][-1]

    sf.loading_spinner("条", variant="bar")
    assert "ld-slide" in calls["md"][-1]

    # 未知变体回退 default
    sf.loading_spinner("X", variant="nope")
    assert "ld-spin" in calls["md"][-1]


def test_loading_spinner_dark_vs_light_color(monkeypatch):
    monkeypatch.setattr(sf, "_theme_is_dark", lambda: True)
    calls = _stub_st(monkeypatch)
    sf.loading_spinner("暗")
    assert "#667eea" in calls["md"][-1]   # 暗夜 accent

    monkeypatch.setattr(sf, "_theme_is_dark", lambda: False)
    calls2 = _stub_st(monkeypatch)
    sf.loading_spinner("亮")
    assert "#555B65" in calls2["md"][-1]  # 白天灰字


def test_get_current_mode_reads_session_state(monkeypatch):
    monkeypatch.setattr(st, "session_state", _FakeSS({"theme_mode": "dark"}))
    assert sf.get_current_mode() == "dark"
    monkeypatch.setattr(st, "session_state", _FakeSS({}))
    assert sf.get_current_mode() == "light"  # 默认 light


def test_inject_plotly_dark_does_not_raise(monkeypatch):
    _stub_st(monkeypatch)
    try:
        sf.inject_plotly_dark()
    except Exception as e:  # pragma: no cover
        raise AssertionError(f"inject_plotly_dark 不应抛异常: {e}")
