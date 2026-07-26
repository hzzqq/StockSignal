"""
纯离线单元测试（不依赖 Streamlit 运行时 / 网络）。

覆盖 modules.page_widgets 中的 PURE 助手：
  - 格式化助手：正常输入返回预期；None/空 -> 安全默认（"—"/""），绝不抛异常；
  - HTML 构建助手（卡片/标题/空态/加载）：数据派生文本（标签/名称/文案）
    被 html.escape，恶意注入文本被转义而非原样写入标记。

运行：
  python -m pytest tests/test_page_widgets.py -q
"""
import os
import sys

# 保证从任意 cwd 都能 import 到项目根下的 modules 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.page_widgets import (
    _fmt_yi,
    _fmt_num,
    _fmt_pct,
    _delta_color,
    _delta_html,
    _data_card_html,
    _section_title_html,
    _empty_info_html,
    _loading_html,
)

_MALICIOUS = '<img src=x onerror=alert(1)>'


# ---------------- 格式化助手：正常输入 ----------------
def test_fmt_yi_normal():
    assert _fmt_yi(1.5e8) == "1.50亿"
    assert _fmt_yi(2.3e4) == "2.3万"


def test_fmt_num_normal():
    assert _fmt_num(1.234) == "1.23"
    assert _fmt_num(-5, nd=1, sign=True) == "-5.0"


def test_fmt_pct_normal():
    assert _fmt_pct(0.1234) == "+12.34%"
    assert _fmt_pct(0.5, sign=False) == "50.00%"


def test_delta_color_normal():
    assert _delta_color(1) == "#ff4d4f"      # A股红涨
    assert _delta_color(-1) == "#00d486"     # A股绿跌
    assert _delta_color(0) == ""


def test_delta_html_normal():
    out = _delta_html(0.1234)
    assert "+12.34%" in out
    assert "color:" in out


# ---------------- 格式化助手：None/空/异常 -> 安全默认，不抛异常 ----------------
def test_fmt_yi_none_safe():
    assert _fmt_yi(None) == "—"
    assert _fmt_yi("") == "—"
    assert _fmt_yi("abc") == "—"
    assert _fmt_yi(float("nan")) == "—"


def test_fmt_num_none_safe():
    assert _fmt_num(None) == "—"
    assert _fmt_num("") == "—"


def test_fmt_pct_none_safe():
    assert _fmt_pct(None) == "—"
    assert _fmt_pct(float("nan")) == "—"


def test_delta_color_none_safe():
    assert _delta_color(None) == ""
    assert _delta_color("bad") == ""


def test_delta_html_none_safe():
    assert "—" in _delta_html(None)
    # delta=0 返回灰化的 "0.00%"，不抛异常
    assert "0.00%" in _delta_html(0)


# ---------------- HTML 构建助手：正常输入 ----------------
def test_data_card_html_normal():
    out = _data_card_html("净流入", "12.3", delta_html="<span>x</span>", unit="亿")
    assert "净流入" in out
    assert "12.3" in out
    assert "亿" in out
    assert "<span>x</span>" in out   # 受信内部 HTML 片段原样保留


def test_section_title_html_normal():
    out = _section_title_html("资金流向")
    assert "资金流向" in out


# ---------------- HTML 构建助手：None/空 -> 安全默认，不抛异常 ----------------
def test_data_card_html_none_safe():
    # 不抛异常即可
    out = _data_card_html(None, None, delta_html=None, unit=None)
    assert isinstance(out, str)
    assert "<div" in out


def test_section_title_html_none_safe():
    out = _section_title_html(None)
    assert isinstance(out, str)


def test_empty_info_html_none_safe():
    out = _empty_info_html(None)
    assert isinstance(out, str)
    assert "<div" in out


def test_loading_html_none_safe():
    out = _loading_html(None)
    assert isinstance(out, str)
    assert "ssspin" in out


# ---------------- HTML 注入防护：恶意文本必须被转义 ----------------
def test_data_card_html_escapes_malicious():
    out = _data_card_html(_MALICIOUS, _MALICIOUS, unit=_MALICIOUS)
    assert _MALICIOUS not in out                     # 原始标签不得出现
    assert "&lt;img src=x onerror=alert(1)&gt;" in out  # 已被转义


def test_section_title_html_escapes_malicious():
    out = _section_title_html(_MALICIOUS)
    assert _MALICIOUS not in out
    assert "&lt;img" in out


def test_empty_info_html_escapes_malicious():
    out = _empty_info_html(_MALICIOUS)
    assert _MALICIOUS not in out
    assert "&lt;img" in out


def test_loading_html_escapes_malicious():
    out = _loading_html(_MALICIOUS)
    assert _MALICIOUS not in out
    assert "&lt;img" in out
