"""
页面级渲染冒烟回归测试（防 _INDEX_INFOS / _dt 类崩溃回归，并覆盖登录门禁后真实内容）。

用 Streamlit AppTest 逐一加载 pages/ 下每个页面，断言渲染过程中**不抛出未捕获异常**。
这是抓「函数内 NameError / AttributeError / KeyError」类崩溃的护栏——普通 import 检查抓不到
（如之前 _INDEX_INFOS、_dt 那种在 render 时才触发的错误）。

与旧版的关键增强（对应自驱迭代「锐评」指出的真问题）：
1. **模拟离线**：monkeypatch requests / urllib 立即抛 ConnectionError，避免单个页面卡 30s+，
   同时逼出各取数函数的 try/except 降级路径——这正是用户真实断网/弱网时看到的页面。
2. **双态覆盖**：每个页面跑两遍——
   - 游客态（无登录态）：只渲染登录门禁，验证门禁本身不崩。
   - 已登录态（注入合法 JWT + user dict）：逼出门禁后真实业务代码，抓「登录才触发」的崩溃。
   旧版只有游客态，门禁后的代码路径从没被执行过。
3. **错误小部件采集**：除 at.exception（未捕获异常）外，收集 st.error / st.exception 小部件文本，
   写入 tests/.pages_smoke_report.json 供人工排雷（空数据提示属正常，代码崩溃属真 bug）。

设计要点：
- 打桩 st.page_link / st.switch_page 为 no-op：AppTest 运行在无浏览器 URL 上下文，原生会抛 KeyError。
- 不 mock 业务数据：页面用真实（被离线打桩后的）降级路径渲染，重点验证「渲染期不崩」而非「数据对不对」。

运行：pytest tests/test_pages_smoke.py -q
"""

from __future__ import annotations

import glob
import json
import os
import time

import jwt
import pytest
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

# 中和 AppTest 环境伪象：page_link / switch_page 需要运行时 URL 上下文，headless 下会 KeyError
st.page_link = lambda *a, **k: None  # noqa: E731
st.switch_page = lambda *a, **k: None  # noqa: E731

PAGE_DIR = os.path.join(os.path.dirname(__file__), "..", "pages")
ALL_PAGE_FILES = sorted(glob.glob(os.path.join(PAGE_DIR, "*.py")))

# 分批支持：SMOKE_BATCH=i/n 只跑第 i 批（共 n 批），用于绕过单条命令 10 分钟墙。
def _select_batch(files):
    raw = os.environ.get("SMOKE_BATCH", "")
    if "/" in raw:
        try:
            i, n = raw.split("/")
            i, n = int(i), int(n)
            if n > 0 and 0 <= i < n:
                per = (len(files) + n - 1) // n
                return files[i * per:(i + 1) * per]
        except ValueError:
            pass
    return files

PAGE_FILES = _select_batch(ALL_PAGE_FILES)
_BATCH_TAG = os.environ.get("SMOKE_BATCH", "all").replace("/", "_")
REPORT_PATH = os.path.join(os.path.dirname(__file__), f".pages_smoke_report_{_BATCH_TAG}.json")

# 预生成一张「永不过期」的合法 JWT（is_authenticated 仅本地解码 exp，不验签）
_FAKE_TOKEN = jwt.encode(
    {"sub": "demo", "username": "demo", "role": "admin", "exp": int(time.time()) + 999999},
    "stocksignal-smoke",
    algorithm="HS256",
)
_FAKE_USER = {
    "id": 1,
    "username": "demo",
    "role": "admin",
    "email": "demo@stocksignal.local",
}


def _simulate_offline():
    """让所有网络调用立即失败，逼出降级路径且不卡 30s。

    返回需在测试结束时复原的清理操作。
    """
    _orig_request = requests.Session.request

    def _fail(*args, **kwargs):
        raise requests.exceptions.ConnectionError("smoke: offline simulated")

    requests.Session.request = _fail  # 同时覆盖 get/post/head
    return _orig_request


def _restore_offline(orig):
    requests.Session.request = orig


def _collect_errors(at: AppTest) -> list[str]:
    """收集页面渲染出的 st.error / st.exception 小部件文本。"""
    out: list[str] = []
    try:
        for w in at.error:
            out.append(getattr(w, "value", str(w)))
    except Exception:
        pass
    try:
        for w in at.exception:
            # at.exception 是 Exception 对象，单独归类
            out.append("EXC:" + str(w))
    except Exception:
        pass
    return out


def _run_page(page_path: str, authed: bool) -> dict:
    at = AppTest.from_file(page_path, default_timeout=30)
    if authed:
        at.session_state["auth_token"] = _FAKE_TOKEN
        at.session_state["auth_user"] = dict(_FAKE_USER)
    at.run()
    return {
        "exception_count": len(at.exception),
        "exceptions": [str(e) for e in at.exception[:3]],
        "errors": _collect_errors(at),
    }


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """全局模拟离线，整轮测试内网络调用立即失败。"""
    orig = _simulate_offline()
    yield
    _restore_offline(orig)


@pytest.mark.parametrize("page_path", PAGE_FILES, ids=lambda p: os.path.basename(p))
def test_page_renders_without_exception(page_path: str):
    """游客态 + 已登录态下，页面渲染均不应抛出未捕获异常。"""
    guest = _run_page(page_path, authed=False)
    authd = _run_page(page_path, authed=True)

    # 汇总写入报告（供排雷），即使本断言通过也保留
    _write_report(page_path, guest, authd)

    msgs = []
    if guest["exception_count"]:
        msgs.append(f"[游客态] {guest['exceptions']}")
    if authd["exception_count"]:
        msgs.append(f"[已登录态] {authd['exceptions']}")
    assert not msgs, (
        f"页面 {os.path.basename(page_path)} 渲染抛出异常:\n" + "\n".join(msgs)
    )


def _write_report(page_path: str, guest: dict, authd: dict):
    report: dict = {}
    if os.path.exists(REPORT_PATH):
        try:
            with open(REPORT_PATH, "r", encoding="utf-8") as f:
                report = json.load(f)
        except Exception:
            report = {}
    report[os.path.basename(page_path)] = {
        "guest_exception": guest["exception_count"],
        "guest_errors": guest["errors"],
        "auth_exception": authd["exception_count"],
        "auth_errors": authd["errors"],
    }
    try:
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def test_all_pages_collected():
    """防守：确保 pages/ 下确有页面被收集，防止 glob 失败导致测试空跑。"""
    assert len(PAGE_FILES) >= 30, f"收集到的页面数异常少: {len(PAGE_FILES)}"
