"""
tests/test_page_guard.py
========================
校验 modules.page_guard 这层「跨页面错误边界 / 数据源隔离」基础设施：

- render_error_card：同名区块多次渲染时，重试按钮 key 必须全局唯一
  （回归防护：否则 Streamlit DuplicateElementId 会让「错误卡片本身崩溃」，
   击穿错误边界的隔离初衷）；
- safe_section：块内抛异常时被隔离、渲染错误卡片，不向外冒泡；
- safe_fragment：被装饰区块抛异常时被隔离为片段级错误卡片；
- get_data_source_health：down / degraded / ok / unknown 的状态判定逻辑。

全部用轻量假 streamlit（monkeypatch page_guard.st 的相关属性）离线运行。
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest

from modules import page_guard


class _FakeSt:
    """记录 st.* 调用的最小假实现（仅覆盖 render_error_card 用到的接口）。"""

    def __init__(self):
        self.errors = []
        self.captions = []
        self.codes = []
        self.button_keys = []

    def error(self, msg, icon=None):
        self.errors.append(msg)

    def caption(self, msg):
        self.captions.append(msg)

    def code(self, body, language=None):
        self.codes.append(body)

    @contextmanager
    def expander(self, label, expanded=False):
        yield self

    def button(self, label, key=None, help=None):
        self.button_keys.append(key)
        return False  # 从不"点击"，避免触发 rerun

    def rerun(self, scope=None):  # pragma: no cover - 本测试不点击按钮
        raise AssertionError("rerun 不应被触发")


@pytest.fixture()
def fake_st(monkeypatch):
    st = _FakeSt()
    monkeypatch.setattr(page_guard, "st", st)
    return st


def _boom():
    raise ValueError("模拟数据源异常")


def test_error_card_keys_are_unique_for_same_name(fake_st):
    """同一区块名渲染两次，两个重试按钮的 key 必须不同（防 DuplicateElementId）。"""
    exc = ValueError("x")
    page_guard.render_error_card("行情卡", exc, retry="fragment")
    page_guard.render_error_card("行情卡", exc, retry="fragment")
    keys = [k for k in fake_st.button_keys if k]
    assert len(keys) == 2
    assert keys[0] != keys[1]
    assert all(k.startswith("frag_retry_行情卡_") for k in keys)


def test_error_card_page_retry_key_prefix(fake_st):
    page_guard.render_error_card("行情看板", ValueError("x"), retry=True)
    assert fake_st.button_keys[-1].startswith("pg_retry_行情看板_")


def test_error_card_no_button_when_retry_false(fake_st):
    page_guard.render_error_card("静默区块", ValueError("x"))
    assert fake_st.button_keys == []
    assert fake_st.errors  # 仍渲染了错误标题


def test_error_card_truncates_long_summary(fake_st):
    long_msg = "e" * 500
    page_guard.render_error_card("区块", ValueError(long_msg))
    # 摘要在标题行不出现，但函数内部会截断 str(exc)；这里只断言不抛异常且渲染成功
    assert fake_st.errors


def test_safe_section_isolates_exception(fake_st):
    """块内异常必须被 safe_section 吞掉并渲染错误卡片，不向外传播。"""
    with page_guard.safe_section("资金流向") as ok:
        assert ok is True
        _boom()
    # 未抛出到这里即说明被隔离
    assert fake_st.errors, "应渲染错误卡片"


def test_safe_section_success_path(fake_st):
    with page_guard.safe_section("正常块") as ok:
        assert ok is True
    assert fake_st.errors == []


def test_safe_fragment_isolates_exception(fake_st, monkeypatch):
    """safe_fragment 装饰的函数抛异常时应被隔离为错误卡片，不向外冒泡。"""
    # st.fragment 在真 streamlit 下需要脚本运行上下文；用透传装饰器替身。
    monkeypatch.setattr(page_guard.st, "fragment", lambda **kw: (lambda f: f), raising=False)

    @page_guard.safe_fragment("板块行情")
    def region():
        raise RuntimeError("区块内部错误")

    region()  # 不应抛出
    assert fake_st.errors


def test_safe_fragment_no_parens_usage(fake_st, monkeypatch):
    """无括号用法 @safe_fragment 也应工作，错误卡片标题取函数名。"""
    monkeypatch.setattr(page_guard.st, "fragment", lambda **kw: (lambda f: f), raising=False)

    @page_guard.safe_fragment
    def my_region():
        raise RuntimeError("boom")

    my_region()
    assert fake_st.errors


def test_page_error_boundary_isolates(fake_st):
    with page_guard.page_error_boundary("行情看板"):
        _boom()
    assert fake_st.errors
    assert fake_st.button_keys[-1].startswith("pg_retry_")


# ── get_data_source_health 状态机 ────────────────────────────
def _patch_metrics(monkeypatch, metrics):
    import modules.fetcher as fetcher
    monkeypatch.setattr(fetcher, "get_source_metrics", lambda: metrics, raising=False)


def test_health_ok(monkeypatch):
    _patch_metrics(monkeypatch, {"em": {"calls": 10, "success_rate": 1.0}})
    assert page_guard.get_data_source_health()["status"] == "ok"


def test_health_degraded(monkeypatch):
    _patch_metrics(monkeypatch, {"em": {"calls": 10, "success_rate": 0.8}})
    h = page_guard.get_data_source_health()
    assert h["status"] == "degraded"
    assert "em" in h["degraded"]


def test_health_down(monkeypatch):
    _patch_metrics(monkeypatch, {"em": {"calls": 10, "success_rate": 0.1}})
    h = page_guard.get_data_source_health()
    assert h["status"] == "down"
    assert "em" in h["down"]


def test_health_unknown_when_no_calls(monkeypatch):
    _patch_metrics(monkeypatch, {"em": {"calls": 0, "success_rate": 1.0}})
    # 全部 calls==0 → 无有效样本 → ok（无降级/宕机）；但空 metrics → unknown
    assert page_guard.get_data_source_health()["status"] == "ok"
    _patch_metrics(monkeypatch, {})
    assert page_guard.get_data_source_health()["status"] == "unknown"
