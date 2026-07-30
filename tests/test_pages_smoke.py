"""
页面级渲染冒烟回归测试（防 _INDEX_INFOS 类崩溃回归）。

用 Streamlit AppTest 在无网络环境下逐一加载 pages/ 下每个页面，断言渲染过程中
**不抛出未捕获异常**。这是抓「函数内 NameError / AttributeError」类崩溃的护栏——
普通 import 检查抓不到（如之前 _INDEX_INFOS、_dt 那种在 render 时才触发的错误）。

设计要点：
- 打桩 `st.page_link` 为 no-op：AppTest 运行在无浏览器 URL 上下文，原生 page_link 会抛
  `KeyError: 'url_pathname'`，那是测试环境伪象而非应用 bug，必须中和才能跑通含导航的页面。
- 不 mock 网络：页面内部的数据取数若未做容错会真实失败，但本项目各取数函数已统一 try/except
  降级，故网络失败不应导致页面级崩溃；若某页面因代码 bug 崩溃，本测试会暴露。
- 各页面独立超时，避免单个页面卡死拖垮整套。

运行：pytest tests/test_pages_smoke.py -q
"""

from __future__ import annotations

import glob
import os

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

# 中和 AppTest 环境伪象：page_link 需要运行时 URL 上下文，headless 下会 KeyError
st.page_link = lambda *a, **k: None  # noqa: E731

PAGE_FILES = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "pages", "*.py")))


def _load(page_path: str) -> AppTest:
    at = AppTest.from_file(page_path, default_timeout=30)
    at.run()
    return at


@pytest.mark.parametrize("page_path", PAGE_FILES, ids=lambda p: os.path.basename(p))
def test_page_renders_without_exception(page_path: str):
    """每个页面在 headless 下加载不应抛出未捕获异常。"""
    at = _load(page_path)
    assert len(at.exception) == 0, (
        f"页面 {os.path.basename(page_path)} 渲染抛出异常:\n"
        + "\n".join(str(e) for e in at.exception[:3])
    )


def test_all_pages_collected():
    """防守：确保 pages/ 下确有页面被收集，防止 glob 失败导致测试空跑。"""
    assert len(PAGE_FILES) >= 30, f"收集到的页面数异常少: {len(PAGE_FILES)}"
