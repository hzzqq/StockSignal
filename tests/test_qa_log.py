"""
tests/test_qa_log.py
--------------------
纯粹离线测试：验证 _safe_qa_log_html 对每条日志 message 做 html.escape 转义，
消除 stored-XSS（原实现用 unsafe_allow_html 直接渲染未转义的用户研究问题）。

不依赖真实 streamlit / 后端，所有外部模块在导入页面模块前桩掉。
"""

import os
import sys
import types

# ── 在导入页面模块之前桩掉 streamlit 及其子依赖（避免 import 副作用 / 网络） ──
_st = types.ModuleType("streamlit")
for _name in (
    "set_page_config", "markdown", "progress", "columns", "text_input", "radio",
    "selectbox", "checkbox", "button", "info", "warning", "error", "exception",
    "caption", "title", "subheader", "divider", "spinner", "expander", "write",
    "toast",
):
    setattr(_st, _name, lambda *a, **k: None)
_st.session_state = {}
_st.fragment = lambda *a, **k: (lambda fn: fn)
sys.modules.setdefault("streamlit", _st)

_sa = types.ModuleType("streamlit_autorefresh")
sys.modules.setdefault("streamlit_autorefresh", _sa)

# colors 等页面依赖的模块桩成最小实现（page_guard 允许真实导入，streamlit 已桩）
# R76 修复：先尝试真实导入 colors——若可用则让真实模块占位，桩不生效，
# 避免 test_qa_log 在按字母序早于真实 colors 导入时注入 stub 且永不还原
# （顺序性污染：后续测试 import modules.colors 拿到残缺桩）。仅当 colors
# 不可导入（如离线裁剪环境）才注入桩。
try:
    import modules.colors as _real_colors  # noqa: F401  确保真实模块占位
except Exception:
    _colors = types.ModuleType("modules.colors")
    _colors.UP_COLOR = "#e04848"
    _colors.DOWN_COLOR = "#19b36b"
    _colors.AMBER = "#d97706"
    sys.modules.setdefault("modules.colors", _colors)


def _load_page_module():
    here = os.path.dirname(os.path.abspath(__file__))
    page_path = os.path.join(here, "..", "pages", "Q_QuantAgent投研.py")
    spec = importlib.util.spec_from_file_location("q_quantagent_page", page_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


import importlib.util  # noqa: E402  (placed after桩，导入页面模块时需用到)

PAGE = _load_page_module()
safe_qa_log_html = PAGE._safe_qa_log_html


def test_script_tag_is_escaped():
    """含 <script> 的日志消息不能原样出现在输出中。"""
    out = safe_qa_log_html([{"stage": "data", "message": "<script>alert(1)</script>"}])
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "qa-log" in out  # 仍保留容器样式


def test_normal_text_preserved():
    """普通文本应原样保留。"""
    out = safe_qa_log_html([{"stage": "data", "message": "正常文本 600519 涨跌幅"}])
    assert "正常文本 600519 涨跌幅" in out
    assert "<script>" not in out


def test_multiline_preserved():
    """多行消息中的换行与各行内容应保留。"""
    out = safe_qa_log_html([{"stage": "fundamental", "message": "第一行\n第二行"}])
    assert "第一行" in out
    assert "第二行" in out


def test_stage_label_and_empty_message():
    """阶段标签应出现；空消息不报错。"""
    out = safe_qa_log_html([
        {"stage": "data", "message": "hello & <b>world</b>"},
        {"stage": "risk", "message": ""},
    ])
    assert "hello &amp; &lt;b&gt;world&lt;/b&gt;" in out  # 同时验证 & 转义
    assert "qa-log" in out
