"""
tests/test_app_home_wiring.py — 首页「情绪笔记 / 次日预判」快捷入口的接线回归测试

背景（2026-08-29）：情绪笔记与次日预判已接进《市场情绪》页，但从首页要点好几层才能到。
老板要「首页快捷入口」。本测试锁死两点：

1. **AST 源码级**：app.py 必须有情绪笔记快捷入口（按钮 + 跳 P_市场情绪.py + 置聚焦标记）；
   P_市场情绪.py 必须消费该聚焦标记（pop 后高亮一次），否则跳过去等于没跳。
2. **功能级**：AppTest 真跑首页（离线打桩后端），断言不崩且按钮真的渲染出来了
   —— 而不只是「源码里写了」。

⚠️ 补缺口：此前 tests/ 里**没有任何用例覆盖 app.py**（test_pages_smoke 只扫 pages/），
   首页改动处于无测试保护状态。本文件补上首页的冒烟 + 接线护栏。
"""
import ast
import os
import time

import jwt
import pytest
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.py")
PAGE = os.path.join(ROOT, "pages", "P_市场情绪.py")

# 首页有登录门禁：游客态只渲染门禁，快捷入口在门禁之后，必须注入登录态才能逼出
from modules.site_config import TEST_SMOKE_SECRET  # noqa: E402

_FAKE_TOKEN = jwt.encode(
    {"sub": "demo", "username": "demo", "role": "admin", "exp": int(time.time()) + 999999},
    TEST_SMOKE_SECRET,
    algorithm="HS256",
)
_FAKE_USER = {
    "id": 1,
    "username": "demo",
    "role": "admin",
    "email": "demo@stocksignal.local",
}

# AppTest 无浏览器 URL 上下文：中和 page_link / switch_page（同 test_pages_smoke）
import streamlit as st  # noqa: E402

st.page_link = lambda *a, **k: None  # noqa: E402
st.switch_page = lambda *a, **k: None  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402


def _src(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _tree(path: str):
    return ast.parse(_src(path))


# ══════════════════════════════════════════════════════════════
#  一、AST 源码级防回退
# ══════════════════════════════════════════════════════════════
def test_app_has_mood_note_entry():
    """首页必须有情绪笔记快捷入口：按钮 key + 跳市场情绪页。"""
    src = _src(APP)
    assert "qe_mood_note" in src, "首页缺少情绪笔记快捷入口按钮（key=qe_mood_note）"
    assert "pages/P_市场情绪.py" in src, "快捷入口未指向《市场情绪》页"


def test_app_sets_focus_flag_before_switch():
    """跳转前必须置 shep_focus_note 标记，否则目标页无从聚焦。"""
    src = _src(APP)
    i_flag = src.find('"shep_focus_note"')
    i_switch = src.find('safe_switch_page("pages/P_市场情绪.py")')
    assert i_flag > 0, "未设置 shep_focus_note 聚焦标记"
    assert i_switch > 0, "未跳转市场情绪页"
    assert i_flag < i_switch, "聚焦标记必须在跳转之前设置（否则目标页读不到）"


def test_page_consumes_focus_flag():
    """目标页必须消费（pop）聚焦标记并高亮笔记区块，否则跳转无意义。"""
    src = _src(PAGE)
    assert 'pop("shep_focus_note"' in src or "pop('shep_focus_note'" in src, \
        "《市场情绪》页未消费 shep_focus_note 标记（跳转后无聚焦提示）"


def test_focus_flag_is_one_shot():
    """聚焦标记必须是「一次性」：用 pop 而非 get，刷新后恢复常态。"""
    src = _src(PAGE)
    assert 'pop("shep_focus_note"' in src, \
        "聚焦标记应用 session_state.pop 读取（一次性），用 get 会每次刷新都高亮"


# ══════════════════════════════════════════════════════════════
#  二、功能级：真跑首页
# ══════════════════════════════════════════════════════════════
@pytest.fixture
def offline_backend(monkeypatch):
    """离线打桩：后端不可达（首页自选股数量等请求应走降级，不该崩）。"""

    def _boom(*a, **k):
        raise requests.exceptions.ConnectionError("offline stub")

    monkeypatch.setattr(requests, "get", _boom, raising=True)
    monkeypatch.setattr(requests, "post", _boom, raising=True)
    try:
        st.cache_data.clear()
    except Exception:  # noqa: BLE001
        pass


def _run_app() -> AppTest:
    """以「已登录 + 后端离线」态跑首页。"""
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["auth_token"] = _FAKE_TOKEN
    at.session_state["auth_user"] = dict(_FAKE_USER)
    at.run()
    return at


def _button_labels(at) -> str:
    labels = []
    for w in at.button:
        labels.append(str(getattr(w, "label", "")))
    for w in at.markdown:
        labels.append(str(getattr(w, "value", "")))
    for w in at.caption:
        labels.append(str(getattr(w, "value", "")))
    return "\n".join(labels)


def test_home_renders_without_exception(offline_backend):
    """首页在后端不可达时仍不崩（离线降级）。"""
    at = _run_app()
    assert not at.exception, f"首页渲染异常: {[str(e) for e in at.exception[:3]]}"


def test_home_shows_mood_note_button(offline_backend):
    """首页必须真的渲染出「情绪笔记」按钮（不只是源码里写了）。"""
    at = _run_app()
    assert not at.exception, f"首页渲染异常: {[str(e) for e in at.exception[:3]]}"
    text = _button_labels(at)
    assert "情绪笔记" in text, "首页未渲染出情绪笔记入口（能力接了但用户看不到）"


def test_home_mood_note_button_clickable(offline_backend):
    """点一下情绪笔记按钮不应抛异常（含 safe_switch_page 路径）。"""
    at = _run_app()
    btn = [b for b in at.button if "情绪笔记" in str(getattr(b, "label", ""))]
    assert btn, "未找到情绪笔记按钮"
    btn[0].set_value(True).run()
    assert not at.exception, f"点击情绪笔记按钮后异常: {[str(e) for e in at.exception[:3]]}"
